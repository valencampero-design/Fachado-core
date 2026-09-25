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
from datetime import date, timedelta, timezone

from app import certificados, clasificador, comprobante, consultas, duplicados, llm, maestros, resolver
from app.config import Settings, settings
from app.maestros import Maestros, Usuario, normalizar, numero
from app.models import (CAMPOS_FICHA_CERTIFICADO, CAMPOS_FICHA_TRASPASO, COLUMNAS_MOVIMIENTOS, Conflicto, Ficha,
                        InterpretarIn,
                        InterpretarOut, PosibleDuplicado, Pregunta)
from app.resolver import Resolucion, Segmento
from app.saldos import como_dicts

logger = logging.getLogger(__name__)

UMBRAL_LLM = 0.75
FACTOR_METODO = {"alias": 1.0, "exacto": 1.0, "cuit": 1.0, "palabra": 0.9, "difuso": 0.9, "llm": 0.8}
ORIGEN_METODO = {"llm": "llm"}  # el resto de los métodos de diccionario son «texto»
MAX_OPCIONES = 10


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
                   if v not in (None, "") and origen.get(k) not in ("inferido", "maestro", "fecha_mensaje")},
        "origen": origen if respuestas else {},
        "clasificacion": contexto.get("clasificacion") or extras.get("clasificacion_respondida"),
        "extras": extras,
    }


def _origen_semilla(semilla: dict, campo: str) -> str:
    return semilla["origen"].get(campo) or "contexto_previo"


# ─── Intención (tanda 6.4, §5.12) ──────────────────────────────────────────────

# Acuses sueltos: no son un movimiento aunque tengan menos de tres palabras.
ACUSES = {"ok", "oka", "okey", "dale", "gracias", "muchas gracias", "listo", "si", "no", "bueno", "perfecto",
          "genial", "joya", "barbaro", "hola", "buen dia", "buenas", "buenas tardes", "buenas noches", "de nada"}
RE_PREGUNTA = re.compile(r"[?¿]|^(?:cuant[oa]s?|que|cual(?:es)?|como|donde|quien|cuando|decime|pasame|mostrame)\b")


def _hay_senales(texto: str, segmentos: list[Segmento]) -> bool:
    """Algo que solo tiene sentido en un movimiento: la barra del formato `algo/algo`, un
    importe, una fecha, una palabra de tipo o cualquier cosa que el diccionario reconozca."""
    return "/" in texto or any(
        seg.importe is not None or seg.fechas or seg.tipo_mov or seg.resueltos or seg.alias_propuesto
        or seg.honorarios or seg.caja or seg.etapa or seg.es_correccion for seg in segmentos)


def _intencion(req: InterpretarIn, texto: str, segmentos: list[Segmento], comprobantes: list) -> str:
    """movimiento | consulta | otro. **Ante la duda, movimiento**: es peor perder un pago que
    hacer una pregunta de más."""
    if req.contexto_previo or req.respuestas:
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
            else:
                diag["advertencias"].append(f"«{valor}» no es un importe")
        elif campo == "fecha":
            f = _fecha_de(valor)
            fijar("fecha", f) if f else libre.append(valor)
        elif campo == "concepto":
            libre.append("honorarios" if n.startswith("hon") else "certificado")
        elif campo == "duplicado":
            extras["no_es_duplicado" if n == "es otro" else "es_el_mismo"] = True
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

    intencion = _intencion(req, texto, segmentos, comprobantes)
    if intencion != "movimiento":
        diag["uso_llm"] = diag["llm_llamadas"] > 0
        return InterpretarOut(intencion=intencion, fichas=[], preguntas=[], requiere_confirmacion=False, diagnostico=diag)

    semilla = _semilla(contexto, respuestas=bool(req.respuestas))
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
        ficha, pregs = armar(seg, comp, req, m, s, diag, semilla if i == 0 else None)
        for p in pregs:
            p.ficha = i
        fichas.append(ficha)
        preguntas += pregs

    _marcar_duplicados(fichas, preguntas, libros, usuario, diag)
    _marcar_certificados_repetidos(fichas, preguntas, libros, usuario, diag)
    for i, ficha in enumerate(fichas):
        ficha.requiere_confirmacion = _requiere_confirmacion(
            ficha, [p for p in preguntas if p.ficha == i], usuario, m)

    diag["uso_llm"] = diag["llm_llamadas"] > 0
    return InterpretarOut(fichas=fichas, preguntas=preguntas, diagnostico=diag,
                          requiere_confirmacion=any(f.requiere_confirmacion for f in fichas))


