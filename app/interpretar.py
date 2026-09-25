"""Orquesta: resolver (diccionario) → LLM para lo que falta → comprobante → cascada → ficha.

Función pura sobre los maestros: nunca escribe en Sheets ni en Drive.

Reparto de autoridad cuando hay adjunto:
  - el comprobante manda en importe, fecha, destinatario, CUIT y número de operación;
  - el texto manda en obra, ítem, rubro y descripción;
  - si texto y comprobante se contradicen en importe o fecha, no se elige: van los dos
    valores a `conflictos` y se pregunta.
"""
import logging
from datetime import date, timedelta, timezone

from app import clasificador, comprobante, llm, maestros, resolver
from app.config import Settings, settings
from app.maestros import Maestros, normalizar
from app.models import COLUMNAS_MOVIMIENTOS, Conflicto, Ficha, InterpretarIn, InterpretarOut, Pregunta
from app.resolver import Resolucion, Segmento

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


def _semilla(contexto: dict | None) -> dict | None:
    """De la ficha anterior se hereda lo que dijo el usuario o el comprobante; lo derivado
    (comitente, rubro inferido) se recalcula con lo nuevo."""
    if not contexto:
        return None
    campos = contexto.get("campos") or {}
    origen = contexto.get("origen_campo") or {}
    return {
        "campos": {k: v for k, v in campos.items()
                   if v not in (None, "") and origen.get(k) not in ("inferido", "maestro", "fecha_mensaje")},
        "clasificacion": contexto.get("clasificacion"),
        "extras": contexto.get("extras") or {},
    }


def interpretar(req: InterpretarIn) -> InterpretarOut:
    s = settings()
    m = maestros.cargar()
    diag: dict = {"llm_llamadas": 0, "llm_uso": [], "resoluciones": []}

    segmentos = resolver.parsear(req.texto, _fecha_local(req, s))
    for seg in segmentos:
        resolver.resolver_segmento(seg, m)

    comprobantes = [comprobante.leer(a) for a in req.adjuntos]
    diag["comprobantes"] = [c.dict() for c in comprobantes]
    diag["llm_llamadas"] += sum(1 for c in comprobantes if c.uso_llm)

    semilla = _semilla(req.contexto_previo)
    fichas: list[Ficha] = []
    preguntas: list[Pregunta] = []
    for i, seg in enumerate(segmentos):
        # Un comprobante por movimiento si coinciden en cantidad; si no, el primero aplica a todos
        # (el cobro de un certificado que sale el mismo día como pago).
        comp = comprobantes[i] if len(comprobantes) == len(segmentos) else (comprobantes[0] if comprobantes else None)
        ficha, pregs = _armar(seg, comp, req, m, s, diag, semilla if i == 0 else None)
        for p in pregs:
            p.ficha = i
        fichas.append(ficha)
        preguntas += pregs

    diag["uso_llm"] = diag["llm_llamadas"] > 0
    return InterpretarOut(fichas=fichas, preguntas=preguntas, diagnostico=diag)


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
        return c.nombre if c else None
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
    if comp is not None:
        extras["comprobante"] = {k: v for k, v in comp.dict().items() if v not in (None, "", {}) and k != "fuente"}
        for campo, valor_comp, fmt in (("importe", comp.importe, _fmt_importe), ("fecha", comp.fecha, str)):
            if valor_comp in (None, ""):
                continue
            valor_texto = campos[campo]
            if valor_texto is not None and valor_texto != valor_comp:
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

    # ── 3. Lo heredado de la ficha anterior (corrección) ───────────────────────
    marcador_personal = bool(seg.de("personal"))
    if semilla:
        for campo, valor in semilla["campos"].items():
            if campo in campos and campos[campo] in (None, ""):
                poner(campo, valor, "contexto_previo")
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
    es_cert = bool(extras.get("certificado"))
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
    if tipo == "PASANTE":
        poner("informal", "sí", "texto")
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

    if campos["importe"] is None and not tiene_adjunto and not any(c.campo == "importe" for c in conflictos):
        preguntas.append(Pregunta(campo="importe", texto="¿Cuál es el importe?"))

    # Tokens que no se pudieron ubicar y no generaron pregunta: van a la descripción.
    if sin_resolver:
        poner("descripcion", " · ".join(filter(None, [campos["descripcion"], *sin_resolver])), "texto")

    requeridos = {
        "EGRESO": ["fecha", "importe", "contratista", "rubro_1", "rubro_2", "medio_pago", "cuenta", "tipo_gasto"]
                  + ([] if res.clasificacion == "personal" else ["obra"]),
        "INGRESO": ["fecha", "importe", "obra", "medio_pago", "cuenta", "tipo_gasto"],
        "TRASPASO": ["fecha", "importe", "cuenta"],
        # Sin cuenta: qué cuenta lleva un pasante no está definido en el contexto (§5.17).
        "PASANTE": ["fecha", "importe", "obra", "contratista", "tipo_gasto"],
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
