"""Clientes de Google Sheets y Drive. Cada API con la credencial que le conviene.

- **Sheets**: service account (la misma del gateway), con el Sheet compartido con ella.
  El scope de Sheets es «sensible»: pedirlo por OAuth de usuario obliga a verificar la app
  de Google, y mientras la app está en «Prueba» el refresh token caduca a los 7 días. La
  service account no tiene consentimiento ni vencimiento. Si no hay service account
  configurada, cae a OAuth de usuario (que entonces sí necesita el scope sensible).
- **Drive**: OAuth de usuario, siempre. Una service account no tiene cuota de storage en un
  Drive personal, y `drive.file` solo alcanza a los archivos que subió esta misma app
  OAuth, que son justamente los adjuntos que subió el gateway.

httplib2 no es thread-safe: un único cliente por API y todo el trabajo de red serializado.
"""
import io
import json
import logging
import threading

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from app.config import settings

logger = logging.getLogger(__name__)

# El día que exista /confirmar, Sheets pasa a necesitar el scope de escritura
# (https://www.googleapis.com/auth/spreadsheets) y la service account tiene que ser Editor.
SCOPES_SHEETS = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SCOPES_DRIVE = ["https://www.googleapis.com/auth/drive.file"]
_TOKEN_URI = "https://oauth2.googleapis.com/token"

_lock = threading.Lock()
_clientes: dict[str, object] = {}


def _credenciales_oauth(scopes: list[str]) -> Credentials:
    s = settings()
    if not s.tiene_oauth_google:
        raise RuntimeError(
            "Faltan credenciales OAuth de Google: GOOGLE_OAUTH_CLIENT_ID, "
            "GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REFRESH_TOKEN."
        )
    return Credentials(
        token=None,
        refresh_token=s.google_refresh_token,
        client_id=s.google_client_id,
        client_secret=s.google_client_secret,
        token_uri=_TOKEN_URI,
        scopes=scopes,
    )


def _credenciales_service_account():
    """Service account, del JSON completo (Railway) o de un archivo (local)."""
    s = settings()
    if s.google_credentials_json:
        return service_account.Credentials.from_service_account_info(
            json.loads(s.google_credentials_json), scopes=SCOPES_SHEETS)
    if s.google_credentials_path:
        return service_account.Credentials.from_service_account_file(
            s.google_credentials_path, scopes=SCOPES_SHEETS)
    return None


def _cliente(api: str, version: str):
    if api not in _clientes:
        if api == "sheets":
            creds = _credenciales_service_account()
            if creds is None:
                logger.warning("Sin service account: se lee el Sheet con OAuth de usuario "
                               "(scope sensible, el token caduca si la app está en «Prueba»)")
                creds = _credenciales_oauth(SCOPES_SHEETS)
        else:
            creds = _credenciales_oauth(SCOPES_DRIVE)
        _clientes[api] = build(api, version, credentials=creds, cache_discovery=False)
    return _clientes[api]


def leer_hojas(sheet_id: str, rangos: list[str]) -> dict[str, list[list[str]]]:
    """Lee varios rangos en una sola llamada. Devuelve {nombre_hoja: filas}."""
    with _lock:
        resp = (
            _cliente("sheets", "v4")
            .spreadsheets()
            .values()
            .batchGet(spreadsheetId=sheet_id, ranges=rangos, valueRenderOption="FORMATTED_VALUE")
            .execute()
        )
    salida: dict[str, list[list[str]]] = {}
    for rango, valores in zip(rangos, resp.get("valueRanges", [])):
        hoja = rango.split("!")[0].strip("'")
        salida[hoja] = valores.get("values", [])
    return salida


def descargar_drive(file_id: str) -> tuple[bytes, str, str]:
    """Baja un archivo de Drive. Devuelve (contenido, nombre, mime)."""
    with _lock:
        drive = _cliente("drive", "v3")
        meta = drive.files().get(fileId=file_id, fields="name,mimeType").execute()
        buffer = io.BytesIO()
        descarga = MediaIoBaseDownload(buffer, drive.files().get_media(fileId=file_id))
        terminado = False
        while not terminado:
            _, terminado = descarga.next_chunk()
    return buffer.getvalue(), meta.get("name", ""), meta.get("mimeType", "")
