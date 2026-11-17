"""M-000024 (Austral · Maximiliano Pelegrini, $ 324.522, 14/10) estaba con un rubro de obra
(Mano de obra › Contratistas, hoy 2.1 Contratista principal). En Austral solo van rubros de
estructura (§5.12 v1.12): Valen eligió Varios › Varios (A12.1) el 17/11.

Por contraasiento (§5.19), con las mismas funciones que las correcciones del 9/10.
Simulacro por defecto, sobre una copia en memoria del libro del estudio. Idempotente: msg_id fijo.

    python scripts/migraciones/2026_11_17_m000024_varios.py
    python scripts/migraciones/2026_11_17_m000024_varios.py --aplicar
"""
import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, ".")
from app import maestros  # noqa: E402
from app.libro import LibroSheets  # noqa: E402

_ruta = Path(__file__).with_name("2026_10_09_correcciones.py")
_spec = importlib.util.spec_from_file_location("correcciones_9_10", _ruta)
nueve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nueve)

CORRECCION = nueve.Correccion(
    "M-000024", {"rubro_1": "Varios", "rubro_2": "Varios"},
    "En Austral solo rubros de estructura: Varios › Varios (A12.1), elegido por Valen el 17/11")


async def correr(args) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    nueve.PREFIJO = "correccion-2026-11-17"
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
    print(f"{'APLICANDO' if args.aplicar else 'SIMULACRO'} · M-000024 a Varios › Varios")
    errores = await nueve.corregir(CORRECCION, estudio, None, archivador, m)
    if not args.aplicar:
        print("\n(simulacro: no se escribió nada. Correr con --aplicar)")
    return 1 if errores else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true", help="escribir en el libro real (sin esto, simulacro)")
    return asyncio.run(correr(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
