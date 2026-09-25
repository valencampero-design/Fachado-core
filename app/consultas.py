"""POST /consultar: las tres preguntas del arquitecto (handoff del 25/09).

- «¿Cuántos pagos se le hicieron a X por la obra Y?»
- «¿Cuánto va gastado en cada obra, de mano de obra y de materiales?»
- «¿El comitente pagó todas las certificaciones?»

Cada respuesta trae los números (`datos`) y un `texto` listo para WhatsApp. Solo lee.

**Lo personal se filtra por persona** (§5.13): quien no tiene `ve_personal` no ve el libro
personal ni las filas personales que hayan quedado en el del estudio. Las líneas del cierre
semanal sí: el estudio ve cuánto salió, no en qué (§5.14).
"""
import re
from datetime import date

from app import certificados, maestros, resolver
from app.filtros import es_cierre_semanal, sin_anulados
from app.libro import Libro
from app.maestros import Maestros, Usuario, normalizar, numero
from app.models import ConsultarIn, ConsultarOut, Pregunta
from app.saldos import como_dicts

TIPOS_PAGO = ("EGRESO", "PASANTE")
MAX_LINEAS = 15  # detalle en el texto de WhatsApp; el resto va en `datos`
CONSULTAS = {"pagos": "Pagos a un contratista", "gasto": "Gasto por obra", "certificaciones": "Certificaciones"}

# Quién puso la plata de un gasto. El comitente se muestra aparte: es costo de la obra aunque
# no sea plata del estudio (§5.8, §5.9).
QUIEN_PAGO = {"estudio": "del estudio", "caja_obra": "de la caja de obra", "comitente": "pagó el comitente"}


class ErrorConsulta(Exception):
    def __init__(self, status: int, detalle: str):
        super().__init__(detalle)
        self.status, self.detalle = status, detalle


def pesos(v: float) -> str:
    entero, dec = f"{v:,.2f}".split(".")
    entero = entero.replace(",", ".")
    return f"${entero}" if dec == "00" else f"${entero},{dec}"


def _dia(valor) -> str:
    try:
        f = date.fromisoformat(str(valor)[:10])
        return f"{f.day:02d}/{f.month:02d}/{f.year % 100:02d}"
    except ValueError:
        return str(valor or "s/f")


def inferir_consulta(texto: str) -> str | None:
    n = normalizar(texto)
    if re.search(r"certific|\bcobr", n):
        return "certificaciones"
    if re.search(r"gast|mano de obra|material", n):
        return "gasto"
    if re.search(r"\bpag", n):
        return "pagos"
    return None


def entidades(texto: str, m: Maestros) -> tuple[str | None, str | None, list[Pregunta]]:
    """Obra y contratista nombrados en una pregunta en castellano, sin «/»: se prueban ventanas
    de tres, dos y una palabra contra el diccionario. Solo coincidencias firmes (alias, exacto,
    una palabra que identifica a uno solo); nada difuso ni LLM: una consulta equivocada es peor
    que una repregunta."""
    obra = contratista = None
    preguntas: list[Pregunta] = []
    for h in resolver.escanear(texto, m)[1]:
        r = h.resolucion
        if r.categoria == "ambiguo":
            preguntas.append(Pregunta(campo="contratista", texto=f"¿«{r.token}» es…?", motivo="apodo_ambiguo",
                                      opciones=[o.split(": ", 1)[1] for o in r.opciones]))
        elif r.categoria == "obra" and obra is None:
            obra = r.valor
        elif r.categoria == "contratista" and contratista is None:
            contratista = r.valor
    return obra, contratista, preguntas


def _visibles(libro: Libro, libro_personal: Libro | None, usuario: Usuario) -> list[dict]:
    movs = []
    for mov in sin_anulados(como_dicts(libro.leer_movimientos())):
        if normalizar(mov.get("tipo_gasto")) == "personal" and not es_cierre_semanal(mov) and not usuario.ve_personal:
            continue
        movs.append({**mov, "libro": "estudio"})
    if usuario.ve_personal and libro_personal is not None:
        movs += [{**mov, "libro": "personal"} for mov in sin_anulados(como_dicts(libro_personal.leer_movimientos()))]
    return movs


