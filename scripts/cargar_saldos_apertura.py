"""Carga los saldos de apertura al 31/10 en CUENTAS (CONTEXTO-FACHADO.md §5.20; handoff del 20/10, M3).

Gabriel y Petrus completan `docs/saldos-apertura-31-10.csv` (una fila por cuenta: `cuenta,
moneda, saldo, fecha`); Valen la carga el 1/11 en un paso:

    python scripts/cargar_saldos_apertura.py --csv docs/saldos-apertura-31-10.csv             (simulacro)
    python scripts/cargar_saldos_apertura.py --csv docs/saldos-apertura-31-10.csv --aplicar

- **Valida** que cada cuenta exista en CUENTAS, que la moneda sea la de la cuenta y que el saldo
  sea un número (acepta `1.234.567,89`, `-1500`, `$ 300.000`). Si algo no valida, no escribe
  nada. Una fila con el saldo vacío se saltea con un aviso (todavía no lo tienen).
- **Escribe** `saldo_apertura` y `fecha_apertura` de cada cuenta en CUENTAS, solo con
  `--aplicar`. Nada más se toca.
- **Control** contra el banco: para cada cuenta que concilia (Banco, Banco USD, Mercado Pago)
  muestra el saldo del extracto al 31/10 —la última línea `ANTERIOR` de BANCO_RAW con fecha
  ≤ la fecha de apertura, si ya está importada— contra el saldo cargado, y la diferencia. Las
  tres cuentas del banco en pesos suman en `Banco`. Si la diferencia no es cero, avisa pero no
  frena: el saldo lo deciden ellos.

Plantilla nueva (lee las cuentas de CUENTAS, con el saldo vacío):

    python scripts/cargar_saldos_apertura.py --plantilla docs/saldos-apertura-31-10.csv
"""
import argparse
import csv
import io
import re
import sys
from datetime import date

sys.path.insert(0, ".")
from app.maestros import Maestros, normalizar, numero  # noqa: E402

