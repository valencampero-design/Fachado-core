"""Crea o reescribe las hojas CC_<OBRA> del Master (CONTEXTO-FACHADO.md §5.21, entregable de la
propuesta).

Una hoja por cada obra que lleva cuenta corriente (§6: administración, «todo» y obras propias
— hoy Lennon, Moreno, Moquehue, Gonzalo, Hua Huan, Grigera Galpón y Tres Cerros). Misma lógica
que la planilla de Gabriel: encabezado (aportes, pagado con plata del estudio, pagado por el
comitente, caja de obra en su moneda, saldo), aportes del comitente, por contratista, por
rubro y el detalle cronológico con el link al comprobante (y la etapa donde hay).

Las hojas se arman **desde las vistas** (VISTA_OBRAS, VISTA_DETALLE), no desde MOVIMIENTOS
crudo, y se escriben **como valores**: el recálculo nocturno (`scripts/recalcular_vistas.py`)
las vuelve a escribir, así que una obra nueva en OBRAS tiene su hoja al día siguiente.
`CC_LENNON` y `CC_GONZALO` ya existen con las fórmulas viejas (no conocen cajas de obra,
dólares ni anulados): se reemplazan. Nunca se toca MOVIMIENTOS.

    python scripts/crear_cc_obras.py              (simulacro: muestra qué escribiría)
    python scripts/crear_cc_obras.py --aplicar
"""
import argparse
import sys

sys.path.insert(0, ".")
from app import maestros, sheets, vistas  # noqa: E402
from app.config import settings  # noqa: E402
from app.libro import LibroSheets  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true", help="escribir en el Master (sin esto, simulacro)")
    args = ap.parse_args()

    libro = LibroSheets()
    m = maestros.cargar()
    hojas = vistas.calcular(libro, None, m)["master"]
    existentes = sheets.estructura(settings().sheet_id)
    cc = {h: f for h, f in hojas.items() if h.startswith("CC_")}
    print(f"Obras con cuenta corriente: {', '.join(o.nombre for o in vistas.obras_con_cc(m))}\n")
    for hoja, filas in cc.items():
        accion = "reescribir (ya existe)" if hoja in existentes else "crear"
        detalle = next((i for i, f in enumerate(filas) if f[:1] == ["DETALLE CRONOLÓGICO"]), None)
        movimientos = len(filas) - detalle - 2 if detalle is not None else 0
        print(f"  · {hoja}: {accion} · {len(filas)} filas · {movimientos} movimientos en el detalle")
        print(f"      {filas[4]}")
    viejas = [h for h in existentes if h.startswith("CC_") and h not in cc and h != "CC_FÓRMULAS"]
    if viejas:
        print(f"\nHojas CC_ que ya no corresponden a una obra con cuenta corriente (no se tocan): {viejas}")
    if not args.aplicar:
        print("\n(simulacro: no se escribió nada. Correr con --aplicar)")
        return
    for hoja, filas in cc.items():
        libro.escribir_hoja(hoja, filas)
    print(f"\nAplicado: {len(cc)} hoja(s) CC_ escritas")


if __name__ == "__main__":
    main()
