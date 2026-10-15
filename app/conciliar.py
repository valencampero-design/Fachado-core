"""Conciliación con el banco (CONTEXTO-FACHADO.md §5.20, handoff del 15/10).

El extracto deja de ser una fuente de errores y pasa a ser el detector de lo que no se cargó:

1. **Importar** las líneas a BANCO_RAW, idempotente por `hash_id`: un extracto que se superpone
   con el anterior no duplica nada. Antes de `CONCILIACION_DESDE` (1/11), `ANTERIOR`.
2. **Conciliar** contra los dos libros (`filtros.para_conciliacion`: lo personal fila por fila,
   nunca la línea semanal, sin pares anulados, solo cuentas que concilian):
   fuerte (mismo importe y ref de operación o CUIT) o probable (mismo importe, ±3 días, uno
   solo) → `CONCILIADO`; varios candidatos → `A_REVISAR`; ninguno → `SIN_CARGAR`.
   Conciliar escribe `id_banco` y `estado_conc` en el movimiento, por columna: **es la única
   escritura sobre una fila ya escrita** (§5.20).
3. Lo que falta: gastos bancarios → lote `gastos_bancarios`; Mercado Libre / Mercado Pago →
   lote `meli_personal`; el resto → una ficha por línea, como si la línea fuera un comprobante.
4. **Resumen**: saldo según el libro contra saldo según el banco, por cuenta y total.

Los contratos (`/conciliar/extracto`, `/conciliar/pendientes`, `/conciliar/lote`) están en §3
del handoff del 15/10. Ningún test escribe en el Sheet real.
"""
import logging
import re
from datetime import date, datetime

from app import maestros
from app.comprobante import DatosComprobante
from app.confirmar import ErrorConfirmar, confirmar
from app.config import settings
from app.extracto import ExtractoNoReconocido, LineaBanco, leer_extracto
from app.filtros import para_conciliacion
from app.libro import Libro
from app.maestros import Maestros, Usuario, normalizar, numero, solo_digitos
from app.models import COLUMNAS_BANCO, Adjunto, ConfirmarIn, FichaConfirmada, InterpretarIn
from app.saldos import en_moneda_de_la_cuenta

logger = logging.getLogger(__name__)

ANTERIOR, CONCILIADO, A_REVISAR, SIN_CARGAR, IGNORADO = "ANTERIOR", "CONCILIADO", "A_REVISAR", "SIN_CARGAR", "IGNORADO"
ABIERTOS = (A_REVISAR, SIN_CARGAR)
DIAS_PROBABLE = 3      # «mismo importe, fecha ±3 días» (handoff del 15/10)
DIAS_FUERTE = 10       # con ref o CUIT alcanza una ventana más ancha: el banco acredita tarde
DIAS_SIN_BANCO = 7     # §5.20: lo del libro que no aparece en el banco después de una semana

# Gastos bancarios (§5.20: un solo lote por extracto, estructura del estudio).
RE_GASTO_BANCARIO = re.compile(
    r"comisi|impuesto|imp\.?\s*db|db/cr|intereses|cruce de fondos|iva percep|percepci|retenci|sellos|"
    r"mantenimiento|cargo\b|seguro de vida|com\.", re.I)
RE_MELI = re.compile(r"mercado\s*libre|mercadolibre|mercado\s*pago|mercadopago|merpago", re.I)
RUBRO_BANCARIO = ("Impuestos y tasas", "Bancarios")
# Supuesto (handoff del 15/10, «decisión de negocio que no está: la más conservadora»): lo de
# Mercado Libre que no cruza es «gasto personal sin clasificar» (§5.6); el rubro personal más
# genérico que hay en RUBROS es Consumos.
RUBRO_MELI = ("Personal", "Consumos")


class ErrorConciliar(Exception):
    def __init__(self, status: int, campo: str, detalle: str):
        super().__init__(detalle)
        self.status, self.campo, self.detalle = status, campo, detalle


# ─── Lectura de los libros ─────────────────────────────────────────────────────

def _movs_con_fila(libro: Libro | None, nombre: str) -> list[dict]:
    """Los movimientos con su número de fila real en el Sheet (las filas vacías cuentan)."""
    if libro is None:
        return []
    filas = libro.leer_movimientos()
    if not filas:
        return []
    encabezado = [str(c) for c in filas[0]]
    salida = []
    for n, f in enumerate(filas[1:], start=2):
        if any(str(x).strip() for x in f):
            mov = {c: (f[i] if i < len(f) else "") for i, c in enumerate(encabezado)}
            mov["_fila"], mov["_libro"] = n, nombre
            salida.append(mov)
    return salida


