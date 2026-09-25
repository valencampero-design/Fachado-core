"""Certificados de obra: lo que falta cobrar (CONTEXTO-FACHADO.md §5.11).

Cada certificado que emite el arquitecto es una **cuenta por cobrar**, y cada cobro que
nombra el certificado lo cancela. Del documento solo interesan obra, etapa, número, fecha y
el **saldo a cobrar de la presente certificación**. Nada más: ni el monto del contrato, ni el
anticipo, ni el fondo de reparo, ni el ajuste por CAC.

Llega por dos vías que valen lo mismo:

- **Texto libre** (`Certificado 5 Moreno1 $3.200.000`): lo arma el resolver de siempre.
- **El PDF** que genera él desde Excel. El texto sale limpio con pypdf, en modo *layout* para
  que cada monto quede en la misma línea que su rótulo: la búsqueda se ancla en el texto
  «Saldo a cancelar en la presente certificación», nunca en el «7» ni en la posición.

Tres trampas del formato:

1. «Austral» es el nombre de su constructora (`CERTIFICADO AUSTRAL`), no la obra de indirectos
   del estudio. Del PDF nunca sale una obra por nombre: sale del destinatario.
2. La obra se identifica por el destinatario (`Sr. Roberto Lo Guercio`) contra
   `OBRAS.comitente`. La «UBICACIÓN» no se usa: `tres cerros` no es la obra Tres Cerros.
3. La etapa puede contradecirse entre el cuerpo y el nombre del archivo: si pasa, no se
   elige, se pregunta.
"""
import re
from dataclasses import asdict, dataclass, field
from datetime import date

from app.filtros import sin_anulados
from app.maestros import Maestros, normalizar, numero
from app.models import EstadoCertificado

# Un monto argentino, con o sin separador de miles: `3.402.032,64` y `348143,38`. Nunca un
# porcentaje (`11,4%`).
RE_MONTO = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})(?![\d%])")

ROTULO_SALDO = r"saldo\s+a\s+cancelar\s+en\s+la\s+presente\s+certificaci[oó]n"
ROTULO_SUBTOTAL = r"sub\.?\s*total\s+de\s+certificaci[oó]n"
ROTULO_INCREMENTO = r"incremento\b"

RE_ES_CERTIFICADO = re.compile(ROTULO_SALDO + r"|\bcertificado\b[^\n]{0,40}\bn\s*[º°o]\s*\.?\s*:", re.I)
RE_NUMERO = re.compile(r"\bcertificado\b[^\n]*?\bn\s*[º°o]\s*\.?\s*:?\s*(\d+)", re.I)
RE_FECHA = re.compile(r"\bfecha\s*:?\s*(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})", re.I)
RE_DESTINATARIO = re.compile(r"^\s*(?:sr|sra|srta|señor|señora)\.?\s+(.+?)\s*$", re.I | re.M)
RE_OBRA = re.compile(r"^\s*obra\s*:\s*(.+?)\s*$", re.I | re.M)
RE_ETAPA = re.compile(r"(?<![a-z])etapa[\s_-]*(\d+)", re.I)  # también `cert_loguercio_etapa3`

# Un certificado que no cierra por más de esto (punto 7 contra 5 + 6) lleva advertencia.
TOLERANCIA_CONTROL = 1.0

# Solo se certifican obras de verdad: nunca la de indirectos del estudio ni un inmueble personal.
TIPOS_OBRA_CERTIFICABLE = ("obra_terceros", "obra_propia")


@dataclass
class DatosCertificado:
    numero: str | None = None
    fecha: str | None = None            # AAAA-MM-DD
    saldo_a_cobrar: float | None = None  # el punto 7, lo único que se guarda del documento
    destinatario: str | None = None      # para buscar la obra por comitente
    obra_documento: str | None = None    # «Vivienda Multifamiliar Etapa 2»: solo para mostrar
    etapa_cuerpo: str | None = None
    etapa_archivo: str | None = None
    control: dict = field(default_factory=dict)  # puntos 5 y 6, si se pudieron leer
    advertencias: list[str] = field(default_factory=list)

    def dict(self) -> dict:
        return asdict(self)


def importe(texto: str) -> float:
    """`3.402.032,64` o `348143,38` → float."""
    return float(texto.replace(".", "").replace(",", "."))


def es_certificado(texto: str) -> bool:
    return bool(texto and RE_ES_CERTIFICADO.search(texto))


def _monto_del_rotulo(texto: str, rotulo: str) -> float | None:
    """El último monto de la línea que tiene el rótulo, a la derecha del rótulo."""
    for linea in texto.splitlines():
        mt = re.search(rotulo, linea, re.I)
        if mt:
            montos = RE_MONTO.findall(linea[mt.end():])
            if montos:
                return importe(montos[-1])
    return None


