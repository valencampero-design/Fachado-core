"""Copia de respaldo de hojas antes de una migración (handoff del 27/10, parte 1.8; ampliado
el 7/11 para el handoff de la reunión del 6/11).

Dos formas:

- **Pestaña** (por defecto, para los maestros y las hojas derivadas): cada hoja se duplica como
  `<HOJA>_bak_<fecha>` dentro del mismo libro. Idempotente: si la copia ya existe, no la pisa.
  Después de copiar verifica que la copia tenga exactamente los mismos valores que el original.
  `MOVIMIENTOS` **no** se duplica como pestaña: un segundo libro de movimientos adentro del
  mismo archivo es una trampa para cualquiera que lea el Sheet.
- **Archivo** (`--archivo CARPETA`): baja los valores de cada hoja a
  `CARPETA/<libro>_<HOJA>_<fecha>.json` (los valores con formato y sin formato) y `.csv`, y
  verifica que el archivo coincida con el Sheet. Es la forma de respaldar `MOVIMIENTOS` antes de
  agregarle filas: el libro es append-only, pero si una escritura sale mal hay con qué comparar.
  La carpeta va **fuera de los repos**: tiene datos del cliente.

`--libro personal` trabaja sobre «FACHADO — Personal» (FACHADO_PERSONAL_SHEET_ID) en vez del
Master.

    python scripts/respaldar_hojas.py RUBROS ALIAS CONTRATISTAS
    python scripts/respaldar_hojas.py OBRAS CUENTAS ALIAS --fecha 2026-11-07
    python scripts/respaldar_hojas.py CC_GESSEL CC_BELELLI --libro personal
    python scripts/respaldar_hojas.py MOVIMIENTOS --archivo ../Fachado/respaldos/2026-11-07
    python scripts/respaldar_hojas.py MOVIMIENTOS --libro personal --archivo ../Fachado/respaldos/2026-11-07
"""
import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, ".")
from app import sheets  # noqa: E402
from app.config import settings  # noqa: E402

SOLO_A_ARCHIVO = {"MOVIMIENTOS"}


def _libro(nombre: str) -> str:
    s = settings()
    sid = s.personal_sheet_id if nombre == "personal" else s.sheet_id
    if not sid:
        sys.exit("Falta FACHADO_PERSONAL_SHEET_ID en el entorno" if nombre == "personal" else "Falta FACHADO_SHEET_ID")
    return sid


def _como_pestana(sid: str, hojas: list[str], fecha: str) -> int:
    existentes = sheets.estructura(sid)
    codigo = 0
    for hoja in hojas:
        copia = f"{hoja}_bak_{fecha}"
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
        original = sheets.leer_hojas(sid, [f"'{hoja}'!A:AZ"])[hoja]
        respaldo = sheets.leer_hojas(sid, [f"'{copia}'!A:AZ"])[copia]
        igual = original == respaldo
        print(f"    {len(original)} filas · {'igual al original' if igual else 'DISTINTO del original'}")
        if not igual:
            codigo = 1
    return codigo


def _a_archivo(sid: str, libro: str, hojas: list[str], fecha: str, carpeta: Path) -> int:
    carpeta.mkdir(parents=True, exist_ok=True)
    existentes = sheets.estructura(sid)
    codigo = 0
    for hoja in hojas:
        if hoja not in existentes:
            print(f"  ✗ {hoja}: no existe")
            codigo = 1
            continue
        base = carpeta / f"{libro}_{hoja}_{fecha}"
        rango = f"'{hoja}'!A:AZ"
        con_formato = sheets.leer_hojas(sid, [rango])[hoja]
        sin_formato = sheets.leer_hojas(sid, [rango], formato="UNFORMATTED_VALUE")[hoja]
        if base.with_suffix(".json").exists():
            previo = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
            igual = previo.get("valores") == con_formato
            print(f"  · {base.name}.json ya existe: no se pisa ({'igual' if igual else 'el Sheet cambió desde entonces'})")
            continue
        base.with_suffix(".json").write_text(json.dumps(
            {"libro": libro, "sheet_id": sid, "hoja": hoja, "fecha": fecha,
             "valores": con_formato, "sin_formato": sin_formato}, ensure_ascii=False), encoding="utf-8")
        with base.with_suffix(".csv").open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(con_formato)
        leido = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))["valores"]
        igual = leido == sheets.leer_hojas(sid, [rango])[hoja]
        print(f"  + {base.name}.json/.csv · {len(con_formato)} filas · {'igual al Sheet' if igual else 'DISTINTO del Sheet'}")
        if not igual:
            codigo = 1
    return codigo


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hojas", nargs="+")
    ap.add_argument("--fecha", default=date.today().isoformat())
    ap.add_argument("--libro", choices=["master", "personal"], default="master")
    ap.add_argument("--archivo", metavar="CARPETA", help="bajar los valores a archivos en vez de duplicar la pestaña")
    args = ap.parse_args()
    sid = _libro(args.libro)
    if args.archivo:
        return _a_archivo(sid, args.libro, args.hojas, args.fecha, Path(args.archivo))
    if SOLO_A_ARCHIVO & set(args.hojas):
        print(f"{sorted(SOLO_A_ARCHIVO & set(args.hojas))} no se duplica como pestaña: usar --archivo CARPETA")
        return 2
    return _como_pestana(sid, args.hojas, args.fecha)


if __name__ == "__main__":
    sys.exit(main())
