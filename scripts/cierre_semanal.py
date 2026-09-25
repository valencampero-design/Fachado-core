"""Dispara el cierre semanal de gastos personales (CONTEXTO-FACHADO.md §5.14).

Lo corre un cron de Railway **los lunes a las 8, hora argentina** (`0 11 * * 1` en UTC), como
un servicio aparte que solo ejecuta esto y termina. Llama al motor por HTTP, así el cierre usa
el mismo lock del id_mov que /confirmar.

    python scripts/cierre_semanal.py                 # la semana anterior
    python scripts/cierre_semanal.py 2026-W39        # una semana puntual

Variables: MOTOR_URL (p. ej. https://web-production-6c935.up.railway.app) y MOTOR_API_KEY.
El endpoint es idempotente: si el cron corre dos veces, la segunda no escribe nada.
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
    cuerpo = {"semana": sys.argv[1]} if len(sys.argv) > 1 else {}
    r = httpx.post(f"{url}/cierre-semanal", json=cuerpo, headers={"X-API-Key": clave}, timeout=120)
    print(r.status_code, json.dumps(r.json(), ensure_ascii=False, indent=2))
    return 0 if r.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
