"""Seguridad del motor (incidente Railway, 22/10/2026). Nunca llama a Google ni a Anthropic.

    python -m tests.test_seguridad
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

CLAVE_NUEVA = "clave-nueva-del-motor-1111"
CLAVE_VIEJA = "clave-vieja-del-motor-0000"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ["MAESTROS_SNAPSHOT"] = str(RAIZ / "maestros_snapshot.json")
    os.environ["LLM_HABILITADO"] = "false"
    os.environ["LEER_ADJUNTOS"] = "false"
    os.environ["MOTOR_API_KEY"] = CLAVE_NUEVA
    os.environ.pop("MOTOR_API_KEY_ANTERIOR", None)

    from fastapi.testclient import TestClient

    from app.main import app

    fallas: list[str] = []

    def check(descripcion, condicion, detalle=""):
        ok = bool(condicion)
        print(f"  {'PASA ' if ok else 'FALLA'}  {descripcion}{'' if ok else '  → ' + str(detalle)[:600]}")
        if not ok:
            fallas.append(descripcion)

    http = TestClient(app)

    def auth(clave):
        return http.get("/salud/auth", headers={"X-API-Key": clave} if clave is not None else {})

    print("\n1 · MOTOR_API_KEY se rota sin corte")
    check("/salud sigue abierto, sin clave: 200", http.get("/salud").status_code == 200)
    r = auth(CLAVE_NUEVA)
    check("clave actual: 200 y dice «actual»", r.status_code == 200 and r.json() == {"ok": True, "clave": "actual"}, r.text)
    check("clave vieja sin MOTOR_API_KEY_ANTERIOR cargada: 401", auth(CLAVE_VIEJA).status_code == 401)
    os.environ["MOTOR_API_KEY_ANTERIOR"] = CLAVE_VIEJA
    r = auth(CLAVE_VIEJA)
    check("con MOTOR_API_KEY_ANTERIOR: la vieja entra y dice «anterior» (ese cliente falta pasar)",
          r.status_code == 200 and r.json()["clave"] == "anterior", r.text)
    check("durante la transición la nueva sigue entrando", auth(CLAVE_NUEVA).json().get("clave") == "actual")
    check("otra clave, vacía o sin header: 401", auth("otra").status_code == 401 and auth("").status_code == 401
          and auth(None).status_code == 401)
    r = http.post("/conciliar/lote", json={}, headers={"X-API-Key": CLAVE_VIEJA})
    check("la anterior vale en todos los endpoints, no solo en /salud/auth (acá falla la validación, no la clave)",
          r.status_code == 422, (r.status_code, r.text))
    del os.environ["MOTOR_API_KEY_ANTERIOR"]
    check("al sacar MOTOR_API_KEY_ANTERIOR la vieja deja de entrar", auth(CLAVE_VIEJA).status_code == 401)

    os.environ["MOTOR_API_KEY"] = ""
    r = auth(CLAVE_NUEVA)
    check("sin MOTOR_API_KEY: 503 y la respuesta no nombra la variable",
          r.status_code == 503 and "MOTOR_API_KEY" not in r.text, r.text)
    os.environ["MOTOR_API_KEY"] = CLAVE_NUEVA

    print("\n2 · Ningún secreto en los logs ni en las respuestas")
    import io
    import logging

    from app import seguridad

    os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"] = "1//0refreshDePruebaNoReal-abcdefghij"
    salida = io.StringIO()
    handler = logging.StreamHandler(salida)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(seguridad.FiltroSecretos())
    log = logging.getLogger("test_seguridad_motor")
    log.addHandler(handler)
    log.propagate = False
    log.error("headers %s", {"X-API-Key": CLAVE_NUEVA})
    try:
        raise RuntimeError(f"invalid_grant con {os.environ['GOOGLE_OAUTH_REFRESH_TOKEN']}")
    except RuntimeError:
        log.exception("Drive")
    log.info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", "/conciliar/estado?telefono=549&api_key=" + CLAVE_NUEVA,
             "1.1", 200)
    texto = salida.getvalue()
    check("el filtro saca la clave del motor y el refresh token (mensaje, traza y access log)",
          CLAVE_NUEVA not in texto and "1//0refresh" not in texto and "RuntimeError" in texto and "telefono=549" in texto,
          texto)
    del os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"]
    instalados = all(any(isinstance(f, seguridad.FiltroSecretos) for f in h.filters) for h in logging.getLogger().handlers)
    check("app.main instala el filtro en los handlers del root", bool(logging.getLogger().handlers) and instalados)

    from app.main import obtener_libro, obtener_libro_personal
    from tests.dobles import LibroMemoria

    app.dependency_overrides[obtener_libro] = lambda: LibroMemoria(["id_mov"])
    app.dependency_overrides[obtener_libro_personal] = lambda: None
    try:
        r = http.post("/cierre-semanal", json={}, headers={"X-API-Key": CLAVE_NUEVA})
        check("sin libro personal: 503 sin nombrar la variable", r.status_code == 503 and "_SHEET_ID" not in r.text, r.text)
    finally:
        app.dependency_overrides.clear()

    print(f"\n{'TODO OK' if not fallas else str(len(fallas)) + ' FALLAS'}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
