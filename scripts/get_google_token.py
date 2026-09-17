"""Genera el refresh token OAuth del motor (Sheets + Drive).

Mismo cliente OAuth «App de escritorio» que usa el gateway, pero con un scope más:
el motor tiene que LEER el Sheet maestro, que no creó esta app, y `drive.file` no alcanza.

Se corre una sola vez, en tu máquina (abre el navegador), autorizando con
valencampero@gmail.com. Requiere `pip install google-auth-oauthlib` (no está en
requirements.txt: el servicio no lo usa).

    python scripts/get_google_token.py <ruta_al_client_secret.json>

Recordatorio: si la app OAuth sigue en «Prueba», el refresh token caduca a los 7 días.
"""
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

sys.path.insert(0, ".")
from app.sheets import SCOPES  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python scripts/get_google_token.py <ruta_al_client_secret.json>")
        sys.exit(1)
    flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
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