def _banco_con_fila(libro: Libro) -> tuple[list[str], list[dict]]:
    filas = libro.leer_banco() or [list(COLUMNAS_BANCO)]
    encabezado = [str(c) for c in filas[0]]
    salida = []
    for n, f in enumerate(filas[1:], start=2):
        if not any(str(x).strip() for x in f):
            continue
        d = {c: (f[i] if i < len(f) else "") for i, c in enumerate(encabezado)}
        if not re.fullmatch(r"[0-9a-f]{64}", str(d.get("hash_id") or "")):
            continue  # la fila de ejemplo del Master («(se calcula al importar)»)
        d["_fila"] = n
        salida.append(d)
    return encabezado, salida


def _cuenta_motor(moneda: str, m: Maestros):
    """§5.7: una sola cuenta bancaria con tramos en pesos y en dólares; las cuentas del banco
    (CA, CC, la de Gabriel) son una división operativa. Pesos → Banco; dólares → Banco USD."""
    return next((c for c in m.cuentas if c.activa and c.tipo == "banco" and c.moneda == moneda), None)


def _conciliables(movs: list[dict], m: Maestros, desde: str) -> list[dict]:
    salida = []
    for mov in para_conciliacion(movs):
        cuenta = m.cuenta(mov.get("cuenta"), incluir_inactivas=True)
        if cuenta is None or not cuenta.concilia_contra_banco or str(mov.get("fecha") or "")[:10] < desde:
            continue
        if str(mov.get("id_banco") or "").strip() or normalizar(mov.get("estado_conc")) == "conciliado":
            continue
        salida.append(mov)
    return salida


# ─── Matcheo ───────────────────────────────────────────────────────────────────

def _dias(a: str, b: str) -> int:
    try:
        return abs((date.fromisoformat(str(a)[:10]) - date.fromisoformat(str(b)[:10])).days)
    except ValueError:
        return 10_000


def _importe_mov(mov: dict, moneda: str) -> float | None:
    """Con signo, en la moneda de la línea: un EGRESO sale (−), un INGRESO entra (+), un
    TRASPASO trae el signo en el importe."""
    valor = en_moneda_de_la_cuenta(mov, moneda)
    if valor is None:
        return None
    if mov.get("tipo") == "EGRESO":
        return -abs(valor)
    if mov.get("tipo") == "INGRESO":
        return abs(valor)
    if mov.get("tipo") == "TRASPASO":
        return valor
    return None


def _cuits_del_mov(mov: dict, m: Maestros) -> set[str]:
    cuits = set()
    c = m.contratista(mov.get("contratista"))
    if c:
        cuits |= {solo_digitos(x) for x in c.cuits if solo_digitos(x)}
    o = m.obra(mov.get("obra"))
    if o and o.cuit_comitente:
        cuits.add(solo_digitos(o.cuit_comitente))
    cuits |= set(re.findall(r"(?<!\d)\d{11}(?!\d)", f"{mov.get('ref_comprobante') or ''} {mov.get('descripcion') or ''}"))
    return cuits


def _candidatos(linea: dict, movs: list[dict], m: Maestros, usados: set) -> tuple[list[dict], list[dict]]:
    """(fuertes, probables) para una línea del banco."""
    importe, moneda = numero(linea.get("credito")) - numero(linea.get("debito")), str(linea.get("moneda") or "ARS")
    fuertes, probables = [], []
    for mov in movs:
        clave = (mov["_libro"], mov["_fila"])
        if clave in usados:
            continue
        cuenta = m.cuenta(mov.get("cuenta"), incluir_inactivas=True)
        if cuenta is None or cuenta.moneda != moneda:
            continue
        valor = _importe_mov(mov, moneda)
        if valor is None or abs(valor - importe) > 0.01:
            continue
        dias = _dias(linea.get("fecha"), mov.get("fecha"))
        ref = str(linea.get("ref") or "")
        texto_mov = f"{mov.get('ref_comprobante') or ''} {mov.get('descripcion') or ''}"
        por_ref = bool(ref) and ref in texto_mov
        por_cuit = bool(linea.get("cuit")) and solo_digitos(linea.get("cuit")) in _cuits_del_mov(mov, m)
        if (por_ref or por_cuit) and dias <= DIAS_FUERTE:
            fuertes.append(mov)
        elif dias <= DIAS_PROBABLE:
            probables.append(mov)
    return fuertes, probables


