"""Prueba cada credencial del motor con una llamada mínima de solo lectura. Nunca imprime un valor.

Para correr después de rotar (docs/seguridad/rotacion-2026-10-22.md en chatbot-contable), con
las variables de cada servicio del proyecto Railway del motor:

    railway run --service web python scripts/verificar_credenciales.py
    railway run --service cierre-semanal python scripts/verificar_credenciales.py   # modo cron
    railway run --service vistas python scripts/verificar_credenciales.py           # modo cron
    python scripts/verificar_credenciales.py                                        # local, con el .env

Qué prueba (OK / FALLA / OMITIDO por NOMBRE de variable; de un secreto, a lo sumo los últimos
4 caracteres, para saber si es el viejo o el nuevo):

- Servicio web: que estén todas las obligatorias (la misma validación que el arranque);
  ANTHROPIC_API_KEY con un mensaje de 1 token; la service account leyendo el título del Master
  y de «FACHADO — Personal»; el OAuth listando 1 archivo de Drive y la carpeta de comprobantes;
  MOTOR_API_KEY (y MOTOR_API_KEY_ANTERIOR si está) contra GET /salud y GET /salud/auth del motor
  publicado.
- Modo cron (sin FACHADO_SHEET_ID, con MOTOR_URL): MOTOR_URL y MOTOR_API_KEY contra el motor.

Sale con 0 si no hubo ninguna FALLA.
"""
import argparse
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import httpx  # noqa: E402

from app import seguridad  # noqa: E402  (carga el .env vía app.config)
from app.config import settings  # noqa: E402

MODELO_PRUEBA = "claude-haiku-5-5"
_fallas = 0


def fin(valor: str | None) -> str:
    """Los últimos 4 caracteres, para identificar cuál está cargada. Nunca más."""
    return f"(…{valor[-4:]})" if valor and len(valor) >= 12 else ""


def informe(estado: str, nombre: str, detalle: str = "") -> None:
    global _fallas
    if estado == "FALLA":
        _fallas += 1
    print(f"  {estado:<8} {nombre}{'  ' + seguridad.redactar(detalle) if detalle else ''}", flush=True)


def _error(e: Exception) -> str:
    estado = getattr(getattr(e, "resp", None), "status", None) or getattr(getattr(e, "response", None), "status_code", None)
    return f"{type(e).__name__}{' HTTP ' + str(estado) if estado else ''}"


def presencia():
    print("\nVariables obligatorias del servicio web")
    problemas = seguridad.problemas_de_entorno()
    for p in problemas:
        informe("FALLA", p)
    if not problemas:
        informe("OK", "todas las obligatorias están cargadas")
    for aviso in seguridad.advertencias_de_entorno():
        informe("AVISO", aviso)


def anthropic_key():
    print("\nAnthropic (un mensaje de 1 token)")
    s = settings()
    if not s.llm_habilitado:
        return informe("OMITIDO", "ANTHROPIC_API_KEY", "LLM_HABILITADO=false")
    if not s.anthropic_api_key:
        return informe("FALLA", "ANTHROPIC_API_KEY", "no está cargada")
    import anthropic

    try:
        anthropic.Anthropic(api_key=s.anthropic_api_key, max_retries=0).messages.create(
            model=os.getenv("VERIFICAR_MODELO", MODELO_PRUEBA), max_tokens=1, messages=[{"role": "user", "content": "ok"}])
        informe("OK", f"ANTHROPIC_API_KEY {fin(s.anthropic_api_key)}")
    except anthropic.AuthenticationError:
        informe("FALLA", f"ANTHROPIC_API_KEY {fin(s.anthropic_api_key)}", "Anthropic la rechaza (revocada o mal copiada)")
    except anthropic.PermissionDeniedError:
        informe("FALLA", f"ANTHROPIC_API_KEY {fin(s.anthropic_api_key)}", "sin permiso (¿key deshabilitada?)")
    except Exception as e:  # noqa: BLE001
        informe("FALLA", f"ANTHROPIC_API_KEY {fin(s.anthropic_api_key)}", _error(e))


def google_service_account():
    print("\nGoogle · service account (lee el título de cada Sheet)")
    s = settings()
    if not (s.google_credentials_json or s.google_credentials_path):
        return informe("FALLA", "GOOGLE_CREDENTIALS_JSON", "no está cargada")
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    try:
        info = (json.loads(s.google_credentials_json) if s.google_credentials_json
                else json.loads(Path(s.google_credentials_path).read_text(encoding="utf-8")))
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        servicio = build("sheets", "v4", credentials=creds, cache_discovery=False)
    except Exception as e:  # noqa: BLE001
        return informe("FALLA", "GOOGLE_CREDENTIALS_JSON", f"no se pudo armar la credencial: {_error(e)}")
    informe("OK", "GOOGLE_CREDENTIALS_JSON", f"service account {info.get('client_email', '?')}, "
             f"key id …{str(info.get('private_key_id', ''))[-4:]}")
    for var, sid in (("FACHADO_SHEET_ID", s.sheet_id), ("FACHADO_PERSONAL_SHEET_ID", s.personal_sheet_id)):
        if not sid:
            informe("FALLA" if var == "FACHADO_SHEET_ID" else "AVISO", var, "vacía")
            continue
        try:
            titulo = servicio.spreadsheets().get(spreadsheetId=sid, fields="properties.title").execute()["properties"]["title"]
            informe("OK", var, f"«{titulo}»")
        except Exception as e:  # noqa: BLE001
            informe("FALLA", var, f"{_error(e)} (¿el Sheet está compartido con la service account nueva, como Editor?)")