def consultar(req: ConsultarIn, libro: Libro, libro_personal: Libro | None) -> ConsultarOut:
    m = maestros.cargar()
    usuario = m.usuario(req.telefono)
    if usuario is None:
        raise ErrorConsulta(403, "Ese teléfono no está en USUARIOS: no consulta el libro")

    consulta = req.consulta or inferir_consulta(req.texto)
    if consulta is None:
        return ConsultarOut(texto="¿Qué querés consultar?", preguntas=[Pregunta(
            campo="consulta", texto="¿Qué querés consultar?", opciones=list(CONSULTAS.values()))])

    obra_txt, contr_txt, preguntas = entidades(req.texto, m) if req.texto else (None, None, [])
    obra = m.obra(req.obra) if req.obra else (m.obra(obra_txt) if obra_txt else None)
    if req.obra and obra is None:
        raise ErrorConsulta(422, f"La obra «{req.obra}» no está en OBRAS")
    contratista = m.contratista(req.contratista) if req.contratista else (m.contratista(contr_txt) if contr_txt else None)
    if req.contratista and contratista is None:
        raise ErrorConsulta(422, f"«{req.contratista}» no está en CONTRATISTAS")

    if consulta == "pagos":
        if contratista is None:
            preguntas = preguntas or [Pregunta(campo="contratista", texto="¿Los pagos a quién?")]
            return ConsultarOut(consulta=consulta, texto=preguntas[0].texto, preguntas=preguntas)
        return pagos(_visibles(libro, libro_personal, usuario), contratista.nombre, obra.nombre if obra else None)
    if consulta == "gasto":
        return gasto(_visibles(libro, libro_personal, usuario), m, obra.nombre if obra else None)
    return certificaciones(libro, obra.nombre if obra else None)


# ─── Las tres consultas ────────────────────────────────────────────────────────

def pagos(movs: list[dict], contratista: str, obra: str | None) -> ConsultarOut:
    detalle = sorted(
        ({"id_mov": mov.get("id_mov"), "fecha": str(mov.get("fecha") or ""), "importe": numero(mov.get("importe")),
          "moneda": mov.get("moneda") or "ARS", "importe_ars": numero(mov.get("importe_ars") or mov.get("importe")),
          "obra": mov.get("obra") or "", "etapa": certificados.texto_etapa(mov.get("etapa")),
          "medio_pago": mov.get("medio_pago") or "", "cuenta": mov.get("cuenta") or "",
          "cargado_por": mov.get("cargado_por") or "", "libro": mov["libro"]}
         for mov in movs
         if mov.get("tipo") in TIPOS_PAGO and normalizar(mov.get("contratista")) == normalizar(contratista)
         and (obra is None or normalizar(mov.get("obra")) == normalizar(obra)) and not es_cierre_semanal(mov)),
        key=lambda d: d["fecha"])
    total = round(sum(d["importe_ars"] for d in detalle), 2)
    titulo = f"*Pagos a {contratista}{' · ' + obra if obra else ''}*"
    if not detalle:
        texto = f"{titulo}\nNo hay pagos cargados."
    else:
        lineas = [f"• {_dia(d['fecha'])} · {pesos(d['importe']) if d['moneda'] == 'ARS' else d['moneda'] + ' ' + pesos(d['importe'])[1:]}"
                  f"{' · ' + d['obra'] if not obra and d['obra'] else ''}"
                  f"{' · ' + d['medio_pago'] if d['medio_pago'] else ''} · {d['cargado_por'] or 'sin dato'}"
                  for d in detalle[-MAX_LINEAS:]]
        if len(detalle) > MAX_LINEAS:
            lineas.insert(0, f"(los últimos {MAX_LINEAS})")
        texto = "\n".join([titulo, f"{len(detalle)} pago{'s' if len(detalle) != 1 else ''}, total {pesos(total)}", *lineas])
    return ConsultarOut(consulta="pagos", texto=texto, datos={
        "contratista": contratista, "obra": obra, "cantidad": len(detalle), "total": total, "detalle": detalle})


def _quien_pago(mov: dict, m: Maestros) -> tuple[str, str | None]:
    """(estudio | caja_obra | comitente, advertencia)."""
    if mov.get("tipo") == "PASANTE":
        return "comitente", None  # §5.17: va a «Pagado por el comitente»
    cuenta = m.cuenta(mov.get("cuenta"), incluir_inactivas=True)
    if cuenta is None:
        return "estudio", f"{mov.get('id_mov')}: la cuenta «{mov.get('cuenta')}» no está en CUENTAS; se cuenta como del estudio"
    if cuenta.tipo == "externa":
        return "comitente", None
    if cuenta.tipo == "caja_obra":
        return "caja_obra", None
    return "estudio", None


