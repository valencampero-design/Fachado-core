"""Seguridad del motor (incidente Railway, 22/10/2026): la clave del gateway y los crons, y
ningún secreto en los logs.

Ver docs/seguridad/ en este repo y docs/seguridad/rotacion-2026-10-22.md en chatbot-contable.
"""
import hmac
import json
import logging
import os
import re

logger = logging.getLogger(__name__)


# ── Qué variables son secretas ────────────────────────────────────────────────
# Las conocidas, más cualquier otra cuyo nombre lo delate. Misma lógica que el gateway
# (chatbot-contable/services/seguridad.py): si se cambia una, cambiar la otra.
SECRETOS = (
    "MOTOR_API_KEY", "MOTOR_API_KEY_ANTERIOR", "ANTHROPIC_API_KEY",
    "GOOGLE_CREDENTIALS_JSON", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN",
)
_NOMBRE_SECRETO = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CLAVE|CREDENTIALS_JSON)", re.I)


def _valores_secretos() -> list[tuple[str, str]]:
    """(nombre, valor) de cada variable secreta cargada, del valor más largo al más corto."""
    pares = []
    for nombre, valor in os.environ.items():
        if not valor or len(valor) < 6:
            continue
        if nombre in SECRETOS or _NOMBRE_SECRETO.search(nombre):
            pares.append((nombre, valor))
            if nombre == "GOOGLE_CREDENTIALS_JSON":
                try:
                    clave = json.loads(valor).get("private_key") or ""
                    if len(clave) >= 20:
                        pares.append((nombre, clave))
                        pares.append((nombre, clave.replace("\n", "\\n")))
                except (ValueError, AttributeError):
                    pass
    return sorted(pares, key=lambda p: -len(p[1]))


# Formatos de credenciales conocidos, por si una aparece sin estar en el entorno.
_PATRONES = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), r"\1[REDACTADO]"),
    (re.compile(r"(?i)\b((?:hub\.verify_token|access_token|appsecret_proof|client_secret|refresh_token"
                r"|api_key|apikey|key|token|secret|password|hash|sig|signature)=)[^&\s\"'<>]+"), r"\1[REDACTADO]"),
    (re.compile(r"(?i)((?:x-api-key|x-hensel-token|authorization|x-hub-signature-256)[\"']?\s*[:=]\s*[\"']?)"
                r"[^\s\"',}]+"), r"\1[REDACTADO]"),
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"), "[REDACTADO:anthropic]"),
    (re.compile(r"\bEAA[A-Za-z0-9]{30,}"), "[REDACTADO:meta]"),
    (re.compile(r"GOCSPX-[A-Za-z0-9_-]{10,}"), "[REDACTADO:google-oauth]"),
    (re.compile(r"\b1//0[A-Za-z0-9_-]{20,}"), "[REDACTADO:google-refresh]"),
    (re.compile(r"\bya29\.[A-Za-z0-9_-]{20,}"), "[REDACTADO:google-access]"),
    (re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), "[REDACTADO:groq]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(-----END [A-Z ]*PRIVATE KEY-----|$)", re.S),
     "[REDACTADO:private-key]"),
]


def redactar(texto) -> str:
    """El texto sin ningún secreto. Nunca falla: ante la duda, devuelve algo redactado."""
    if texto is None:
        return ""
    s = texto if isinstance(texto, str) else str(texto)
    for nombre, valor in _valores_secretos():
        if valor in s:
            s = s.replace(valor, f"[{nombre}]")
    for patron, reemplazo in _PATRONES:
        s = patron.sub(reemplazo, s)
    return s


class FiltroSecretos(logging.Filter):
    """Redacta mensaje, argumentos y traza de cada registro antes de que se escriba."""

    _fmt = logging.Formatter()

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redactar(record.msg)
            if isinstance(record.args, tuple):
                # Se conserva la tupla: el formateador de uvicorn.access la desarma por posición.
                record.args = tuple(a if isinstance(a, (int, float, bool, type(None))) else redactar(a)
                                    for a in record.args)
            elif record.args:
                record.msg, record.args = redactar(record.getMessage()), None
            if record.exc_info and not record.exc_text:
                record.exc_text = self._fmt.formatException(record.exc_info)
            if record.exc_text:
                record.exc_text = redactar(record.exc_text)
        except Exception:  # un log nunca tumba el request
            record.msg, record.args, record.exc_info, record.exc_text = "[registro no redactable]", None, None, None
        return True