def _decidir(linea: dict, movs: list[dict], m: Maestros, usados: set) -> tuple[str, list[dict]]:
    fuertes, probables = _candidatos(linea, movs, m, usados)
    if len(fuertes) == 1:
        return CONCILIADO, fuertes
    if len(fuertes) > 1:
        return A_REVISAR, fuertes
    if len(probables) == 1:
        return CONCILIADO, probables
    if len(probables) > 1:
        return A_REVISAR, probables
    return SIN_CARGAR, []


def lote_de(linea: dict) -> str | None:
    """Gastos bancarios y Mercado Libre van en lote. Solo en pesos: en dólares hace falta el
    tipo de cambio, y eso va de a uno como ficha (supuesto conservador, anotado en el handoff)."""
    if str(linea.get("moneda") or "ARS") != "ARS":
        return None
    desc = str(linea.get("descripcion") or "")
    if RE_GASTO_BANCARIO.search(desc):
        return "gastos_bancarios"
    if numero(linea.get("debito")) > 0 and RE_MELI.search(desc):
        return "meli_personal"
    return None


# ─── Texto ─────────────────────────────────────────────────────────────────────

def _dinero(v: float, moneda: str = "ARS") -> str:
    entero, dec = f"{abs(v):,.2f}".split(".")
    entero = entero.replace(",", ".")
    signo = "US$" if moneda == "USD" else "$"
    return f"{signo} {entero}" if dec == "00" else f"{signo} {entero},{dec}"


def _dia(fecha: str) -> str:
    try:
        f = date.fromisoformat(str(fecha)[:10])
        return f"{f.day:02d}/{f.month:02d}"
    except ValueError:
        return str(fecha)


def _quien(linea: dict) -> str:
    nombre = str(linea.get("nombre") or "").strip()
    return nombre.title() if nombre else f"«{str(linea.get('descripcion') or '').strip()}»"


def texto_pendiente(linea: dict) -> str:
    importe = numero(linea.get("credito")) - numero(linea.get("debito"))
    moneda = str(linea.get("moneda") or "ARS")
    if importe < 0:
        return f"Vi un pago de {_dinero(importe, moneda)} a {_quien(linea)} el {_dia(linea.get('fecha'))} que no tengo cargado."
    return f"Vi un ingreso de {_dinero(importe, moneda)} de {_quien(linea)} el {_dia(linea.get('fecha'))} que no tengo cargado."


def texto_ambigua(linea: dict, candidatos: list[str]) -> str:
    importe = numero(linea.get("credito")) - numero(linea.get("debito"))
    que = "pago" if importe < 0 else "ingreso"
    lista = " o ".join([", ".join(candidatos[:-1]), candidatos[-1]] if len(candidatos) > 1 else candidatos)
    return (f"Este {que} de {_dinero(importe, str(linea.get('moneda') or 'ARS'))} del {_dia(linea.get('fecha'))} "
            f"puede ser {lista}. ¿Cuál es?")


def texto_lote(tipo: str, lineas: list[dict]) -> str:
    total = sum(numero(x.get("debito")) - numero(x.get("credito")) for x in lineas)
    n = len(lineas)
    if tipo == "gastos_bancarios":
        return f"{n} gasto{'s' if n != 1 else ''} bancario{'s' if n != 1 else ''} por {_dinero(total)}"
    return (f"{n} compra{'s' if n != 1 else ''} de Mercado Libre / Mercado Pago sin comprobante por {_dinero(total)} "
            f"(gasto personal sin clasificar)")


# ─── La ficha de una línea sin cargar ──────────────────────────────────────────

def ficha_de_linea(linea: dict, telefono: str, libros: dict) -> dict:
    """La línea del banco hace de comprobante (§5.20): importe, fecha, cuenta Banco y el
    contratista por CUIT o nombre con el resolver, con las preguntas de siempre."""
    from app.interpretar import interpretar
    importe = numero(linea.get("credito")) - numero(linea.get("debito"))

    def lector(_adj):
        d = DatosComprobante(url="", nombre_archivo="")
        d.completar({"importe": abs(importe), "fecha": str(linea.get("fecha"))[:10], "moneda": linea.get("moneda") or "ARS",
                     "cuit": linea.get("cuit") or None, "razon_social": linea.get("nombre") or None,
                     "medio_pago": "Transferencia", "tipo_comprobante": "Línea del extracto",
                     "id_operacion": linea.get("ref") or None}, "extracto")
        return d
    req = InterpretarIn(texto="Ingreso" if importe > 0 else "", telefono=telefono,
                        fecha_mensaje=f"{str(linea.get('fecha'))[:10]}T15:00:00Z",
                        adjuntos=[Adjunto(url=f"banco:{linea['hash_id']}", nombre="extracto")])
    salida = interpretar(req, libros=libros, lector=lector)
    for ficha in salida.fichas:
        ficha.extras["id_banco"] = linea["hash_id"]
        ficha.campos["comprobante_url"] = None  # no hay archivo: la línea es el comprobante
        if not ficha.campos.get("descripcion"):
            ficha.campos["descripcion"] = f"Extracto: {linea.get('descripcion')}"
    return salida.model_dump()


