"""M-000013 (Lennon · Miguel Soto, $ 3.000.000, 9/10) lo pagó Lennon directo, no el estudio.

Valen lo confirmó el 6/11: la transferencia no está en el extracto del estudio (revisión del
28/10). Pasa de «Banco» a «Pagado por el comitente» (§5.9), por contraasiento (§5.19), con las
mismas funciones que las correcciones del 9/10 (`2026_10_09_correcciones.py`).

Simulacro por defecto, sobre una copia en memoria del libro del estudio. Idempotente: msg_id fijo.

    python scripts/migraciones/2026_11_06_lennon_m000013.py
    python scripts/migraciones/2026_11_06_lennon_m000013.py --aplicar
"""
import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, ".")
from app import maestros  # noqa: E402
from app.libro import LibroSheets  # noqa: E402
from app.maestros import CUENTA_PAGADO_POR_COMITENTE  # noqa: E402

_ruta = Path(__file__).with_name("2026_10_09_correcciones.py")
_spec = importlib.util.spec_from_file_location("correcciones_9_10", _ruta)
nueve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nueve)

CORRECCION = nueve.Correccion(
    "M-000013", {"cuenta": CUENTA_PAGADO_POR_COMITENTE},
    "Lo pagó Lennon directo (confirmado por Valen el 6/11): la transferencia no está en el extracto del estudio")


async def correr(args) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    nueve.PREFIJO = "correccion-2026-11-06"
    m = maestros.cargar(forzar=True)
    real = LibroSheets()
    if args.aplicar:
        from app.main import obtener_archivador
        estudio, archivador = real, obtener_archivador()
    else:
        from tests.dobles import ArchivadorFalso, LibroMemoria
        filas = real.leer_movimientos()
        estudio = LibroMemoria(filas[0])
        estudio.filas = [list(f) for f in filas]
        archivador = ArchivadorFalso()
    print(f"{'APLICANDO' if args.aplicar else 'SIMULACRO'} · M-000013 a «{CUENTA_PAGADO_POR_COMITENTE}»")
    print(f"\nLennon antes:   {nueve.resumen_lennon(estudio, m)}")
    errores = await nueve.corregir(CORRECCION, estudio, None, archivador, m)
    print(f"\nLennon después: {nueve.resumen_lennon(estudio, m)}")
    if not args.aplicar:
        print("\n(simulacro: no se escribió nada. Correr con --aplicar)")
    return 1 if errores else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true", help="escribir en el libro real (sin esto, simulacro)")
    return asyncio.run(correr(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
