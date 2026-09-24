"""Clientes de Google Sheets y Drive. Cada API con la credencial que le conviene.

- **Sheets**: service account (la misma del gateway), con el Sheet compartido con ella como
  **Editor**: `/confirmar` escribe. El scope de Sheets es «sensible»: pedirlo por OAuth de
  usuario obliga a verificar la app de Google, y mientras la app está en «Prueba» el refresh
  token caduca a los 7 días. La service account no tiene consentimiento ni vencimiento. Si no
  hay service account configurada, cae a OAuth de usuario.
- **Drive**: OAuth de usuario, siempre. Una service account no tiene cuota de storage en un
  Drive personal, y `drive.file` solo alcanza a los archivos que creó esta misma app OAuth:
  los adjuntos que subió el gateway y las carpetas que crea el motor.

httplib2 no es thread-safe: un único cliente por API y cada request serializado por `_lock`.
Los errores transitorios de Google (429, 5xx) se reintentan con espera creciente, soltando el
lock mientras se espera para no frenar a los demás.
"""
import io
import json
import logging
import threading
import time

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from app.config import settings

logger = logging.getLogger(__name__)

SCOPES_SHEETS = ["https://www.googleapis.com/auth/spreadsheets"]
SCOPES_DRIVE = ["https://www.googleapis.com/auth/drive.file"]
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_MIME_CARPETA = "application/vnd.google-apps.folder"

# Tres intentos: el primero, y dos reintentos esperando 1 y 2 segundos.
_REINTENTABLES = {429, 500, 502, 503, 504}
_ESPERAS = (1, 2)

_lock = threading.Lock()
_lock_clientes = threading.Lock()
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
    with _lock_clientes:
        if api not in _clientes:
            if api == "sheets":
                creds = _credenciales_service_account()
                if creds is None:
                    logger.warning("Sin service account: se usa el Sheet con OAuth de usuario "
                                   "(scope sensible, el token caduca si la app está en «Prueba»)")
                    creds = _credenciales_oauth(SCOPES_SHEETS)
            else:
                creds = _credenciales_oauth(SCOPES_DRIVE)
            _clientes[api] = build(api, version, credentials=creds, cache_discovery=False)
        return _clientes[api]


def _ejecutar(request):
    """Ejecuta un request de Google reintentando los errores transitorios."""
    for espera in (*_ESPERAS, None):
        try:
            with _lock:
                return request.execute()
        except HttpError as e:
            if e.resp.status not in _REINTENTABLES or espera is None:
                raise
            logger.warning("Google devolvió %s; reintento en %ss", e.resp.status, espera)
            time.sleep(espera)


def _valores():
    return _cliente("sheets", "v4").spreadsheets().values()


# ─── Sheets ────────────────────────────────────────────────────────────────────

def leer_hojas(sheet_id: str, rangos: list[str], formato: str = "FORMATTED_VALUE") -> dict[str, list[list]]:
    """Lee varios rangos en una sola llamada. Devuelve {nombre_hoja: filas}."""
    resp = _ejecutar(_valores().batchGet(spreadsheetId=sheet_id, ranges=rangos, valueRenderOption=formato))
    salida: dict[str, list[list]] = {}
    for rango, valores in zip(rangos, resp.get("valueRanges", [])):
        hoja = rango.split("!")[0].strip("'")
        salida[hoja] = valores.get("values", [])
    return salida


def leer_rango(sheet_id: str, rango: str, formato: str = "UNFORMATTED_VALUE") -> list[list]:
    """Sin formato por defecto: los importes vuelven como número, no como «4.032.391,70»."""
    return _ejecutar(_valores().get(spreadsheetId=sheet_id, range=rango, valueRenderOption=formato)).get("values", [])


def escribir_rango(sheet_id: str, rango: str, valores: list[list]) -> None:
    """RAW, nunca USER_ENTERED: una descripción que empiece con «=» no puede ejecutarse
    como fórmula, y los números van como números."""
    _ejecutar(_valores().update(spreadsheetId=sheet_id, range=rango, valueInputOption="RAW",
                                body={"values": valores}))