def parsear(texto: str, nombre_archivo: str = "") -> DatosCertificado:
    """`texto` es el del PDF en modo layout (cada monto en la línea de su rótulo)."""
    d = DatosCertificado()
    d.saldo_a_cobrar = _monto_del_rotulo(texto, ROTULO_SALDO)
    if d.saldo_a_cobrar is None:
        d.advertencias.append("No se encontró «Saldo a cancelar en la presente certificación» en el PDF")

    mt = RE_NUMERO.search(texto)
    d.numero = mt.group(1) if mt else None
    mt = RE_FECHA.search(texto)
    if mt:
        dia, mes, anio = (int(x) for x in mt.groups())
        try:
            d.fecha = date(anio, mes, dia).isoformat()
        except ValueError:
            d.advertencias.append(f"La fecha «{mt.group(0)}» del certificado no existe")

    mt = RE_DESTINATARIO.search(texto)
    d.destinatario = re.sub(r"\s+", " ", mt.group(1)).strip() if mt else None
    mt = RE_OBRA.search(texto)
    if mt:
        d.obra_documento = re.sub(r"\s+", " ", mt.group(1)).strip()
        me = RE_ETAPA.search(d.obra_documento)
        d.etapa_cuerpo = me.group(1) if me else None
    me = RE_ETAPA.search(nombre_archivo or "")
    d.etapa_archivo = me.group(1) if me else None

    # Control gratis: el punto 7 es la suma de los puntos 5 y 6.
    subtotal, incremento = _monto_del_rotulo(texto, ROTULO_SUBTOTAL), _monto_del_rotulo(texto, ROTULO_INCREMENTO)
    if subtotal is not None and incremento is not None and d.saldo_a_cobrar is not None:
        diferencia = round(abs(subtotal + incremento - d.saldo_a_cobrar), 2)
        d.control = {"subtotal": subtotal, "incremento": incremento, "diferencia": diferencia}
        if diferencia > TOLERANCIA_CONTROL:
            d.advertencias.append(f"El saldo a cobrar no es la suma de los puntos 5 y 6: difiere en ${diferencia:,.2f}")
    return d


def obras_por_comitente(destinatario: str | None, m: Maestros) -> list[str]:
    """Las obras cuyo comitente es el destinatario del certificado. Con todas sus palabras:
    un nombre de pila suelto no alcanza para decir de qué obra es."""
    palabras = set(normalizar(destinatario).split())
    if not palabras:
        return []
    compacto = "".join(sorted(palabras))
    salida = []
    for o in m.obras:
        del_comitente = set(normalizar(o.comitente).split())
        if not del_comitente or o.tipo not in TIPOS_OBRA_CERTIFICABLE:
            continue
        if "".join(sorted(del_comitente)) == compacto or (len(palabras) >= 2 and palabras <= del_comitente):
            salida.append(o.nombre)
    abiertas = [n for n in salida if m.obra(n).estado != "cerrada"]
    return abiertas or salida


def clave_numero(valor) -> str:
    """Cómo se compara el número de un certificado con el que nombra un cobro. Se conserva el
    texto que acompaña al número: en Moreno «cert 4» y «cert 4 extras» son dos series, y
    confundirlas cancelaría el certificado equivocado."""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)  # el Sheet devuelve 5.0
    n = normalizar(str(valor if valor is not None else ""))
    n = re.sub(r"\b(?:n|no|nro|numero|num)\b", " ", n)  # «Nº 5» normaliza a «no 5»
    return " ".join(n.split())


def texto_etapa(valor) -> str:
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return "" if valor is None else str(valor).strip()


def clave_certificado(obra, etapa, numero) -> tuple[str, str, str]:
    return normalizar(obra), texto_etapa(etapa), clave_numero(numero)


def es_cobro(mov: dict) -> bool:
    """Un INGRESO que nombra un certificado: lo cancela (§5.11)."""
    return mov.get("tipo") == "INGRESO" and bool(clave_numero(mov.get("certificado"))) and bool(mov.get("obra"))


def estados(certs: list[dict], movs: list[dict], obra: str | None = None) -> tuple[list[EstadoCertificado], list[dict], list[str]]:
    """Cada certificado con lo cobrado y lo pendiente, más los cobros que nombran un
    certificado que no está cargado. Esos no se restan de ningún lado: se muestran aparte,
    para que el pendiente no dé negativo por un certificado que falta cargar.
    Obra, etapa y número tienen que coincidir los tres."""
    filtro = normalizar(obra) if obra else None
    movs = sin_anulados(movs)  # un cobro anulado no cancela nada (§5.19)
    salida: list[EstadoCertificado] = []
    por_clave: dict[tuple, EstadoCertificado] = {}
    advertencias: list[str] = []
    for c in certs:
        if filtro and normalizar(c.get("obra")) != filtro:
            continue
        clave = clave_certificado(c.get("obra"), c.get("etapa"), c.get("numero"))
        e = EstadoCertificado(obra=str(c.get("obra") or ""), etapa=texto_etapa(c.get("etapa")),
                              numero=texto_etapa(c.get("numero")), fecha=str(c.get("fecha") or ""),
                              saldo_a_cobrar=numero(c.get("saldo_a_cobrar")), cobrado=0.0, pendiente=0.0)
        salida.append(e)
        if clave in por_clave:
            advertencias.append(f"El certificado {e.numero} de {e.obra}{' etapa ' + e.etapa if e.etapa else ''} "
                                f"está cargado dos veces: los cobros se descuentan del primero")
        else:
            por_clave[clave] = e

    sin_certificado = []
    for mov in movs:
        if not es_cobro(mov) or (filtro and normalizar(mov.get("obra")) != filtro):
            continue
        e = por_clave.get(clave_certificado(mov.get("obra"), mov.get("etapa"), mov.get("certificado")))
        if e is None:
            sin_certificado.append(mov)
            continue
        e.cobrado += numero(mov.get("importe_ars") or mov.get("importe"))
        e.cobros.append(str(mov.get("id_mov") or ""))
    for e in salida:
        e.cobrado = round(e.cobrado, 2)
        e.pendiente = round(e.saldo_a_cobrar - e.cobrado, 2)
    return salida, sin_certificado, advertencias
