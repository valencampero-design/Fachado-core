"""Baja los maestros del Sheet a tests/maestros_snapshot.json.

El test del corpus corre contra ese snapshot para que la métrica sea reproducible: si
sube o baja, es por un cambio de código o porque se regeneró el snapshot a propósito.

    python scripts/snapshot_maestros.py      (requiere FACHADO_SHEET_ID y OAuth de Google)
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, ".")
from app import sheets  # noqa: E402
from app.config import settings  # noqa: E402
from app.maestros import HOJAS  # noqa: E402

DESTINO = Path("tests/maestros_snapshot.json")


def main() -> None:
    s = settings()
    crudo = sheets.leer_hojas(s.sheet_id, [f"{h}!A:Z" for h in HOJAS] + ["MOVIMIENTOS!1:1"])
    salida = {"_meta": {"fuente": s.sheet_id, "tomado": date.today().isoformat(),
                        "nota": "Copia literal de las hojas maestras. Se regenera con scripts/snapshot_maestros.py."}}
    salida.update(crudo)
    DESTINO.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{DESTINO}: " + ", ".join(f"{h} {len(filas) - 1}" for h, filas in crudo.items()))


if __name__ == "__main__":
    main()
