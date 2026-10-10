"""Orquesta: resolver (diccionario) → LLM para lo que falta → comprobante → cascada → ficha →
búsqueda de duplicados en el libro.

Nunca escribe en Sheets ni en Drive. Lee el libro para buscar el mismo hecho ya cargado
(§5.16): eso no lo vuelve un escritor, y si el libro no responde, la ficha sale igual.

Reparto de autoridad cuando hay adjunto:
  - el comprobante manda en importe, fecha, destinatario, CUIT y número de operación;
  - el texto manda en obra, ítem, rubro y descripción;
  - si texto y comprobante se contradicen en importe o fecha, no se elige: van los dos
    valores a `conflictos` y se pregunta.
"""
import copy
import logging
import re
from collections import Counter
from datetime import date, timedelta, timezone

from app import certificados, clasificador, comprobante, consultas, duplicados, llm, maestros, obligatorios, resolver
from app.config import Settings, settings
from app.maestros import Maestros, Usuario, normalizar, numero, solo_digitos
from app.models import (CAMPOS_FICHA_CERTIFICADO, CAMPOS_FICHA_TRASPASO, COLUMNAS_MOVIMIENTOS, Conflicto, Ficha,
                        InterpretarIn,
                        InterpretarOut, PosibleDuplicado, Pregunta)
from app.resolver import Resolucion, Segmento
from app.filtros import sin_anulados
from app.saldos import como_dicts

logger = logging.getLogger(__name__)

UMBRAL_LLM = 0.75
FACTOR_METODO = {"alias": 1.0, "exacto": 1.0, "cuit": 1.0, "palabra": 0.9, "difuso": 0.9, "llm": 0.8}
ORIGEN_METODO = {"llm": "llm"}  # el resto de los métodos de diccionario son «texto»
MAX_OPCIONES = 10


# El medio de pago que corresponde a una cuenta cuando nadie lo dijo (§5.7). «Pagado por el
# comitente» no está: cómo pagó el comitente no se sabe.
MEDIO_POR_TIPO_DE_CUENTA = {"banco": "Transferencia", "efectivo": "Efectivo", "caja_obra": "Efectivo",
                            "chequera": "Cheque", "billetera": "Mercado Pago"}
# §5.8 v1.8: respuestas a «¿A qué tipo de cambio?» cuando la cuenta está en dólares.
RE_SIN_CONVERSION = re.compile(r"\b(?:dolar(?:es)?|usd|no hay|sin tipo|sin tc|no se convierte)\b")


def _cuenta_de_tipo(m: Maestros, tipo: str, moneda: str | None = "ARS"):
    """La única cuenta activa de ese tipo y moneda (Banco, Banco USD, Chequera, Mercado Pago),
    o None si hay varias o ninguna: nunca se elige al azar."""
    candidatas = [c for c in m.cuentas if c.activa and c.tipo == tipo and c.moneda == (moneda or "ARS")]
    return candidatas[0] if len(candidatas) == 1 else None


def _cuenta_del_comprobante(comp, obra, moneda: str | None, m: Maestros):
    """§5.7, regla 2: lo que dice el comprobante. Si lo pagó el comitente de la obra (su CUIT
    es el originante), «Pagado por el comitente» (§5.9); una transferencia o un débito, el
    banco (en dólares si el comprobante lo está); un cheque, la chequera; Mercado Pago, la
    billetera. Un comprobante en efectivo ya lo resolvió la regla del medio de pago."""
    if obra and obra.cuit_comitente and comp.cuit_originante \
            and solo_digitos(comp.cuit_originante) == solo_digitos(obra.cuit_comitente):
        return m.cuenta(maestros.CUENTA_PAGADO_POR_COMITENTE)
    medio = normalizar(" ".join(filter(None, [comp.medio_pago, comp.tipo_comprobante])))
    moneda = (comp.moneda or moneda or "ARS").upper()
    if "mercado pago" in medio or "mercadopago" in medio:
        return _cuenta_de_tipo(m, "billetera")
    if "cheque" in medio:
        return _cuenta_de_tipo(m, "chequera")
    if "transferencia" in medio or "debito" in medio:
        return _cuenta_de_tipo(m, "banco", moneda)
    return None


def _decidir_etapa(obra, pedida: str | None, ya: str | None, extras: dict, m: Maestros
                   ) -> tuple[str | None, str | None, list[Pregunta], list[str]]:
    """§5.15 (v1.7). Devuelve (etapa, origen, preguntas, advertencias).

    - El mensaje nombra una etapa: si está en curso, se usa; si es futura o terminada, se usa
      y se pregunta si se activa (salvo que el usuario ya dijo que sí); si no existe, se pregunta.
    - No la nombra: una sola en curso → esa, con origen «maestro» (la ficha dice «etapa 1, en
      curso»); dos o más en curso → se pregunta cuál; ninguna → la obra no la necesita.
    """
    if obra is None:
        return None, None, [], []
    todas, en_curso = m.etapas_de(obra.nombre), m.etapas_en_curso(obra.nombre)
    if pedida:
        if not todas:
            return None, None, [], [f"{obra.nombre} no tiene etapas cargadas en ETAPAS: se ignora la etapa {pedida}"]
        e = m.etapa(obra.nombre, m.etapa_por_nombre(obra.nombre, pedida) or pedida)
        if e is None:
            return None, None, [Pregunta(campo="etapa", texto=f"¿Qué etapa de {obra.nombre}?", opciones=en_curso)], \
                [f"{obra.nombre} no tiene una etapa {pedida}"]
        if e.en_curso or normalizar(extras.get("activar_etapa")) == e.etapa:
            return e.etapa, "texto", [], []
        extras["etapa_propuesta"] = e.etapa
        return e.etapa, "texto", [Pregunta(
            campo="activar_etapa", texto=f"La etapa {e.etapa} de {obra.nombre} figura como {e.estado}, ¿la paso a en curso?",
            opciones=["Sí", "No"])], []
    if ya:
        return ya, None, [], []
    if len(en_curso) == 1:
        return en_curso[0], "maestro", [], []
    if len(en_curso) > 1:
        return None, None, [Pregunta(campo="etapa", texto=f"¿Qué etapa de {obra.nombre}? ({' o '.join(en_curso)})",
                                     opciones=en_curso)], []
    return None, None, [], []


def _etapa_del_certificado(valor: str | None, obra, m: Maestros) -> tuple[str | None, str | None]:
    """«4 extras» en Moreno → (número «4», etapa «extras») (§5.11 v1.7: los certificados son
    correlativos dentro de cada etapa). Sin obra, o si ninguna palabra es una etapa con
    nombre de la obra, el número queda como vino."""
    if not valor or obra is None:
        return valor, None
    palabras = str(valor).split()
    for i, p in enumerate(palabras):
        e = m.etapa_por_nombre(obra.nombre, p) if not p.isdigit() else None
        if e:
            resto = " ".join(palabras[:i] + palabras[i + 1:])
            return resto or None, e
    return valor, None


def _fmt_importe(v: float) -> str:
    return "$" + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fecha_local(req: InterpretarIn, s: Settings) -> date | None:
    if not req.fecha_mensaje:
        return None
    f = req.fecha_mensaje
    if f.tzinfo is None:
        f = f.replace(tzinfo=timezone.utc)
    return f.astimezone(timezone(timedelta(hours=s.utc_offset_horas))).date()


def _semilla(contexto: dict | None, respuestas: bool = False) -> dict | None:
    """De la ficha anterior se hereda lo que dijo el usuario o el comprobante; lo derivado
    (comitente, rubro inferido) se recalcula con lo nuevo. Con `respuestas`, cada campo
    conserva su origen (sigue siendo «del comprobante»); en una corrección, es contexto_previo."""
    if not contexto:
        return None
    campos = contexto.get("campos") or {}
    origen = contexto.get("origen_campo") or {}
    extras = contexto.get("extras") or {}
    return {
        "campos": {k: v for k, v in campos.items()
                   if v not in (None, "") and origen.get(k) not in ("inferido", "maestro", "fecha_mensaje", "supuesto")},
        "origen": origen if respuestas else {},
        "clasificacion": contexto.get("clasificacion") or extras.get("clasificacion_respondida")
        or ("personal" if extras.get("destino_personal") else None),
        "extras": extras,
    }


def _origen_semilla(semilla: dict, campo: str) -> str:
    return semilla["origen"].get(campo) or "contexto_previo"


# ─── Intención (tanda 6.4, §5.12) ──────────────────────────────────────────────

# Acuses sueltos: no son un movimiento aunque tengan menos de tres palabras.
ACUSES = {"ok", "oka", "okey", "dale", "gracias", "muchas gracias", "listo", "si", "no", "bueno", "perfecto",
          "genial", "joya", "barbaro", "hola", "buen dia", "buenas", "buenas tardes", "buenas noches", "de nada"}
# §5.12 v1.9 (captura 3 del 9/10): «el M 0014 ESTA MAL HAY QUE ELIMINARLO». El id se acepta
# como M 0014, M-0014, M14, M-000014 (y P- igual).
RE_ID_MOV = re.compile(r"(?<![a-z0-9])([mp])\s*-?\s*(\d{1,6})(?![0-9])", re.I)
RE_BORRAR = re.compile(r"\b(?:elimin|borr|anul|sac[aá]|quit|dar de baja|dalo de baja)")
RE_CORREGIR = re.compile(r"\b(?:corregi|correg|esta mal|estan mal|cambia)")
# Una consulta que se reconoce aunque no lleve «?»: «En cuanto esta el saldo de la caja chica».
RE_CONSULTA_CLARA = re.compile(r"\bsaldo\b|\bcuant[oa]s?\b.*\b(?:hay|queda|tengo|va|van|esta)\b|"
                               r"\bquier[oe] saber\b|\bquieto saber\b")
RE_PREGUNTA = re.compile(r"[?¿]|^(?:cuant[oa]s?|que|cual(?:es)?|como|donde|quien|cuando|decime|pasame|mostrame)\b")


def _hay_senales(texto: str, segmentos: list[Segmento]) -> bool:
    """Algo que solo tiene sentido en un movimiento: la barra del formato `algo/algo`, un
    importe, una fecha, una palabra de tipo o cualquier cosa que el diccionario reconozca."""
    return "/" in texto or any(
        seg.importe is not None or seg.fechas or seg.tipo_mov or seg.resueltos or seg.alias_propuesto
        or seg.honorarios or seg.caja or seg.etapa or seg.es_correccion for seg in segmentos)