# ─── Resumen ───────────────────────────────────────────────────────────────────

def _saldo_banco(banco: list[dict]) -> dict[str, tuple[float, str, str]]:
    """{cuenta_banco: (saldo, fecha, moneda)} con la última línea de cada cuenta: la de fecha
    más nueva y, el mismo día, la del extracto más reciente con menor orden (el banco lista del
    más nuevo al más viejo)."""
    salida: dict[str, tuple] = {}
    for x in banco:
        if x.get("saldo") in ("", None):
            continue
        clave = (str(x.get("fecha"))[:10], str(x.get("importado_ts") or ""), -int(numero(x.get("orden"))))
        actual = salida.get(x["cuenta_banco"])
        if actual is None or clave > actual[0]:
            salida[x["cuenta_banco"]] = (clave, numero(x.get("saldo")), str(x.get("fecha"))[:10], x.get("moneda") or "ARS")
    return {k: v[1:] for k, v in salida.items()}


def _saldo_libro(cuenta, movs: list[dict]) -> float:
    """CUENTAS.saldo_apertura + los movimientos desde fecha_apertura, en la moneda de la cuenta.
    Los dos libros: lo personal también sale del banco (§5.14), sin la línea semanal."""
    total = cuenta.saldo_apertura
    for mov in para_conciliacion(movs):
        if normalizar(mov.get("cuenta")) != normalizar(cuenta.nombre):
            continue
        if cuenta.fecha_apertura and str(mov.get("fecha") or "")[:10] < cuenta.fecha_apertura:
            continue
        valor = _importe_mov(mov, cuenta.moneda)
        total += valor or 0.0
    return round(total, 2)


def resumen(banco: list[dict], movs: list[dict], m: Maestros) -> dict:
    """Saldo según el libro contra saldo según el banco, por cuenta del motor (Banco, Banco
    USD) y total en pesos; las cuentas del banco detalladas; conteos por estado."""
    saldos = _saldo_banco(banco)
    por_cuenta = []
    for moneda in ("ARS", "USD"):
        cuenta = _cuenta_motor(moneda, m)
        del_banco = {k: v for k, v in saldos.items() if v[2] == moneda}
        if cuenta is None or (not del_banco and moneda != "ARS"):
            continue
        libro_ = _saldo_libro(cuenta, movs)
        banco_ = round(sum(v[0] for v in del_banco.values()), 2)
        por_cuenta.append({"cuenta": cuenta.nombre, "moneda": moneda, "saldo_libro": libro_, "saldo_banco": banco_,
                           "diferencia": round(banco_ - libro_, 2), "fecha_apertura": cuenta.fecha_apertura,
                           "cuentas_banco": [{"cuenta_banco": k, "saldo": v[0], "al": v[1]} for k, v in sorted(del_banco.items())]})
    ars = next((c for c in por_cuenta if c["moneda"] == "ARS"), {"saldo_libro": 0.0, "saldo_banco": 0.0, "diferencia": 0.0})
    conteos: dict[str, int] = {}
    for x in banco:
        conteos[x.get("estado") or ""] = conteos.get(x.get("estado") or "", 0) + 1
    return {"saldo_libro": ars["saldo_libro"], "saldo_banco": ars["saldo_banco"], "diferencia": ars["diferencia"],
            "moneda": "ARS", "por_cuenta": por_cuenta, "conteos": conteos}