def agregar_filas(sheet_id: str, rango: str, valores: list[list]) -> str:
    """Appendea al final de la tabla. Devuelve el rango escrito («ALIAS!A42:C42»)."""
    resp = _ejecutar(_valores().append(spreadsheetId=sheet_id, range=rango, valueInputOption="RAW",
                                       insertDataOption="INSERT_ROWS", body={"values": valores}))
    return resp.get("updates", {}).get("updatedRange", "")


def estructura(sheet_id: str) -> dict[str, dict]:
    """{hoja: {id, filas, columnas}}: el tamaño de la grilla, no el de los datos."""
    meta = _ejecutar(_cliente("sheets", "v4").spreadsheets().get(
        spreadsheetId=sheet_id, fields="sheets(properties(title,sheetId,gridProperties))"))
    return {h["properties"]["title"]: {
        "id": h["properties"]["sheetId"],
        "filas": h["properties"]["gridProperties"]["rowCount"],
        "columnas": h["properties"]["gridProperties"]["columnCount"],
    } for h in meta["sheets"]}


def modificar(sheet_id: str, requests: list[dict]) -> dict:
    """batchUpdate estructural: agregar hojas, ampliar la grilla."""
    return _ejecutar(_cliente("sheets", "v4").spreadsheets().batchUpdate(
        spreadsheetId=sheet_id, body={"requests": requests}))


# ─── Drive ─────────────────────────────────────────────────────────────────────

def _drive():
    return _cliente("drive", "v3").files()


def descargar_drive(file_id: str) -> tuple[bytes, str, str]:
    """Baja un archivo de Drive. Devuelve (contenido, nombre, mime)."""
    meta = _ejecutar(_drive().get(fileId=file_id, fields="name,mimeType"))
    buffer = io.BytesIO()
    with _lock:
        descarga = MediaIoBaseDownload(buffer, _drive().get_media(fileId=file_id))
        terminado = False
        while not terminado:
            _, terminado = descarga.next_chunk()
    return buffer.getvalue(), meta.get("name", ""), meta.get("mimeType", "")


def metadata_drive(file_id: str) -> dict:
    return _ejecutar(_drive().get(fileId=file_id, fields="id,name,mimeType,parents,webViewLink"))


def carpeta_drive(nombre: str, padre_id: str | None) -> str:
    """Id de la carpeta `nombre` dentro de `padre_id` (o en la raíz), creándola si no existe.
    Con `drive.file` la búsqueda solo ve carpetas que creó esta app, que es lo que se quiere."""
    escapado = nombre.replace("\\", "\\\\").replace("'", "\\'")
    q = f"name = '{escapado}' and mimeType = '{_MIME_CARPETA}' and trashed = false"
    q += f" and '{padre_id}' in parents" if padre_id else " and 'root' in parents"
    encontradas = _ejecutar(_drive().list(q=q, fields="files(id)", pageSize=1)).get("files", [])
    if encontradas:
        return encontradas[0]["id"]
    cuerpo = {"name": nombre, "mimeType": _MIME_CARPETA, **({"parents": [padre_id]} if padre_id else {})}
    return _ejecutar(_drive().create(body=cuerpo, fields="id"))["id"]


def mover_drive(file_id: str, destino_id: str, nombre: str) -> str:
    """Mueve y renombra. El id del archivo no cambia, así que el link viejo sigue sirviendo.
    Idempotente: si ya está en el destino solo lo renombra, así un reintento no falla.
    Devuelve el link para verlo."""
    padres = metadata_drive(file_id).get("parents", [])
    mover = {} if destino_id in padres else {
        "addParents": destino_id, "removeParents": ",".join(padres)}
    movido = _ejecutar(_drive().update(fileId=file_id, body={"name": nombre}, fields="id,webViewLink", **mover))
    return movido.get("webViewLink", "")


def columna_a_letra(n: int) -> str:
    """1 → A, 27 → AA."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s