def _intencion(req: InterpretarIn, texto: str, segmentos: list[Segmento], comprobantes: list) -> str:
    """movimiento | consulta | otro. **Ante la duda, movimiento**: es peor perder un pago que
    hacer una pregunta de más.

    §5.12 v1.9: un pedido sobre un movimiento ya cargado («el M 0014 está mal, hay que
    eliminarlo») o una consulta clara («¿cuánto hay en la caja chica de Lennon?») nunca son una
    respuesta, aunque el gateway los mande con la ficha pendiente en `contexto_previo`."""
    if req.respuestas:
        return "movimiento"
    if not comprobantes and _id_mov_nombrado(texto):
        if RE_BORRAR.search(normalizar(texto)):
            return "anular"
        if RE_CORREGIR.search(normalizar(texto)):
            return "corregir"
    if not comprobantes and "/" not in texto and (RE_CONSULTA_CLARA.search(normalizar(texto)) or "?" in texto) \
            and consultas.inferir_consulta(texto) and not any(seg.importe is not None for seg in segmentos):
        return "consulta"
    if req.contexto_previo:
        return "movimiento"
    if comprobantes:
        # Un adjunto leído sin nada de un comprobante —ni importe, ni fecha, ni CUIT— es una
        # foto de obra. Si no se pudo leer, no se sabe: movimiento.
        leido = [c for c in comprobantes if c.error is None]
        datos = any(c.importe is not None or c.fecha or c.cuit or c.certificado or c.numero_cheque or c.id_operacion
                    for c in comprobantes)
        if datos or len(leido) < len(comprobantes) or _hay_senales(texto, segmentos):
            return "movimiento"
        return "otro"
    plano = normalizar(texto)
    if not plano:
        return "otro"
    if "/" not in texto and RE_PREGUNTA.search(texto.strip().lower() if "?" in texto or "¿" in texto else plano) \
            and consultas.inferir_consulta(texto) and not any(seg.importe is not None for seg in segmentos):
        return "consulta"
    if _hay_senales(texto, segmentos):
        return "movimiento"
    # Sin nada reconocible: charla si es un acuse o una frase; una o dos palabras sueltas
    # pueden ser un contratista nuevo, y eso es movimiento.
    return "otro" if plano in ACUSES or len(plano.split()) >= 3 else "movimiento"


# ─── Respuestas a las preguntas (tanda 6.4) ────────────────────────────────────

def _fecha_de(valor: str) -> str | None:
    try:
        return date.fromisoformat(valor.strip()[:10]).isoformat()
    except ValueError:
        pass
    mt = resolver.RE_FECHA.search(valor)
    f = resolver._parsear_fecha(*mt.groups()) if mt else None
    return f.valor.isoformat() if f else None


def _aplicar_respuestas(contexto: dict, respuestas: list, m: Maestros, diag: dict) -> tuple[dict, list[str]]:
    """Pone cada respuesta en la ficha anterior, de forma determinística. Lo que no es una
    opción del maestro vuelve como texto libre, para resolverlo con el diccionario como
    cualquier mensaje. La cascada la vuelve a correr `_armar`: cambiar la obra puede cambiar
    `tipo_gasto`."""
    ficha = copy.deepcopy(contexto)
    campos = ficha.setdefault("campos", {})
    origen = ficha.setdefault("origen_campo", {})
    extras = ficha.setdefault("extras", {})
    libre: list[str] = []

    def fijar(campo: str, valor) -> None:
        campos[campo] = valor
        origen[campo] = "texto"

    for r in respuestas:
        campo, valor = r.campo, r.valor.strip()
        n = normalizar(valor)
        if campo == "obra":
            o = m.obra(valor)
            if o:
                if normalizar(campos.get("obra")) != normalizar(o.nombre):
                    campos["etapa"] = None  # otra obra: la etapa de la anterior ya no vale
                fijar("obra", o.nombre)
            else:
                libre.append(valor)
        elif campo == "contratista":
            c = m.contratista(valor)
            fijar("contratista", c.nombre) if c else libre.append(valor)
        elif campo == "rubro":
            rubros = [x for x in m.rubros if normalizar(x.rubro_2) == n]
            if not rubros and " / " in valor:
                rubros = [x for x in [m.rubro(*valor.split(" / ", 1))] if x]
            if rubros:
                fijar("rubro_1", rubros[0].rubro_1)
                fijar("rubro_2", rubros[0].rubro_2)
            else:
                libre.append(valor)
        elif campo in ("cuenta", "cuenta_origen", "cuenta_destino"):
            c = m.cuenta(valor)
            fijar(campo, c.nombre) if c else libre.append(valor)
        elif campo == "clasificacion":
            extras["clasificacion_respondida"] = "personal" if n == "personal" else "obra"
        elif campo in ("importe", "saldo_a_cobrar"):
            importe = numero(valor)
            if importe > 0:
                fijar(campo, importe)
                # «400 dólares» como respuesta al importe (M-000005, 3/10): la moneda que dice
                # el texto manda; antes se tomaba el número y quedaba en pesos.
                if campo == "importe" and resolver.RE_USD.search(valor):
                    fijar("moneda", "USD")
                elif campo == "importe" and re.search(r"\bpesos\b|\$(?!\s*us)", valor, re.I):
                    fijar("moneda", "ARS")
            else:
                diag["advertencias"].append(f"«{valor}» no es un importe")
        elif campo == "fecha":
            f = _fecha_de(valor)
            fijar("fecha", f) if f else libre.append(valor)
        elif campo == "concepto":
            libre.append("honorarios" if n.startswith("hon") else "caja" if n.startswith("adelanto") else "certificado")
        elif campo == "duplicado":
            extras["no_es_duplicado" if n == "es otro" else "es_el_mismo"] = True
        elif campo == "tipo_cambio":
            # §5.7 (v1.7): «1.450», «1450», «1450,50». Se guarda en la columna `tc`.
            tc = numero(valor)
            destino = m.cuenta(campos.get("cuenta") or campos.get("cuenta_destino"))
            if tc > 0:
                fijar("tc", tc)
            elif RE_SIN_CONVERSION.search(n) and destino and destino.moneda != "ARS":
                # §5.8 v1.8: «lo dejamos en dólares», «no hay tipo de cambio»: la cuenta está en
                # dólares y el movimiento también; no hay nada que convertir.
                fijar("moneda", destino.moneda)
                campos["tc"] = None
            else:
                diag["advertencias"].append(f"«{valor}» no es un tipo de cambio: se vuelve a preguntar")
        elif campo == "activar_etapa":
            # §5.15: «La etapa 2 de Lennon figura como futura, ¿la paso a en curso?»
            if n in ("si", "sí", "s", "dale", "ok"):
                extras["activar_etapa"] = extras.get("etapa_propuesta") or campos.get("etapa")
            else:
                campos["etapa"] = None
                origen.pop("etapa", None)
                extras.pop("etapa_propuesta", None)
        elif campo == "inactivo":
            if n == "reactivar":
                extras["reactivar"] = True
            else:  # «Es otro»: el contratista inactivo no era; se vuelve a preguntar
                campos["contratista"] = None
                origen.pop("contratista", None)
                extras["contratista_descartado"] = extras.get("inactivo_propuesto")
        else:  # etapa, numero y cualquier otro campo de la ficha: el valor tal cual
            fijar(campo, valor)
    return ficha, libre


def interpretar(req: InterpretarIn, libros: dict | None = None, lector=None) -> InterpretarOut:
    """`libros` es {"estudio": Libro, "personal": Libro | None}: dónde buscar duplicados.
    `lector` lee un adjunto; por defecto baja el archivo de Drive (los tests leen uno local)."""
    s = settings()
    m = maestros.cargar()
    diag: dict = {"llm_llamadas": 0, "llm_uso": [], "resoluciones": [], "advertencias": []}
    usuario = m.usuario(req.telefono)

    contexto, texto = req.contexto_previo, req.texto
    if req.respuestas and contexto:
        contexto, libre = _aplicar_respuestas(contexto, req.respuestas, m, diag)
        texto = " / ".join(filter(None, [texto, *libre]))
    elif req.respuestas:
        diag["advertencias"].append("Llegaron respuestas sin contexto_previo: no hay ficha a la cual aplicarlas")

    segmentos = resolver.parsear(texto, _fecha_local(req, s))
    for seg in segmentos:
        resolver.resolver_segmento(seg, m)

    comprobantes = [(lector or comprobante.leer)(a) for a in req.adjuntos]
    diag["comprobantes"] = [c.dict() for c in comprobantes]
    diag["llm_llamadas"] += sum(1 for c in comprobantes if c.uso_llm)
    diag["llm_uso"] += [c.uso for c in comprobantes if c.uso]  # el lector es la llamada más cara: se mide

    intencion = _intencion(req, texto, segmentos, comprobantes)
    if intencion != "movimiento":
        diag["uso_llm"] = diag["llm_llamadas"] > 0
        return InterpretarOut(intencion=intencion, fichas=[], preguntas=[], requiere_confirmacion=False, diagnostico=diag,
                              id_mov=_id_mov_nombrado(texto) if intencion in ("anular", "corregir") else None)

    semilla = _semilla(contexto, respuestas=bool(req.respuestas))
    # Los libros que el usuario puede ver, leídos una vez: el rubro de la última vez con cada
    # contratista (§5.12 v1.8) y los duplicados (§5.16) salen de acá.
    libros_leidos = _leer_libros(libros, usuario, diag)
    historia = sin_anulados([mv for movs in libros_leidos.values() for mv in movs])
    fichas: list[Ficha] = []
    preguntas: list[Pregunta] = []
    for i, seg in enumerate(segmentos):
        # Un comprobante por movimiento si coinciden en cantidad; si no, el primero aplica a todos
        # (el cobro de un certificado que sale el mismo día como pago).
        comp = comprobantes[i] if len(comprobantes) == len(segmentos) else (comprobantes[0] if comprobantes else None)
        previa = semilla if i == 0 else None
        if _es_certificado(seg, comp, previa):
            armar = _armar_certificado
        elif _es_traspaso(seg, previa):
            armar = _armar_traspaso
        else:
            armar = _armar
        ficha, pregs = armar(seg, comp, req, m, s, diag, semilla if i == 0 else None, historia=historia)
        for p in pregs:
            p.ficha = i
        fichas.append(ficha)
        preguntas += pregs

    _marcar_duplicados(fichas, preguntas, libros_leidos, usuario)
    _marcar_certificados_repetidos(fichas, preguntas, libros, usuario, diag)
    # §5.12 v1.8: el rubro sale del contratista (habitual, último uso) y de si es de obra o
    # personal; mientras eso esté preguntado, preguntar el rubro es una pregunta de más.
    rubro_despues = {p.ficha for p in preguntas if p.campo in obligatorios.PREGUNTAS_QUE_DEFINEN_EL_RUBRO}
    preguntas = [p for p in preguntas if not (p.campo == "rubro" and p.ficha in rubro_despues)]
    for i, ficha in enumerate(fichas):
        preguntas += _completar_preguntas(ficha, i, [p for p in preguntas if p.ficha == i], m, historia)
    for i, ficha in enumerate(fichas):
        ficha.requiere_confirmacion = _requiere_confirmacion(
            ficha, [p for p in preguntas if p.ficha == i], usuario, m)

    diag["uso_llm"] = diag["llm_llamadas"] > 0
    return InterpretarOut(fichas=fichas, preguntas=preguntas, diagnostico=diag,
                          requiere_confirmacion=any(f.requiere_confirmacion for f in fichas))


