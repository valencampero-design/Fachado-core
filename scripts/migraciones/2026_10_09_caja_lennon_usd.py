"""Caja obra Lennon en dólares (CONTEXTO-FACHADO.md §5.8 v1.8, handoff del 9/10, G).

Lennon le dio a Gabriel USD 20.000 para la caja (28/09): el saldo de esa caja se lleva en
dólares y cada pago en pesos descuenta importe / tc.

- Si «Caja obra Lennon» **no tiene movimientos** en MOVIMIENTOS (al 9/10 no tiene: los pagos
  se cargaron contra Efectivo), se le cambia la moneda a USD.
- Si tiene, no se toca su moneda (sus filas están en pesos): se crea «Caja obra Lennon USD»
  y la vieja pasa a inactiva.

Idempotente; nada se borra.

    python scripts/migraciones/2026_10_09_caja_lennon_usd.py                  (simulacro)
    python scripts/migraciones/2026_10_09_caja_lennon_usd.py --aplicar
    python scripts/migraciones/2026_10_09_caja_lennon_usd.py --snapshot tests/maestros_snapshot.json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _comun import Migracion  # noqa: E402

from app.maestros import normalizar  # noqa: E402

CAJA = "Caja obra Lennon"
MONEDA = "USD"
POR_QUE = "§5.8 v1.8: la caja de Lennon se lleva en dólares (9/10)"


def main() -> None:
    mig = Migracion(["CUENTAS", "MOVIMIENTOS"], __doc__)
    encontradas = mig.buscar("CUENTAS", cuenta=CAJA)
    if not encontradas:
        sys.exit(f"No está «{CAJA}» en CUENTAS")
    fila, caja = encontradas[0]
    movimientos = [r for _, r in mig.registros("MOVIMIENTOS") if normalizar(r.get("cuenta")) == normalizar(CAJA)]
    if caja["moneda"] == MONEDA:
        print(f"«{CAJA}» ya está en {MONEDA}.")
    elif not movimientos:
        print(f"«{CAJA}» no tiene movimientos: se le cambia la moneda.")
        mig.poner("CUENTAS", fila, "moneda", MONEDA, POR_QUE)
    else:
        nueva = f"{CAJA} {MONEDA}"
        print(f"«{CAJA}» tiene {len(movimientos)} movimiento(s) en pesos: se crea «{nueva}» y la vieja queda inactiva.")
        if not mig.buscar("CUENTAS", cuenta=nueva):
            mig.agregar("CUENTAS", {**caja, "cuenta": nueva, "moneda": MONEDA, "saldo_apertura": "0,00",
                                    "notas": f"{caja.get('notas', '')} En dólares desde el 9/10".strip()}, POR_QUE)
        mig.poner("CUENTAS", fila, "estado", "inactiva", f"{POR_QUE}; la reemplaza «{nueva}»")
    mig.terminar()


if __name__ == "__main__":
    main()
