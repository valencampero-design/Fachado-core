"""Deja el Sheet maestro listo para que /confirmar escriba. Idempotente: se puede correr
las veces que haga falta y solo agrega lo que falta.

    python scripts/preparar_sheet.py --titular <telefono> --titular-nombre "<nombre>"
    python scripts/preparar_sheet.py ... --aplicar

Sin `--aplicar` es un simulacro. Qué hace:

1. Agrega al final de MOVIMIENTOS las columnas que escribe /confirmar y todavía no están
   (`msg_id`, `certificado`). Siempre al final, nunca en el medio: las fórmulas de las CC
   usan rangos fijos. Si la grilla no tiene lugar, la amplía.
2. Crea la hoja USUARIOS (`telefono · nombre · rol · activo`) con el titular y a Petrus
   sin teléfono (CONTEXTO-FACHADO.md §5.13). Si ya existe, no la toca.

El teléfono del titular se pasa por argumento: no vive en el código.
"""
import argparse
import sys

sys.path.insert(0, ".")
from app import sheets  # noqa: E402
from app.config import settings  # noqa: E402
from app.sheets import columna_a_letra as letra  # noqa: E402

COLUMNAS_NUEVAS_MOVIMIENTOS = ["msg_id", "certificado"]
ENCABEZADO_USUARIOS = ["telefono", "nombre", "rol", "activo"]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--titular", required=True, help="teléfono del titular, como llega de WhatsApp")
    ap.add_argument("--titular-nombre", required=True)
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    sid = settings().sheet_id
    hojas = sheets.estructura(sid)
    acciones: list[tuple[str, callable]] = []

    # 1. Columnas nuevas en MOVIMIENTOS
    encabezado = sheets.leer_rango(sid, "MOVIMIENTOS!1:1", formato="FORMATTED_VALUE")[0]
    faltan = [c for c in COLUMNAS_NUEVAS_MOVIMIENTOS if c not in encabezado]
    if faltan:
        desde = len(encabezado) + 1
        hasta = len(encabezado) + len(faltan)
        grilla = hojas["MOVIMIENTOS"]
        if hasta > grilla["columnas"]:
            extra = hasta - grilla["columnas"]
            acciones.append((f"MOVIMIENTOS: ampliar la grilla {extra} columna(s) ({grilla['columnas']} → {hasta})",
                             lambda extra=extra: sheets.modificar(sid, [{"appendDimension": {
                                 "sheetId": grilla["id"], "dimension": "COLUMNS", "length": extra}}])))
        rango = f"MOVIMIENTOS!{letra(desde)}1:{letra(hasta)}1"
        acciones.append((f"MOVIMIENTOS: encabezado {rango} = {faltan}",
                         lambda rango=rango: sheets.escribir_rango(sid, rango, [faltan])))
    else:
        print(f"MOVIMIENTOS ya tiene {COLUMNAS_NUEVAS_MOVIMIENTOS}")

    # 2. Hoja USUARIOS
    if "USUARIOS" not in hojas:
        filas = [ENCABEZADO_USUARIOS,
                 [args.titular, args.titular_nombre, "titular", "sí"],
                 ["", "Petrus", "colaborador", "sí"]]
        acciones.append(("USUARIOS: crear la hoja", lambda: sheets.modificar(sid, [{"addSheet": {
            "properties": {"title": "USUARIOS", "gridProperties": {"rowCount": 50, "columnCount": 4}}}}])))
        acciones.append((f"USUARIOS: cargar {len(filas) - 1} usuarios (Petrus sin teléfono, a completar)",
                         lambda: sheets.escribir_rango(sid, "USUARIOS!A1:D3", filas)))
    else:
        print("USUARIOS ya existe: no se toca")

    for descripcion, _ in acciones:
        print(f"  · {descripcion}")
    if not acciones:
        print("Nada que hacer.")
        return
    if not args.aplicar:
        print("\n(simulacro: no se escribió nada. Correr con --aplicar)")
        return
    for descripcion, accion in acciones:
        accion()
    print(f"\nAplicado: {len(acciones)} cambio(s)")


if __name__ == "__main__":
    main()