def _leer_libros(libros: dict | None, usuario: Usuario | None, diag: dict) -> dict[str, list[dict]]:
    """{nombre: movimientos} de los libros que el usuario puede ver. El personal, solo con
    `ve_personal`: si no, ni siquiera se le puede decir que ahí hay algo parecido. Si un libro
    no responde, la ficha sale igual, sin su historia."""
    salida: dict[str, list[dict]] = {}
    for nombre, libro in (libros or {}).items():
        if libro is None or (nombre == "personal" and not (usuario and usuario.ve_personal)):
            continue
        try:
            salida[nombre] = como_dicts(libro.leer_movimientos())
        except Exception as e:  # noqa: BLE001
            logger.exception("No se pudo leer el libro %s", nombre)
            diag["advertencias"].append(f"No se pudo leer el libro {nombre} ({type(e).__name__}): sin duplicados ni "
                                        f"rubro de la última vez")
    return salida


def _id_mov_nombrado(texto: str) -> str | None:
    """«M 0014», «M-0014», «M14», «m-000014» → «M-000014»; lo mismo con P-. None si no hay."""
    mt = RE_ID_MOV.search(texto or "")
    return f"{mt.group(1).upper()}-{int(mt.group(2)):06d}" if mt else None


def _puede_ser_un_nombre(token: str) -> bool:
    """Un contratista nuevo se da de alta con lo que escribió el usuario: una a tres palabras
    sin números. «Nelson mano de obra 2» no es un nombre: se pregunta."""
    palabras = normalizar(token).split()
    return 1 <= len(palabras) <= 3 and not any(ch.isdigit() for ch in token)


def _contratista_nuevo(token: str, comp, m: Maestros) -> dict:
    """§5.6 v1.9: el alta que se propone. Nombre y CUIT del destinatario del comprobante si lo
    hay; si no, el nombre como lo escribió, capitalizado. Lo que escribió queda como alias."""
    razon = comp.razon_social if comp and comp.razon_social else None
    nombre = resolver.nombre_propio(razon or token)
    alias = normalizar(token)
    return {"nombre": nombre, "cuit": (comp.cuit if comp and comp.cuit and razon else "") or "",
            "rubro_habitual_1": "", "rubro_habitual_2": "",
            "alias": alias if alias != normalizar(nombre) else ""}


def _tc_del_dia(cuenta: str, fecha, historia) -> float | None:
    """§5.8 v1.8: el tipo de cambio del último movimiento de esa cuenta en esa fecha (el primer
    pago del día lo preguntó; los siguientes lo reusan)."""
    if not fecha:
        return None
    del_dia = [mv for mv in historia if normalizar(mv.get("cuenta")) == normalizar(cuenta)
               and str(mv.get("fecha") or "")[:10] == str(fecha)[:10] and numero(mv.get("tc")) > 1]
    if not del_dia:
        return None
    return numero(max(del_dia, key=lambda mv: str(mv.get("ts") or "")).get("tc"))


def _formato_tc(tc: float) -> str:
    """1450 → «1.450»; 1450.5 → «1.450,50»."""
    entero, _, dec = f"{tc:,.2f}".partition(".")
    entero = entero.replace(",", ".")
    return entero if dec == "00" else f"{entero},{dec}"


def _ultimo_rubro(contratista: str, historia: list[dict], personal: bool, m: Maestros):
    """§5.12 v1.8: el rubro de la última vez que se le pagó a este contratista, en los dos
    libros. Solo uno del mismo lado (personal o no) que el movimiento de ahora."""
    suyos = [mv for mv in historia if normalizar(mv.get("contratista")) == normalizar(contratista)
             and mv.get("rubro_1") and mv.get("rubro_2")]
    suyos.sort(key=lambda mv: (str(mv.get("fecha") or ""), str(mv.get("ts") or "")), reverse=True)
    for mv in suyos:
        r = m.rubro(mv["rubro_1"], mv["rubro_2"])
        if r and (r.afecta == "personal") == personal:
            return r
    return None


def _rubros_por_uso(afecta: str, historia: list[dict], m: Maestros, contratista=None) -> list[str]:
    """Las opciones de la pregunta del rubro (§5.12 v1.8: no los primeros diez de RUBROS):
    primero la categoría del contratista si la tiene, después los más usados —en los libros y
    como rubro habitual de los contratistas—, y después el resto en el orden del maestro."""
    uso: Counter = Counter()
    for mv in historia:
        r = m.rubro(mv.get("rubro_1"), mv.get("rubro_2"))
        if r and r.afecta == afecta:
            uso[(r.rubro_1, r.rubro_2)] += 2
    for c in m.contratistas:
        r = m.rubro(c.rubro_1, c.rubro_2)
        if r and r.afecta == afecta:
            uso[(r.rubro_1, r.rubro_2)] += 1
    categoria = normalizar(contratista.rubro_1) if contratista and contratista.rubro_1 else None
    rubros = [r for r in m.rubros if r.afecta == afecta]
    orden = sorted(range(len(rubros)), key=lambda i: (
        not (categoria and normalizar(rubros[i].rubro_1) == categoria), -uso[(rubros[i].rubro_1, rubros[i].rubro_2)], i))
    return [rubros[i].rubro_2 for i in orden][:MAX_OPCIONES]


def _completar_preguntas(ficha: Ficha, i: int, suyas: list[Pregunta], m: Maestros,
                         historia: list[dict] = ()) -> list[Pregunta]:
    """§5.7 (v1.7): **ninguna ficha sale con un obligatorio vacío y sin pregunta.** Por cada
    faltante que ninguna pregunta completa, se genera una, con opciones del maestro cuando
    existen. Es el paso que faltaba el 29/09: la ficha volvía con `cuenta` faltante, sin
    pregunta, y /confirmar la rechazaba."""
    c = ficha.campos
    ya = {p.campo for p in suyas}
    nuevas: list[Pregunta] = []
    tipo = str(c.get("tipo") or "").upper()
    obra = m.obra(c.get("obra"))
    verbo = "entró" if tipo == "INGRESO" else "salió"
    cuentas = [x.nombre for x in m.cuentas if x.activa]

    for campo in ficha.faltantes:
        if obligatorios.cubierto(campo, ya | {p.campo for p in nuevas}):
            continue
        if campo in ("obra", "tipo_gasto"):
            p = Pregunta(campo="obra", texto="¿A qué obra?", opciones=[
                o.nombre for o in m.obras if o.estado != "cerrada" and o.tipo in ("obra_terceros", "obra_propia")][:MAX_OPCIONES])
        elif campo in ("rubro_1", "rubro_2"):
            afecta = "personal" if normalizar(c.get("tipo_gasto")) == "personal" else "obra"
            p = Pregunta(campo="rubro", texto="¿Qué rubro?",
                         opciones=_rubros_por_uso(afecta, list(historia), m, m.contratista(c.get("contratista"))))
        elif campo == "cuenta":
            p = Pregunta(campo="cuenta", texto=f"¿De qué cuenta {verbo}?",
                         opciones=[x for x in cuentas if m.cuenta(x).tipo != "caja_obra"][:MAX_OPCIONES])
        elif campo == "cuenta_origen":
            p = Pregunta(campo=campo, texto="¿De qué cuenta sale la plata?", opciones=cuentas[:MAX_OPCIONES])
        elif campo == "cuenta_destino":
            p = Pregunta(campo=campo, texto="¿A qué cuenta entra?", opciones=cuentas[:MAX_OPCIONES])
        elif campo == "contratista":
            p = Pregunta(campo="contratista", texto="¿A quién se le pagó?")
        elif campo == "tc":
            cta = m.cuenta(c.get("cuenta"))
            if cta and cta.moneda != "ARS" and str(c.get("moneda") or "ARS").upper() == "ARS":
                # §5.8 v1.8: el primer pago en pesos del día desde una caja en dólares.
                p = Pregunta(campo="tipo_cambio", texto=f"{cta.nombre} está en dólares. ¿A qué tipo de cambio "
                                                        f"pagaste hoy? (lo uso para los demás pagos del día)")
            else:
                p = Pregunta(campo="tipo_cambio", texto="¿A qué tipo de cambio?")
        elif campo == "etapa":
            p = Pregunta(campo="etapa", texto=f"¿Qué etapa de {obra.nombre if obra else 'la obra'}?",
                         opciones=m.etapas_en_curso(obra.nombre) if obra else [])
        elif campo == "tipo":
            p = Pregunta(campo="tipo", texto="¿Es un pago o un cobro?", opciones=["EGRESO", "INGRESO"])
        elif campo == "moneda":
            p = Pregunta(campo="moneda", texto="¿En qué moneda?", opciones=["ARS", "USD"])
        else:
            textos = {"importe": "¿Cuál es el importe?", "fecha": "¿Qué fecha?", "numero": "¿Qué número de certificado es?",
                      "saldo_a_cobrar": "¿Cuál es el saldo a cobrar de este certificado?"}
            p = Pregunta(campo=campo, texto=textos.get(campo, f"Falta «{campo}». ¿Cuál es?"))
        p.ficha = i
        nuevas.append(p)
    return nuevas


def _marcar_duplicados(fichas: list[Ficha], preguntas: list[Pregunta], movs: dict[str, list[dict]],
                       usuario: Usuario | None) -> None:
    """§5.16: si el hecho ya está en el libro, lo dice y pregunta. Nunca lo descarta solo.
    `movs` son los libros que el usuario puede ver (`_leer_libros`)."""
    fichas_mov = [f for f in fichas if f.campos.get("tipo") != "CERTIFICADO"]
    if not movs or not any(f.campos.get("importe") is not None or f.campos.get("ref_comprobante") for f in fichas_mov):
        return
    for i, ficha in enumerate(fichas):
        dup = duplicados.buscar(ficha.campos, movs) if ficha.campos.get("tipo") != "CERTIFICADO" else None
        if dup and ficha.extras.get("es_el_mismo"):
            ficha.posible_duplicado = dup  # el usuario ya dijo que es el mismo: no se pregunta de nuevo
            continue
        if dup and not ficha.extras.get("no_es_duplicado"):
            ficha.posible_duplicado = dup
            preguntas.append(Pregunta(
                campo="duplicado", motivo="posible_duplicado", ficha=i, opciones=["Es el mismo", "Es otro"],
                texto=duplicados.texto_pregunta(dup, ficha.campos.get("tipo"), usuario.nombre if usuario else None)))


def _marcar_certificados_repetidos(fichas: list[Ficha], preguntas: list[Pregunta], libros: dict | None,
                                   usuario: Usuario | None, diag: dict) -> None:
    """§5.16 aplicado a certificados: misma obra, etapa y número que uno ya cargado. Se avisa y
    se pregunta, como con los movimientos; nunca se descarta solo."""
    pendientes = [(i, f) for i, f in enumerate(fichas)
                  if f.campos.get("tipo") == "CERTIFICADO" and f.campos.get("obra") and f.campos.get("numero")]
    libro = (libros or {}).get("estudio")
    if not pendientes or libro is None:
        return
    try:
        certs = como_dicts(libro.leer_certificados())
    except Exception as e:  # noqa: BLE001 — sin la hoja no hay repetidos, pero la ficha sale igual
        logger.exception("No se pudo leer CERTIFICADOS para buscar repetidos")
        diag["advertencias"].append(f"No se pudo buscar certificados repetidos ({type(e).__name__})")
        return
    for i, ficha in pendientes:
        c = ficha.campos
        clave = certificados.clave_certificado(c["obra"], c.get("etapa"), c["numero"])
        previo = next((x for x in certs if certificados.clave_certificado(x.get("obra"), x.get("etapa"), x.get("numero")) == clave), None)
        if previo is None:
            continue
        etapa = certificados.texto_etapa(previo.get("etapa"))
        ficha.posible_duplicado = PosibleDuplicado(
            id_mov=f"{previo.get('obra')}{' etapa ' + etapa if etapa else ''} · certificado {certificados.texto_etapa(previo.get('numero'))}",
            cargado_por=str(previo.get("cargado_por") or "alguien"), fecha=str(previo.get("fecha") or ""),
            importe=numero(previo.get("saldo_a_cobrar")), fuerza="fuerte", libro="certificados")
        preguntas.append(Pregunta(
            campo="duplicado", motivo="posible_duplicado", ficha=i, opciones=["Es el mismo", "Es otro"],
            texto=duplicados.texto_pregunta(ficha.posible_duplicado, "CERTIFICADO", usuario.nombre if usuario else None)))


