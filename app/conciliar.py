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
del handoff del 15/10; `/conciliar/estado`, el PDF de Mercado Pago, los traspasos entre cuentas
propias y los lotes en dólares, en §3 del handoff del 20/10. Ningún test escribe en el Sheet
real.

**Traspasos entre cuentas propias** (20/10, §5.20 v1.11): con cinco fuentes, la misma plata
aparece dos veces. Se emparejan **al armar lo pendiente** (el par puede completarse con el
archivo siguiente), ±1 día hábil:
- entre dos cuentas del banco que van a la misma cuenta del libro (CA $ → CC $): `INTERNA`,
  concilia sola, sin movimiento (supuesto S4);
- entre cuentas distintas del libro (Banco ↔ Mercado Pago, pesos ↔ dólares): **una ficha de
  traspaso** con las dos líneas; entre monedas, el tc sale del par (pesos / dólares).
"""
import logging
import re
from datetime import date, datetime, timedelta, timezone

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
INTERNA = "INTERNA"    # 20/10: un pase entre dos cuentas del banco que van a la misma cuenta del libro
ABIERTOS = (A_REVISAR, SIN_CARGAR)
DIAS_PROBABLE = 3      # «mismo importe, fecha ±3 días» (handoff del 15/10)
DIAS_FUERTE = 10       # con ref o CUIT alcanza una ventana más ancha: el banco acredita tarde
DIAS_SIN_BANCO = 7     # §5.20: lo del libro que no aparece en el banco después de una semana

# Gastos bancarios (§5.20: un solo lote por extracto, estructura del estudio).
RE_GASTO_BANCARIO = re.compile(
    r"comisi|impuesto|imp\.?\s*db|db/cr|intereses|cruce de fondos|iva percep|percepci|retenci|"
    r"mantenimiento|cargo\b|seguro de vida|com\.|rendimiento", re.I)
# §5.20 v1.12: lo que el banco debita por cuenta de otro organismo (DPR Sellos, rentas, ingresos
# brutos) no es un gasto bancario: va como pregunta, con rubro Impuestos y tasas › Rentas, para
# saber de qué obra es o si es del estudio. Va antes que RE_GASTO_BANCARIO («retención de IIBB»).
RE_IMPUESTO_DE_OTRO = re.compile(r"\bdpr\b|rentas|ingresos\s+brutos|\biibb\b|sellos", re.I)
RUBRO_IMPUESTO_DE_OTRO = "Rentas"  # Impuestos y tasas › Rentas
# Compras de Mercado Libre. «Mercado Pago» a secas en el banco no: puede ser un pase a la cuenta
# de Mercado Pago del estudio, que se empareja como traspaso (20/10).
RE_MELI = re.compile(r"mercado\s*libre|mercadolibre|merpago", re.I)
# §5.6 v1.12: una TRANSFERENCIA a MERCADOLIBRE S.R.L. (CUIT 30-70308853-4) es a un CVU de Mercado
# Pago: el pago a un contratista que cobra por ahí (Mathias) o una carga a la cuenta del estudio.
# Se concilia como cualquier transferencia; al lote van solo las compras («PAGO CON TRANSFERENCIA
# (PCT) … MERCADOLIBRE», compras con tarjeta).
RE_TRANSFERENCIA_A_CVU = re.compile(r"^\s*transferencia\b", re.I)
CUIT_MERCADOLIBRE = "30703088534"


def es_transferencia_a_cvu(linea: dict) -> bool:
    desc = str(linea.get("descripcion") or "")
    return bool(RE_TRANSFERENCIA_A_CVU.search(desc)) and (
        bool(RE_MELI.search(desc)) or solo_digitos(linea.get("cuit")) == CUIT_MERCADOLIBRE)
# Compra o venta de dólares entre la CA $ y la CA U$S (§5.7: traspaso entre monedas).
RE_CAMBIO = re.compile(r"compra.?venta (?:de )?d[oó]lares|compra de d[oó]lares|venta de d[oó]lares|"
                       r"compra.?venta (?:de )?moneda", re.I)
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


def _clave_cuenta_banco(texto: str) -> str:
    return re.sub(r"\s+", "", str(texto or "")).lower()


def cuenta_de_linea(linea: dict, m: Maestros):
    """La cuenta del libro de una línea: la que nombra esa cuenta del banco en
    `CUENTAS.cuentas_banco` (§5.20 v1.11); si no está configurada, Mercado Pago para el PDF de
    Mercado Pago y Banco / Banco USD por la moneda para el banco."""
    clave = _clave_cuenta_banco(linea.get("cuenta_banco"))
    configurada = next((c for c in m.cuentas if c.activa and clave in {_clave_cuenta_banco(x) for x in c.cuentas_banco}), None)
    if configurada:
        return configurada
    if linea.get("origen") == "mercado_pago" or clave == _clave_cuenta_banco("Mercado Pago"):
        return next((c for c in m.cuentas if c.activa and c.tipo == "billetera" and c.moneda == "ARS"), None)
    return _cuenta_motor(str(linea.get("moneda") or "ARS"), m)


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
    # Una línea de Mercado Pago se cruza con lo cargado en Mercado Pago; una del banco, con Banco.
    destino = cuenta_de_linea(linea, m)
    fuertes, probables = [], []
    for mov in movs:
        clave = (mov["_libro"], mov["_fila"])
        if clave in usados:
            continue
        cuenta = m.cuenta(mov.get("cuenta"), incluir_inactivas=True)
        if cuenta is None or cuenta.moneda != moneda or (destino is not None and cuenta.nombre != destino.nombre):
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


def _desempate_por_fecha(linea: dict, cands: list[dict]) -> list[dict]:
    """§5.20 v1.12: con varios candidatos del mismo importe, si uno solo tiene la misma fecha que
    la línea, es ese (los dos pagos de $ 200.000 del 14 y el 16/10)."""
    mismo_dia = [c for c in cands if _dias(linea.get("fecha"), c.get("fecha")) == 0]
    return mismo_dia if len(mismo_dia) == 1 else cands


def _decidir(linea: dict, movs: list[dict], m: Maestros, usados: set) -> tuple[str, list[dict]]:
    fuertes, probables = _candidatos(linea, movs, m, usados)
    for cands in (fuertes, probables):
        cands = _desempate_por_fecha(linea, cands)
        if len(cands) == 1:
            return CONCILIADO, cands
        if len(cands) > 1:
            return A_REVISAR, cands
    return SIN_CARGAR, []


def lote_de(linea: dict) -> str | None:
    """Gastos bancarios (también rendimientos, comisiones y retenciones de Mercado Pago: supuesto
    S3) y compras de Mercado Libre van en lote. Los gastos en dólares van en un lote aparte, con
    un tipo de cambio para todo el lote (supuesto S2, 20/10); Mercado Libre, solo en pesos."""
    desc = str(linea.get("descripcion") or "")
    if RE_CAMBIO.search(desc):
        return None  # compra o venta de dólares: es un traspaso entre monedas
    if RE_IMPUESTO_DE_OTRO.search(desc):
        return None  # §5.20 v1.12: DPR Sellos, rentas, IIBB: pregunta, no gasto bancario
    if RE_GASTO_BANCARIO.search(desc):
        return "gastos_bancarios"
    if es_transferencia_a_cvu(linea):
        return None  # §5.6 v1.12: una transferencia a un CVU de Mercado Pago no es una compra
    if str(linea.get("moneda") or "ARS") == "ARS" and numero(linea.get("debito")) > 0 and RE_MELI.search(desc):
        return "meli_personal"
    return None


# ─── Traspasos entre cuentas propias (20/10) ───────────────────────────────────

def _dias_habiles(a: str, b: str) -> int:
    """Días hábiles entre dos fechas (lunes a viernes; los feriados no se cuentan aparte)."""
    try:
        d1, d2 = sorted((date.fromisoformat(str(a)[:10]), date.fromisoformat(str(b)[:10])))
    except ValueError:
        return 10_000
    n, d = 0, d1
    while d < d2:
        d = date.fromordinal(d.toordinal() + 1)
        if d.weekday() < 5:
            n += 1
    return n


def emparejar(lineas: list[dict], m: Maestros) -> list[tuple[str, dict, dict]]:
    """Los pares entre cuentas propias entre las líneas abiertas: (clase, sale, entra).
    `interna`: mismo importe, dos cuentas del banco que van a la misma cuenta del libro.
    `traspaso`: mismo importe entre cuentas distintas del libro (Banco ↔ Mercado Pago).
    `cambio`: compra o venta de dólares, una línea en pesos y otra en dólares.
    ±1 día hábil; cada línea en un solo par, el más cercano en fecha."""
    sales = [x for x in lineas if numero(x.get("debito")) > 0]
    entran = [x for x in lineas if numero(x.get("credito")) > 0]
    pares, usadas = [], set()
    for s in sorted(sales, key=lambda x: (str(x.get("fecha")), x["hash_id"])):
        cs = cuenta_de_linea(s, m)
        mejor = None
        for e in entran:
            if e["hash_id"] in usadas or e["hash_id"] == s["hash_id"] or e.get("cuenta_banco") == s.get("cuenta_banco"):
                continue
            if _dias_habiles(s.get("fecha"), e.get("fecha")) > 1:
                continue
            ce = cuenta_de_linea(e, m)
            if cs is None or ce is None:
                continue
            misma_moneda = str(s.get("moneda") or "ARS") == str(e.get("moneda") or "ARS")
            if misma_moneda and abs(numero(s.get("debito")) - numero(e.get("credito"))) <= 0.01:
                clase = "interna" if cs.nombre == ce.nombre else "traspaso"
            elif not misma_moneda and RE_CAMBIO.search(str(s.get("descripcion"))) and RE_CAMBIO.search(str(e.get("descripcion"))):
                pesos, dolares = (numero(s.get("debito")), numero(e.get("credito"))) if s.get("moneda") == "ARS" \
                    else (numero(e.get("credito")), numero(s.get("debito")))
                if not dolares or not 50 <= pesos / dolares <= 100000:
                    continue
                clase = "cambio"
            else:
                continue
            distancia = _dias(s.get("fecha"), e.get("fecha"))
            if mejor is None or distancia < mejor[0]:
                mejor = (distancia, clase, e)
        if mejor:
            usadas |= {s["hash_id"], mejor[2]["hash_id"]}
            pares.append((mejor[1], s, mejor[2]))
    return pares


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


def _con_signo(v: float, moneda: str = "ARS") -> str:
    """§5.20 v1.12: un saldo o una diferencia negativa lleva el signo («−$ 7.166.358,10»).
    `_dinero` no lo pone: «Vi un pago de $ 165.700» ya dice para qué lado va."""
    return f"{'−' if round(v, 2) < 0 else ''}{_dinero(v, moneda)}"


def _quien(linea: dict) -> str:
    if es_transferencia_a_cvu(linea):
        return "una cuenta de Mercado Pago (MERCADOLIBRE S.R.L.)"
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


def texto_lote(tipo: str, lineas: list[dict], moneda: str = "ARS") -> str:
    total = sum(numero(x.get("debito")) - numero(x.get("credito")) for x in lineas)
    n = len(lineas)
    if tipo == "gastos_bancarios":
        en = " en US$" if moneda == "USD" else ""
        return f"{n} gasto{'s' if n != 1 else ''} bancario{'s' if n != 1 else ''}{en} por {_dinero(total, moneda)}"
    return (f"{n} compra{'s' if n != 1 else ''} de Mercado Libre / Mercado Pago sin comprobante por {_dinero(total)} "
            f"(gasto personal sin clasificar)")


# ─── La ficha de una línea sin cargar ──────────────────────────────────────────

def ficha_de_linea(linea: dict, telefono: str, libros: dict) -> dict:
    """La línea del banco hace de comprobante (§5.20): importe, fecha, cuenta Banco y el
    contratista por CUIT o nombre con el resolver, con las preguntas de siempre."""
    from app.interpretar import interpretar
    importe = numero(linea.get("credito")) - numero(linea.get("debito"))

    # §5.6 v1.12: en una transferencia a un CVU, MERCADOLIBRE S.R.L. es la pasarela, no a quién
    # se le pagó: no se resuelve como contratista.
    pasarela = es_transferencia_a_cvu(linea)

    def lector(_adj):
        d = DatosComprobante(url="", nombre_archivo="")
        d.completar({"importe": abs(importe), "fecha": str(linea.get("fecha"))[:10], "moneda": linea.get("moneda") or "ARS",
                     "cuit": None if pasarela else (linea.get("cuit") or None),
                     "razon_social": None if pasarela else (linea.get("nombre") or None),
                     "medio_pago": "Transferencia", "tipo_comprobante": "Línea del extracto",
                     "id_operacion": linea.get("ref") or None}, "extracto")
        return d
    # §5.20 v1.12: un impuesto de otro organismo (DPR Sellos, rentas, IIBB) va con su rubro.
    texto = "Ingreso" if importe > 0 else RUBRO_IMPUESTO_DE_OTRO if RE_IMPUESTO_DE_OTRO.search(str(linea.get("descripcion"))) else ""
    req = InterpretarIn(texto=texto, telefono=telefono,
                        fecha_mensaje=f"{str(linea.get('fecha'))[:10]}T15:00:00Z",
                        adjuntos=[Adjunto(url=f"banco:{linea['hash_id']}", nombre="extracto")])
    salida = interpretar(req, libros=libros, lector=lector)
    for ficha in salida.fichas:
        ficha.extras["id_banco"] = linea["hash_id"]
        ficha.campos["comprobante_url"] = None  # no hay archivo: la línea es el comprobante
        if not ficha.campos.get("descripcion"):
            ficha.campos["descripcion"] = f"Extracto: {linea.get('descripcion')}"
    return salida.model_dump()


# ─── La ficha de un traspaso entre cuentas propias (20/10) ─────────────────────

def _formato_tc(tc: float) -> str:
    entero, _, dec = f"{tc:,.2f}".partition(".")
    entero = entero.replace(",", ".")
    return entero if dec == "00" else f"{entero},{dec}"


def _datos_traspaso(clase: str, sale: dict, entra: dict, m: Maestros) -> dict:
    co, cd = cuenta_de_linea(sale, m), cuenta_de_linea(entra, m)
    moneda = str(sale.get("moneda") or "ARS")
    importe = numero(sale.get("debito"))
    if clase == "cambio":
        pesos, dolares = (importe, numero(entra.get("credito"))) if moneda == "ARS" else (numero(entra.get("credito")), importe)
        tc = round(pesos / dolares, 4)
    else:
        pesos, dolares, tc = (importe if moneda == "ARS" else None), None, 1
    return {"co": co, "cd": cd, "moneda": moneda, "importe": importe, "tc": tc, "pesos": pesos, "dolares": dolares}


def texto_traspaso(clase: str, sale: dict, entra: dict, m: Maestros) -> str:
    d = _datos_traspaso(clase, sale, entra, m)
    if clase == "cambio":
        que = "una compra" if d["moneda"] == "ARS" else "una venta"
        return (f"Vi {que} de {_dinero(d['dolares'], 'USD')} por {_dinero(d['pesos'])} (TC {_formato_tc(d['tc'])}) "
                f"el {_dia(sale.get('fecha'))}. ¿La cargo como traspaso?")
    return (f"Vi que pasaste {_dinero(d['importe'], d['moneda'])} de {d['co'].nombre} a {d['cd'].nombre} "
            f"el {_dia(sale.get('fecha'))}. ¿Lo cargo como traspaso?")


def ficha_de_traspaso(clase: str, sale: dict, entra: dict, m: Maestros) -> dict:
    """Una sola ficha TRASPASO con las dos líneas (no dos egresos sueltos). Entre monedas, el
    tc sale del par, origen `comprobante`, y no se pregunta (§5.7). Se confirma con
    `msg_id = "banco:<hash de la que sale>"` y `extras.ids_banco = [sale, entra]`."""
    from app.models import CAMPOS_FICHA_TRASPASO, Ficha, InterpretarOut
    d = _datos_traspaso(clase, sale, entra, m)
    campos = {c: None for c in CAMPOS_FICHA_TRASPASO}
    campos.update({"tipo": "TRASPASO", "fecha": str(sale.get("fecha"))[:10], "importe": d["importe"], "moneda": d["moneda"],
                   "tc": d["tc"], "importe_ars": round(d["importe"] * (d["tc"] if d["moneda"] != "ARS" else 1), 2),
                   "cuenta_origen": d["co"].nombre, "cuenta_destino": d["cd"].nombre,
                   "descripcion": f"Extracto: {sale.get('descripcion')} / {entra.get('descripcion')}"})
    origen = {k: "comprobante" for k, v in campos.items() if v not in (None, "")}
    ficha = Ficha(campos=campos, origen_campo=origen, extras={"ids_banco": [sale["hash_id"], entra["hash_id"]]})
    return InterpretarOut(intencion="movimiento", fichas=[ficha], preguntas=[], requiere_confirmacion=True,
                          diagnostico={"origen": "conciliacion", "clase": clase}).model_dump()


def lineas_por_hash(libro: Libro, hash_ids: list[str]) -> dict[str, dict]:
    _, banco = _banco_con_fila(libro)
    return {x["hash_id"]: x for x in banco if x["hash_id"] in set(hash_ids)}


# ─── Resumen ───────────────────────────────────────────────────────────────────

def _saldo_banco(banco: list[dict]) -> dict[str, tuple[float, str, str, str]]:
    """{cuenta_banco: (saldo, fecha, moneda, origen)} con la última línea de cada cuenta: la de
    fecha más nueva y, el mismo día, la del extracto más reciente con menor orden (orden 0 = la
    más nueva del archivo)."""
    salida: dict[str, tuple] = {}
    for x in banco:
        if x.get("saldo") in ("", None):
            continue
        clave = (str(x.get("fecha"))[:10], str(x.get("importado_ts") or ""), -int(numero(x.get("orden"))))
        actual = salida.get(x["cuenta_banco"])
        if actual is None or clave > actual[0]:
            salida[x["cuenta_banco"]] = (clave, numero(x.get("saldo")), str(x.get("fecha"))[:10], x.get("moneda") or "ARS",
                                         x.get("origen") or "banco_patagonia")
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
    """Saldo según el libro contra saldo según el banco, por cuenta del libro (Banco, Banco USD,
    Mercado Pago: la de cada cuenta del banco, `cuenta_de_linea`) y total en pesos (las cuentas
    del libro en pesos: Banco + Mercado Pago); las cuentas del banco detalladas; conteos."""
    saldos = _saldo_banco(banco)
    grupos: dict[str, dict] = {}
    banco_ars = _cuenta_motor("ARS", m)
    if banco_ars is not None:
        grupos[banco_ars.nombre] = {"cuenta": banco_ars, "banco": {}}
    for k, (saldo, fecha, moneda, origen) in saldos.items():
        cuenta = cuenta_de_linea({"cuenta_banco": k, "moneda": moneda, "origen": origen}, m)
        if cuenta is None:
            continue
        grupos.setdefault(cuenta.nombre, {"cuenta": cuenta, "banco": {}})["banco"][k] = (saldo, fecha)
    por_cuenta = []
    for nombre, g in grupos.items():
        cuenta = g["cuenta"]
        libro_ = _saldo_libro(cuenta, movs)
        banco_ = round(sum(v[0] for v in g["banco"].values()), 2)
        por_cuenta.append({"cuenta": nombre, "moneda": cuenta.moneda, "saldo_libro": libro_, "saldo_banco": banco_,
                           "diferencia": round(banco_ - libro_, 2), "fecha_apertura": cuenta.fecha_apertura,
                           "cuentas_banco": [{"cuenta_banco": k, "saldo": v[0], "al": v[1]} for k, v in sorted(g["banco"].items())]})
    ars = [c for c in por_cuenta if c["moneda"] == "ARS"]
    conteos: dict[str, int] = {}
    for x in banco:
        conteos[x.get("estado") or ""] = conteos.get(x.get("estado") or "", 0) + 1
    return {"saldo_libro": round(sum(c["saldo_libro"] for c in ars), 2),
            "saldo_banco": round(sum(c["saldo_banco"] for c in ars), 2),
            "diferencia": round(sum(c["diferencia"] for c in ars), 2),
            "moneda": "ARS", "por_cuenta": por_cuenta, "conteos": conteos}


def _sin_banco(movs: list[dict], banco: list[dict], m: Maestros, desde: str) -> list[dict]:
    """§5.20: lo del libro que no apareció en el banco después de una semana (solo dentro de
    lo que el extracto cubre). Se avisa en el resumen, no se pregunta uno por uno."""
    hasta_por_cuenta: dict[str, str] = {}  # hasta dónde cubre el extracto cada cuenta del libro
    for x in banco:
        cuenta = cuenta_de_linea(x, m)
        if cuenta is not None:
            hasta_por_cuenta[cuenta.nombre] = max(hasta_por_cuenta.get(cuenta.nombre, ""), str(x.get("fecha"))[:10])
    salida = []
    for mov in _conciliables(movs, m, desde):
        cuenta = m.cuenta(mov.get("cuenta"), incluir_inactivas=True)
        hasta = hasta_por_cuenta.get(cuenta.nombre)
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
               "lote": lote or "", "orden": linea.orden, "importado_ts": ts, "origen": linea.origen}
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
    ts = _ahora().strftime("%Y-%m-%d %H:%M:%S")  # hora de Argentina: Railway corre en UTC
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
    # §5.20 v1.12: las que tienen más de un candidato se deciden al final, cuando las demás ya se
    # llevaron los suyos (el pago del 16/10 se queda con el del 16/10 y el del 14/10 con el otro).
    nuevas = []
    for linea in lineas:
        if linea.hash_id in ya or linea.hash_id in vistos:
            repetidas += 1
            continue
        vistos.add(linea.hash_id)
        if linea.fecha < desde:
            anteriores += 1
            nuevas_filas.append(_fila_banco(linea, ANTERIOR, "", [], None, ts))
            continue
        nuevas.append(linea)
    ambiguas_primero = {linea.hash_id for linea in nuevas
                        if _decidir(linea.dict(), conciliables, m, set(usados))[0] == A_REVISAR}
    for linea in [x for x in nuevas if x.hash_id not in ambiguas_primero] + [x for x in nuevas if x.hash_id in ambiguas_primero]:
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

    # S4 (20/10): un pase entre dos cuentas del banco que van a la misma cuenta del libro
    # (CA $ → CC $) concilia solo, sin movimiento. Se busca entre todas las abiertas: el par puede
    # haber llegado en un extracto anterior.
    _, banco = _banco_con_fila(libro)
    internas = [p for p in emparejar([x for x in banco if x.get("estado") == SIN_CARGAR], m) if p[0] == "interna"]
    if internas:
        libro.actualizar_banco([(x["_fila"], {"estado": INTERNA, "lote": "", "candidatos": ""})
                                for _, a, b in internas for x in (a, b)])

    salida = pendientes(telefono, libro, libro_personal, _m=m)
    salida.update({"origen": lineas[0].origen, "cuenta_banco": lineas[0].cuenta_banco, "internas": len(internas)})
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
    abierto (los conteos de importación en cero). Solo lee: los pares entre cuentas propias se
    arman acá, pero solo `procesar_extracto` marca los `INTERNA`."""
    m = _m or maestros.cargar()
    usuario = _usuario(m, telefono)
    libros = {k: (_LeidoUnaVez(v) if v is not None else None) for k, v in _libros(libro, libro_personal, usuario).items()}
    movs = _movs_con_fila(libros["estudio"], "estudio") + _movs_con_fila(libros["personal"], "personal")
    _, banco = _banco_con_fila(libro)
    desde = settings().conciliacion_desde

    abiertas = [x for x in banco if x.get("estado") == SIN_CARGAR]
    pares = [p for p in emparejar(abiertas, m) if p[0] != "interna"]
    en_par = {h for _, a, b in pares for h in (a["hash_id"], b["hash_id"])}
    lotes: dict[tuple[str, str], list[dict]] = {}
    ambiguas, pendientes_ = [], []
    for clase, sale, entra in pares:
        pendientes_.append({"tipo": "traspaso", "hash_id": sale["hash_id"], "hash_ids": [sale["hash_id"], entra["hash_id"]],
                            "texto": texto_traspaso(clase, sale, entra, m),
                            "interpretacion": ficha_de_traspaso(clase, sale, entra, m)})
    for x in sorted(banco, key=lambda x: (str(x.get("fecha")), -int(numero(x.get("orden"))))):
        if x.get("estado") == A_REVISAR:
            cands = [c.strip() for c in str(x.get("candidatos") or "").split(",") if c.strip()]
            ambiguas.append({"hash_id": x["hash_id"], "texto": texto_ambigua(x, cands), "candidatos": cands})
        elif x.get("estado") != SIN_CARGAR or x["hash_id"] in en_par:
            continue
        elif x.get("lote"):
            lotes.setdefault((x["lote"], str(x.get("moneda") or "ARS")), []).append(x)
        else:
            pendientes_.append({"tipo": "linea", "hash_id": x["hash_id"], "texto": texto_pendiente(x),
                                "interpretacion": ficha_de_linea(x, telefono, libros)})
    sin_banco = _sin_banco(movs, banco, m, desde)
    salida = {
        "importadas": 0, "repetidas": 0, "anteriores": 0, "conciliadas": 0, "internas": 0,
        "a_revisar": len(ambiguas),
        "sin_cargar": len(pendientes_) + sum(len(v) for v in lotes.values()),
        "sin_banco": len(sin_banco),
        "lotes": [_lote_salida(tipo, moneda, xs, movs) for (tipo, moneda), xs in sorted(lotes.items())],
        "ambiguas": ambiguas,
        "pendientes": pendientes_,
        "resumen": resumen(banco, movs, m),
        "sin_banco_detalle": [str(mov.get("id_mov")) for mov in sin_banco],
    }
    salida["texto"] = _texto_resumen(salida)
    return salida


