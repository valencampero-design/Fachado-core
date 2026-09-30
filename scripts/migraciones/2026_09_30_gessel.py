"""Gessel y «belleli» (reunión del 29/09, CONTEXTO-FACHADO.md §6 v1.7).

- **Gessel**: inmueble personal, igual que Sur, Abucoque y Belelli (misma forma de alta:
  tipo `personal`, activa, sin comitente). Va al circuito personal (§5.4, R1).
- Alias `gessel` → Gessel y `belleli` → Belelli (así lo escribió en la reunión).

Idempotente; nada se borra.

    python scripts/migraciones/2026_09_30_gessel.py                  (simulacro)
    python scripts/migraciones/2026_09_30_gessel.py --aplicar
    python scripts/migraciones/2026_09_30_gessel.py --snapshot tests/maestros_snapshot.json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _comun import Migracion  # noqa: E402

POR_QUE = "§6 v1.7: reunión del 29/09"
ALIAS = [("gessel", "Gessel", "obra"), ("belleli", "Belelli", "obra")]


def main() -> None:
    mig = Migracion(["OBRAS", "ALIAS"], __doc__)
    modelo = mig.buscar("OBRAS", obra="Sur")
    if not modelo:
        sys.exit("No está «Sur» en OBRAS: es el modelo de alta de un inmueble personal")
    if not mig.buscar("OBRAS", obra="Gessel"):
        _, sur = modelo[0]
        mig.agregar("OBRAS", {**{k: "" for k in sur}, "obra": "Gessel", "codigo": "Gessel", "tipo": sur["tipo"],
                              "estado": sur["estado"], "notas": "Inmueble personal. Se sumó el 29/09 (reunión 5)"}, POR_QUE)
    for como, obra, tipo in ALIAS:
        if not mig.buscar("OBRAS", obra=obra) and obra != "Gessel":
            sys.exit(f"No está la obra «{obra}» en OBRAS")
        if not mig.buscar("ALIAS", como_lo_dice=como, valor_canonico=obra, tipo=tipo):
            mig.agregar("ALIAS", {"como_lo_dice": como, "valor_canonico": obra, "tipo": tipo}, POR_QUE)
    mig.terminar()


if __name__ == "__main__":
    main()
