"""Gessel y Belelli pasan a ser obras propias (reunión del 6/11, CONTEXTO-FACHADO.md §6 v1.14).

- `OBRAS`: Gessel y Belelli, de `tipo = personal` a `obra_propia`, servicio `todo`, comitente
  «El arquitecto», con una nota del cambio. Nada se borra: la fila es la misma.
- `ALIAS`: `gesell` → Gessel (así lo escribe, §6 v1.14); se verifica que esté `belleli` →
  Belelli (y `gessel` → Gessel), y si falta se agrega.

Lo ya cargado en el libro personal con esas obras pasa al estudio con
`2026_11_07_pase_de_libro.py`, después de desplegar el motor nuevo.

Idempotente; nada se borra.

    python scripts/migraciones/2026_11_07_gessel_belelli.py                  (simulacro)
    python scripts/migraciones/2026_11_07_gessel_belelli.py --aplicar
    python scripts/migraciones/2026_11_07_gessel_belelli.py --snapshot tests/maestros_snapshot.json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _comun import Migracion  # noqa: E402

POR_QUE = "§6 v1.14: reunión del 6/11"
NOTA = "Obra propia desde el 6/11 (reunión del 6/11, §6 v1.14): hasta entonces, inmueble personal"
OBRAS = {"Gessel": "Remodelación de departamento", "Belelli": "Recibe las facturas de Edesur y Metrogas"}
ALIAS = [("gesell", "Gessel", "obra"), ("gessel", "Gessel", "obra"), ("belleli", "Belelli", "obra")]


def main() -> None:
    mig = Migracion(["OBRAS", "ALIAS"], __doc__)
    for obra, descripcion in OBRAS.items():
        filas = mig.buscar("OBRAS", obra=obra)
        if len(filas) != 1:
            sys.exit(f"«{obra}» tiene que estar una vez en OBRAS (está {len(filas)})")
        n, r = filas[0]
        mig.poner("OBRAS", n, "tipo", "obra_propia", POR_QUE)
        mig.poner("OBRAS", n, "servicio", "todo", POR_QUE)
        mig.poner("OBRAS", n, "comitente", "El arquitecto", POR_QUE)
        if "obra propia desde el 6/11" not in (r.get("notas") or "").lower():
            mig.poner("OBRAS", n, "notas", f"{descripcion}. {NOTA}", POR_QUE)
    for como, obra, tipo in ALIAS:
        if not mig.buscar("ALIAS", como_lo_dice=como, valor_canonico=obra, tipo=tipo):
            mig.agregar("ALIAS", {"como_lo_dice": como, "valor_canonico": obra, "tipo": tipo}, POR_QUE)
    mig.terminar()


if __name__ == "__main__":
    main()