def _tc_sugerido(lineas: list[dict], movs: list[dict]) -> str | None:
    """S2 (20/10): si el libro ya usó un tipo de cambio el día del lote (la última fecha), ese."""
    fecha = max(str(x.get("fecha"))[:10] for x in lineas)
    del_dia = [mv for mv in movs if str(mv.get("fecha") or "")[:10] == fecha and numero(mv.get("tc")) > 1]
    if not del_dia:
        return None
    tc = numero(max(del_dia, key=lambda mv: str(mv.get("ts") or "")).get("tc"))
    return str(int(tc)) if tc == int(tc) else f"{tc:.2f}"


def _lote_salida(tipo: str, moneda: str, xs: list[dict], movs: list[dict]) -> dict:
    requiere_tc = moneda != "ARS"
    return {"tipo": tipo, "moneda": moneda, "cantidad": len(xs),
            "total": round(sum(numero(x.get("debito")) - numero(x.get("credito")) for x in xs), 2),
            "hash_ids": [x["hash_id"] for x in xs], "texto": texto_lote(tipo, xs, moneda),
            "requiere_tc": requiere_tc, "tc_sugerido": _tc_sugerido(xs, movs) if requiere_tc else None,
            # para el botón «Ver detalle» del gateway: una línea corta por movimiento
            "detalle": [f"{_dia(x.get('fecha'))} · "
                        f"{'−' if numero(x.get('debito')) else '+'}{_dinero(numero(x.get('debito')) or numero(x.get('credito')), moneda)}"
                        f" · {str(x.get('descripcion') or '').strip()}" for x in xs]}


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
    if s.get("internas"):
        partes.append(f"{s['internas']} pase{'s' if s['internas'] != 1 else ''} entre cuentas propias del banco, "
                      f"conciliado{'s' if s['internas'] != 1 else ''} solo{'s' if s['internas'] != 1 else ''}.")
    abiertas = s.get("a_revisar", 0) + len(s.get("pendientes", [])) + sum(x["cantidad"] for x in s.get("lotes", []))
    if abiertas:
        partes.append(f"Quedan {abiertas} para revisar: {len(s.get('pendientes', []))} sin cargar, "
                      f"{s.get('a_revisar', 0)} con más de un candidato"
                      + (f" y {', '.join(x['texto'] for x in s['lotes'])}" if s.get("lotes") else "") + ".")
    if s.get("sin_banco"):
        partes.append(f"{s['sin_banco']} movimiento{'s' if s['sin_banco'] != 1 else ''} del libro no aparece"
                      f"{'n' if s['sin_banco'] != 1 else ''} en el banco hace más de una semana.")
    for c in r["por_cuenta"]:
        partes.append(f"{c['cuenta']}: libro {_con_signo(c['saldo_libro'], c['moneda'])} · banco "
                      f"{_con_signo(c['saldo_banco'], c['moneda'])} · diferencia {_con_signo(c['diferencia'], c['moneda'])}"
                      + (" (sin saldo de apertura cargado)" if not c.get("fecha_apertura") else ""))
    return "\n".join(partes) or "No hay nada pendiente del banco."