def _requiere_confirmacion(ficha: Ficha, preguntas: list[Pregunta], usuario: Usuario | None, m: Maestros) -> bool:
    """§5.12. Durante el período de prueba del usuario, siempre true. Después, false solo si el
    movimiento está completamente claro: importe, fecha y destinatario del comprobante; obra y
    contratista del maestro; sin preguntas, sin conflictos y sin posible duplicado.
    Un certificado pide confirmación siempre: la regla de «completamente claro» está escrita
    para movimientos."""
    if usuario is None or not usuario.auto_confirmar or ficha.campos.get("tipo") == "CERTIFICADO":
        return True
    c, o = ficha.campos, ficha.origen_campo
    claro = (
        o.get("importe") == "comprobante" and o.get("fecha") == "comprobante"
        and bool(ficha.extras.get("cuit") or ficha.extras.get("razon_social"))
        and m.obra(c.get("obra")) is not None and m.contratista(c.get("contratista")) is not None
        and not preguntas and not ficha.conflictos and ficha.posible_duplicado is None
    )
    return not claro


def _resolver_con_llm(seg: Segmento, req: InterpretarIn, m: Maestros, diag: dict) -> tuple[list[str], Resolucion | None]:
    """Manda al LLM lo que el diccionario no resolvió. Devuelve (descripciones, rubro sugerido)."""
    tipo = seg.tipo_mov or "EGRESO"
    obra, contr, rubro = seg.primero("obra"), seg.primero("contratista"), seg.primero("rubro")
    contr_m = m.contratista(contr.valor) if contr else None
    personal = bool(seg.de("personal"))
    if personal:
        # Destino personal: no hace falta obra, y el contratista, si aparece, ya está.
        slots_vacios = not rubro and not contr
    else:
        slots_vacios = not obra or (tipo == "EGRESO" and (not contr or not rubro))
    pedir_rubro = tipo == "EGRESO" and not rubro and not personal and contr_m is not None and not contr_m.rubro_1

    if not llm.disponible() or not ((seg.sin_resolver and slots_vacios) or pedir_rubro):
        return [], None

    contexto = {r.categoria: r.valor for r in seg.resueltos if r.categoria in ("obra", "contratista", "rubro", "cuenta")}
    # §5.13: el LLM sabe quién escribe (de USUARIOS, nunca un teléfono en el código).
    quien = m.usuario(req.telefono)
    titular = next((u for u in m.usuarios if u.rol == "titular"), None)
    datos, uso = llm.resolver_tokens(m, req.texto or seg.texto, seg.sin_resolver, contexto, pedir_rubro,
                                     quien=quien.nombre if quien else None, titular=titular.nombre if titular else None)
    diag["llm_llamadas"] += 1
    diag["llm_uso"].append(uso)
    if not datos:
        return [], None

    descripciones: list[str] = []
    pendientes = {normalizar(t): t for t in seg.sin_resolver}
    for item in datos.get("tokens", []):
        token = pendientes.get(normalizar(item.get("token")))
        if token is None:
            continue
        categoria, valor, conf = item.get("categoria"), _validar(item.get("categoria"), item.get("valor"), m), item.get("confianza") or 0
        ocupado = categoria in ("obra", "contratista", "rubro", "cuenta") and seg.primero(categoria) is not None
        if valor and conf >= UMBRAL_LLM and not ocupado:
            seg.resueltos.append(Resolucion(categoria, valor, "llm", token, round(conf * 100)))
            pendientes.pop(normalizar(token))
        elif categoria == "descripcion":
            descripciones.append(token)
            pendientes.pop(normalizar(token))
        elif valor:
            seg.candidatos[token] = [valor]
    seg.sin_resolver = list(pendientes.values())

    sugerido = datos.get("rubro_sugerido") or {}
    valor = _validar("rubro", sugerido.get("valor"), m)
    rubro_llm = Resolucion("rubro", valor, "llm", "", round((sugerido.get("confianza") or 0) * 100)) if valor else None
    return descripciones, rubro_llm


def _validar(categoria: str | None, valor: str | None, m: Maestros) -> str | None:
    """El LLM solo puede devolver valores que existen en los maestros."""
    if not valor:
        return None
    if categoria == "obra":
        o = m.obra(valor) or next((o for o in m.obras if normalizar(o.codigo) == normalizar(valor)), None)
        return o.nombre if o else None
    if categoria == "contratista":
        c = m.contratista(valor)
        return c.nombre if c and c.activo else None  # el LLM nunca propone un inactivo (§5.6)
    if categoria == "cuenta":
        c = m.cuenta(valor)
        return c.nombre if c else None
    if categoria == "rubro":
        partes = [p.strip() for p in valor.split("/")]
        r = m.rubro(partes[0], partes[1]) if len(partes) == 2 else None
        return f"{r.rubro_1} / {r.rubro_2}" if r else None
    return None


