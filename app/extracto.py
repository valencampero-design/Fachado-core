"""El extracto del banco (§5.20): el Excel que exporta Banco Patagonia → líneas.

Formato de los archivos «CompartirDetalleMovimiento-*.xlsx» (agosto 2026): unas filas de
encabezado (`Cuenta:`, `Saldos al:`, `Ultimos Movimientos`), después
`Fecha | Descripción | Débito | Crédito | Saldo`, importes como «$ 14.000,00» o «US$ 200,00»
(con espacio duro), fechas dd/mm/aaaa, del más nuevo al más viejo. Las transferencias traen
CUIT y nombre en la descripción («TRANSFERENCIA ENTRE CUENTAS VAR 20929415044 MARAGAÑO …»).

Solo lee. `hash_id` identifica la línea para que un extracto que se superpone con el anterior
no la duplique: sha256 de `cuenta_banco|fecha|descripcion|importe|saldo`.
"""
import hashlib
import io
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime

RE_CUIT = re.compile(r"(?<!\d)(\d{11})(?!\d)")
RE_OPERACION = re.compile(r"(?:\bop(?:eraci[oó]n)?\.?|\bnro\.?|\bref\.?)\s*:?\s*(\d{6,})", re.I)


class ExtractoNoReconocido(ValueError):
    """El archivo no es un extracto que el motor sepa leer (422 en /conciliar/extracto)."""


@dataclass
class LineaBanco:
    cuenta_banco: str      # «CA $ 273-125852351-000», como lo escribe el banco
    moneda: str            # ARS | USD, de la cuenta
    fecha: str             # AAAA-MM-DD
    descripcion: str
    debito: float
    credito: float
    saldo: float | None
    cuit: str | None
    nombre: str | None
    ref: str | None
    orden: int             # posición en el archivo: 0 es la más nueva
    hash_id: str = ""

    @property
    def importe(self) -> float:
        """Con signo: positivo entra, negativo sale."""
        return round(self.credito - self.debito, 2)

    def dict(self) -> dict:
        d = asdict(self)
        d["importe"] = self.importe
        return d


def _importe(valor) -> float | None:
    """«$ 1.964.843,40», «-$ 2,14», «US$ 200,00», 1964843.4 → número. Vacío → None."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).replace("\xa0", " ").strip()
    if not texto:
        return None
    negativo = texto.startswith("-") or texto.endswith("-")
    limpio = re.sub(r"[^\d,.]", "", texto)
    if not limpio:
        return None
    if "," in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    elif limpio.count(".") > 1 or re.search(r"\.\d{3}$", limpio):
        limpio = limpio.replace(".", "")
    try:
        numero = float(limpio)
    except ValueError:
        return None
    return -numero if negativo else numero


def _fecha(valor) -> str | None:
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{2,4})", str(valor or ""))
    if not m:
        return None
    d, mes, a = (int(x) for x in m.groups())
    a = a + 2000 if a < 100 else a
    try:
        return date(a, mes, d).isoformat()
    except ValueError:
        return None


def moneda_de_cuenta(cuenta_banco: str) -> str:
    return "USD" if re.search(r"u\$s|us\$|usd|d[oó]lar", cuenta_banco or "", re.I) else "ARS"


def partes_de_descripcion(descripcion: str) -> tuple[str | None, str | None, str | None]:
    """(cuit, nombre, ref): el CUIT de 11 dígitos, lo que sigue como nombre y un número de
    operación si lo dice. «PCT 30703088534  MERCADOLIBRE S.R.L.       MERCADOLIBRE» →
    («30703088534», «MERCADOLIBRE S.R.L.», None)."""
    cuit = nombre = ref = None
    m = RE_CUIT.search(descripcion or "")
    if m:
        cuit = m.group(1)
        resto = descripcion[m.end():].strip()
        # El banco rellena con espacios y a veces repite el nombre cortado: el primer tramo.
        tramo = re.split(r"\s{3,}", resto)[0].strip(" -")
        nombre = tramo or None
    r = RE_OPERACION.search(descripcion or "")
    if r:
        ref = r.group(1)
    return cuit, nombre, ref


def hash_linea(cuenta_banco: str, fecha: str, descripcion: str, importe: float, saldo: float | None) -> str:
    base = "|".join([cuenta_banco.strip(), fecha, " ".join((descripcion or "").split()),
                     f"{importe:.2f}", "" if saldo is None else f"{saldo:.2f}"])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def leer_extracto(contenido: bytes) -> list[LineaBanco]:
    """Todas las líneas de todas las hojas que tengan el encabezado de movimientos. Lanza
    ExtractoNoReconocido si el archivo no es un Excel o no tiene ninguna."""
    try:
        import openpyxl
        libro = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
    except Exception as e:  # noqa: BLE001 — cualquier cosa que no se abre no es un extracto
        raise ExtractoNoReconocido(f"No se pudo abrir como Excel ({type(e).__name__})") from e

    lineas: list[LineaBanco] = []
    for hoja in libro.worksheets:
        filas = [list(f) for f in hoja.iter_rows(values_only=True)]
        cuenta = next((str(f[1]).strip() for f in filas if f and str(f[0] or "").strip().lower().startswith("cuenta")
                       and len(f) > 1 and f[1]), None)
        enc = next((i for i, f in enumerate(filas)
                    if f and str(f[0] or "").strip().lower() == "fecha" and any("descrip" in str(c or "").lower() for c in f)),
                   None)
        if enc is None or not cuenta:
            continue
        nombres = [str(c or "").strip().lower() for c in filas[enc]]

        def col(*claves: str) -> int | None:
            return next((i for i, n in enumerate(nombres) if any(n.startswith(c) for c in claves)), None)
        i_fecha, i_desc, i_deb, i_cred, i_saldo = col("fecha"), col("descrip"), col("déb", "deb"), col("créd", "cred"), \
            col("saldo")
        if None in (i_fecha, i_desc) or (i_deb is None and i_cred is None):
            continue
        moneda = moneda_de_cuenta(cuenta)
        orden = 0
        for f in filas[enc + 1:]:
            if not f or all(c in (None, "") for c in f):
                continue
            fecha = _fecha(f[i_fecha] if i_fecha < len(f) else None)
            if not fecha:
                continue
            desc = " ".join(str(f[i_desc] or "").split())
            debito = abs(_importe(f[i_deb]) or 0.0) if i_deb is not None and i_deb < len(f) else 0.0
            credito = abs(_importe(f[i_cred]) or 0.0) if i_cred is not None and i_cred < len(f) else 0.0
            saldo = _importe(f[i_saldo]) if i_saldo is not None and i_saldo < len(f) else None
            cuit, nombre, ref = partes_de_descripcion(desc)
            linea = LineaBanco(cuenta, moneda, fecha, desc, round(debito, 2), round(credito, 2), saldo, cuit, nombre, ref,
                               orden)
            linea.hash_id = hash_linea(cuenta, fecha, desc, linea.importe, saldo)
            lineas.append(linea)
            orden += 1
    if not lineas:
        raise ExtractoNoReconocido("No tiene el encabezado «Fecha | Descripción | Débito | Crédito | Saldo»")
    return lineas
