"""Genera el refresh token OAuth del motor (Drive, y opcionalmente Sheets).

Tiene que ser el MISMO cliente OAuth «App de escritorio» que usa el gateway: `drive.file`
solo da acceso a los archivos que subió esa app, que son los adjuntos que hay que leer.

Se corre una sola vez, en tu máquina (abre el navegador), autorizando con
valencampero@gmail.com. Requiere `pip install google-auth-oauthlib` (no está en
requirements.txt: el servicio no lo usa).

    python scripts/get_google_token.py <ruta_al_client_secret.json>
    python scripts/get_google_token.py <client_secret.json> --con-sheets

`--con-sheets` agrega el scope para leer el Sheet maestro. Solo hace falta si NO se usa la
service account: es un scope sensible, y con él publicar la app OAuth requiere verificación
de Google. Lo recomendado es compartir el Sheet con la service account y no usar este flag.

Recordatorio: mientras la app OAuth esté en «Prueba», el refresh token caduca a los 7 días.
"""
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

sys.path.insert(0, ".")
from app.sheets import SCOPES_DRIVE, SCOPES_SHEETS  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python scripts/get_google_token.py <ruta_al_client_secret.json> [--con-sheets]")
        sys.exit(1)
    scopes = SCOPES_DRIVE + (SCOPES_SHEETS if "--con-sheets" in sys.argv else [])
    print("Scopes:", " ".join(scopes))
    flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], scopes)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        print("No se devolvió refresh_token. Volvé a correrlo.")
        sys.exit(1)
    print("\n=== Variables de entorno ===\n")
    print(f"GOOGLE_OAUTH_CLIENT_ID={creds.client_id}")
    print(f"GOOGLE_OAUTH_CLIENT_SECRET={creds.client_secret}")
    print(f"GOOGLE_OAUTH_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