FECHA_APERTURA = "2026-10-31"
COLUMNAS = ["cuenta", "moneda", "saldo", "fecha"]
# Las que llevan saldo propio (§5.20): las del banco, la billetera, el efectivo y cada caja de obra.
# Chequera y «Pagado por el comitente» no: no son plata en una cuenta.
TIPOS_CON_SALDO = ("banco", "billetera", "efectivo", "caja_obra")
RE_NUMERO = re.compile(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?|-?\d+\.\d{1,2}")


def cuentas_con_saldo(m: Maestros) -> list:
    return [c for c in m.cuentas if c.activa and str(c.tipo).strip().lower() in TIPOS_CON_SALDO]


def plantilla(m: Maestros, fecha: str = FECHA_APERTURA) -> str:
    salida = io.StringIO()
    escritor = csv.writer(salida, lineterminator="\n")
    escritor.writerow(COLUMNAS)
    for c in cuentas_con_saldo(m):
        escritor.writerow([c.nombre, c.moneda, "", fecha])
    return salida.getvalue()


def _saldo(texto: str) -> float | None:
    """El saldo como número, o None si no es un número. Sin `numero()` a ciegas: «abc» no es cero."""
    limpio = re.sub(r"(?i)us\$|u\$s|\$|\s", "", str(texto))
    if not RE_NUMERO.fullmatch(limpio):
        return None
    return numero(limpio)


def _fecha(texto: str) -> str | None:
    texto = str(texto or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", texto) or re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", texto)
    if not m:
        return None
    a, b, c = m.groups()
    anio, mes, dia = (a, b, c) if len(a) == 4 else (c, b, a)
    try:
        return date(int(anio), int(mes), int(dia)).isoformat()
    except ValueError:
        return None


def leer_csv(texto: str) -> list[dict]:
    """Las filas del CSV. Acepta coma o punto y coma (el Excel en castellano guarda con «;»)."""
    texto = texto.lstrip("﻿")
    primera = texto.splitlines()[0] if texto.strip() else ""
    separador = ";" if primera.count(";") > primera.count(",") else ","
    lector = csv.DictReader(io.StringIO(texto), delimiter=separador)
    faltan = [c for c in COLUMNAS if c not in [normalizar(x) for x in (lector.fieldnames or [])]]
    if faltan:
        raise ValueError(f"al CSV le faltan columnas: {', '.join(faltan)} (tienen que ser {','.join(COLUMNAS)})")
    return [{normalizar(k): (v or "").strip() for k, v in fila.items() if k} for fila in lector
            if any((v or "").strip() for v in fila.values() if isinstance(v, str))]


def planear(texto_csv: str, m: Maestros, banco: list[dict]) -> dict:
    """Lo que se cargaría: {cargas: [{cuenta, moneda, saldo, fecha}], errores, avisos, controles}.
    No escribe nada."""
    errores: list[str] = []
    avisos: list[str] = []
    cargas: list[dict] = []
    try:
        filas = leer_csv(texto_csv)
    except ValueError as e:
        return {"cargas": [], "errores": [str(e)], "avisos": [], "controles": []}
    vistas: set[str] = set()
    for n, fila in enumerate(filas, start=2):
        cuenta = m.cuenta(fila.get("cuenta"))
        if cuenta is None:
            errores.append(f"fila {n}: «{fila.get('cuenta')}» no está en CUENTAS (o está inactiva)")
            continue
        if cuenta.nombre in vistas:
            errores.append(f"fila {n}: «{cuenta.nombre}» está dos veces")
            continue
        vistas.add(cuenta.nombre)
        moneda = fila.get("moneda", "").upper().replace("U$S", "USD").replace("US$", "USD") or cuenta.moneda
        if moneda != cuenta.moneda:
            errores.append(f"fila {n}: «{cuenta.nombre}» es en {cuenta.moneda}, no en {fila.get('moneda')}")
            continue
        if not fila.get("saldo"):
            avisos.append(f"«{cuenta.nombre}»: sin saldo, no se carga")
            continue
        saldo = _saldo(fila["saldo"])
        if saldo is None:
            errores.append(f"fila {n}: el saldo de «{cuenta.nombre}» no es un número: «{fila['saldo']}»")
            continue
        fecha = _fecha(fila.get("fecha") or FECHA_APERTURA)
        if fecha is None:
            errores.append(f"fila {n}: la fecha de «{cuenta.nombre}» no es una fecha: «{fila.get('fecha')}»")
            continue
        cargas.append({"cuenta": cuenta.nombre, "moneda": cuenta.moneda, "saldo": round(saldo, 2), "fecha": fecha})
    return {"cargas": cargas, "errores": errores, "avisos": avisos, "controles": controles(cargas, m, banco)}


def _saldo_al(banco: list[dict], cuenta_banco: str, hasta: str) -> tuple[float, str] | None:
    """(saldo, fecha) de la última línea ANTERIOR de esa cuenta del banco con fecha ≤ hasta: la
    de fecha más nueva y, el mismo día, la del extracto más reciente con menor orden."""
    from app.conciliar import ANTERIOR, _clave_cuenta_banco
    clave_cuenta = _clave_cuenta_banco(cuenta_banco)
    mejor = None
    for x in banco:
        if (x.get("estado") != ANTERIOR or _clave_cuenta_banco(x.get("cuenta_banco")) != clave_cuenta
                or x.get("saldo") in ("", None) or str(x.get("fecha"))[:10] > hasta):
            continue
        clave = (str(x.get("fecha"))[:10], str(x.get("importado_ts") or ""), -int(numero(x.get("orden"))))
        if mejor is None or clave > mejor[0]:
            mejor = (clave, numero(x.get("saldo")), str(x.get("fecha"))[:10])
    return mejor[1:] if mejor else None


def controles(cargas: list[dict], m: Maestros, banco: list[dict]) -> list[dict]:
    """Por cada cuenta cargada que concilia: el saldo del banco al día de apertura contra el
    cargado. `banco` None: todavía no hay extracto de ninguna de sus cuentas.

    Las cuentas del banco de cada una salen de `CUENTAS.cuentas_banco`; si la columna todavía no
    está (antes de la migración del 20/10), de las líneas importadas, con la misma regla que la
    conciliación (`cuenta_de_linea`): así el control funciona igual, sin poder decir qué falta."""
    from app.conciliar import cuenta_de_linea
    salida = []
    for carga in cargas:
        cuenta = m.cuenta(carga["cuenta"])
        if not cuenta or str(cuenta.tipo).strip().lower() not in ("banco", "billetera"):
            continue
        fuentes = list(cuenta.cuentas_banco)
        if not fuentes:
            vistas = {x.get("cuenta_banco") for x in banco if x.get("cuenta_banco")}
            fuentes = sorted(cb for cb in vistas
                             if getattr(cuenta_de_linea(next(x for x in banco if x.get("cuenta_banco") == cb), m),
                                        "nombre", None) == cuenta.nombre)
        partes = {cb: _saldo_al(banco, cb, carga["fecha"]) for cb in fuentes}
        presentes = {cb: v for cb, v in partes.items() if v is not None}
        saldo_banco = round(sum(v[0] for v in presentes.values()), 2) if presentes else None
        salida.append({
            "cuenta": cuenta.nombre, "moneda": cuenta.moneda, "cargado": carga["saldo"], "banco": saldo_banco,
            "diferencia": None if saldo_banco is None else round(carga["saldo"] - saldo_banco, 2),
            "partes": {cb: (v[0], v[1]) for cb, v in presentes.items()},
            "faltan": [cb for cb, v in partes.items() if v is None],
        })
    return salida


def _plata(valor: float, moneda: str) -> str:
    texto = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if valor < 0 else ''}{'US$' if moneda == 'USD' else '$'} {texto}"


