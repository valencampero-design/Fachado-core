"""Recalcula las vistas del tablero y las cuentas corrientes por obra (CONTEXTO-FACHADO.md §5.21).

Lo corre un cron de Railway **cada noche a las 3, hora argentina** (`0 6 * * *` en UTC), como
un servicio aparte que solo ejecuta esto y termina, igual que `cierre-semanal`. Llama al motor
por HTTP: el motor lee los libros y reescribe las hojas derivadas (VISTA_*, CC_*, y
VISTA_PERSONAL en el libro personal). Nunca toca MOVIMIENTOS.

    python scripts/recalcular_vistas.py

Variables: MOTOR_URL (p. ej. https://web-production-6c935.up.railway.app) y MOTOR_API_KEY.
Es idempotente: correrlo dos veces deja lo mismo.
"""
import json
import os
import sys

import httpx


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    url, clave = os.getenv("MOTOR_URL", "").rstrip("/"), os.getenv("MOTOR_API_KEY", "")
    if not (url and clave):
        print("Faltan MOTOR_URL y/o MOTOR_API_KEY")
        return 2
    r = httpx.post(f"{url}/vistas/recalcular", json={}, headers={"X-API-Key": clave}, timeout=600)
    print(r.status_code, json.dumps(r.json(), ensure_ascii=False, indent=2))
    return 0 if r.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
