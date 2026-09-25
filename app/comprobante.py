"""Lectura de comprobantes: nombre de archivo → texto del PDF → visión.

Del más barato y confiable al más caro:
  1. El nombre del archivo. «Cheque9679_SOTO MIGUEL ANGEL_20217263256.pdf» ya trae número
     de cheque, razón social y CUIT.
  2. El texto del PDF (los del homebanking son texto, no imagen), con pypdf y regex.
  3. El modelo: solo para fotos, o si el PDF no dio importe y fecha.
"""
import hashlib
import io
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date

from app import llm
from app.config import settings
from app.models import Adjunto
from app.resolver import parsear_importe

logger = logging.getLogger(__name__)

CAMPOS = ["fecha", "fecha_pago", "importe", "moneda", "razon_social", "cuit", "cuenta_destino",
          "id_operacion", "numero_cheque", "medio_pago", "tipo_comprobante", "cuit_originante"]


@dataclass
class DatosComprobante:
    url: str = ""
    nombre_archivo: str = ""
    fecha: str | None = None        # AAAA-MM-DD, fecha del hecho económico (emisión)
    fecha_pago: str | None = None   # cheque diferido
    importe: float | None = None
    moneda: str | None = None
    razon_social: str | None = None  # destinatario
    cuit: str | None = None          # destinatario
    cuenta_destino: str | None = None
    id_operacion: str | None = None
    numero_cheque: str | None = None
    medio_pago: str | None = None
    tipo_comprobante: str | None = None
    cuit_originante: str | None = None
    sha256: str | None = None        # del archivo: la referencia más fuerte para duplicados (§5.16)
    fuente: dict[str, str] = field(default_factory=dict)  # campo → nombre_archivo | pdf_texto | vision
    uso_llm: bool = False
    error: str | None = None
    texto: str = ""                  # el texto del PDF, para reconocer un certificado; no se devuelve

    def referencias(self) -> list[str]:
        """Lo que identifica al comprobante, del más fuerte al más débil (§5.16)."""
        refs = []
        if self.id_operacion:
            refs.append(f"op:{self.id_operacion}")
        if self.numero_cheque:
            refs.append(f"cheque:{self.numero_cheque}")
        if self.sha256:
            refs.append(f"sha256:{self.sha256}")
        return refs

    def completar(self, datos: dict, fuente: str) -> None:
        for campo in CAMPOS:
            valor = datos.get(campo)
            if valor not in (None, "") and getattr(self, campo) in (None, ""):
                setattr(self, campo, valor)
                self.fuente[campo] = fuente

    def dict(self) -> dict:
        d = asdict(self)
        d.pop("texto", None)
        return d


def formatear_cuit(texto: str | None) -> str | None:
    digitos = re.sub(r"\D", "", texto or "")
    return f"{digitos[:2]}-{digitos[2:10]}-{digitos[10]}" if len(digitos) == 11 else None


def id_drive(url: str) -> str | None:
    m = re.search(r"/d/([\w-]{20,})", url) or re.search(r"[?&]id=([\w-]{20,})", url)
    return m.group(1) if m else None


# ─── 1. Nombre de archivo ──────────────────────────────────────────────────────

RE_NOMBRE_CHEQUE = re.compile(r"cheque\s*(\d+)_(.+?)_(\d{11})", re.I)
RE_CUIT_SUELTO = re.compile(r"(?<!\d)(\d{2}-?\d{8}-?\d)(?!\d)")


def parsear_nombre(nombre: str) -> dict:
    if not nombre:
        return {}
    m = RE_NOMBRE_CHEQUE.search(nombre)
    if m:
        return {"numero_cheque": m.group(1), "razon_social": m.group(2).strip(), "cuit": formatear_cuit(m.group(3)),
                "medio_pago": "Cheque", "tipo_comprobante": "Cheque"}
    datos = {}
    m = RE_CUIT_SUELTO.search(nombre)
    if m:
        datos["cuit"] = formatear_cuit(m.group(1))
    # El homebanking nombra los PDF con el número de operación: «13851988_LR92K2y581_1.pdf».
    # Es la parte que mezcla letras y números; las que son solo números son documentos o índices.
    base = nombre.rsplit(".", 1)[0]
    ops = [p for p in re.split(r"[_\s-]+", base)
           if 8 <= len(p) <= 20 and re.search(r"[A-Za-z]", p) and re.search(r"\d", p)]
    if len(ops) == 1:
        datos["id_operacion"] = ops[0]
    return datos


# ─── 2. Texto del PDF ──────────────────────────────────────────────────────────

def texto_pdf(contenido: bytes) -> str:
    try:
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(contenido)).pages).strip()
    except Exception as e:  # PDF roto o escaneado
        logger.warning("No se pudo extraer texto del PDF: %s", e)
        return ""


def _fecha_iso(d: str, m: str, a: str) -> str | None:
    try:
        return date(int(a) + (2000 if len(a) == 2 else 0), int(m), int(d)).isoformat()
    except ValueError:
        return None


