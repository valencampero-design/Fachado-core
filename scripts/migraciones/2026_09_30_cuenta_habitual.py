"""OBRAS.cuenta_habitual (fix del arranque, 30/09): la regla 3 de «de qué cuenta salió».

CONTEXTO-FACHADO.md §5.7 (v1.7): si ni el mensaje ni el comprobante dicen la cuenta, manda la
obra: **en Lennon, `Pagado por el comitente`** (§5.9). El handoff del fix decía que esa regla
ya existía; en el motor no estaba. Para no escribir «Lennon» en el código, la obra lo dice en
el maestro.

    python scripts/preparar_sheet.py --aplicar                       (crea la columna)
    python scripts/migraciones/2026_09_30_cuenta_habitual.py         (simulacro)
    python scripts/migraciones/2026_09_30_cuenta_habitual.py --aplicar
    python scripts/migraciones/2026_09_30_cuenta_habitual.py --snapshot tests/maestros_snapshot.json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _comun import Migracion  # noqa: E402

CUENTA_HABITUAL = {"Lennon": "Pagado por el comitente"}


def main() -> None:
    mig = Migracion(["OBRAS"], __doc__)
    mig.asegurar_columna("OBRAS", "cuenta_habitual")
    for obra, cuenta in CUENTA_HABITUAL.items():
        filas = mig.buscar("OBRAS", obra=obra)
        if not filas:
            sys.exit(f"No está la obra «{obra}» en OBRAS")
        for n, _ in filas:
            mig.poner("OBRAS", n, "cuenta_habitual", cuenta, "§5.7 regla 3 y §5.9: el comitente paga directo")
    mig.terminar()


if __name__ == "__main__":
    main()
