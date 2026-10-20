"""Recalcula las vistas del tablero y las cuentas corrientes por obra (CONTEXTO-FACHADO.md §5.21).

Lo corre un cron de Railway **cada noche a las 3, hora argentina** (`0 6 * * *` en UTC), como
un servicio aparte que solo ejecuta esto y termina, igual que `cierre-semanal`. Llama al motor
por HTTP: el motor lee los libros y reescribe las hojas derivadas (VISTA_*, CC_*, y
VISTA_PERSONAL en el libro personal). Nunca toca MOVIMIENTOS. Los pasos para crear el servicio
están en docs/handoff-fachado-core.md.

    python scripts/recalcular_vistas.py               (escribe las hojas)
    python scripts/recalcular_vistas.py --simulacro   (qué hojas y cuántas filas escribiría, sin escribir)

Variables: MOTOR_URL (p. ej. https://web-production-6c935.up.railway.app) y MOTOR_API_KEY.
Es idempotente: correrlo dos veces deja lo mismo.

Termina con 0 si el motor escribió (o simuló) todo; si no, con un código distinto de 0 y una
línea que empieza con «ERROR» (Railway marca la corrida como fallida y el log dice por qué):
2 faltan variables, 3 el motor no contesta o tarda más de TIMEOUT segundos, 1 el motor contestó
un error.
"""
import argparse
import os
import sys

import httpx

TIMEOUT = 600  # el recálculo lee los dos libros y escribe ~25 hojas: un par de minutos


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simulacro", action="store_true", help="no escribir: mostrar qué hojas y filas escribiría")
    args = ap.parse_args()

    url, clave = os.getenv("MOTOR_URL", "").rstrip("/"), os.getenv("MOTOR_API_KEY", "")
    if not (url and clave):
        faltan = [n for n, v in (("MOTOR_URL", url), ("MOTOR_API_KEY", clave)) if not v]
        print(f"ERROR: faltan variables: {', '.join(faltan)}")
        return 2
    destino = f"{url}/vistas/recalcular"
    try:
        r = httpx.post(destino, json={"simulacro": args.simulacro}, headers={"X-API-Key": clave}, timeout=TIMEOUT)
    except httpx.TimeoutException:
        print(f"ERROR: el motor ({url}) no terminó en {TIMEOUT} s. Las hojas pueden haber quedado a medio escribir; "
              f"la próxima corrida las reescribe enteras.")
        return 3
    except httpx.HTTPError as e:
        print(f"ERROR: no pude llegar al motor ({url}): {type(e).__name__}: {e}")
        return 3
    try:
        cuerpo = r.json()
    except ValueError:
        cuerpo = None
    if r.status_code != 200 or not isinstance(cuerpo, dict):
        detalle = cuerpo.get("detail") if isinstance(cuerpo, dict) else r.text[:500]
        pista = {401: " (MOTOR_API_KEY no coincide con la del motor)", 503: " (al motor le falta configuración)"}
        print(f"ERROR: el motor contestó {r.status_code}{pista.get(r.status_code, '')}: {detalle}")
        return 1
    hojas = cuerpo.get("escribiria" if args.simulacro else "escritas") or {}
    titulo = "Simulacro: escribiría" if args.simulacro else "Escritas"
    print(f"{titulo} {len(hojas)} hojas:")
    for hoja, filas in hojas.items():
        print(f"  · {hoja}: {filas} filas")
    if not hojas:
        print("ERROR: el motor no escribió ninguna hoja")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
