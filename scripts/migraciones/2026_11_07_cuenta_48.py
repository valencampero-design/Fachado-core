"""La caja de ahorro en pesos 48 pasa a ser la cuenta personal de Gabriel (reunión del 6/11,
CONTEXTO-FACHADO.md §5.7 v1.14).

- Cuenta nueva **`Banco personal (CA 48)`**: tipo `personal`, ARS, no concilia, sin saldo de
  apertura, `cuentas_banco` = la CA $ 48-69556582-001. Solo se usa en el libro personal (el
  motor rechaza una fila del estudio con esa cuenta).
- **La fecha de corte va en `fecha_apertura`** (2026-11-01): desde ese día Gabriel la usa para
  lo personal. El motor la lee de ahí (no está fija en el código): con ella decide si un retiro
  de Gabriel sin cuenta de origen sale de la 48 y si una línea del extracto del estudio que va a
  la 48 es un retiro.
- En `Banco`, la 48 sale de `cuentas_banco`: el extracto de la 48 ya no se concilia ni se pide.

Lo de la 48 que ya está en BANCO_RAW queda como está (son todas líneas `ANTERIOR`).

Idempotente; nada se borra.

    python scripts/migraciones/2026_11_07_cuenta_48.py                  (simulacro)
    python scripts/migraciones/2026_11_07_cuenta_48.py --aplicar
    python scripts/migraciones/2026_11_07_cuenta_48.py --snapshot tests/maestros_snapshot.json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _comun import Migracion  # noqa: E402
from app.maestros import normalizar  # noqa: E402

POR_QUE = "§5.7 v1.14: reunión del 6/11"
CA48 = "CA $ 48-69556582-001"
NOMBRE = "Banco personal (CA 48)"
CORTE = "2026-11-01"
NOTA = (f"Cuenta personal de Gabriel desde el 1/11/2026 (fecha_apertura = la fecha de corte; §5.7 v1.14, "
        f"reunión del 6/11). Solo en el libro personal: no concilia, no lleva saldo de apertura y no entra "
        f"en el cierre semanal. Lo que el estudio le pasa es un retiro")


def main() -> None:
    mig = Migracion(["CUENTAS"], __doc__)
    for columna in ("fecha_apertura", "cuentas_banco", "estado"):
        mig.asegurar_columna("CUENTAS", columna)

    banco = mig.buscar("CUENTAS", cuenta="Banco")
    if len(banco) != 1:
        sys.exit(f"«Banco» tiene que estar una vez en CUENTAS (está {len(banco)})")
    n, r = banco[0]
    partes = [x.strip() for x in (r.get("cuentas_banco") or "").split(";") if x.strip()]
    sin_48 = [x for x in partes if normalizar(x).replace(" ", "") != normalizar(CA48).replace(" ", "")]
    if sin_48 != partes:
        mig.poner("CUENTAS", n, "cuentas_banco", "; ".join(sin_48), POR_QUE)

    if not mig.buscar("CUENTAS", cuenta=NOMBRE):
        mig.agregar("CUENTAS", {"cuenta": NOMBRE, "tipo": "personal", "moneda": "ARS", "concilia_contra_banco": "no",
                                "saldo_apertura": "", "notas": NOTA, "estado": "activa", "fecha_apertura": CORTE,
                                "cuentas_banco": CA48}, POR_QUE)
    mig.terminar()


if __name__ == "__main__":
    main()
