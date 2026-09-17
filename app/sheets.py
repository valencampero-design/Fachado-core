"""Cliente de Google Sheets y Drive con OAuth de usuario.

Scopes: `spreadsheets.readonly` para leer el maestro (no lo creó esta app, así que
`drive.file` no alcanza) y `drive.file` para bajar los adjuntos que subió el gateway con
el mismo cliente OAuth.

httplib2 no es thread-safe: un único cliente por API y todo el trabajo de red serializado.
"""
import io
import logging
import threading

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from app.config import settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.file",
]
_TOKEN_URI = "https://oauth2.googleapis.com/token"

_lock = threading.Lock()
_clientes: dict[str, object] = {}


def _cliente(api: str, version: str):
    if api not in _clientes:
        s = settings()
        if not s.tiene_oauth_google:
            raise RuntimeError(
                "Faltan credenciales OAuth de Google: GOOGLE_OAUTH_CLIENT_ID, "
                "GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REFRESH_TOKEN."
            )
        creds = Credentials(
            token=None,
            refresh_token=s.google_refresh_token,
            client_id=s.google_client_id,
            client_secret=s.google_client_secret,
            token_uri=_TOKEN_URI,
            scopes=SCOPES,
        )
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
