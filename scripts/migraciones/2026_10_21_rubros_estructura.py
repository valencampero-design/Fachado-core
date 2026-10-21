"""Los rubros de estructura que faltaban (CONTEXTO-FACHADO.md §5.12 v1.12, 21/10).

En Austral el bot ofrecía rubros de obra: en RUBROS no había «Gastos generales» ni
«Combustible» de estructura (fallas 1 y 2 del 20/10: el ticket de YPF de Petrus y
«Austral/Mathias»).

- RUBROS: `Estructura del estudio › Gastos generales` y `Estructura del estudio › Combustible`,
  los dos con `afecta = estructura`.
- ALIAS (tipo `rubro`, nuevo el 21/10; `valor_canonico` = el rubro_2):
  - `combustible`, `nafta`, `gasoil` → Combustible;
  - `gastos generales`, `generales` → Gastos generales.

Idempotente; nada se borra.

    python scripts/migraciones/2026_10_21_rubros_estructura.py                  (simulacro)
    python scripts/migraciones/2026_10_21_rubros_estructura.py --aplicar
    python scripts/migraciones/2026_10_21_rubros_estructura.py --snapshot tests/maestros_snapshot.json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _comun import Migracion  # noqa: E402

POR_QUE = "§5.12 v1.12: los rubros de estructura (21/10)"
RUBRO_1 = "Estructura del estudio"
RUBROS = ["Gastos generales", "Combustible"]
ALIAS = {"combustible": "Combustible", "nafta": "Combustible", "gasoil": "Combustible",
         "gastos generales": "Gastos generales", "generales": "Gastos generales"}


def main() -> None:
    mig = Migracion(["RUBROS", "ALIAS"], __doc__)
    for rubro_2 in RUBROS:
        if not mig.buscar("RUBROS", rubro_1=RUBRO_1, rubro_2=rubro_2):
            mig.agregar("RUBROS", {"rubro_1": RUBRO_1, "rubro_2": rubro_2, "afecta": "estructura"}, POR_QUE)
    for como, rubro_2 in ALIAS.items():
        if not mig.buscar("ALIAS", como_lo_dice=como, tipo="rubro"):
            mig.agregar("ALIAS", {"como_lo_dice": como, "valor_canonico": rubro_2, "tipo": "rubro"}, POR_QUE)
    mig.terminar()


if __name__ == "__main__":
    main()