# ─── Lotes y asignaciones ──────────────────────────────────────────────────────

def _obra_estructura(m: Maestros):
    return next((o for o in m.obras if o.tipo == "estructura" and o.estado != "cerrada"), None)


def _ficha_lote(tipo: str, x: dict, m: Maestros, tc: float | None = None) -> FichaConfirmada:
    importe = numero(x.get("credito")) - numero(x.get("debito"))
    cuenta = cuenta_de_linea(x, m)
    moneda = str(x.get("moneda") or "ARS")
    base = {"fecha": str(x.get("fecha"))[:10], "tipo": "EGRESO" if importe < 0 else "INGRESO", "importe": abs(importe),
            "moneda": moneda, "tc": 1 if moneda == "ARS" else tc, "cuenta": cuenta.nombre if cuenta else "Banco",
            "origen": "BANCO", "item": x.get("nombre") or x.get("descripcion"),
            "descripcion": f"Extracto: {x.get('descripcion')}", "tipo_comprobante": "Línea del extracto",
            "comprobante_url": None, "id_mov": None}
    if tipo == "gastos_bancarios":
        obra = _obra_estructura(m)
        base.update({"obra": obra.nombre if obra else None, "tipo_gasto": "estructura", "rubro_1": RUBRO_BANCARIO[0],
                     "rubro_2": RUBRO_BANCARIO[1], "medio_pago": "Mercado Pago" if x.get("origen") == "mercado_pago"
                     else "Débito automático" if importe < 0 else "Otro"})
    else:
        base.update({"obra": None, "tipo_gasto": "personal", "rubro_1": RUBRO_MELI[0], "rubro_2": RUBRO_MELI[1],
                     "medio_pago": "Transferencia", "item": "Mercado Libre"})
    return FichaConfirmada(campos=base, extras={"id_banco": x["hash_id"]})