def _sin_banco(movs: list[dict], banco: list[dict], m: Maestros, desde: str) -> list[dict]:
    """§5.20: lo del libro que no apareció en el banco después de una semana (solo dentro de
    lo que el extracto cubre). Se avisa en el resumen, no se pregunta uno por uno."""
    hasta_por_moneda: dict[str, str] = {}
    for x in banco:
        hasta_por_moneda[x.get("moneda") or "ARS"] = max(hasta_por_moneda.get(x.get("moneda") or "ARS", ""),
                                                        str(x.get("fecha"))[:10])
    salida = []
    for mov in _conciliables(movs, m, desde):
        cuenta = m.cuenta(mov.get("cuenta"), incluir_inactivas=True)
        hasta = hasta_por_moneda.get(cuenta.moneda)
        if hasta and _dias(mov.get("fecha"), hasta) >= DIAS_SIN_BANCO and str(mov.get("fecha"))[:10] <= hasta:
            salida.append(mov)
    return salida


# ─── El circuito ───────────────────────────────────────────────────────────────

def _usuario(m: Maestros, telefono: str) -> Usuario:
    u = m.usuario(telefono)
    if u is None:
        raise ErrorConciliar(403, "telefono", "Ese teléfono no está en USUARIOS")
    return u


def _libros(libro: Libro, libro_personal: Libro | None, usuario: Usuario) -> dict:
    # Lo personal solo con ve_personal (§5.13); sin el libro personal, solo el estudio.
    return {"estudio": libro, "personal": libro_personal if usuario.ve_personal else None}


class _LeidoUnaVez:
    """Un libro que lee MOVIMIENTOS una sola vez: armar N fichas pendientes no puede leer el
    Sheet 2 × N veces (cuota de la API de Sheets). El resto se delega al libro."""

    def __init__(self, libro: Libro):
        self._libro, self._filas = libro, None

    def leer_movimientos(self):
        if self._filas is None:
            self._filas = self._libro.leer_movimientos()
        return [list(f) for f in self._filas]

    def __getattr__(self, nombre):
        return getattr(self._libro, nombre)


def _fila_banco(linea: LineaBanco, estado: str, id_mov: str, candidatos: list[str], lote: str | None, ts: str) -> dict:
    valores = {"hash_id": linea.hash_id, "fecha": linea.fecha, "descripcion": linea.descripcion,
               "debito": linea.debito or "", "credito": linea.credito or "",
               "saldo": "" if linea.saldo is None else linea.saldo, "estado": estado, "id_mov": id_mov,
               "cuenta_banco": linea.cuenta_banco, "moneda": linea.moneda, "cuit": linea.cuit or "",
               "nombre": linea.nombre or "", "ref": linea.ref or "", "candidatos": ", ".join(candidatos),
               "lote": lote or "", "orden": linea.orden, "importado_ts": ts}
    return valores



def procesar_extracto(contenido: bytes, telefono: str, libro: Libro, libro_personal: Libro | None) -> dict:
    """POST /conciliar/extracto: importa, concilia y devuelve el resumen y lo pendiente."""
    m = maestros.cargar()
    usuario = _usuario(m, telefono)
    try:
        lineas = leer_extracto(contenido)
    except ExtractoNoReconocido as e:
        raise ErrorConciliar(422, "adjunto", f"No es un extracto del banco que conozca: {e}") from e
    desde = settings().conciliacion_desde
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    libros = _libros(libro, libro_personal, usuario)
    movs = _movs_con_fila(libros["estudio"], "estudio") + _movs_con_fila(libros["personal"], "personal")
    encabezado, banco = _banco_con_fila(libro)
    if [c for c in COLUMNAS_BANCO if c not in encabezado]:
        raise ErrorConciliar(500, "BANCO_RAW", "A BANCO_RAW le faltan columnas: correr scripts/preparar_sheet.py")
    ya = {x["hash_id"] for x in banco}

    conciliables = _conciliables(movs, m, desde)
    usados: set = set()
    nuevas_filas: list[dict] = []
    marcas: list[tuple[dict, str]] = []  # (movimiento, hash_id) a marcar CONCILIADO
    repetidas = anteriores = 0
    vistos: set = set()
    for linea in lineas:
        if linea.hash_id in ya or linea.hash_id in vistos:
            repetidas += 1
            continue
        vistos.add(linea.hash_id)
        if linea.fecha < desde:
            anteriores += 1
            nuevas_filas.append(_fila_banco(linea, ANTERIOR, "", [], None, ts))
            continue
        d = linea.dict()
        estado, cands = _decidir(d, conciliables, m, usados)
        id_mov, lista = "", [str(c.get("id_mov")) for c in cands]
        if estado == CONCILIADO:
            usados.add((cands[0]["_libro"], cands[0]["_fila"]))
            id_mov, lista = str(cands[0].get("id_mov")), []
            marcas.append((cands[0], linea.hash_id))
        lote = lote_de(d) if estado == SIN_CARGAR else None
        nuevas_filas.append(_fila_banco(linea, estado, id_mov, lista, lote, ts))

    # Las que quedaron abiertas de extractos anteriores pueden cruzar con lo cargado después.
    cambios_banco: list[tuple[int, dict]] = []
    for x in banco:
        if x.get("estado") not in ABIERTOS or x.get("lote"):
            continue
        estado, cands = _decidir(x, conciliables, m, usados)
        if estado == CONCILIADO:
            usados.add((cands[0]["_libro"], cands[0]["_fila"]))
            cambios_banco.append((x["_fila"], {"estado": CONCILIADO, "id_mov": str(cands[0].get("id_mov")), "candidatos": ""}))
            marcas.append((cands[0], x["hash_id"]))

    filas = [[f.get(c, "") for c in encabezado] for f in nuevas_filas]
    libro.agregar_banco(filas)
    if cambios_banco:
        libro.actualizar_banco(cambios_banco)
    for mov, hash_id in marcas:
        libros[mov["_libro"]].marcar_conciliado(mov["_fila"], {"id_banco": hash_id, "estado_conc": CONCILIADO})

    salida = pendientes(telefono, libro, libro_personal, _m=m)
    conteo = {CONCILIADO: 0, A_REVISAR: 0, SIN_CARGAR: 0}
    for f in nuevas_filas:
        if f["estado"] in conteo:
            conteo[f["estado"]] += 1
    conteo[CONCILIADO] += len(cambios_banco)
    salida.update({"importadas": len(nuevas_filas), "repetidas": repetidas, "anteriores": anteriores,
                   "conciliadas": conteo[CONCILIADO], "a_revisar": conteo[A_REVISAR], "sin_cargar": conteo[SIN_CARGAR]})
    salida["texto"] = _texto_resumen(salida)
    return salida


