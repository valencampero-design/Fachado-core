"""Las dos «Sofi» (CONTEXTO-FACHADO.md §7 v1.10, 15/10).

- **Sofía Fachado**, la hija de Gabriel (CUIT 27-47181632-4; en las transferencias «FACHADO,
  SOFIA»): contratista nuevo, gasto personal, rubro habitual `Personal › Familia`.
- **Sofía Cervera** trabaja para el estudio: deja de ser dual y pasa a estructura (Austral),
  con el rubro que el maestro ya usa para el personal del estudio,
  `Estructura del estudio › Sueldos y cargas sociales`.
- El alias `sofi` apunta a las dos: el motor desempata por el comprobante, «Retiro» o Austral,
  y si no hay ninguna señal pregunta con dos botones.

Idempotente; nada se borra.

    python scripts/migraciones/2026_10_15_sofias.py                  (simulacro)
    python scripts/migraciones/2026_10_15_sofias.py --aplicar
    python scripts/migraciones/2026_10_15_sofias.py --snapshot tests/maestros_snapshot.json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _comun import Migracion  # noqa: E402

POR_QUE = "§7 v1.10: las dos Sofía (15/10)"
FACHADO = {"contratista": "Sofía Fachado", "cuit": "27-47181632-4", "rubro_habitual_1": "Personal",
           "rubro_habitual_2": "Familia", "estado": "activo",
           "notas": "Hija de Gabriel. Gasto personal (§7 v1.10). En las transferencias, «FACHADO, SOFIA»"}
CERVERA = "Sofia Cervera"
RUBRO_CERVERA = ("Estructura del estudio", "Sueldos y cargas sociales")
NOTAS_CERVERA = ("Trabaja para el estudio: lo que se le paga es estructura (Austral), nunca personal "
                 "(§7 v1.10, 15/10). Hasta el 15/10 se preguntaba si era de obra o personal")


def main() -> None:
    mig = Migracion(["CONTRATISTAS", "ALIAS", "RUBROS"], __doc__)
    if not mig.buscar("RUBROS", rubro_1=RUBRO_CERVERA[0], rubro_2=RUBRO_CERVERA[1]):
        sys.exit(f"No está el rubro {' › '.join(RUBRO_CERVERA)} en RUBROS")
    if not mig.buscar("RUBROS", rubro_1="Personal", rubro_2="Familia"):
        sys.exit("No está el rubro Personal › Familia en RUBROS")

    cervera = mig.buscar("CONTRATISTAS", contratista=CERVERA)
    if not cervera:
        sys.exit(f"No está «{CERVERA}» en CONTRATISTAS")
    for fila, _ in cervera:  # CONTRATISTAS tiene repetidos que se fusionan al leer: todas las filas
        mig.poner("CONTRATISTAS", fila, "rubro_habitual_1", RUBRO_CERVERA[0], POR_QUE)
        mig.poner("CONTRATISTAS", fila, "rubro_habitual_2", RUBRO_CERVERA[1], POR_QUE)
        mig.poner("CONTRATISTAS", fila, "notas", NOTAS_CERVERA, f"{POR_QUE}: ya no se pregunta obra o personal")

    if not mig.buscar("CONTRATISTAS", contratista=FACHADO["contratista"]):
        mig.agregar("CONTRATISTAS", FACHADO, POR_QUE)
    for canonico in ("Sofía Cervera", FACHADO["contratista"]):
        if not mig.buscar("ALIAS", como_lo_dice="sofi", valor_canonico=canonico, tipo="contratista"):
            mig.agregar("ALIAS", {"como_lo_dice": "sofi", "valor_canonico": canonico, "tipo": "contratista"},
                        f"{POR_QUE}: «sofi» puede ser cualquiera de las dos")
    mig.terminar()


if __name__ == "__main__":
    main()