def parsear_texto(texto: str) -> dict:
    if not texto:
        return {}
    datos: dict = {}
    plano = re.sub(r"[ \t]+", " ", texto)

    m = re.search(r"fecha de (?:pago|vencimiento|cobro)\D{0,15}(\d{1,2})/(\d{1,2})/(\d{2,4})", plano, re.I)
    if m:
        datos["fecha_pago"] = _fecha_iso(*m.groups())
    m = re.search(r"fecha(?: de (?:emisi[oó]n|operaci[oó]n|transferencia))?\D{0,15}(\d{1,2})/(\d{1,2})/(\d{2,4})", plano, re.I) \
        or re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", plano)
    if m:
        datos["fecha"] = _fecha_iso(*m.groups())

    m = re.search(r"(?:importe|monto|total)[^\d\n]{0,25}(\d{1,3}(?:\.\d{3})*,\d{2})", plano, re.I) \
        or re.search(r"\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})", plano)
    if m:
        datos["importe"] = parsear_importe(m.group(1))
    if re.search(r"u\$s|usd|d[oó]lares", plano, re.I):
        datos["moneda"] = "USD"

    m = re.search(r"(?:destinatario|beneficiario|cuit\s*/?\s*cuil\s*(?:del\s*)?destino|cuit destino)[^\d\n]{0,40}(\d{2}-?\d{8}-?\d)", plano, re.I)
    cuits = [formatear_cuit(c) for c in RE_CUIT_SUELTO.findall(plano)]
    if m:
        datos["cuit"] = formatear_cuit(m.group(1))
    elif len(set(cuits)) == 1:
        datos["cuit"] = cuits[0]

    m = re.search(r"(?i:destinatario|beneficiario|titular(?: de la cuenta)? destino|a nombre de|raz[oó]n social)[ \t]*:?[ \t]*"
                  r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ .&,]{3,60})", plano)
    if m:
        datos["razon_social"] = m.group(1).strip(" ,.")

    m = re.search(r"\b(\d{22})\b", plano)
    if m:
        datos["cuenta_destino"] = m.group(1)

    m = re.search(r"(?:n[uú]mero de operaci[oó]n|nro\.? de operaci[oó]n|id de operaci[oó]n|n[uú]mero de transacci[oó]n|"
                  r"c[oó]digo de (?:operaci[oó]n|transferencia)|referencia)\s*:?\s*([A-Za-z0-9-]{5,})", plano, re.I)
    if m:
        datos["id_operacion"] = m.group(1)

    m = re.search(r"cheque\s*(?:n[°º.]?|nro\.?|n[uú]mero)?\s*:?\s*(\d{3,})", plano, re.I)
    if m:
        datos["numero_cheque"] = m.group(1)
        datos["medio_pago"] = "Cheque"
    elif re.search(r"transferencia", plano, re.I):
        datos["medio_pago"] = "Transferencia"
        datos["tipo_comprobante"] = "Comprobante de transferencia"
    return datos


# ─── Orquestación ──────────────────────────────────────────────────────────────

def leer(adjunto: Adjunto) -> DatosComprobante:
    datos = DatosComprobante(url=adjunto.url, nombre_archivo=adjunto.nombre or "", sha256=adjunto.sha256)
    datos.completar(parsear_nombre(adjunto.nombre or ""), "nombre_archivo")

    s = settings()
    file_id = id_drive(adjunto.url)
    if not (s.leer_adjuntos and s.tiene_oauth_google and file_id):
        datos.error = "adjunto_no_leido"
        return datos

    try:
        from app import sheets
        contenido, nombre, mime = sheets.descargar_drive(file_id)
    except Exception as e:
        logger.error("No se pudo bajar el adjunto %s: %s", file_id, e)
        datos.error = f"descarga: {type(e).__name__}"
        return datos
    return leer_bytes(contenido, nombre, adjunto.mime or mime, datos)


def leer_bytes(contenido: bytes, nombre: str, mime: str, datos: DatosComprobante | None = None) -> DatosComprobante:
    """Lo que se lee de un archivo ya bajado. Separado de `leer` para poder probarlo con un
    archivo local, como el certificado de ejemplo de tests/fixtures."""
    datos = datos or DatosComprobante()
    if not datos.sha256:
        datos.sha256 = hashlib.sha256(contenido).hexdigest()
    if nombre and not datos.nombre_archivo:
        datos.nombre_archivo = nombre
        datos.completar(parsear_nombre(nombre), "nombre_archivo")

    texto = texto_pdf(contenido) if mime == "application/pdf" else ""
    datos.texto = texto
    if texto:
        datos.completar(parsear_texto(texto), "pdf_texto")

    if datos.importe is not None and datos.fecha:
        return datos  # alcanzó sin modelo
    if not llm.disponible():
        return datos
    extraido, uso = llm.extraer_comprobante(contenido, mime, texto or None)
    datos.uso_llm = True
    if extraido:
        extraido["razon_social"] = extraido.get("razon_social_destinatario")
        extraido["cuit"] = formatear_cuit(extraido.get("cuit_destinatario"))
        extraido["cuit_originante"] = formatear_cuit(extraido.get("cuit_originante"))
        datos.completar(extraido, "vision" if not texto else "pdf_llm")
    else:
        datos.error = uso.get("error")
    return datos