def pendientes(telefono: str, libro: Libro, libro_personal: Libro | None, _m: Maestros | None = None) -> dict:
    """GET /conciliar/pendientes: la misma forma que /conciliar/extracto, solo lo que sigue
    abierto (los conteos de importación en cero)."""
    m = _m or maestros.cargar()
    usuario = _usuario(m, telefono)
    libros = {k: (_LeidoUnaVez(v) if v is not None else None) for k, v in _libros(libro, libro_personal, usuario).items()}
    movs = _movs_con_fila(libros["estudio"], "estudio") + _movs_con_fila(libros["personal"], "personal")
    _, banco = _banco_con_fila(libro)
    desde = settings().conciliacion_desde

    lotes: dict[str, list[dict]] = {}
    ambiguas, pendientes_ = [], []
    for x in sorted(banco, key=lambda x: (str(x.get("fecha")), -int(numero(x.get("orden"))))):
        if x.get("estado") == A_REVISAR:
            cands = [c.strip() for c in str(x.get("candidatos") or "").split(",") if c.strip()]
            ambiguas.append({"hash_id": x["hash_id"], "texto": texto_ambigua(x, cands), "candidatos": cands})
        elif x.get("estado") == SIN_CARGAR and x.get("lote"):
            lotes.setdefault(x["lote"], []).append(x)
        elif x.get("estado") == SIN_CARGAR:
            pendientes_.append({"hash_id": x["hash_id"], "texto": texto_pendiente(x),
                                "interpretacion": ficha_de_linea(x, telefono, libros)})
    sin_banco = _sin_banco(movs, banco, m, desde)
    salida = {
        "importadas": 0, "repetidas": 0, "anteriores": 0, "conciliadas": 0,
        "a_revisar": len(ambiguas), "sin_cargar": len(pendientes_) + sum(len(v) for v in lotes.values()),
        "sin_banco": len(sin_banco),
        "lotes": [{"tipo": tipo, "cantidad": len(xs), "total": round(sum(numero(x.get("debito")) - numero(x.get("credito"))
                                                                        for x in xs), 2),
                   "hash_ids": [x["hash_id"] for x in xs], "texto": texto_lote(tipo, xs),
                   # para el botón «Ver detalle» del gateway: una línea corta por movimiento
                   "detalle": [f"{_dia(x.get('fecha'))} · "
                               f"{'−' if numero(x.get('debito')) else '+'}{_dinero(numero(x.get('debito')) or numero(x.get('credito')))}"
                               f" · {str(x.get('descripcion') or '').strip()}" for x in xs]}
                  for tipo, xs in sorted(lotes.items())],
        "ambiguas": ambiguas,
        "pendientes": pendientes_,
        "resumen": resumen(banco, movs, m),
        "sin_banco_detalle": [str(mov.get("id_mov")) for mov in sin_banco],
    }
    salida["texto"] = _texto_resumen(salida)
    return salida