def _armar(seg: Segmento, comp, req: InterpretarIn, m: Maestros, s: Settings, diag: dict,
           semilla: dict | None, historia: list[dict] = ()) -> tuple[Ficha, list[Pregunta]]:
    campos: dict = {c: None for c in COLUMNAS_MOVIMIENTOS}
    origen: dict[str, str] = {}
    extras: dict = {}
    advertencias: list[str] = []
    conflictos: list[Conflicto] = []
    preguntas: list[Pregunta] = []
    factor = 1.0

    def poner(campo: str, valor, org: str) -> None:
        if valor not in (None, ""):
            campos[campo] = valor
            origen[campo] = org

    def origen_de(r: Resolucion) -> str:
        return ORIGEN_METODO.get(r.metodo, "texto")

    descripciones, rubro_llm = _resolver_con_llm(seg, req, m, diag)
    diag["resoluciones"].append([
        {"token": r.token, "categoria": r.categoria, "valor": r.valor, "metodo": r.metodo} for r in seg.resueltos
    ] + [{"token": t, "categoria": None, "valor": None, "metodo": "sin_resolver"} for t in seg.sin_resolver])

    # ── 1. Lo que dice el texto ────────────────────────────────────────────────
    poner("tipo", seg.tipo_mov, "texto")
    if seg.importe is not None:
        poner("importe", seg.importe, "texto")
    poner("moneda", seg.moneda, "texto")
    if seg.fechas:
        f = seg.fechas[0]
        poner("fecha", f.valor.isoformat(), "texto")
        if f.corregida:
            advertencias.append(f"La fecha «{f.original}» no existe; se interpretó como {f.valor:%d/%m/%Y}")
            factor *= 0.9
    for invalida in seg.fechas_invalidas:
        advertencias.append(f"No se pudo interpretar la fecha «{invalida}»")

    for categoria in ("obra", "contratista", "cuenta"):
        r = seg.primero(categoria)
        if r:
            poner(categoria, r.valor, origen_de(r))
            factor *= FACTOR_METODO.get(r.metodo, 1.0)
    r = seg.primero("rubro")
    if r:
        rubro_1, rubro_2 = r.valor.split(" / ")
        poner("rubro_1", rubro_1, origen_de(r))
        poner("rubro_2", rubro_2, origen_de(r))
        factor *= FACTOR_METODO.get(r.metodo, 1.0)

    # `Lennon1C`: la etapa y la caja vienen pegadas a la obra; «etapa 1» y «caja», sueltas.
    r_obra = seg.primero("obra")
    etapa_texto = (r_obra.etapa if r_obra else None) or seg.etapa
    caja_pedida = bool(r_obra and r_obra.caja) or seg.caja

    cert = seg.primero("certificado")
    if cert:
        extras["certificado"] = cert.valor
    if seg.alias_propuesto and seg.primero("contratista"):
        extras["alias_propuesto"] = {"como_lo_dice": seg.alias_propuesto["como_lo_dice"],
                                     "valor_canonico": seg.primero("contratista").valor, "tipo": "contratista"}

    # ── 2. Lo que dice el comprobante ──────────────────────────────────────────
    compartido = req.texto_compartido > 1
    if comp is not None:
        extras["comprobante"] = {k: v for k, v in comp.dict().items() if v not in (None, "", {}) and k != "fuente"}
        for campo, valor_comp, fmt in (("importe", comp.importe, _fmt_importe), ("fecha", comp.fecha, str)):
            valor_texto = campos[campo]
            if compartido and campo == "importe" and valor_texto is not None and valor_texto != valor_comp:
                # Un texto para N comprobantes: su importe es el total o el de otro comprobante.
                advertencias.append(f"El texto dice {fmt(valor_texto)}, pero es un texto para {req.texto_compartido} "
                                    f"comprobantes: el importe sale de este comprobante")
                campos["importe"] = None
                origen.pop("importe", None)
            if valor_comp in (None, ""):
                continue
            if valor_texto is not None and valor_texto != valor_comp and not compartido:
                conflictos.append(Conflicto(campo=campo, valor_texto=valor_texto, valor_comprobante=valor_comp,
                                            detalle=f"El texto dice {fmt(valor_texto)} y el comprobante {fmt(valor_comp)}"))
                campos[campo] = None
                origen.pop(campo, None)
                preguntas.append(Pregunta(campo=campo, texto=f"¿Cuál es {'el importe' if campo == 'importe' else 'la fecha'}?",
                                          opciones=[fmt(valor_texto), fmt(valor_comp)], motivo="conflicto"))
            else:
                poner(campo, valor_comp, "comprobante")
        poner("moneda", campos["moneda"] or comp.moneda, origen.get("moneda", "comprobante"))
        poner("medio_pago", comp.medio_pago, "comprobante")
        poner("tipo_comprobante", comp.tipo_comprobante, "comprobante")
        for clave in ("fecha_pago", "id_operacion", "numero_cheque", "cuit", "cuenta_destino", "razon_social"):
            if getattr(comp, clave):
                extras[clave] = getattr(comp, clave)

        contr_comp = resolver.contratista_por_cuit(comp.cuit, m)
        metodo_comp = "cuit"
        if not contr_comp and comp.razon_social:
            r = next((r for r in resolver.resolver_token(comp.razon_social, m) if r.categoria == "contratista"), None)
            contr_comp, metodo_comp = (r.valor, r.metodo) if r else (None, None)
            if not contr_comp:
                contr_comp = resolver.contratista_por_razon_social(comp.razon_social, m)
                metodo_comp = "exacto" if contr_comp else None
        if contr_comp:
            if campos["contratista"] and campos["contratista"] != contr_comp:
                conflictos.append(Conflicto(campo="contratista", valor_texto=campos["contratista"], valor_comprobante=contr_comp,
                                            detalle=f"El texto dice «{campos['contratista']}» y el comprobante es a nombre de «{contr_comp}»"))
                preguntas.append(Pregunta(campo="contratista", texto="¿A quién se le pagó?",
                                          opciones=[campos["contratista"], contr_comp], motivo="conflicto"))
            poner("contratista", contr_comp, "comprobante")
            factor *= FACTOR_METODO.get(metodo_comp, 1.0)
        if (campos["tipo"] == "INGRESO") and not campos["obra"]:
            poner("obra", resolver.obra_por_cuit_comitente(comp.cuit_originante, m), "comprobante")
        # §5.16: lo que identifica al comprobante, para reconocerlo si otro usuario lo manda.
        poner("ref_comprobante", duplicados.SEPARADOR_REFS.join(comp.referencias()), "comprobante")

    # ── 3. Lo heredado de la ficha anterior (corrección) ───────────────────────
    marcador_personal = bool(seg.de("personal"))
    if semilla:
        for campo, valor in semilla["campos"].items():
            if campo in campos and campos[campo] in (None, ""):
                poner(campo, valor, _origen_semilla(semilla, campo))
        for clave, valor in semilla["extras"].items():
            extras.setdefault(clave, valor)
        if semilla.get("clasificacion") == "personal" and not (seg.primero("obra") or seg.primero("contratista")):
            marcador_personal = True

    # ── 4. Derivados de los maestros ───────────────────────────────────────────
    poner("tipo", campos["tipo"] or "EGRESO", origen.get("tipo", "inferido"))
    tipo = campos["tipo"]
    obra = m.obra(campos["obra"])
    contratista = m.contratista(campos["contratista"])
    if campos["contratista"] and not contratista:
        advertencias.append(f"«{campos['contratista']}» no está en CONTRATISTAS (viene de ALIAS)")
    # §5.6: un inactivo llega acá solo por nombre exacto, alias exacto o CUIT. Se pregunta si
    # se reactiva; si el usuario dijo «Es otro», se descarta y se pregunta a quién.
    if contratista and not contratista.activo:
        if normalizar(contratista.nombre) == normalizar(extras.get("contratista_descartado")):
            campos["contratista"] = None
            origen.pop("contratista", None)
            contratista = None
        elif not extras.get("reactivar"):
            extras["inactivo_propuesto"] = contratista.nombre
            preguntas.append(Pregunta(campo="inactivo", texto=f"{contratista.nombre} está inactivo, ¿lo reactivo?",
                                      opciones=["Reactivar", "Es otro"], motivo="inactivo"))
    if obra:
        poner("comitente", obra.comitente, "maestro")

    # El rubro (§5.12 v1.8): el habitual del contratista; si no tiene, el de la última vez que se
    # le pagó (origen «supuesto»: Gabriel lo ve y lo corrige); si no, el que sugiera el LLM.
    # Para un dual sin saber todavía si es personal u obra, la última vez no sirve.
    lado_personal = True if marcador_personal or (semilla and semilla.get("clasificacion") == "personal") else \
        False if (semilla and semilla.get("clasificacion") == "obra") or not (contratista and contratista.dual) else None
    if tipo in ("EGRESO", "PASANTE") and not campos["rubro_1"]:
        ultimo = _ultimo_rubro(contratista.nombre, historia, lado_personal, m) \
            if contratista and lado_personal is not None else None
        if contratista and contratista.rubro_1 and m.rubro(contratista.rubro_1, contratista.rubro_2):
            poner("rubro_1", contratista.rubro_1, "inferido")
            poner("rubro_2", contratista.rubro_2, "inferido")
            factor *= 0.95
        elif ultimo:
            poner("rubro_1", ultimo.rubro_1, "supuesto")
            poner("rubro_2", ultimo.rubro_2, "supuesto")
        elif rubro_llm and rubro_llm.puntaje >= UMBRAL_LLM * 100:
            rubro_1, rubro_2 = rubro_llm.valor.split(" / ")
            poner("rubro_1", rubro_1, "llm")
            poner("rubro_2", rubro_2, "llm")
            factor *= FACTOR_METODO["llm"]
    rubro = m.rubro(campos["rubro_1"], campos["rubro_2"])

    # ── 5. Cascada de clasificación (código, no LLM) ──────────────────────────
    res = clasificador.clasificar(m, tipo, obra, contratista, rubro, marcador_personal)
    if semilla and semilla.get("clasificacion") == "obra" and res.preguntar == "clasificacion":
        # El usuario contestó «Obra» (no personal) a la pregunta de un dual (R2): sigue la
        # cascada como si no fuera dual. Con obra, manda su tipo (R4): Austral es estructura.
        res = clasificador.Resultado(
            clasificador.CLASIFICACION_POR_TIPO_OBRA.get(obra.tipo) if obra else "obra",
            f"R2: «{contratista.nombre}» es dual y el usuario dijo obra", preguntar=None if obra else "obra")
    if semilla and semilla.get("clasificacion"):
        extras["clasificacion_respondida"] = semilla["clasificacion"]
    if res.clasificacion == "personal" and marcador_personal:
        # Queda en la ficha: en la ronda de una respuesta el texto ya no trae «Retiro», y sin
        # esto el dual volvía a preguntar y aparecía «¿A qué obra?» (captura 1, 30/09).
        extras["destino_personal"] = True
    if res.clasificacion == "personal":
        # §5.12 v1.8: un gasto personal no lleva la obra de un tercero ni una propia (P-000001
        # quedó con «Moreno etapa 1»). Un inmueble personal (Belelli, Gessel) sí.
        if obra and obra.tipo != "personal":
            advertencias.append(f"Un gasto personal no lleva la obra «{obra.nombre}»: no se escribe")
            for campo in ("obra", "etapa", "comitente"):
                campos[campo] = None
                origen.pop(campo, None)
            obra = None
        # Sofi y Juanma (duales, §7) en lo personal: Familia, como supuesto.
        if tipo in ("EGRESO", "PASANTE") and not campos["rubro_1"] and contratista and contratista.dual:
            familia = next((r for r in m.rubros if r.afecta == "personal" and normalizar(r.rubro_2) == "familia"), None)
            if familia:
                poner("rubro_1", familia.rubro_1, "supuesto")
                poner("rubro_2", familia.rubro_2, "supuesto")
                rubro = familia

    if tipo in ("EGRESO", "PASANTE"):
        poner("item", (comp.razon_social if comp else None) or campos["contratista"],
              "comprobante" if comp and comp.razon_social else "inferido")
    if campos["cuenta"] and not campos["medio_pago"] and normalizar(campos["cuenta"]) == "efectivo":
        poner("medio_pago", "Efectivo", "inferido")
    if not campos["cuenta"] and normalizar(campos["medio_pago"]) == "efectivo" and tipo != "PASANTE":
        poner("cuenta", "Efectivo", "inferido")

    # ── Caja de obra (§5.8) ────────────────────────────────────────────────────
    # Sale o entra de la caja de la obra si lo dice la C (o «caja»), o si es el cobro de un
    # certificado en una obra que el estudio administra: esa plata es de la obra, no del
    # estudio. Si dice honorarios, es del estudio. La cuenta nunca se inventa.
    es_cert = seg.primero("certificado") is not None  # «cert Moreno» también: sin número, pero certificado
    administrada = obra is not None and normalizar(obra.servicio) in ("administracion", "todo")
    if obra and tipo in ("INGRESO", "EGRESO"):
        caja = m.caja_de_obra(obra.nombre)
        verbo = "entra" if tipo == "INGRESO" else "sale"
        # §5.8 v1.8: Gabriel no usa la C. En una obra con caja, «efectivo» (lo diga el texto o el
        # comprobante) es la caja de la obra; «efectivo del estudio» es el Efectivo del estudio.
        # La C y «efectivo del estudio» se dicen una vez: viajan en extras para que una respuesta
        # posterior (el tc, el rubro) no los pierda. La C solo vale para la misma obra.
        if caja_pedida:
            extras["caja_de"] = obra.nombre
        caja_pedida = caja_pedida or extras.get("caja_de") == obra.nombre
        if seg.efectivo_estudio:
            extras["efectivo_estudio"] = True
        cuenta_dicha = m.cuenta(campos["cuenta"])
        efectivo_de_la_obra = caja is not None and cuenta_dicha is not None and cuenta_dicha.tipo == "efectivo" \
            and not extras.get("efectivo_estudio")
        if caja_pedida or efectivo_de_la_obra or (tipo == "INGRESO" and administrada and es_cert and not seg.honorarios):
            actual = m.cuenta(campos["cuenta"])
            if caja is None:
                advertencias.append(f"{obra.nombre} no tiene caja de obra en CUENTAS: no se inventa la cuenta")
                campos["cuenta"] = None
                origen.pop("cuenta", None)
                preguntas.append(Pregunta(campo="cuenta", texto=f"{obra.nombre} no tiene caja de obra. ¿De qué cuenta {verbo}?",
                                          opciones=[c.nombre for c in m.cuentas_del_estudio() if c.activa]))
            elif actual and actual.nombre != caja.nombre and actual.tipo != "efectivo":
                conflictos.append(Conflicto(campo="cuenta", valor_texto=actual.nombre, valor_comprobante=caja.nombre,
                                            detalle=f"El texto dice «{actual.nombre}», pero va por la caja de {obra.nombre}"))
                campos["cuenta"] = None
                origen.pop("cuenta", None)
                preguntas.append(Pregunta(campo="cuenta", texto=f"¿De qué cuenta {verbo}?",
                                          opciones=[caja.nombre, actual.nombre], motivo="conflicto"))
            else:
                # «/efectivo» en un cobro de certificado dice cómo se pagó, no a qué cuenta entra.
                if actual and actual.tipo == "efectivo":
                    poner("medio_pago", "Efectivo", origen.get("cuenta", "texto"))
                poner("cuenta", caja.nombre, "inferido")
        elif tipo == "INGRESO" and administrada and not es_cert and not seg.honorarios:
            # §5.12 v1.8: en una obra con caja, un ingreso puede ser un adelanto del comitente a
            # la caja (Lennon, USD 20.000 el 28/09): esa opción tiene que estar.
            opciones = ["Certificación", "Honorarios"] + (["Adelanto para la caja de obra"] if caja else [])
            preguntas.append(Pregunta(campo="concepto", texto=f"Este ingreso de {obra.nombre}, ¿qué es?", opciones=opciones))

    # ── Etapa (§5.15 v1.7) ─────────────────────────────────────────────────────
    # «cert 4 extras»: extras es la etapa y 4 el número (§5.11). «Marcelo/Moreno/extras»: un
    # tramo suelto que es una etapa con nombre de la obra.
    if obra and extras.get("certificado"):
        numero_cert, etapa_cert = _etapa_del_certificado(extras["certificado"], obra, m)
        if etapa_cert:
            extras["certificado"] = numero_cert or ""
            etapa_texto = etapa_texto or etapa_cert
    if obra and not etapa_texto:
        for t in list(seg.sin_resolver):
            if (e := m.etapa_por_nombre(obra.nombre, t)) and not t.isdigit():
                etapa_texto = e
                seg.sin_resolver.remove(t)
                break
    if tipo != "TRASPASO":
        valor, org, pregs, avisos = _decidir_etapa(obra, etapa_texto, campos["etapa"], extras, m)
        preguntas += pregs
        advertencias += avisos
        if org:
            poner("etapa", valor, org)

    # ── Depósito «en negro» (§5.17) ────────────────────────────────────────────
    # Una sola fila en «Pagado por el comitente»: suma a la cuenta corriente del contratista
    # como un pago directo del comitente y no toca el saldo del estudio. La cuenta la fija el
    # motor, diga lo que diga el texto.
    if tipo == "PASANTE":
        poner("informal", "VERDADERO", "inferido")
        if campos["cuenta"] and normalizar(campos["cuenta"]) != normalizar(maestros.CUENTA_PAGADO_POR_COMITENTE):
            advertencias.append(f"Un depósito va siempre a «{maestros.CUENTA_PAGADO_POR_COMITENTE}», no a «{campos['cuenta']}»")
        poner("cuenta", maestros.CUENTA_PAGADO_POR_COMITENTE, "inferido")
    poner("moneda", campos["moneda"] or "ARS", origen.get("moneda", "inferido"))

    # ── De qué cuenta salió (§5.7, v1.7) ───────────────────────────────────────
    # 1. El texto: una cuenta nombrada, «efectivo», la C de la caja (ya puestos arriba).
    # 2. El comprobante. 3. La obra (su cuenta habitual). 4. Si nada lo dice, Banco /
    # transferencia con origen «supuesto»: se muestra marcado y no se pregunta. Nunca pisa una
    # pregunta de cuenta que ya exista (una obra sin caja, un conflicto).
    if tipo in ("INGRESO", "EGRESO") and not campos["cuenta"] and not any(p.campo == "cuenta" for p in preguntas):
        por_comprobante = _cuenta_del_comprobante(comp, obra, campos["moneda"], m) if comp else None
        habitual = m.cuenta(obra.cuenta_habitual) if obra and obra.cuenta_habitual and tipo == "EGRESO" else None
        if por_comprobante:
            poner("cuenta", por_comprobante.nombre, "comprobante")
        elif habitual:
            poner("cuenta", habitual.nombre, "maestro")
        else:
            banco = _cuenta_de_tipo(m, "banco", campos["moneda"])
            if banco:
                poner("cuenta", banco.nombre, "supuesto")
                if not campos["medio_pago"]:
                    poner("medio_pago", "Transferencia", "supuesto")
                advertencias.append(f"Cuenta asumida: {banco.nombre}")
    # El medio de pago que corresponde a la cuenta, si nadie lo dijo.
    cuenta_elegida = m.cuenta(campos["cuenta"])
    if cuenta_elegida and not campos["medio_pago"] and tipo in ("INGRESO", "EGRESO"):
        poner("medio_pago", MEDIO_POR_TIPO_DE_CUENTA.get(cuenta_elegida.tipo),
              "supuesto" if origen.get("cuenta") == "supuesto" else "inferido")

    # §5.7 y §5.8 v1.8. Dólares a una caja en dólares: sin tc. Un pago en pesos desde una caja
    # en dólares: el tc del día, que se pide en el primer pago del día de esa caja y se lee del
    # libro en los siguientes (el motor sigue sin estado).
    if not obligatorios.necesita_tc(campos, m):
        if campos["moneda"] == "ARS":
            poner("tc", 1, "inferido")
            if campos["importe"] is not None:
                poner("importe_ars", campos["importe"], "inferido")
    else:
        if campos["moneda"] == "ARS" and campos["tc"] in (None, "", 1) and cuenta_elegida:
            campos["tc"] = None
            # La fecha del mensaje se pone más abajo: si el texto no trae fecha, es esa.
            fecha_pago = campos["fecha"] or (f.isoformat() if (f := _fecha_local(req, s)) else None)
            tc_hoy = _tc_del_dia(cuenta_elegida.nombre, fecha_pago, historia)
            if tc_hoy:
                poner("tc", tc_hoy, "inferido")
                extras["tc_de_hoy"] = True
                advertencias.append(f"TC {_formato_tc(tc_hoy)} (de hoy)")
        if campos["tc"] not in (None, "") and campos["importe"] is not None:
            # §5.7: en dólares, con el tipo de cambio que dijo el usuario; en pesos, ya está.
            pesos = numero(campos["importe"]) * (numero(campos["tc"]) if campos["moneda"] != "ARS" else 1)
            poner("importe_ars", round(pesos, 2), "inferido")
    if req.adjuntos:
        poner("comprobante_url", req.adjuntos[0].url, "comprobante")
    # En una corrección el adjunto vino con el mensaje anterior.
    tiene_adjunto = bool(req.adjuntos or campos["comprobante_url"])
    if not tiene_adjunto:
        poner("tipo_comprobante", campos["tipo_comprobante"] or "Sin comprobante", origen.get("tipo_comprobante", "inferido"))
    cuenta = m.cuenta(campos["cuenta"])
    if cuenta:
        poner("concilia", "VERDADERO" if cuenta.concilia_contra_banco else "FALSO", "maestro")
    poner("origen", "WHATSAPP", "inferido")
    poner("tipo_gasto", res.clasificacion, "inferido")
    fecha_msg = _fecha_local(req, s)
    if not campos["fecha"] and fecha_msg and not any(c.campo == "fecha" for c in conflictos):
        poner("fecha", fecha_msg.isoformat(), "fecha_mensaje")
    if campos["fecha"] and fecha_msg and campos["fecha"] > fecha_msg.isoformat():
        advertencias.append(f"La fecha {campos['fecha']} es posterior al mensaje")

    partes = []
    if extras.get("certificado"):
        partes.append(f"Certificado {extras['certificado']}")
    tokens_libres = descripciones + seg.libres + ([] if res.clasificacion != "personal" else seg.sin_resolver)
    partes += tokens_libres
    if extras.get("numero_cheque"):
        partes.append(f"Cheque {extras['numero_cheque']}")
    if extras.get("id_operacion"):
        partes.append(f"Op. {extras['id_operacion']}")
    if partes:
        poner("descripcion", " · ".join(partes), "texto")
    elif semilla and semilla["campos"].get("descripcion"):
        poner("descripcion", semilla["campos"]["descripcion"], "contexto_previo")

    # ── 6. Preguntas y faltantes ───────────────────────────────────────────────
    sin_resolver = [t for t in seg.sin_resolver if t not in tokens_libres]

    for r in seg.de("ambiguo"):
        cat = "obra" if any(o.startswith("obra") for o in r.opciones) else "contratista"
        preguntas.append(Pregunta(campo=cat, texto=f"¿«{r.token}» es…?", motivo="apodo_ambiguo",
                                  opciones=[o.split(": ", 1)[1] for o in r.opciones]))

    if res.preguntar == "clasificacion":
        preguntas.append(Pregunta(campo="clasificacion", texto=f"¿Lo de «{campos['contratista']}» es de obra o personal?",
                                  opciones=["Obra", "Personal"], motivo="dual"))

    pregunta_obra = not campos["obra"] and tipo != "TRASPASO" and res.clasificacion != "personal" \
        and res.preguntar != "clasificacion" and not any(p.campo == "obra" for p in preguntas)
    if pregunta_obra and (res.preguntar == "obra" or res.clasificacion in ("obra", "estructura")):
        opciones = [o.nombre for o in m.obras if o.estado != "cerrada" and o.tipo in ("obra_terceros", "obra_propia")]
        preguntas.append(Pregunta(campo="obra", texto="¿A qué obra?", opciones=opciones[:MAX_OPCIONES]))

    if tipo in ("EGRESO", "PASANTE") and not campos["contratista"] and res.clasificacion != "personal" \
            and not any(p.campo == "contratista" for p in preguntas):
        if sin_resolver:
            token = sin_resolver.pop(0)
            # §5.6 v1.9: solo parecidos de verdad cercanos; si no hay, el contratista es nuevo.
            opciones = resolver.cercanos(token, seg.candidatos.get(token) or resolver.candidatos(token, m, "contratista"))
            # Con la obra preguntada, el token suelto puede ser la obra mal escrita: no se da de alta.
            if opciones or not _puede_ser_un_nombre(token) or any(p.campo == "obra" for p in preguntas):
                preguntas.append(Pregunta(campo="contratista", texto=f"¿Quién es «{token}»?", opciones=opciones))
            else:
                nuevo = _contratista_nuevo(token, comp, m)
                extras["contratista_nuevo"] = nuevo
                poner("contratista", nuevo["nombre"], "comprobante" if nuevo["cuit"] else "texto")
        elif not tiene_adjunto and res.clasificacion == "obra":
            preguntas.append(Pregunta(campo="contratista", texto="¿A quién se le pagó?"))

    if tipo in ("EGRESO", "PASANTE") and not campos["rubro_1"] and res.preguntar != "clasificacion" \
            and (res.clasificacion == "personal" or campos["contratista"]):
        afecta = "personal" if res.clasificacion == "personal" else "obra"
        opciones = _rubros_por_uso(afecta, list(historia), m, contratista)  # §5.12 v1.8: los más usados
        if rubro_llm and res.clasificacion != "personal":
            opciones = [rubro_llm.valor.split(" / ")[1]] + [o for o in opciones if o != rubro_llm.valor.split(" / ")[1]]
        preguntas.append(Pregunta(campo="rubro", texto="¿Qué rubro?", opciones=opciones[:MAX_OPCIONES]))

    # El contratista nuevo (también el que viene de la ficha anterior, después de una respuesta):
    # el rubro habitual es el de la ficha, y la ficha lo avisa. Si el usuario eligió otro, ya no
    # hay alta.
    nuevo = extras.get("contratista_nuevo")
    if nuevo and campos["contratista"] == nuevo.get("nombre") and m.contratista(nuevo["nombre"]) is None:
        nuevo.update(rubro_habitual_1=campos["rubro_1"] or "", rubro_habitual_2=campos["rubro_2"] or "")
        poner("item", campos["item"] or nuevo["nombre"], origen.get("contratista", "texto"))
        advertencias.append(f"{nuevo['nombre']} es nuevo: lo agrego como contratista"
                            + (f" · {campos['rubro_2']}" if campos["rubro_2"] else ""))
    elif nuevo:
        extras.pop("contratista_nuevo")

    if campos["importe"] is None and (not tiene_adjunto or compartido) and not any(c.campo == "importe" for c in conflictos):
        preguntas.append(Pregunta(campo="importe", texto="¿Cuál es el importe?"))

    # Tokens que no se pudieron ubicar y no generaron pregunta: van a la descripción.
    if sin_resolver:
        poner("descripcion", " · ".join(filter(None, [campos["descripcion"], *sin_resolver])), "texto")

    faltantes = obligatorios.faltantes(campos, m)  # la misma lista que valida /confirmar

    factor *= 0.8 ** len(preguntas) * 0.7 ** len(conflictos)
    if advertencias:
        extras["advertencias"] = advertencias

    ficha = Ficha(campos=campos, origen_campo=origen, faltantes=faltantes, conflictos=conflictos,
                  confianza=round(max(0.0, min(1.0, factor)), 2), regla=res.regla, extras=extras)
    return ficha, preguntas