def informe(plan: dict) -> str:
    lineas = []
    if plan["cargas"]:
        lineas.append("Se cargaría en CUENTAS (saldo_apertura, fecha_apertura):")
        lineas += [f"  · {c['cuenta']}: {_plata(c['saldo'], c['moneda'])} al {c['fecha']}" for c in plan["cargas"]]
    if plan["controles"]:
        lineas.append("\nControl contra el banco (la última línea ANTERIOR de BANCO_RAW hasta esa fecha):")
        for c in plan["controles"]:
            if c["banco"] is None:
                lineas.append(f"  · {c['cuenta']}: todavía no hay extracto importado hasta esa fecha; sin control")
                continue
            detalle = "; ".join(f"{cb} {_plata(s, c['moneda'])} ({f})" for cb, (s, f) in c["partes"].items())
            estado = "OK" if c["diferencia"] == 0 else f"AVISO: diferencia {_plata(c['diferencia'], c['moneda'])}"
            lineas.append(f"  · {c['cuenta']}: cargado {_plata(c['cargado'], c['moneda'])}, banco "
                          f"{_plata(c['banco'], c['moneda'])} → {estado}")
            lineas.append(f"      {detalle}")
            if c["faltan"]:
                lineas.append(f"      AVISO: sin extracto de {', '.join(c['faltan'])}: la suma del banco está incompleta")
    if plan["avisos"]:
        lineas.append("\nAvisos:")
        lineas += [f"  · {a}" for a in plan["avisos"]]
    if plan["errores"]:
        lineas.append("\nErrores (no se escribe nada hasta corregirlos):")
        lineas += [f"  · {e}" for e in plan["errores"]]
    return "\n".join(lineas) if lineas else "El CSV no tiene filas."


def celdas(plan: dict, tabla_cuentas: list[list]) -> list[tuple[str, object]]:
    """[(rango A1, valor)] a escribir en CUENTAS: las dos celdas de cada cuenta cargada."""
    from app.sheets import columna_a_letra as letra
    encabezado = [str(x) for x in tabla_cuentas[0]]
    faltan = [c for c in ("saldo_apertura", "fecha_apertura") if c not in encabezado]
    if faltan:
        raise ValueError(f"CUENTAS no tiene {', '.join(faltan)}: correr antes scripts/preparar_sheet.py --aplicar")
    i_cuenta = encabezado.index("cuenta")
    filas = {normalizar(f[i_cuenta]): n for n, f in enumerate(tabla_cuentas[1:], start=2) if len(f) > i_cuenta}
    salida = []
    for carga in plan["cargas"]:
        n = filas[normalizar(carga["cuenta"])]
        salida.append((f"CUENTAS!{letra(encabezado.index('saldo_apertura') + 1)}{n}", carga["saldo"]))
        salida.append((f"CUENTAS!{letra(encabezado.index('fecha_apertura') + 1)}{n}", carga["fecha"]))
    return salida


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grupo = ap.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--csv", help="el CSV con los saldos")
    grupo.add_argument("--plantilla", metavar="CSV", help="escribir la plantilla vacía con las cuentas de CUENTAS")
    ap.add_argument("--aplicar", action="store_true", help="escribir en CUENTAS (sin esto, simulacro)")
    args = ap.parse_args()

    from app import maestros
    m = maestros.cargar()
    if args.plantilla:
        with open(args.plantilla, "w", encoding="utf-8", newline="") as f:
            f.write(plantilla(m))
        print(f"Plantilla: {args.plantilla} ({len(cuentas_con_saldo(m))} cuentas)")
        return 0

    from app.libro import LibroSheets
    with open(args.csv, encoding="utf-8-sig") as f:
        texto = f.read()
    crudo = LibroSheets().leer_banco()
    banco = [dict(zip(crudo[0], fila)) for fila in crudo[1:]] if crudo else []
    plan = planear(texto, m, banco)
    print(informe(plan))
    if plan["errores"]:
        return 1
    if not plan["cargas"]:
        print("\nNada que cargar.")
        return 0
    if not args.aplicar:
        print("\n(simulacro: no se escribió nada. Correr con --aplicar)")
        return 0
    from app import sheets
    from app.config import settings
    sid = settings().sheet_id
    tabla = sheets.leer_hojas(sid, ["CUENTAS!A:Z"])["CUENTAS"]
    for rango, valor in celdas(plan, tabla):
        sheets.escribir_rango(sid, rango, [[valor]])
    print(f"\nAplicado: {len(plan['cargas'])} cuenta(s) en CUENTAS. El saldo del libro cuenta desde la fecha de apertura.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