def _texto_resumen(s: dict) -> str:
    r = s["resumen"]
    partes = []
    if s.get("importadas") or s.get("repetidas") or s.get("anteriores"):
        partes.append(f"Extracto importado: {s['importadas']} línea{'s' if s['importadas'] != 1 else ''} nuevas"
                      + (f", {s['repetidas']} ya estaban" if s.get("repetidas") else "")
                      + (f", {s['anteriores']} anteriores al {_dia(settings().conciliacion_desde)} (no se concilian)"
                         if s.get("anteriores") else "") + ".")
    if s.get("conciliadas"):
        partes.append(f"{s['conciliadas']} conciliada{'s' if s['conciliadas'] != 1 else ''} sola{'s' if s['conciliadas'] != 1 else ''}.")
    abiertas = s.get("a_revisar", 0) + len(s.get("pendientes", [])) + sum(x["cantidad"] for x in s.get("lotes", []))
    if abiertas:
        partes.append(f"Quedan {abiertas} para revisar: {len(s.get('pendientes', []))} sin cargar, "
                      f"{s.get('a_revisar', 0)} con más de un candidato"
                      + (f" y {', '.join(x['texto'] for x in s['lotes'])}" if s.get("lotes") else "") + ".")
    if s.get("sin_banco"):
        partes.append(f"{s['sin_banco']} movimiento{'s' if s['sin_banco'] != 1 else ''} del libro no aparece"
                      f"{'n' if s['sin_banco'] != 1 else ''} en el banco hace más de una semana.")
    for c in r["por_cuenta"]:
        partes.append(f"{c['cuenta']}: libro {_dinero(c['saldo_libro'], c['moneda'])} · banco "
                      f"{_dinero(c['saldo_banco'], c['moneda'])} · diferencia {_dinero(c['diferencia'], c['moneda'])}"
                      + (" (sin saldo de apertura cargado)" if not c.get("fecha_apertura") else ""))
    return "\n".join(partes) or "No hay nada pendiente del banco."


# ─── Lotes y asignaciones ──────────────────────────────────────────────────────

def _obra_estructura(m: Maestros):
    return next((o for o in m.obras if o.tipo == "estructura" and o.estado != "cerrada"), None)


def _ficha_lote(tipo: str, x: dict, m: Maestros) -> FichaConfirmada:
    importe = numero(x.get("credito")) - numero(x.get("debito"))
    base = {"fecha": str(x.get("fecha"))[:10], "tipo": "EGRESO" if importe < 0 else "INGRESO", "importe": abs(importe),
            "moneda": "ARS", "tc": 1, "cuenta": "Banco", "origen": "BANCO", "item": x.get("nombre") or x.get("descripcion"),
            "descripcion": f"Extracto: {x.get('descripcion')}", "tipo_comprobante": "Línea del extracto",
            "comprobante_url": None, "id_mov": None}
    if tipo == "gastos_bancarios":
        obra = _obra_estructura(m)
        base.update({"obra": obra.nombre if obra else None, "tipo_gasto": "estructura", "rubro_1": RUBRO_BANCARIO[0],
                     "rubro_2": RUBRO_BANCARIO[1], "medio_pago": "Débito automático" if importe < 0 else "Otro"})
    else:
        base.update({"obra": None, "tipo_gasto": "personal", "rubro_1": RUBRO_MELI[0], "rubro_2": RUBRO_MELI[1],
                     "medio_pago": "Transferencia", "item": "Mercado Libre"})
    return FichaConfirmada(campos=base, extras={"id_banco": x["hash_id"]})


