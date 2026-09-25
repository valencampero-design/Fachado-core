"""Deja la ESTRUCTURA del Sheet maestro como la espera el motor. Idempotente: se puede correr
las veces que haga falta y solo agrega lo que falta. No toca datos.

    python scripts/preparar_sheet.py
    python scripts/preparar_sheet.py --aplicar
    python scripts/preparar_sheet.py --titular <telefono> --titular-nombre "<nombre>" --aplicar

Sin `--aplicar` es un simulacro. Qué hace:

1. Agrega al final de cada hoja las columnas que el motor escribe y todavía no están.
   **Siempre al final, nunca en el medio**: las fórmulas de las CC usan rangos fijos. Si la
   grilla no tiene lugar, la amplía.
2. Crea las hojas que faltan, solo con el encabezado. USUARIOS es la excepción: se crea con
   el titular, así que pide `--titular` y `--titular-nombre` (el teléfono no vive en el código).
"""
import argparse
import sys

sys.path.insert(0, ".")
from app import sheets  # noqa: E402
from app.config import settings  # noqa: E402
from app.sheets import columna_a_letra as letra  # noqa: E402

# Columnas que tienen que existir, en el orden en que se agregan al final si faltan.
COLUMNAS = {
    "MOVIMIENTOS": ["msg_id", "certificado", "etapa", "informal", "ref_comprobante"],
    "USUARIOS": ["telefono", "nombre", "rol", "activo", "ve_personal", "auto_confirmar"],
    "CUENTAS": ["estado"],
}

# Hojas que se crean vacías, con su encabezado.
HOJAS_NUEVAS = {
    "USUARIOS": ["telefono", "nombre", "rol", "activo", "ve_personal", "auto_confirmar"],
    # §5.15. Arranca vacía: las etapas las carga el arquitecto. Obra sin filas = sin etapas.
    "ETAPAS": ["obra", "etapa", "descripcion", "estado"],
}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--titular", help="teléfono del titular, solo si hay que crear USUARIOS")
    ap.add_argument("--titular-nombre")
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    sid = settings().sheet_id
    hojas = sheets.estructura(sid)
    acciones: list[tuple[str, callable]] = []

    # 1. Hojas que faltan
    for hoja, encabezado in HOJAS_NUEVAS.items():
        if hoja in hojas:
            continue
        filas = [encabezado]
        if hoja == "USUARIOS":
            if not (args.titular and args.titular_nombre):
                sys.exit("USUARIOS no existe: hace falta --titular y --titular-nombre para crearla")
            filas.append([args.titular, args.titular_nombre, "titular", "sí", "sí", "no"])
        ultima = letra(len(encabezado))
        acciones.append((f"{hoja}: crear la hoja", lambda hoja=hoja, n=len(encabezado): sheets.modificar(sid, [{"addSheet": {
            "properties": {"title": hoja, "gridProperties": {"rowCount": 1000, "columnCount": n}}}}])))
        acciones.append((f"{hoja}: encabezado{' y titular' if len(filas) > 1 else ''}",
                         lambda hoja=hoja, filas=filas, ultima=ultima: sheets.escribir_rango(
                             sid, f"{hoja}!A1:{ultima}{len(filas)}", filas)))

    # 2. Columnas que faltan en las hojas que ya existen
    for hoja, columnas in COLUMNAS.items():
        if hoja not in hojas:
            continue  # la crea el paso 1 con todas sus columnas
        leido = sheets.leer_rango(sid, f"{hoja}!1:1", formato="FORMATTED_VALUE")
        encabezado = leido[0] if leido else []
        faltan = [c for c in columnas if c not in encabezado]
        if not faltan:
            print(f"{hoja} ya tiene {columnas}")
            continue
        desde, hasta = len(encabezado) + 1, len(encabezado) + len(faltan)
        grilla = hojas[hoja]
        if hasta > grilla["columnas"]:
            extra = hasta - grilla["columnas"]
            acciones.append((f"{hoja}: ampliar la grilla {extra} columna(s) ({grilla['columnas']} → {hasta})",
                             lambda g=grilla, extra=extra: sheets.modificar(sid, [{"appendDimension": {
                                 "sheetId": g["id"], "dimension": "COLUMNS", "length": extra}}])))
        rango = f"{hoja}!{letra(desde)}1:{letra(hasta)}1"
        acciones.append((f"{hoja}: encabezado {rango} = {faltan}",
                         lambda rango=rango, faltan=faltan: sheets.escribir_rango(sid, rango, [faltan])))

    for descripcion, _ in acciones:
        print(f"  · {descripcion}")
    if not acciones:
        print("Nada que hacer.")
        return
    if not args.aplicar:
        print("\n(simulacro: no se escribió nada. Correr con --aplicar)")
        return
    for _, accion in acciones:
        accion()
    print(f"\nAplicado: {len(acciones)} cambio(s)")


if __name__ == "__main__":
    main()