async def lote(telefono: str, tipo: str, hash_ids: list[str], id_mov: str | None, libro: Libro,
               libro_personal: Libro | None, archivador, tipo_cambio: str | None = None) -> dict:
    """POST /conciliar/lote: confirma un lote (gastos bancarios o MeLi personal), asigna una
    ambigua a uno de sus candidatos o ignora líneas. Un lote en dólares lleva `tipo_cambio`
    (string, como lo escribió el usuario: «1.450»), uno para todo el lote (supuesto S2)."""
    m = maestros.cargar()
    usuario = _usuario(m, telefono)
    _, banco = _banco_con_fila(libro)
    por_hash = {x["hash_id"]: x for x in banco}
    faltan = [h for h in hash_ids if h not in por_hash]
    if faltan:
        raise ErrorConciliar(404, "hash_ids", f"Líneas que no están en BANCO_RAW: {faltan[:3]}")
    escritos, conciliadas, avisos = [], [], []

    if tipo in ("gastos_bancarios", "meli_personal"):
        tc = None
        if any(str(por_hash[h].get("moneda") or "ARS") != "ARS" for h in hash_ids):
            tc = numero(tipo_cambio) if tipo_cambio not in (None, "") else 0.0
            if tc <= 1:
                raise ErrorConciliar(422, "tipo_cambio", f"El lote está en dólares: hace falta el tipo de cambio "
                                                         f"(llegó «{tipo_cambio or ''}»)")
        for h in hash_ids:
            x = por_hash[h]
            if x.get("estado") == CONCILIADO:
                conciliadas.append(h)
                continue
            req = ConfirmarIn(msg_id=f"banco:{h}", telefono=telefono, ficha=_ficha_lote(tipo, x, m, tc))
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