async def lote(telefono: str, tipo: str, hash_ids: list[str], id_mov: str | None, libro: Libro,
               libro_personal: Libro | None, archivador) -> dict:
    """POST /conciliar/lote: confirma un lote (gastos bancarios o MeLi personal), asigna una
    ambigua a uno de sus candidatos o ignora líneas."""
    m = maestros.cargar()
    usuario = _usuario(m, telefono)
    _, banco = _banco_con_fila(libro)
    por_hash = {x["hash_id"]: x for x in banco}
    faltan = [h for h in hash_ids if h not in por_hash]
    if faltan:
        raise ErrorConciliar(404, "hash_ids", f"Líneas que no están en BANCO_RAW: {faltan[:3]}")
    escritos, conciliadas, avisos = [], [], []

    if tipo in ("gastos_bancarios", "meli_personal"):
        for h in hash_ids:
            x = por_hash[h]
            if x.get("estado") == CONCILIADO:
                conciliadas.append(h)
                continue
            req = ConfirmarIn(msg_id=f"banco:{h}", telefono=telefono, ficha=_ficha_lote(tipo, x, m))
            try:
                out = await confirmar(req, libro, archivador, libro_personal)
                escritos.append(out.id_mov)
                conciliadas.append(h)
            except ErrorConfirmar as e:
                avisos.append(f"{_dia(x.get('fecha'))} {_dinero(numero(x.get('debito')) or numero(x.get('credito')))}: "
                              f"no se cargó ({e.campo}: {e.detalle})")
        n = len(escritos)
        texto = (f"Cargué {n} gasto{'s' if n != 1 else ''} bancario{'s' if n != 1 else ''}." if tipo == "gastos_bancarios"
                 else f"Cargué {n} compra{'s' if n != 1 else ''} de Mercado Libre como gasto personal sin clasificar.")
    elif tipo == "asignar":
        if len(hash_ids) != 1 or not id_mov:
            raise ErrorConciliar(422, "id_mov", "«asignar» es una línea y el id_mov elegido")
        x = por_hash[hash_ids[0]]
        nombre = "personal" if id_mov.upper().startswith("P-") else "estudio"
        lib = libro_personal if nombre == "personal" and usuario.ve_personal else (libro if nombre == "estudio" else None)
        if lib is None:
            raise ErrorConciliar(403, "id_mov", "Ese movimiento es del libro personal")
        mov = next((mv for mv in _movs_con_fila(lib, nombre) if str(mv.get("id_mov")) == id_mov.upper()), None)
        if mov is None:
            raise ErrorConciliar(404, "id_mov", f"No está {id_mov} en el libro")
        lib.marcar_conciliado(mov["_fila"], {"id_banco": x["hash_id"], "estado_conc": CONCILIADO})
        libro.actualizar_banco([(x["_fila"], {"estado": CONCILIADO, "id_mov": id_mov.upper(), "candidatos": ""})])
        conciliadas.append(x["hash_id"])
        texto = f"Listo: esa línea del banco es {id_mov.upper()}."
    elif tipo == "ignorar":
        libro.actualizar_banco([(por_hash[h]["_fila"], {"estado": IGNORADO}) for h in hash_ids])
        texto = f"Dejé {len(hash_ids)} línea{'s' if len(hash_ids) != 1 else ''} del banco sin cargar."
    else:
        raise ErrorConciliar(422, "tipo", f"Tipo «{tipo}»: gastos_bancarios, meli_personal, asignar o ignorar")
    if avisos:
        texto += " " + " · ".join(avisos)
    return {"escritos": escritos, "conciliadas": conciliadas, "texto": texto, "advertencias": avisos}


def marcar_linea(libro: Libro, hash_id: str, id_mov: str) -> bool:
    """/confirmar de una línea sin cargar (msg_id «banco:<hash_id>»): la línea pasa a
    CONCILIADO con el id_mov escrito. False si la línea no está."""
    _, banco = _banco_con_fila(libro)
    x = next((x for x in banco if x["hash_id"] == hash_id), None)
    if x is None:
        return False
    libro.actualizar_banco([(x["_fila"], {"estado": CONCILIADO, "id_mov": id_mov, "candidatos": ""})])
    return True


def resumen_banco(libro: Libro, libro_personal: Libro | None) -> dict | None:
    """Para /cierre-semanal (§5.20: el resumen también el lunes). None si no hay extractos."""
    m = maestros.cargar()
    _, banco = _banco_con_fila(libro)
    if not banco:
        return None
    movs = _movs_con_fila(libro, "estudio") + _movs_con_fila(libro_personal, "personal")
    r = resumen(banco, movs, m)
    r["pendientes"] = sum(1 for x in banco if x.get("estado") in ABIERTOS)
    r["sin_banco"] = len(_sin_banco(movs, banco, m, settings().conciliacion_desde))
    return r


def leer_desde_drive(adjunto: Adjunto) -> bytes:
    from app import sheets
    from app.comprobante import id_drive
    file_id = id_drive(adjunto.url)
    if not file_id:
        raise ErrorConciliar(422, "adjunto", "El link no es de Drive")
    contenido, _, _ = sheets.descargar_drive(file_id)
    return contenido