# ─── Certificados (§5.11) ──────────────────────────────────────────────────────

def _es_certificado(seg: Segmento, comp, semilla: dict | None) -> bool:
    """Un certificado es un documento, no un gasto. Lo es si llega el PDF de un certificado, o
    si el texto nombra un certificado sin decir que es un movimiento: «Ingreso Moreno/cert. 4»
    es el cobro de un certificado, «Certificado 5 Moreno1 $3.200.000» es el certificado."""
    if seg.tipo_mov:
        return False
    if comp is not None and comp.certificado is not None:
        return True
    if semilla and semilla["campos"].get("tipo"):
        # Una corrección sigue siendo lo que corrige: «Cert. 4 extras» después de un cobro
        # corrige el número del cobro, no anuncia un certificado.
        return semilla["campos"]["tipo"] == "CERTIFICADO"
    return (comp is None and seg.primero("certificado") is not None and not seg.honorarios
            and not (seg.primero("contratista") or seg.primero("cuenta") or seg.de("personal")))


def _armar_certificado(seg: Segmento, comp, req: InterpretarIn, m: Maestros, s: Settings, diag: dict,
                       semilla: dict | None, historia: list[dict] = ()) -> tuple[Ficha, list[Pregunta]]:
    """La ficha de un certificado: obra, etapa, número, fecha y saldo a cobrar. Nada más.

    Mismo reparto de autoridad que un movimiento: el comprobante manda en montos, fecha y
    número; el texto, en obra y etapa. Si se contradicen, no se elige."""
    campos: dict = {c: None for c in CAMPOS_FICHA_CERTIFICADO}
    origen: dict[str, str] = {}
    extras: dict = {}
    advertencias: list[str] = []
    conflictos: list[Conflicto] = []
    preguntas: list[Pregunta] = []

    def poner(campo: str, valor, org: str) -> None:
        if valor not in (None, ""):
            campos[campo] = valor
            origen[campo] = org

    descripciones, _ = _resolver_con_llm(seg, req, m, diag)
    diag["resoluciones"].append([
        {"token": r.token, "categoria": r.categoria, "valor": r.valor, "metodo": r.metodo} for r in seg.resueltos
    ] + [{"token": t, "categoria": None, "valor": None, "metodo": "sin_resolver"} for t in seg.sin_resolver])

    del_pdf = comp.certificado if comp is not None else None
    poner("tipo", "CERTIFICADO", "comprobante" if del_pdf else "texto")
    poner("fuente", "PDF" if del_pdf else "TEXTO", "inferido")

    # ── 1. Lo que dice el texto ────────────────────────────────────────────────
    r_obra = seg.primero("obra")
    if r_obra:
        o = m.obra(r_obra.valor)
        if o is not None and o.tipo not in certificados.TIPOS_OBRA_CERTIFICABLE:
            # «Austral» es también su constructora: en un certificado nunca es la obra de indirectos.
            advertencias.append(f"«{r_obra.token}» no puede ser la obra de un certificado: {o.nombre} es {o.tipo}")
            r_obra = None
        else:
            poner("obra", r_obra.valor, ORIGEN_METODO.get(r_obra.metodo, "texto"))
    etapa = (r_obra.etapa if r_obra else None) or seg.etapa
    origen_etapa = "texto"
    cert = seg.primero("certificado")
    if cert and certificados.clave_numero(cert.valor):
        poner("numero", cert.valor, "texto")
    if seg.importe is not None:
        poner("saldo_a_cobrar", seg.importe, "texto")
    if seg.fechas:
        poner("fecha", seg.fechas[0].valor.isoformat(), "texto")

    # ── 2. Lo que dice el PDF ──────────────────────────────────────────────────
    if comp is not None:
        extras["comprobante"] = {k: v for k, v in comp.dict().items() if v not in (None, "", {}) and k != "fuente"}
    if del_pdf:
        advertencias += del_pdf.get("advertencias") or []
        for campo, valor_pdf, fmt in (("saldo_a_cobrar", del_pdf.get("saldo_a_cobrar"), _fmt_importe),
                                      ("fecha", del_pdf.get("fecha"), str), ("numero", del_pdf.get("numero"), str)):
            if valor_pdf in (None, ""):
                continue
            valor_texto = campos[campo]
            igual = (certificados.clave_numero(valor_texto) == certificados.clave_numero(valor_pdf)) if campo == "numero" \
                else valor_texto == valor_pdf
            if valor_texto is not None and not igual and req.texto_compartido == 1:
                conflictos.append(Conflicto(campo=campo, valor_texto=valor_texto, valor_comprobante=valor_pdf,
                                            detalle=f"El texto dice {fmt(valor_texto)} y el certificado {fmt(valor_pdf)}"))
                campos[campo] = None
                origen.pop(campo, None)
                preguntas.append(Pregunta(campo=campo, texto=f"¿Cuál es {'el saldo a cobrar' if campo == 'saldo_a_cobrar' else 'la fecha' if campo == 'fecha' else 'el número'}?",
                                          opciones=[fmt(valor_texto), fmt(valor_pdf)], motivo="conflicto"))
            else:
                poner(campo, valor_pdf, "comprobante")

        # La obra: si el texto no la dice, por el destinatario contra OBRAS.comitente.
        if not campos["obra"]:
            destinatario = del_pdf.get("destinatario")
            obras = certificados.obras_por_comitente(destinatario, m)
            if len(obras) == 1:
                poner("obra", obras[0], "comprobante")
            elif destinatario:
                abiertas = [o.nombre for o in m.obras if o.estado != "cerrada" and o.tipo in certificados.TIPOS_OBRA_CERTIFICABLE]
                texto = (f"El certificado está dirigido a {destinatario}, que es comitente de más de una obra. ¿De cuál es?"
                         if obras else f"El certificado está dirigido a {destinatario}, que no es comitente de ninguna obra. "
                                       f"¿De qué obra es?")
                preguntas.append(Pregunta(campo="obra", texto=texto, opciones=(obras or abiertas)[:MAX_OPCIONES]))

        # La etapa: el texto manda; si no dice, el cuerpo y el nombre del archivo, y si esos
        # dos no coinciden, no se elige.
        if not etapa:
            cuerpo, del_archivo = del_pdf.get("etapa_cuerpo"), del_pdf.get("etapa_archivo")
            if cuerpo and del_archivo and cuerpo != del_archivo:
                conflictos.append(Conflicto(campo="etapa", valor_texto=del_archivo, valor_comprobante=cuerpo,
                                            detalle=f"El certificado dice etapa {cuerpo} y el nombre del archivo, etapa {del_archivo}"))
                preguntas.append(Pregunta(campo="etapa", texto="El certificado dice una etapa y el nombre del archivo, "
                                          "otra. ¿De qué etapa es?", opciones=[cuerpo, del_archivo], motivo="conflicto"))
            else:
                etapa, origen_etapa = cuerpo or del_archivo, "comprobante"

    # ── 3. Lo heredado de la ficha anterior (corrección) ───────────────────────
    if semilla:
        for campo, valor in semilla["campos"].items():
            if campo in campos and campos[campo] in (None, "") and not any(c.campo == campo for c in conflictos):
                poner(campo, valor, _origen_semilla(semilla, campo))
        for clave, valor in semilla["extras"].items():
            extras.setdefault(clave, valor)
        if not etapa and campos["etapa"]:
            etapa, origen_etapa = campos["etapa"], origen["etapa"]

    # ── 4. Etapa contra ETAPAS (§5.15 v1.7) ────────────────────────────────────
    obra = m.obra(campos["obra"])
    # «cert 4 extras» en Moreno: el certificado 4 de la etapa extras (§5.11 v1.7).
    if obra and campos["numero"]:
        numero_cert, etapa_cert = _etapa_del_certificado(campos["numero"], obra, m)
        if etapa_cert:
            campos["numero"] = numero_cert
            etapa = etapa or etapa_cert
    campos["etapa"] = None
    origen.pop("etapa", None)
    if any(p.campo == "etapa" for p in preguntas):
        pass  # el PDF y el nombre del archivo no coinciden: ya se pregunta
    elif obra:
        valor, org, pregs, avisos = _decidir_etapa(obra, etapa, None, extras, m)
        preguntas += pregs
        advertencias += avisos
        if valor:
            poner("etapa", valor, origen_etapa if org == "texto" else org)
    elif etapa:
        extras["etapa_leida"] = etapa  # se valida cuando se sepa la obra

    fecha_msg = _fecha_local(req, s)
    if not campos["fecha"] and fecha_msg and not any(c.campo == "fecha" for c in conflictos):
        poner("fecha", fecha_msg.isoformat(), "fecha_mensaje")
    if req.adjuntos:
        poner("comprobante_url", req.adjuntos[0].url, "comprobante")

    # ── 5. Preguntas y faltantes ───────────────────────────────────────────────
    ya = {p.campo for p in preguntas}
    if not campos["obra"] and "obra" not in ya:
        opciones = [o.nombre for o in m.obras if o.estado != "cerrada" and o.tipo in certificados.TIPOS_OBRA_CERTIFICABLE]
        preguntas.append(Pregunta(campo="obra", texto="¿De qué obra es el certificado?", opciones=opciones[:MAX_OPCIONES]))
    if not campos["numero"] and "numero" not in ya:
        preguntas.append(Pregunta(campo="numero", texto="¿Qué número de certificado es?"))
    if campos["saldo_a_cobrar"] is None and "saldo_a_cobrar" not in ya:
        preguntas.append(Pregunta(campo="saldo_a_cobrar", texto="¿Cuál es el saldo a cobrar de este certificado?"))

    notas = descripciones + seg.sin_resolver
    if notas:
        extras["notas"] = " · ".join(notas)
    if del_pdf:
        extras["certificado_pdf"] = {k: v for k, v in del_pdf.items() if v not in (None, "", [], {})}
    if advertencias:
        extras["advertencias"] = advertencias

    faltantes = obligatorios.faltantes(campos, m)
    factor = 0.8 ** len(preguntas) * 0.7 ** len(conflictos)
    ficha = Ficha(campos=campos, origen_campo=origen, faltantes=faltantes, conflictos=conflictos,
                  confianza=round(max(0.0, min(1.0, factor)), 2), regla="§5.11", extras=extras)
    return ficha, preguntas


