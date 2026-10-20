"""Crea o reescribe las hojas CC_<OBRA> (CONTEXTO-FACHADO.md §5.21 v1.11, entregable de la
propuesta).

- **En el Master**, una hoja por **cada obra** de OBRAS: las de terceros con cualquier
  servicio (las de proyecto y dirección muestran sobre todo los honorarios cobrados), las
  propias, Austral y Jardín Maternal aunque esté cerrada. Una obra sin movimientos tiene igual
  su hoja, en cero. Misma lógica que la planilla de Gabriel: encabezado (aportes, pagado con
  plata del estudio, pagado por el comitente, caja de obra en su moneda, saldo), aportes del
  comitente, por contratista, por rubro y el detalle cronológico con el link al comprobante
  (y la etapa donde hay).
- **En el libro personal**, la de cada inmueble personal (Sur, Abucoque, Belelli, Gessel), con
  el mismo formato. Nunca en el Master: así no la ve quien no tiene `ve_personal` (§5.13).

Las hojas se arman **desde las vistas**, no desde MOVIMIENTOS crudo, y se escriben **como
valores**: el recálculo nocturno (`scripts/recalcular_vistas.py`) las vuelve a escribir, así
que una obra nueva en OBRAS tiene su hoja al día siguiente. Las CC_ que ya existen se
reemplazan. Nunca se toca MOVIMIENTOS.

    python scripts/crear_cc_obras.py              (simulacro: muestra qué escribiría)
    python scripts/crear_cc_obras.py --aplicar

El libro personal se lee de FACHADO_PERSONAL_SHEET_ID; si no está, solo el Master.
"""
import argparse
import sys

sys.path.insert(0, ".")
from app import maestros, sheets, vistas  # noqa: E402
from app.config import settings  # noqa: E402
from app.libro import LibroSheets  # noqa: E402


def _mostrar(hojas: dict, existentes: dict, donde: str) -> dict:
    cc = {h: f for h, f in hojas.items() if h.startswith("CC_")}
    print(f"\n{donde}: {len(cc)} hoja(s)")
    for hoja, filas in cc.items():
        accion = "reescribir (ya existe)" if hoja in existentes else "crear"
        detalle = next((i for i, f in enumerate(filas) if f[:1] == ["DETALLE CRONOLÓGICO"]), None)
        movimientos = len(filas) - detalle - 2 if detalle is not None else 0
        print(f"  · {hoja}: {accion} · {len(filas)} filas · {movimientos} movimientos en el detalle")
        print(f"      {filas[4]}")
    viejas = [h for h in existentes if h.startswith("CC_") and h not in cc and h != "CC_FÓRMULAS"]
    if viejas:
        print(f"  Hojas CC_ que ya no corresponden a ninguna obra (no se tocan): {viejas}")
    return cc


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true", help="escribir en los libros (sin esto, simulacro)")
    args = ap.parse_args()

    s = settings()
    libro = LibroSheets()
    personal = LibroSheets(s.personal_sheet_id) if s.personal_sheet_id else None
    m = maestros.cargar()
    hojas = vistas.calcular(libro, personal, m)
    cc_master = _mostrar(hojas["master"], sheets.estructura(s.sheet_id), "Master")
    cc_personal = {}
    if personal is not None:
        cc_personal = _mostrar(hojas["personal"], sheets.estructura(s.personal_sheet_id), "Libro personal")
    else:
        print("\nSin FACHADO_PERSONAL_SHEET_ID: las CC de los inmuebles personales no se arman")
    if not args.aplicar:
        print("\n(simulacro: no se escribió nada. Correr con --aplicar)")
        return
    for hoja, filas in cc_master.items():
        libro.escribir_hoja(hoja, filas)
    for hoja, filas in cc_personal.items():
        personal.escribir_hoja(hoja, filas)
    print(f"\nAplicado: {len(cc_master)} hoja(s) CC_ en el Master y {len(cc_personal)} en el libro personal")


if __name__ == "__main__":
    main()