def google_oauth():
    print("\nGoogle · OAuth de usuario (Drive)")
    s = settings()
    if not s.tiene_oauth_google:
        return informe("FALLA", "GOOGLE_OAUTH_CLIENT_ID/SECRET/REFRESH_TOKEN", "falta alguna")
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(token=None, refresh_token=s.google_refresh_token, client_id=s.google_client_id,
                        client_secret=s.google_client_secret, token_uri="https://oauth2.googleapis.com/token",
                        scopes=["https://www.googleapis.com/auth/drive.file"])
    try:
        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        archivos = drive.files().list(pageSize=1, fields="files(id)").execute().get("files", [])
        informe("OK", f"GOOGLE_OAUTH_* (secret {fin(s.google_client_secret)}, refresh {fin(s.google_refresh_token)})",
                f"Drive responde; {len(archivos)} archivo listado")
    except RefreshError as e:
        texto = str(e)
        motivo = ("invalid_client: el client secret no es el de ese client id" if "invalid_client" in texto
                  else "invalid_grant: el refresh token fue revocado o es de otro client" if "invalid_grant" in texto
                  else "Google no renovó el token")
        return informe("FALLA", "GOOGLE_OAUTH_*", motivo)
    except Exception as e:  # noqa: BLE001
        return informe("FALLA", "GOOGLE_OAUTH_*", _error(e))
    if s.drive_carpeta_comprobantes_id:
        try:
            nombre = drive.files().get(fileId=s.drive_carpeta_comprobantes_id, fields="name").execute().get("name")
            informe("OK", "DRIVE_CARPETA_COMPROBANTES_ID", f"«{nombre}»")
        except Exception as e:  # noqa: BLE001
            informe("FALLA", "DRIVE_CARPETA_COMPROBANTES_ID", f"{_error(e)} (drive.file solo ve lo que creó este cliente OAuth)")


def clave_motor(url: str):
    print("\nMOTOR_API_KEY contra el motor publicado")
    if not url:
        return informe("OMITIDO", "MOTOR_API_KEY", "sin URL del motor (MOTOR_URL, RAILWAY_PUBLIC_DOMAIN o --url)")
    try:
        r = httpx.get(f"{url}/salud", timeout=20)
        informe("OK" if r.status_code == 200 else "FALLA", "URL del motor", f"/salud HTTP {r.status_code}")
    except httpx.HTTPError as e:
        return informe("FALLA", "URL del motor", _error(e))
    for var, esperado in (("MOTOR_API_KEY", "actual"), ("MOTOR_API_KEY_ANTERIOR", "anterior")):
        clave = os.getenv(var, "")
        if not clave:
            if var == "MOTOR_API_KEY":
                informe("FALLA", var, "no está cargada")
            continue
        try:
            r = httpx.get(f"{url}/salud/auth", headers={"X-API-Key": clave}, timeout=20)
            if r.status_code == 404:  # motor sin desplegar la versión con /salud/auth
                r = httpx.get(f"{url}/movimientos/NO-EXISTE", params={"telefono": "0"}, headers={"X-API-Key": clave},
                              timeout=20)
                ok = r.status_code not in (401, 503)
                informe("OK" if ok else "FALLA", f"{var} {fin(clave)}",
                        f"motor sin /salud/auth (versión vieja): HTTP {r.status_code}")
                continue
            if r.status_code != 200:
                informe("FALLA", f"{var} {fin(clave)}", f"el motor publicado la rechaza (HTTP {r.status_code}); "
                        "si recién la cargaste, ¿se desplegó?")
                continue
            cual = r.json().get("clave")
            if var == "MOTOR_API_KEY" and cual == "anterior":
                informe("AVISO", f"{var} {fin(clave)}", "el motor publicado la toma como ANTERIOR: este servicio "
                        "todavía tiene la clave vieja")
            else:
                informe("OK" if cual == esperado else "AVISO", f"{var} {fin(clave)}", f"el motor la toma como «{cual}»")
        except httpx.HTTPError as e:
            informe("FALLA", var, _error(e))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    dominio = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
    defecto = (os.getenv("MOTOR_URL") or (f"https://{dominio}" if dominio else "")).rstrip("/")
    p.add_argument("--url", default=defecto, help="URL pública del motor (default: MOTOR_URL o RAILWAY_PUBLIC_DOMAIN)")
    p.add_argument("--cron", action="store_true", help="solo MOTOR_URL y MOTOR_API_KEY (servicios cierre-semanal y vistas)")
    args = p.parse_args()
    cron = args.cron or (not settings().sheet_id and bool(os.getenv("MOTOR_URL")))
    if cron:
        print("Modo cron: solo la clave contra el motor")
    else:
        presencia()
        anthropic_key()
        google_service_account()
        google_oauth()
    clave_motor(args.url.rstrip("/"))
    print(f"\n{'TODO OK' if not _fallas else str(_fallas) + ' FALLA(S)'}")
    return 1 if _fallas else 0


if __name__ == "__main__":
    sys.exit(main())