# ─── Traspasos (§5.18) ─────────────────────────────────────────────────────────

ARTICULOS = {"la", "el", "los", "las", "lo", "mi", "su"}
HACIA_ORIGEN = {"de", "desde", "del", "con"}      # «del banco», «con efectivo»: de ahí sale
HACIA_DESTINO = {"a", "al", "hacia", "para", "en"}  # «al banco», «a la caja»: ahí entra


def _es_traspaso(seg: Segmento, semilla: dict | None) -> bool:
    if seg.tipo_mov:
        return seg.tipo_mov == "TRASPASO"
    return bool(semilla and semilla["campos"].get("tipo") == "TRASPASO")


def _previa(palabras: list[str], i: int) -> int:
    """El índice de la palabra anterior a `i` que no es un artículo (−1 si no hay)."""
    j = i - 1
    while j >= 0 and palabras[j] in ARTICULOS:
        j -= 1
    return j


def _cuentas_del_texto(texto: str, m: Maestros, advertencias: list[str]) -> list[tuple[str, str | None]]:
    """(cuenta, rol) de lo que nombra el texto, en orden. El rol sale de la preposición de
    adelante: «del banco» → origen, «al banco» → destino. Una obra es su caja si lleva la C
    (`LennonC`) o si dice «caja de Lennon» / «caja de obra Lennon» (§5.8)."""
    palabras, hallazgos = resolver.escanear(texto, m)
    salida: list[tuple[str, str | None]] = []
    for h in hallazgos:
        r = h.resolucion
        j = _previa(palabras, h.inicio)
        if r.categoria == "cuenta":
            cuenta = m.cuenta(r.valor)
        elif r.categoria == "obra":
            # «la caja de obra Moreno»: se camina hacia atrás hasta «caja».
            k = h.inicio - 1
            while k >= 0 and palabras[k] in ({"de", "del", "obra"} | ARTICULOS):
                k -= 1
            dice_caja = k >= 0 and palabras[k] == "caja"
            if not (r.caja or dice_caja):
                continue  # una obra sin caja no es una cuenta
            if dice_caja:
                j = _previa(palabras, k)
            cuenta = m.caja_de_obra(r.valor)
            if cuenta is None:
                advertencias.append(f"{r.valor} no tiene caja de obra en CUENTAS: no se inventa la cuenta")
                continue
        else:
            continue
        if cuenta is None or cuenta.tipo == "externa":
            continue
        previa = palabras[j] if j >= 0 else ""
        rol = "origen" if previa in HACIA_ORIGEN else "destino" if previa in HACIA_DESTINO else None
        if all(c != cuenta.nombre for c, _ in salida):
            salida.append((cuenta.nombre, rol))
    return salida