_LOGGERS_CON_HANDLER = ("", "uvicorn", "uvicorn.error", "uvicorn.access", "gunicorn.error", "gunicorn.access")


def instalar_filtro_logs() -> None:
    """Pone FiltroSecretos en todos los handlers (el filtro de un logger no alcanza a sus hijos)."""
    for nombre in _LOGGERS_CON_HANDLER:
        for handler in logging.getLogger(nombre).handlers:
            if not any(isinstance(f, FiltroSecretos) for f in handler.filters):
                handler.addFilter(FiltroSecretos())


# ── La clave del gateway y los crons ──────────────────────────────────────────

def clave_que_coincide(recibida: str | None) -> str | None:
    """"actual" si `recibida` es MOTOR_API_KEY, "anterior" si es MOTOR_API_KEY_ANTERIOR, si no None.

    MOTOR_API_KEY_ANTERIOR existe solo durante una rotación: motor con las dos → gateway y crons
    con la nueva → sacar la anterior. Las dos comparaciones corren siempre (sin cortocircuito).
    """
    if not recibida:
        return None
    resultado = None
    for nombre, var in (("anterior", "MOTOR_API_KEY_ANTERIOR"), ("actual", "MOTOR_API_KEY")):
        esperada = os.getenv(var, "")
        if esperada and hmac.compare_digest(recibida.encode(), esperada.encode()):
            resultado = nombre
    return resultado


# ── Arranque ──────────────────────────────────────────────────────────────────

OAUTH_DRIVE = ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN")


def problemas_de_entorno() -> list[str]:
    """Lo que impide arrancar el servicio web, por NOMBRE de variable (nunca el valor)."""
    from app.config import settings

    s = settings()
    problemas = [] if s.motor_api_key else ["falta MOTOR_API_KEY"]
    offline = bool(s.maestros_snapshot)  # tests y pruebas locales: sin Sheet ni Drive
    if not offline:
        if not s.sheet_id:
            problemas.append("falta FACHADO_SHEET_ID")
        if s.google_credentials_json:
            try:
                datos = json.loads(s.google_credentials_json)
                if not (isinstance(datos, dict) and datos.get("client_email") and datos.get("private_key")):
                    problemas.append("GOOGLE_CREDENTIALS_JSON no es el JSON de una service account (sin client_email/private_key)")
            except ValueError:
                problemas.append("GOOGLE_CREDENTIALS_JSON no es JSON válido")
        elif not s.google_credentials_path:
            problemas.append("falta GOOGLE_CREDENTIALS_JSON (la service account que escribe el Sheet)")
        # Drive con OAuth de usuario: /confirmar mueve los comprobantes y el lector los baja.
        problemas += [f"falta {v} (Drive)" for v in OAUTH_DRIVE if not os.getenv(v)]
    if s.llm_habilitado and not s.anthropic_api_key:
        problemas.append("falta ANTHROPIC_API_KEY (o LLM_HABILITADO=false)")
    return problemas


def advertencias_de_entorno() -> list[str]:
    from app.config import settings

    s = settings()
    avisos = []
    if not s.personal_sheet_id and not s.maestros_snapshot:
        avisos.append("FACHADO_PERSONAL_SHEET_ID vacía: lo personal se rechaza con 503")
    if os.getenv("MOTOR_API_KEY_ANTERIOR"):
        avisos.append("MOTOR_API_KEY_ANTERIOR cargada: rotación en curso, sacarla cuando gateway y crons usen la nueva")
    return avisos


def validar_entorno() -> None:
    problemas = problemas_de_entorno()
    if problemas:
        raise RuntimeError("El motor no arranca. " + "; ".join(problemas)
                           + ". Cargá estas variables en Railway (servicio web del motor) y volvé a desplegar.")
    for aviso in advertencias_de_entorno():
        logger.warning("Entorno: %s", aviso)
    logger.info("Validación de variables de entorno: OK")
