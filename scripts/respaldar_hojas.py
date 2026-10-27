"""Copia de respaldo de hojas del Master antes de una migración: cada hoja se duplica como
`<HOJA>_bak_<fecha>` dentro del mismo libro (handoff del 27/10, parte 1.8).

Idempotente: si la copia ya existe, no la pisa. Después de copiar verifica que la copia tenga
exactamente los mismos valores que el original. Nunca toca MOVIMIENTOS ni el libro personal.

    python scripts/respaldar_hojas.py RUBROS ALIAS CONTRATISTAS
    python scripts/respaldar_hojas.py RUBROS --fecha 2026-10-27
"""
import argparse
import sys
from datetime import date

sys.path.insert(0, ".")
from app import sheets  # noqa: E402
from app.config import settings  # noqa: E402

PROHIBIDAS = {"MOVIMIENTOS"}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hojas", nargs="+")
    ap.add_argument("--fecha", default=date.today().isoformat())
    args = ap.parse_args()
    if PROHIBIDAS & set(args.hojas):
        print(f"No se respaldan con este script: {sorted(PROHIBIDAS & set(args.hojas))}")
        return 2
    sid = settings().sheet_id
    existentes = sheets.estructura(sid)
    codigo = 0
    for hoja in args.hojas:
        copia = f"{hoja}_bak_{args.fecha}"
        if hoja not in existentes:
            print(f"  ✗ {hoja}: no existe")
            codigo = 1
            continue
        if copia in existentes:
            print(f"  · {copia} ya existe: no se pisa")
        else:
            sheets.modificar(sid, [{"duplicateSheet": {"sourceSheetId": existentes[hoja]["id"], "newSheetName": copia,
                                                       "insertSheetIndex": len(existentes)}}])
            print(f"  + {copia}")
        original = sheets.leer_hojas(sid, [f"{hoja}!A:Z"])[hoja]
        respaldo = sheets.leer_hojas(sid, [f"'{copia}'!A:Z"])[copia]
        igual = original == respaldo
        print(f"    {len(original)} filas · {'igual al original' if igual else 'DISTINTO del original'}")
        if not igual:
            codigo = 1
    return codigo


if __name__ == "__main__":
    sys.exit(main())
