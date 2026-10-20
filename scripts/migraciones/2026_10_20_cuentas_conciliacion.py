"""Las cinco fuentes de la conciliación en CUENTAS (CONTEXTO-FACHADO.md §5.20 v1.11, 20/10).

- **Las cuatro cuentas del banco son del estudio**: `cuentas_banco` de cada cuenta del libro dice
  qué cuentas del banco se concilian contra ella, como las escribe el extracto:
  - `Banco` ← CA $ 273-125852351-000; CC $ 273-125852351-000; CA $ 48-69556582-001
  - `Banco USD` ← CA U$S 273-125852351-000
- **Mercado Pago** pasa a conciliar (el reporte en PDF es la quinta fuente) y su fuente es el
  reporte: `cuentas_banco = Mercado Pago`.

Con esto, `GET /conciliar/estado` sabe qué tiene que llegar cada semana, sin números de cuenta
escritos en el código. Antes, la columna: `python scripts/preparar_sheet.py --aplicar`.

Idempotente; nada se borra.

    python scripts/migraciones/2026_10_20_cuentas_conciliacion.py                  (simulacro)
    python scripts/migraciones/2026_10_20_cuentas_conciliacion.py --aplicar
    python scripts/migraciones/2026_10_20_cuentas_conciliacion.py --snapshot tests/maestros_snapshot.json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _comun import Migracion  # noqa: E402

POR_QUE = "§5.20 v1.11: las cinco fuentes de la conciliación (20/10)"
FUENTES = {
    "Banco": "CA $ 273-125852351-000; CC $ 273-125852351-000; CA $ 48-69556582-001",
    "Banco USD": "CA U$S 273-125852351-000",
    "Mercado Pago": "Mercado Pago",
}


def main() -> None:
    mig = Migracion(["CUENTAS"], __doc__)
    mig.asegurar_columna("CUENTAS", "cuentas_banco")
    for cuenta, fuentes in FUENTES.items():
        encontradas = mig.buscar("CUENTAS", cuenta=cuenta)
        if not encontradas:
            sys.exit(f"No está «{cuenta}» en CUENTAS")
        fila, registro = encontradas[0]
        mig.poner("CUENTAS", fila, "cuentas_banco", fuentes, POR_QUE)
        if cuenta == "Mercado Pago" and registro.get("concilia_contra_banco", "").strip().lower() not in ("sí", "si"):
            mig.poner("CUENTAS", fila, "concilia_contra_banco", "SÍ", f"{POR_QUE}: el reporte de Mercado Pago se concilia")
    mig.terminar()


if __name__ == "__main__":
    main()