def gasto(movs: list[dict], m: Maestros, obra: str | None) -> ConsultarOut:
    """Por obra y `rubro_1`. Sin filtro, solo las obras de verdad (de terceros y propias): ni
    los indirectos del estudio ni los inmuebles personales."""
    obras: dict[str, dict] = {}
    advertencias: list[str] = []
    for mov in movs:
        if mov.get("tipo") not in TIPOS_PAGO or not mov.get("obra") or es_cierre_semanal(mov):
            continue
        o = m.obra(mov.get("obra"))
        nombre = o.nombre if o else str(mov["obra"])
        if obra is not None:
            if normalizar(nombre) != normalizar(obra):
                continue
        elif o is None or o.tipo not in certificados.TIPOS_OBRA_CERTIFICABLE:
            continue
        quien, aviso = _quien_pago(mov, m)
        if aviso:
            advertencias.append(aviso)
        importe = numero(mov.get("importe_ars") or mov.get("importe"))
        datos_obra = obras.setdefault(nombre, {"obra": nombre, "total": 0.0, **{q: 0.0 for q in QUIEN_PAGO}, "por_rubro": {}})
        rubro = datos_obra["por_rubro"].setdefault(mov.get("rubro_1") or "Sin rubro", {"total": 0.0, **{q: 0.0 for q in QUIEN_PAGO}})
        for destino in (datos_obra, rubro):
            destino[quien] += importe
            destino["total"] += importe

    salida = sorted(obras.values(), key=lambda d: -d["total"])
    for d in salida:
        for bloque in (d, *d["por_rubro"].values()):
            for k in ("total", *QUIEN_PAGO):
                bloque[k] = round(bloque[k], 2)

    def partes(bloque: dict) -> str:
        abiertas = [f"{QUIEN_PAGO[q]} {pesos(bloque[q])}" for q in QUIEN_PAGO if bloque[q]]
        return f" ({' · '.join(abiertas)})" if len(abiertas) > 1 or (abiertas and not bloque["estudio"]) else ""

    lineas = [f"*Gasto por obra{' · ' + obra if obra else ''}*"]
    if not salida:
        lineas.append("No hay gastos cargados.")
    for d in salida:
        lineas.append(f"\n*{d['obra']}*: {pesos(d['total'])}{partes(d)}")
        for nombre, r in sorted(d["por_rubro"].items(), key=lambda x: -x[1]["total"]):
            lineas.append(f"• {nombre}: {pesos(r['total'])}{partes(r)}")
    return ConsultarOut(consulta="gasto", texto="\n".join(lineas), datos={"obra": obra, "obras": salida},
                        advertencias=sorted(set(advertencias)))


def certificaciones(libro: Libro, obra: str | None) -> ConsultarOut:
    """Por obra y etapa: certificado, cobrado y pendiente (§5.11). Los cobros que nombran un
    certificado que no está cargado se muestran aparte y no se restan."""
    advertencias: list[str] = []
    movs = como_dicts(libro.leer_movimientos())
    try:
        certs = como_dicts(libro.leer_certificados())
    except Exception as e:  # noqa: BLE001 — sin la hoja, todos los cobros quedan sin certificado
        certs = []
        advertencias.append(f"No se pudo leer CERTIFICADOS ({type(e).__name__}): ¿se corrió scripts/preparar_sheet.py?")
    estados, sin_cert, avisos = certificados.estados(certs, movs, obra)
    advertencias += avisos

    grupos: dict[tuple[str, str], dict] = {}
    for e in estados:
        g = grupos.setdefault((e.obra, e.etapa), {"obra": e.obra, "etapa": e.etapa, "certificado": 0.0, "cobrado": 0.0,
                                                  "pendiente": 0.0, "certificados": []})
        g["certificado"] += e.saldo_a_cobrar
        g["cobrado"] += e.cobrado
        g["pendiente"] += e.pendiente
        g["certificados"].append(e.model_dump())
    for g in grupos.values():
        for k in ("certificado", "cobrado", "pendiente"):
            g[k] = round(g[k], 2)
    sin_certificado = [{"id_mov": mov.get("id_mov"), "fecha": str(mov.get("fecha") or ""), "obra": mov.get("obra"),
                        "etapa": certificados.texto_etapa(mov.get("etapa")), "certificado": str(mov.get("certificado")),
                        "importe": numero(mov.get("importe_ars") or mov.get("importe"))} for mov in sin_cert]

    lineas = [f"*Certificaciones{' · ' + obra if obra else ''}*"]
    if not grupos:
        lineas.append("No hay certificados cargados.")
    for g in sorted(grupos.values(), key=lambda g: (g["obra"], g["etapa"])):
        lineas.append(f"\n*{g['obra']}{' etapa ' + g['etapa'] if g['etapa'] else ''}*")
        lineas.append(f"Certificado {pesos(g['certificado'])} · cobrado {pesos(g['cobrado'])} · "
                      f"*pendiente {pesos(g['pendiente'])}*")
        for c in g["certificados"]:
            if c["pendiente"]:
                lineas.append(f"• Cert. {c['numero']} ({_dia(c['fecha'])}): falta {pesos(c['pendiente'])}")
    if sin_certificado:
        total = round(sum(c["importe"] for c in sin_certificado), 2)
        lineas.append(f"\n{len(sin_certificado)} cobro{'s' if len(sin_certificado) != 1 else ''} por {pesos(total)} "
                      f"nombran un certificado que no está cargado.")
    total_pendiente = round(sum(g["pendiente"] for g in grupos.values()), 2)
    return ConsultarOut(consulta="certificaciones", texto="\n".join(lineas), advertencias=advertencias, datos={
        "obra": obra, "pendiente": total_pendiente, "grupos": sorted(grupos.values(), key=lambda g: (g["obra"], g["etapa"])),
        "cobros_sin_certificado": sin_certificado})