def _marcar_duplicados(fichas: list[Ficha], preguntas: list[Pregunta], libros: dict | None,
                       usuario: Usuario | None, diag: dict) -> None:
    """§5.16: si el hecho ya está en el libro, lo dice y pregunta. Nunca lo descarta solo.
    El libro personal solo se mira si el que escribe tiene `ve_personal`: si no, ni siquiera
    se le puede decir que ahí hay algo parecido."""
    fichas_mov = [f for f in fichas if f.campos.get("tipo") != "CERTIFICADO"]
    if not libros or not any(f.campos.get("importe") is not None or f.campos.get("ref_comprobante") for f in fichas_mov):
        return
    movs: dict[str, list[dict]] = {}
    for nombre, libro in libros.items():
        if libro is None or (nombre == "personal" and not (usuario and usuario.ve_personal)):
            continue
        try:
            movs[nombre] = como_dicts(libro.leer_movimientos())
        except Exception as e:  # noqa: BLE001 — sin libro no hay duplicados, pero la ficha sale igual
            logger.exception("No se pudo leer el libro %s para buscar duplicados", nombre)
            diag["advertencias"].append(f"No se pudo buscar duplicados en el libro {nombre} ({type(e).__name__})")
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
    datos, uso = llm.resolver_tokens(m, req.texto, seg.sin_resolver, contexto, pedir_rubro)
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
           semilla: dict | None) -> tuple[Ficha, list[Pregunta]]:
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

    if tipo in ("EGRESO", "PASANTE") and not campos["rubro_1"]:
        if contratista and contratista.rubro_1 and m.rubro(contratista.rubro_1, contratista.rubro_2):
            poner("rubro_1", contratista.rubro_1, "inferido")
            poner("rubro_2", contratista.rubro_2, "inferido")
            factor *= 0.95
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
        if caja_pedida or (tipo == "INGRESO" and administrada and es_cert and not seg.honorarios):
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
            preguntas.append(Pregunta(campo="concepto", texto=f"Este ingreso de {obra.nombre}, ¿es una certificación "
                                      f"de obra o son honorarios del estudio?", opciones=["Certificación", "Honorarios"]))

    # ── Etapa (§5.15) ──────────────────────────────────────────────────────────
    etapas_obra = m.etapas_de(obra.nombre) if obra else []
    if obra and etapa_texto:
        if not etapas_obra:
            advertencias.append(f"{obra.nombre} no tiene etapas cargadas en ETAPAS: se ignora la etapa {etapa_texto}")
        elif etapa_texto in etapas_obra:
            poner("etapa", etapa_texto, "texto")
        else:
            advertencias.append(f"{obra.nombre} no tiene una etapa {etapa_texto}")
            preguntas.append(Pregunta(campo="etapa", texto=f"¿Qué etapa de {obra.nombre}?", opciones=etapas_obra))
    elif obra and etapas_obra and tipo != "TRASPASO" and not campos["etapa"]:
        preguntas.append(Pregunta(campo="etapa", texto=f"¿Qué etapa de {obra.nombre}?", opciones=etapas_obra))

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
    if campos["moneda"] == "ARS":
        poner("tc", 1, "inferido")
        if campos["importe"] is not None:
            poner("importe_ars", campos["importe"], "inferido")
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
    tokens_libres = descripciones + ([] if res.clasificacion != "personal" else seg.sin_resolver)
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
            opciones = seg.candidatos.get(token) or resolver.candidatos(token, m, "contratista")
            preguntas.append(Pregunta(campo="contratista", texto=f"¿Quién es «{token}»?", opciones=opciones))
        elif not tiene_adjunto and res.clasificacion == "obra":
            preguntas.append(Pregunta(campo="contratista", texto="¿A quién se le pagó?"))

    if tipo in ("EGRESO", "PASANTE") and not campos["rubro_1"] and res.preguntar != "clasificacion" \
            and (res.clasificacion == "personal" or campos["contratista"]):
        afecta = "personal" if res.clasificacion == "personal" else "obra"
        opciones = [r.rubro_2 for r in m.rubros if r.afecta == afecta]
        if rubro_llm and res.clasificacion != "personal":
            opciones = [rubro_llm.valor.split(" / ")[1]] + [o for o in opciones if o != rubro_llm.valor.split(" / ")[1]]
        preguntas.append(Pregunta(campo="rubro", texto="¿Qué rubro?", opciones=opciones[:MAX_OPCIONES]))

    if campos["importe"] is None and (not tiene_adjunto or compartido) and not any(c.campo == "importe" for c in conflictos):
        preguntas.append(Pregunta(campo="importe", texto="¿Cuál es el importe?"))

    # Tokens que no se pudieron ubicar y no generaron pregunta: van a la descripción.
    if sin_resolver:
        poner("descripcion", " · ".join(filter(None, [campos["descripcion"], *sin_resolver])), "texto")

    requeridos = {
        "EGRESO": ["fecha", "importe", "contratista", "rubro_1", "rubro_2", "medio_pago", "cuenta", "tipo_gasto"]
                  + ([] if res.clasificacion == "personal" else ["obra"]),
        "INGRESO": ["fecha", "importe", "obra", "medio_pago", "cuenta", "tipo_gasto"],
        "TRASPASO": ["fecha", "importe", "cuenta"],
        "PASANTE": ["fecha", "importe", "obra", "contratista", "cuenta", "tipo_gasto"],
    }[tipo]
    if res.clasificacion == "personal":
        requeridos = [c for c in requeridos if c != "contratista"]
    faltantes = [c for c in COLUMNAS_MOVIMIENTOS if c in requeridos and campos[c] in (None, "")]

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
                       semilla: dict | None) -> tuple[Ficha, list[Pregunta]]:
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

    # ── 4. Etapa contra ETAPAS (§5.15) ─────────────────────────────────────────
    obra = m.obra(campos["obra"])
    etapas_obra = m.etapas_de(obra.nombre) if obra else []
    campos["etapa"] = None
    origen.pop("etapa", None)
    ya_pregunta_etapa = any(p.campo == "etapa" for p in preguntas)
    if obra and etapa:
        if not etapas_obra:
            advertencias.append(f"{obra.nombre} no tiene etapas cargadas en ETAPAS: se ignora la etapa {etapa}")
        elif etapa in etapas_obra:
            poner("etapa", etapa, origen_etapa)
        elif not ya_pregunta_etapa:
            advertencias.append(f"{obra.nombre} no tiene una etapa {etapa}")
            preguntas.append(Pregunta(campo="etapa", texto=f"¿Qué etapa de {obra.nombre}?", opciones=etapas_obra))
    elif obra and etapas_obra and not ya_pregunta_etapa:
        preguntas.append(Pregunta(campo="etapa", texto=f"¿Qué etapa de {obra.nombre}?", opciones=etapas_obra))
    elif not obra and etapa:
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

    requeridos = ["obra", "numero", "fecha", "saldo_a_cobrar"] + (["etapa"] if etapas_obra else [])
    faltantes = [c for c in CAMPOS_FICHA_CERTIFICADO if c in requeridos and campos[c] in (None, "")]
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
                    semilla: dict | None) -> tuple[Ficha, list[Pregunta]]:
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
    if co and cd and co.moneda != cd.moneda:
        advertencias.append(f"{co.nombre} está en {co.moneda} y {cd.nombre} en {cd.moneda}: un traspaso entre monedas "
                            f"no está definido en el contexto")
    moneda = campos["moneda"] or (co.moneda if co else cd.moneda if cd else "ARS")
    poner("moneda", moneda, origen.get("moneda", "inferido"))
    if moneda == "ARS":
        poner("tc", 1, "inferido")
        if campos["importe"] is not None:
            poner("importe_ars", campos["importe"], "inferido")
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
    requeridos = ["fecha", "importe", "cuenta_origen", "cuenta_destino"]
    faltantes = [c for c in requeridos if campos[c] in (None, "")]
    factor = 0.8 ** len(preguntas) * 0.7 ** len(conflictos)
    diag["resoluciones"].append([{"token": seg.texto, "categoria": "traspaso", "valor": seg.traspaso, "metodo": "frase"}])
    return Ficha(campos=campos, origen_campo=origen, faltantes=faltantes, conflictos=conflictos,
                 confianza=round(max(0.0, min(1.0, factor)), 2), regla="T: traspaso entre cuentas (§5.18)",
                 extras=extras), preguntas