def _unica(m: Maestros, tipo: str) -> str | None:
    """La única cuenta activa en pesos de ese tipo, o None si hay varias o ninguna."""
    candidatas = [c.nombre for c in m.cuentas if c.activa and c.tipo == tipo and c.moneda == "ARS"]
    return candidatas[0] if len(candidatas) == 1 else None


def _armar_traspaso(seg: Segmento, comp, req: InterpretarIn, m: Maestros, s: Settings, diag: dict,
                    semilla: dict | None, historia: list[dict] = ()) -> tuple[Ficha, list[Pregunta]]:
    """Una ficha TRASPASO con cuenta de origen y de destino (§5.18). /confirmar la escribe
    como dos filas vinculadas. No pasa por la cascada: un traspaso no es de obra ni personal."""
    campos: dict = {c: None for c in CAMPOS_FICHA_TRASPASO}
    origen: dict[str, str] = {}
    extras: dict = {}
    advertencias: list[str] = []
    conflictos: list[Conflicto] = []
    preguntas: list[Pregunta] = []

    def poner(campo: str, valor, org: str) -> None:
        if valor not in (None, ""):
            campos[campo] = valor
            origen[campo] = org

    poner("tipo", "TRASPASO", "texto" if seg.tipo_mov else "contexto_previo")
    if seg.importe is not None:
        poner("importe", seg.importe, "texto")
    poner("moneda", seg.moneda, "texto")
    if seg.fechas:
        poner("fecha", seg.fechas[0].valor.isoformat(), "texto")

    # ── Las cuentas ────────────────────────────────────────────────────────────
    nombradas = _cuentas_del_texto(seg.texto, m, advertencias)
    cuenta_origen = next((c for c, rol in nombradas if rol == "origen"), None)
    cuenta_destino = next((c for c, rol in nombradas if rol == "destino" and c != cuenta_origen), None)
    sueltas = [c for c, _ in nombradas if c not in (cuenta_origen, cuenta_destino)]
    if seg.traspaso in ("extraccion", "reposicion"):
        # Lo que dice la frase: una extracción entra en efectivo (o en una caja de obra) y sale
        # del banco; una reposición entra en la caja que se repone.
        for c in list(sueltas):
            tipo = m.cuenta(c).tipo
            if cuenta_destino is None and (tipo == "caja_obra" or (tipo == "efectivo" and seg.traspaso == "extraccion")):
                cuenta_destino = c
            elif cuenta_origen is None:
                cuenta_origen = c
            else:
                continue
            sueltas.remove(c)
        if seg.traspaso == "extraccion":
            # «retiro de efectivo»: el «de» no dice origen, el efectivo es el destino.
            if cuenta_origen and m.cuenta(cuenta_origen).tipo == "efectivo" and cuenta_destino is None:
                cuenta_origen, cuenta_destino = None, cuenta_origen
            cuenta_origen = cuenta_origen or _unica(m, "banco")
            cuenta_destino = cuenta_destino or _unica(m, "efectivo")
    elif len(sueltas) == 1 and (cuenta_origen is None) != (cuenta_destino is None):
        if cuenta_origen is None:
            cuenta_origen = sueltas.pop()
        else:
            cuenta_destino = sueltas.pop()
    poner("cuenta_origen", cuenta_origen, "texto")
    poner("cuenta_destino", cuenta_destino, "texto")
    if sueltas:
        extras["cuentas_mencionadas"] = [c for c, _ in nombradas]

    # ── Comprobante: manda en importe y fecha ──────────────────────────────────
    if comp is not None:
        extras["comprobante"] = {k: v for k, v in comp.dict().items() if v not in (None, "", {}) and k != "fuente"}
        for campo, valor_comp, fmt in (("importe", comp.importe, _fmt_importe), ("fecha", comp.fecha, str)):
            if valor_comp in (None, ""):
                continue
            if campos[campo] is not None and campos[campo] != valor_comp and req.texto_compartido == 1:
                conflictos.append(Conflicto(campo=campo, valor_texto=campos[campo], valor_comprobante=valor_comp,
                                            detalle=f"El texto dice {fmt(campos[campo])} y el comprobante {fmt(valor_comp)}"))
                preguntas.append(Pregunta(campo=campo, texto=f"¿Cuál es {'el importe' if campo == 'importe' else 'la fecha'}?",
                                          opciones=[fmt(campos[campo]), fmt(valor_comp)], motivo="conflicto"))
                campos[campo] = None
                origen.pop(campo, None)
            else:
                poner(campo, valor_comp, "comprobante")
        poner("ref_comprobante", duplicados.SEPARADOR_REFS.join(comp.referencias()), "comprobante")

    if semilla:
        for campo, valor in semilla["campos"].items():
            if campo in campos and campos[campo] in (None, "") and not any(c.campo == campo for c in conflictos):
                poner(campo, valor, _origen_semilla(semilla, campo))
        for clave, valor in semilla["extras"].items():
            extras.setdefault(clave, valor)
        mencionadas = extras.get("cuentas_mencionadas") or []
        if len(mencionadas) == 2 and (campos["cuenta_origen"] is None) != (campos["cuenta_destino"] is None):
            # «traspaso Banco/Efectivo»: contestada una, la otra es la que queda.
            conocida = campos["cuenta_origen"] or campos["cuenta_destino"]
            otra = next((c for c in mencionadas if c != conocida), None)
            poner("cuenta_destino" if campos["cuenta_destino"] is None else "cuenta_origen", otra, "inferido")

    # ── Derivados ──────────────────────────────────────────────────────────────
    co, cd = m.cuenta(campos["cuenta_origen"]), m.cuenta(campos["cuenta_destino"])
    if co and cd and co.nombre == cd.nombre:
        advertencias.append(f"Origen y destino son la misma cuenta ({co.nombre})")
        campos["cuenta_destino"] = None
        origen.pop("cuenta_destino", None)
        cd = None
    # §5.7 (v1.7): entre dólares y pesos, dos filas, cada una en su moneda, con el tipo de cambio
    # que diga el usuario (la pregunta «tipo_cambio» la genera la lista de obligatorios). El
    # importe de la ficha está en su moneda: la del texto o, si no dice, la de la cuenta de origen.
    moneda = campos["moneda"] or (co.moneda if co else cd.moneda if cd else "ARS")
    poner("moneda", moneda, origen.get("moneda", "inferido"))
    en_dolares = "USD" in {moneda, co.moneda if co else "ARS", cd.moneda if cd else "ARS"}
    if not en_dolares:
        poner("tc", 1, "inferido")
        if campos["importe"] is not None:
            poner("importe_ars", campos["importe"], "inferido")
    elif campos["tc"] not in (None, "") and campos["importe"] is not None:
        poner("importe_ars", round(numero(campos["importe"]) * (numero(campos["tc"]) if moneda != "ARS" else 1), 2), "inferido")
    cajas = [c for c in (co, cd) if c and c.tipo == "caja_obra"]
    if cajas:
        obra = m.obra_de_caja(cajas[0].nombre)
        poner("obra", obra.nombre if obra else None, "maestro")
    fecha_msg = _fecha_local(req, s)
    if not campos["fecha"] and fecha_msg and not any(c.campo == "fecha" for c in conflictos):
        poner("fecha", fecha_msg.isoformat(), "fecha_mensaje")
    if req.adjuntos:
        poner("comprobante_url", req.adjuntos[0].url, "comprobante")
    if not campos["descripcion"] and co and cd:
        poner("descripcion", f"Traspaso {co.nombre} → {cd.nombre}", "inferido")

    # ── Preguntas ──────────────────────────────────────────────────────────────
    opciones = [c.nombre for c in m.cuentas if c.activa and c.tipo != "externa"]
    mencionadas = extras.get("cuentas_mencionadas")
    if not campos["cuenta_origen"]:
        preguntas.append(Pregunta(campo="cuenta_origen", texto="¿De qué cuenta sale la plata?",
                                  opciones=[c for c in (mencionadas or opciones) if c != campos["cuenta_destino"]][:MAX_OPCIONES]))
    if not campos["cuenta_destino"] and not mencionadas:
        preguntas.append(Pregunta(campo="cuenta_destino", texto="¿A qué cuenta entra?",
                                  opciones=[c for c in opciones if c != campos["cuenta_origen"]][:MAX_OPCIONES]))
    if campos["importe"] is None and not req.adjuntos and not any(c.campo == "importe" for c in conflictos):
        preguntas.append(Pregunta(campo="importe", texto="¿Cuál es el importe?"))

    if advertencias:
        extras["advertencias"] = advertencias
    faltantes = obligatorios.faltantes(campos, m)
    factor = 0.8 ** len(preguntas) * 0.7 ** len(conflictos)
    diag["resoluciones"].append([{"token": seg.texto, "categoria": "traspaso", "valor": seg.traspaso, "metodo": "frase"}])
    return Ficha(campos=campos, origen_campo=origen, faltantes=faltantes, conflictos=conflictos,
                 confianza=round(max(0.0, min(1.0, factor)), 2), regla="T: traspaso entre cuentas (§5.18)",
                 extras=extras), preguntas