def _ahora() -> datetime:
    return datetime.now(timezone(timedelta(hours=settings().utc_offset_horas)))


def _rotulos(fuentes: list[str]) -> dict[str, str]:
    """Rótulos cortos para la plantilla: «CA $ 273-125852351-000» → «CA $»; si dos quedan
    iguales (las dos CA $), se les suma el primer número: «CA $ 273» y «CA $ 48»."""
    def corto(cb: str) -> str:
        m_ = re.match(r"\s*(\S+\s+\S+)\s+(\d+)", cb)
        return m_.group(1) if m_ else cb.strip()
    cortos = {cb: corto(cb) for cb in fuentes}
    repetidos = {r for r in cortos.values() if list(cortos.values()).count(r) > 1}
    salida = {}
    for cb, r in cortos.items():
        num = re.match(r"\s*\S+\s+\S+\s+(\d+)", cb)
        salida[cb] = f"{r} {int(num.group(1))}" if r in repetidos and num else r
    return salida


def _y(partes: list[str]) -> str:
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


def estado(telefono: str, libro: Libro, hoy: date | None = None) -> dict:
    """GET /conciliar/estado (20/10, solo lectura): qué llegó y qué falta de la semana, por
    fuente. Las fuentes salen de CUENTAS (`cuentas_banco` de cada cuenta que concilia: las cuatro
    del banco y Mercado Pago); si todavía no está configurado, de lo que ya hay en BANCO_RAW.
    `al_dia` = hay líneas importadas con fecha dentro de la semana (desde el lunes)."""
    m = maestros.cargar()
    _usuario(m, telefono)
    hoy = hoy or _ahora().date()
    semana_desde = hoy - timedelta(days=hoy.weekday())
    _, banco = _banco_con_fila(libro)
    fuentes: list[tuple[str, str, str]] = []  # (cuenta_banco, cuenta del libro, origen)
    for c in m.cuentas:
        if c.activa and c.concilia_contra_banco:
            for cb in c.cuentas_banco:
                fuentes.append((cb, c.nombre, "mercado_pago" if c.tipo == "billetera" else "banco_patagonia"))
    if not fuentes:
        vistas: dict[str, tuple] = {}
        for x in banco:
            cuenta = cuenta_de_linea(x, m)
            vistas.setdefault(x["cuenta_banco"], (x["cuenta_banco"], cuenta.nombre if cuenta else "",
                                                   x.get("origen") or "banco_patagonia"))
        fuentes = list(vistas.values())
        mp = next((c for c in m.cuentas if c.activa and c.tipo == "billetera" and c.concilia_contra_banco), None)
        if mp and not any(f[2] == "mercado_pago" for f in fuentes):
            fuentes.append(("Mercado Pago", mp.nombre, "mercado_pago"))
    rotulos = _rotulos([f[0] for f in fuentes])
    offset = settings().utc_offset_horas
    salida, faltan = [], []
    for cb, cuenta, origen in fuentes:
        propias = [x for x in banco if _clave_cuenta_banco(x.get("cuenta_banco")) == _clave_cuenta_banco(cb)]
        ultima_imp = max((str(x.get("importado_ts") or "") for x in propias), default="")
        ultima_fecha = max((str(x.get("fecha"))[:10] for x in propias), default="")
        al_dia = bool(ultima_fecha) and ultima_fecha >= semana_desde.isoformat()
        salida.append({"cuenta_banco": cb, "cuenta": cuenta, "origen": origen, "rotulo": rotulos[cb],
                       "ultima_importacion": (ultima_imp.replace(" ", "T") + f"{offset:+03d}:00") if ultima_imp else None,
                       "ultima_fecha_linea": ultima_fecha or None, "al_dia": al_dia})
        if not al_dia:
            faltan.append(rotulos[cb])
    texto = f"Me faltan: {_y(faltan)}" if faltan else "Llegó todo lo de la semana."
    return {"semana_desde": semana_desde.isoformat(), "fuentes": salida, "faltan": faltan, "texto": texto}


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
