"""Los saldos de apertura al 31/10 (handoff del 20/10, M3): la plantilla, la validación del CSV,
el control contra el banco y las celdas que se escribirían en CUENTAS. Contra el snapshot y un
libro en memoria; nunca se escribe en el Sheet real.

    python -m tests.test_apertura
"""
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ["MAESTROS_SNAPSHOT"] = str(RAIZ / "maestros_snapshot.json")
    os.environ["LLM_HABILITADO"] = "false"

    from app import maestros
    from app.conciliar import ANTERIOR, SIN_CARGAR, _fila_banco
    from app.extracto import leer_extracto
    from scripts import cargar_saldos_apertura as ap
    from tests.dobles import LibroMemoria

    fallas: list[str] = []

    def check(descripcion, condicion, detalle=""):
        ok = bool(condicion)
        print(f"  {'PASA ' if ok else 'FALLA'}  {descripcion}{'' if ok else '  → ' + str(detalle)[:600]}")
        if not ok:
            fallas.append(descripcion)

    m = maestros.cargar(forzar=True)
    snapshot = json.loads((RAIZ / "maestros_snapshot.json").read_text(encoding="utf-8"))

    print("\n1 · La plantilla sale de CUENTAS")
    texto = ap.plantilla(m)
    filas = [f.split(",") for f in texto.strip().splitlines()]
    nombres = [f[0] for f in filas[1:]]
    check("encabezado cuenta,moneda,saldo,fecha", filas[0] == ["cuenta", "moneda", "saldo", "fecha"], filas[0])
    check("Banco, Banco USD, Mercado Pago, Efectivo y cada caja de obra activa; ni Chequera, ni «Pagado por el "
          "comitente», ni la caja_obra inactiva",
          {"Banco", "Banco USD", "Mercado Pago", "Efectivo", "Caja obra Lennon", "Caja obra Moreno"} <= set(nombres)
          and not {"Chequera", "Pagado por el comitente", "caja_obra"} & set(nombres)
          and len(nombres) == 4 + len([c for c in m.cuentas if c.activa and c.tipo == "caja_obra"]), nombres)
    check("cada una en su moneda, saldo vacío y fecha 2026-10-31",
          all(f[2] == "" and f[3] == "2026-10-31" for f in filas[1:])
          and next(f for f in filas if f[0] == "Caja obra Lennon")[1] == "USD"
          and next(f for f in filas if f[0] == "Banco USD")[1] == "USD", filas)
    archivo = RAIZ.parent / "docs" / "saldos-apertura-31-10.csv"
    check("docs/saldos-apertura-31-10.csv tiene las mismas cuentas que CUENTAS",
          archivo.exists() and [f.split(",")[0] for f in archivo.read_text(encoding="utf-8").strip().splitlines()[1:]]
          == nombres, archivo)

    print("\n2 · El control contra el banco (libro en memoria con los extractos armados de octubre)")
    libro = LibroMemoria(snapshot["MOVIMIENTOS"][0])
    for nombre in ("armado-octubre-CA.xlsx", "armado-octubre-CC.xlsx", "armado-octubre-USD.xlsx",
                   "armado-octubre-mercado-pago.pdf"):
        for linea in leer_extracto((RAIZ / "fixtures" / nombre).read_bytes()):
            fila = _fila_banco(linea, ANTERIOR, "", [], None, "2026-11-01 09:00:00")
            libro.agregar_banco([[fila.get(c, "") for c in libro.banco[0]]])
    # una línea de noviembre (no cuenta: es posterior) y una ya conciliable (no es ANTERIOR)
    extra = dict(zip(libro.banco[0], libro.banco[1]))
    libro.agregar_banco([list({**extra, "hash_id": "x1", "fecha": "2026-11-02", "saldo": 7, "estado": ANTERIOR}.values()),
                         list({**extra, "hash_id": "x2", "fecha": "2026-10-31", "saldo": 9, "estado": SIN_CARGAR,
                               "importado_ts": "2026-11-05 10:00:00"}.values())])  # extra ya está en el orden de BANCO_RAW
    banco = libro.banco_dicts()
    csv_ok = ("cuenta;moneda;saldo;fecha\n"
              "Banco;ARS;1.050.000,00;31/10/2026\n"
              "Banco USD;U$S;98,05;2026-10-31\n"
              "Mercado Pago;ARS;$ 124.000;2026-10-31\n"
              "Efectivo;ARS;;2026-10-31\n"
              "Caja obra Lennon;USD;-1500;2026-10-31\n")
    plan = ap.planear(csv_ok, m, banco)
    cargas = {c["cuenta"]: c for c in plan["cargas"]}
    check("CSV con «;» (Excel en castellano), saldos «1.050.000,00», «$ 124.000», «-1500», fecha dd/mm/aaaa",
          not plan["errores"] and cargas["Banco"]["saldo"] == 1050000.0 and cargas["Mercado Pago"]["saldo"] == 124000.0
          and cargas["Caja obra Lennon"]["saldo"] == -1500.0 and cargas["Banco"]["fecha"] == "2026-10-31"
          and cargas["Banco USD"]["moneda"] == "USD", plan)
    check("el saldo vacío se saltea con un aviso", "Efectivo" not in cargas and any("Efectivo" in a for a in plan["avisos"]),
          plan["avisos"])
    ctl = {c["cuenta"]: c for c in plan["controles"]}
    check("control solo para las que concilian: Banco, Banco USD y Mercado Pago", set(ctl) == {"Banco", "Banco USD", "Mercado Pago"},
          list(ctl))
    check("Banco: suma CA $ 273 (1.000.000, la del 31/10, no la de noviembre ni la conciliable) + CC $ (50.000); "
          "avisa que falta la CA $ 48",
          ctl["Banco"]["banco"] == 1050000.0 and ctl["Banco"]["diferencia"] == 0
          and ctl["Banco"]["faltan"] == ["CA $ 48-69556582-001"], ctl["Banco"])
    check("Banco USD: 98,05 contra 98,05 → sin diferencia", ctl["Banco USD"]["banco"] == 98.05 and ctl["Banco USD"]["diferencia"] == 0,
          ctl["Banco USD"])
    check("Mercado Pago: la diferencia (124.000 − 124.172,89 = −172,89) se avisa pero no frena",
          ctl["Mercado Pago"]["diferencia"] == -172.89 and not plan["errores"], ctl["Mercado Pago"])
    salida = ap.informe(plan)
    check("el informe muestra las tres cosas", "AVISO: diferencia -$ 172,89" in salida and "Banco: cargado $ 1.050.000,00" in salida
          and "sin extracto de CA $ 48-69556582-001" in salida, salida)
    import copy
    import dataclasses
    viejo = copy.copy(m)
    viejo.cuentas = [dataclasses.replace(c, cuentas_banco=[]) for c in m.cuentas]
    ctl_viejo = {c["cuenta"]: c for c in ap.planear(csv_ok, viejo, banco)["controles"]}
    check("sin la columna cuentas_banco (el Sheet antes de la migración): las fuentes salen de las líneas, mismo control",
          {k: v["banco"] for k, v in ctl_viejo.items()} == {"Banco": 1050000.0, "Banco USD": 98.05, "Mercado Pago": 124172.89},
          {k: (v["banco"], list(v["partes"])) for k, v in ctl_viejo.items()})
    sin_banco = ap.planear(csv_ok, m, [])
    check("sin extractos importados: el control lo dice y no frena",
          all(c["banco"] is None for c in sin_banco["controles"]) and "sin control" in ap.informe(sin_banco)
          and not sin_banco["errores"], ap.informe(sin_banco))

    print("\n3 · Las celdas que escribiría --aplicar (en la tabla CUENTAS del snapshot)")
    tabla = snapshot["CUENTAS"]
    enc = tabla[0]
    escritas = dict(ap.celdas(plan, tabla))
    fila_banco = next(n for n, f in enumerate(tabla[1:], start=2) if f[0] == "Banco")
    fila_lennon = next(n for n, f in enumerate(tabla[1:], start=2) if f[0] == "Caja obra Lennon")
    col = {c: chr(ord("A") + enc.index(c)) for c in ("saldo_apertura", "fecha_apertura")}
    check("dos celdas por cuenta cargada, en su fila y en saldo_apertura / fecha_apertura, y nada más",
          len(escritas) == 8 and escritas[f"CUENTAS!{col['saldo_apertura']}{fila_banco}"] == 1050000.0
          and escritas[f"CUENTAS!{col['fecha_apertura']}{fila_banco}"] == "2026-10-31"
          and escritas[f"CUENTAS!{col['saldo_apertura']}{fila_lennon}"] == -1500.0, escritas)
    try:
        ap.celdas(plan, [[c for c in enc if c != "fecha_apertura"]] + tabla[1:])
        check("sin la columna fecha_apertura no escribe y dice qué correr", False)
    except ValueError as e:
        check("sin la columna fecha_apertura no escribe y dice qué correr", "preparar_sheet" in str(e), e)

    print("\n4 · Lo que no valida no se escribe")
    malo = ap.planear("cuenta,moneda,saldo,fecha\n"
                      "Banco Galicia,ARS,100,2026-10-31\n"
                      "Banco,ARS,mil pesos,2026-10-31\n"
                      "Banco USD,ARS,10,2026-10-31\n"
                      "Efectivo,ARS,10,31/13/2026\n"
                      "Mercado Pago,ARS,10,2026-10-31\n"
                      "mercado pago,ARS,20,2026-10-31\n", m, banco)
    errores = " | ".join(malo["errores"])
    check("cuenta inexistente, saldo que no es número, moneda equivocada, fecha imposible y cuenta repetida: un error cada una",
          len(malo["errores"]) == 5 and "Banco Galicia" in errores and "mil pesos" in errores and "en USD" in errores
          and "31/13/2026" in errores and "dos veces" in errores, malo["errores"])
    check("faltan columnas: error claro", ap.planear("cuenta,saldo\nBanco,10\n", m, [])["errores"][0].startswith("al CSV le faltan"),
          ap.planear("cuenta,saldo\nBanco,10\n", m, [])["errores"])

    print()
    if fallas:
        print(f"{len(fallas)} FALLA(S)")
        return 1
    print("TODO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
