"""La lista oficial de rubros del estudio (CONTEXTO-FACHADO.md §5.4 v1.13, 27/10).

Lee `docs/maestros/Listado_general_rubros_obra_formato_unificado.xlsx` (Rubros de obra, Austral,
Retiros) y la pasa a RUBROS, con tres columnas nuevas: `codigo`, `estado` (activo / inactivo) y
`reemplazado_por` (el código nuevo).

- **obra**: `rubro_1` = Materiales, Mano de obra, Servicios, Asesoría, Indirectos, Varios (sin el
  «1. »); código del Excel (1.1, 2.3…).
- **estructura (Austral)**: `rubro_1` = el rubro general (completado hacia abajo); código A1.1…;
  el «Etc.» de Gastos corrientes es «Otros».
- **personal (Retiros)**: `rubro_1 = Personal` (la regla R3 depende de eso); código R1…R9.

**Nada se borra.** Un rubro viejo con el mismo rubro_1 y rubro_2 que uno nuevo se queda en su fila
y toma el código. Uno con equivalente claro pasa a `inactivo` con `reemplazado_por`. Uno sin
equivalente claro **queda activo** y va a la lista «a confirmar con Gabriel»
(`docs/maestros/mapa-rubros-2026-10-27.md`). CONTRATISTAS: el rubro habitual que quedó inactivo
pasa al nuevo; Elias Rodriguez y Contador Pasolli, que tenían un rubro inexistente, al que dice su
historial o su nombre. ALIAS de rubro: si apuntan a uno inactivo, al nuevo.

Idempotente. MOVIMIENTOS no se toca (el tablero traduce los rubros viejos).

    python scripts/migraciones/2026_10_27_rubros_estudio.py                  (simulacro)
    python scripts/migraciones/2026_10_27_rubros_estudio.py --aplicar
    python scripts/migraciones/2026_10_27_rubros_estudio.py --snapshot tests/maestros_snapshot.json
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

RAIZ = Path(__file__).resolve().parent.parent.parent
EXCEL = RAIZ / "docs" / "maestros" / "Listado_general_rubros_obra_formato_unificado.xlsx"
POR_QUE = "§5.4 v1.13: la lista de rubros del estudio (27/10)"
NOMBRE_6_1 = "Gastos varios de obra"  # el Excel dice «Gastos varios de obra no incluidos en los rubros anteriores.»

# Lo viejo → el código nuevo, con el motivo. None = sin equivalente claro: queda activo y se
# confirma con Gabriel (la propuesta va en PROPUESTA). Los que tienen el mismo rubro_1 y rubro_2
# que uno nuevo no están acá: se quedan en su fila con el código.
MAPA = {
    ("Materiales", "Hormigón"): ("1.3", "el hormigón es material de la estructura"),
    ("Materiales", "Albañilería"): ("1.2", "«Corralón / albañilería»"),
    ("Materiales", "Maderas"): ("1.4", "«Maderera»"),
    ("Materiales", "Sanitarias"): ("1.6", "«Sanitarios»"),
    ("Materiales", "Grifería"): ("1.16", "«Griferías»"),
    ("Materiales", "Artefactos Sanitarios."): ("1.17", "«Artefactos de baño»"),
    ("Materiales", "Accesorios de Baños"): ("1.21", "«Accesorios de baño»"),
    ("Materiales", "Climatización A.A."): ("1.24", "«Aire acondicionado»"),
    ("Materiales", "Amoblamiento"): ("1.10", "«Amoblamientos: placares y cocina»"),
    ("Mano de obra", "Contratistas"): ("2.1", "«Contratista principal»"),
    ("Mano de obra", "Jornales"): ("2.11", "«Jornales varios»"),
    ("Mano de obra", "Carpintero"): ("2.10", "«Carpintería» (mano de obra)"),
    ("Mano de obra", "Albañil"): ("2.9", "«Albañilería» (mano de obra)"),
    ("Mano de obra", "Zinguería"): ("2.8", "«Zinguero»"),
    ("Servicios de obra", "Baños químicos"): ("3.5", "«Baño químico»"),
    ("Servicios de obra", "Volquetes"): ("3.6", "el mismo, con rubro general «Servicios»"),
    ("Servicios de obra", "Fletes"): ("3.8", "el mismo, con rubro general «Servicios»"),
    ("Servicios de obra", "Movimiento de suelos"): ("3.1", "«Movimiento de suelo»"),
    ("Servicios de obra", "Alquiler de equipos"): ("3.11", "«Alquiler de herramientas»"),
    ("Servicios de obra", "Volteo de árboles"): ("3.3", "«Volteo»"),
    ("Servicios de obra", "Contenciones y gaviones"): ("3.7", "«Contenciones»"),
    ("Honorarios", "Contador"): ("A4.1", "Austral › Asesorías externas › Contador"),
    ("Estructura del estudio", "Sueldos y cargas sociales"): ("A3.1", "Austral › Sueldos › Sueldos fijos"),
    ("Estructura del estudio", "Alquiler"): ("A9.1", "Austral › Alquiler"),
    ("Personal", "Supermercado"): ("R7", "Retiros › Súper"),
    ("Personal", "Tarjeta"): ("R8", "Retiros › Tarjetas"),
}
# Sin equivalente claro: siguen activos. La propuesta, para confirmar con Gabriel.
PROPUESTA = {
    ("Materiales", "Durlock"): ("1.2", "¿Corralón / albañilería?"),
    ("Materiales", "Steel"): ("1.3", "¿Estructura (steel frame)?"),
    ("Materiales", "Ballon"): (None, "no sé qué es: ¿una marca?"),
    ("Materiales", "Aberturas"): ("1.8", "¿Carpinterías de PVC o aluminio, o de madera (1.9)?"),
    ("Materiales", "Aislación"): (None, "no está en la lista: ¿Techo (1.5), Corralón (1.2) o un rubro nuevo?"),
    ("Materiales", "Artefactos eléctricos"): ("1.18", "¿Artefactos de iluminación?"),
    ("Materiales", "pisos"): ("1.20", "¿Revestimientos?"),
    ("Materiales", "Mesadas"): ("1.19", "¿Marmolería?"),
    ("Materiales", "Zocalos y contramarcos"): ("1.9", "¿Carpinterías de madera, o Maderera (1.4)?"),
    ("Materiales", "Terminaciones"): (None, "no está en la lista (Insucom, Sergio González la usan)"),
    ("Mano de obra", "Especialistas"): (None, "según el oficio: Electricista (2.16), Sanitarista (2.2)…"),
    ("Servicios de obra", "Agrimensura"): (None, "no está en la lista: ¿Asesoría?"),
    ("Servicios públicos", "EPEN"): ("5.4", "en una obra, ¿Indirectos › Operativos? (en Austral es Servicios › Luz)"),
    ("Servicios públicos", "Camuzzi"): ("5.4", "en una obra, ¿Indirectos › Operativos? (en Austral, Servicios › Gas)"),
    ("Servicios públicos", "Metrogas"): ("5.4", "en una obra, ¿Indirectos › Operativos? (en Austral, Servicios › Gas)"),
    ("Servicios públicos", "Agua"): ("5.4", "en una obra, ¿Indirectos › Operativos?"),
    ("Honorarios", "Arquitectura"): (None, "un ingreso del estudio: no está en la lista"),
    ("Honorarios", "Dirección de obra"): (None, "un ingreso del estudio: no está en la lista"),
    ("Honorarios", "Escribanía"): (None, "no está en la lista: ¿Asesoría, o Indirectos › Administrativos (5.3)?"),
    ("Honorarios", "Asesores"): ("A5", "¿Austral › Contratados, o Asesorías externas (A4)?"),
    ("Impuestos y tasas", "AFIP"): ("A2.1", "¿Austral › Impuestos? (hoy sirve para obra y estudio)"),
    ("Impuestos y tasas", "IVA"): ("A2.1", "¿Austral › Impuestos? (hoy sirve para obra y estudio)"),
    ("Impuestos y tasas", "Rentas"): ("A11.1", "¿Austral › Impuestos y ART › Rentas? (hoy sirve para obra y estudio)"),
    ("Impuestos y tasas", "Municipales"): (None, "las tasas de una obra: no está en la lista"),
    ("Impuestos y tasas", "Bancarios"): (None, "los gastos bancarios del lote de la conciliación"),
    ("Estructura del estudio", "Aportes profesionales"): ("A11.6", "¿Caja previsional, o Colegio de Arquitectos (A8.1)?"),
    ("Estructura del estudio", "Servicios"): ("A1", "¿Austral › Servicios (Internet, Luz, Gas, Celular)? Hay que elegir el detalle"),
    ("Estructura del estudio", "Software"): (None, "no está en la lista: ¿Insumos (A6.1)?"),
    ("Estructura del estudio", "Movilidad"): (None, "no está en la lista"),
    ("Estructura del estudio", "Gastos generales"): ("A7.3", "¿Gastos corrientes › Otros? (21/10)"),
    ("Estructura del estudio", "Combustible"): (None, "no está en la lista (21/10, el ticket de YPF)"),
    ("Personal", "Familia"): (None, "no está en Retiros (las transferencias a la familia)"),
    ("Financiero", "Compra-venta de divisas"): (None, "no está en la lista"),
    ("Financiero", "Intereses"): (None, "no está en la lista"),
    ("Financiero", "Comisiones"): (None, "no está en la lista"),
}
# Rubros habituales inexistentes en CONTRATISTAS, resueltos por historial o nombre.
HABITUAL_FIJO = {
    "Elias Rodriguez": ("2.8", "su pago M-000012 está en Mano de obra › Zinguería"),
    "Contador Pasolli": ("A4.1", "es el contador del estudio («Honorarios › Terceros» no existía)"),
}


def _sin_numero(texto: str) -> str:
    return re.sub(r"^\s*\d+\.\s*", "", str(texto or "")).strip()


def _filas(hoja) -> list[tuple]:
    """Las filas de datos: las que vienen después del encabezado («Código · Rubro general · Descripción»)."""
    filas = list(hoja.iter_rows(values_only=True))
    inicio = next(i for i, f in enumerate(filas) if any(str(v or "").strip() == "Descripción" for v in f))
    return filas[inicio + 1:]


def rubros_del_excel(ruta: Path = EXCEL) -> list[dict]:
    """[{codigo, rubro_1, rubro_2, afecta}] en el orden del Excel."""
    import openpyxl
    libro = openpyxl.load_workbook(ruta, data_only=True)
    salida: list[dict] = []
    for fila in _filas(libro["Rubros de obra"]):
        codigo, general, detalle = (list(fila) + [None] * 3)[:3]
        if not codigo:
            continue
        codigo = str(codigo).strip()
        detalle = NOMBRE_6_1 if codigo == "6.1" else str(detalle).strip()
        salida.append({"codigo": codigo, "rubro_1": _sin_numero(general), "rubro_2": detalle, "afecta": "obra"})
    general = numero = None
    i = 0
    for fila in _filas(libro["Austral"]):
        codigo, nuevo_general, detalle = (list(fila) + [None] * 3)[:3]
        if not detalle:
            continue
        if nuevo_general:
            general, numero, i = str(nuevo_general).strip(), str(codigo).strip(), 0
        i += 1
        detalle = "Otros" if str(detalle).strip().lower().startswith("etc") else str(detalle).strip()
        salida.append({"codigo": f"A{numero}.{i}", "rubro_1": general, "rubro_2": detalle, "afecta": "estructura"})
    n = 0
    for fila in _filas(libro["Retiros"]):
        detalle = (list(fila) + [None] * 3)[2]
        if detalle:
            n += 1
            salida.append({"codigo": f"R{n}", "rubro_1": "Personal", "rubro_2": str(detalle).strip(), "afecta": "personal"})
    return salida


def _clave(r1, r2) -> tuple[str, str]:
    from app.maestros import normalizar
    return normalizar(r1), normalizar(r2)


def plan(filas_rubros: list[list], nuevos: list[dict]) -> dict:
    """Qué pasa con cada rubro: {«en_su_fila»: [(fila, nuevo)], «agregar»: [nuevo], «inactivar»:
    [(fila, viejo, codigo, motivo)], «a_confirmar»: [(fila, viejo, propuesta, motivo)]}."""
    enc = [str(x) for x in filas_rubros[0]]
    i1, i2 = enc.index("rubro_1"), enc.index("rubro_2")
    viejos = {_clave(f[i1], f[i2]): (n, f) for n, f in enumerate(filas_rubros[1:], start=2) if len(f) > i2 and f[i2]}
    por_codigo = {x["codigo"]: x for x in nuevos}
    salida = {"en_su_fila": [], "agregar": [], "inactivar": [], "a_confirmar": [], "sin_mapa": []}
    for x in nuevos:
        if _clave(x["rubro_1"], x["rubro_2"]) in viejos:
            salida["en_su_fila"].append((viejos[_clave(x["rubro_1"], x["rubro_2"])][0], x))
        else:
            salida["agregar"].append(x)
    nuevas_claves = {_clave(x["rubro_1"], x["rubro_2"]) for x in nuevos}
    mapa = {_clave(*k): v for k, v in MAPA.items()}
    propuesta = {_clave(*k): v for k, v in PROPUESTA.items()}
    for clave, (n, f) in viejos.items():
        if clave in nuevas_claves:
            continue
        viejo = (f[i1], f[i2])
        if clave in mapa:
            codigo, motivo = mapa[clave]
            assert codigo in por_codigo, codigo
            salida["inactivar"].append((n, viejo, codigo, motivo))
        elif clave in propuesta:
            codigo, motivo = propuesta[clave]
            salida["a_confirmar"].append((n, viejo, codigo, motivo))
        else:
            salida["sin_mapa"].append((n, viejo))
    return salida


def _orden_codigo(codigo: str | None) -> tuple:
    """1.2 < 1.10 < 2.1 < A1.1 < A11.1 < R1: el prefijo y los números, en orden numérico."""
    c = str(codigo or "")
    prefijo = c[:1] if c[:1].isalpha() else ""
    return (prefijo, [int(x) for x in re.findall(r"[0-9]+", c)])


def escribir_mapa(p: dict, nuevos: list[dict], destino: Path) -> None:
    """docs/maestros/mapa-rubros-2026-10-27.md, para que Gabriel lo revise."""
    por_codigo = {x["codigo"]: x for x in nuevos}

    def nombre(codigo):
        if not codigo:
            return "—"
        if codigo in por_codigo:
            x = por_codigo[codigo]
            return f"{codigo} · {x['rubro_1']} › {x['rubro_2']}"
        return codigo
    lineas = [
        "# Rubros: de la lista vieja a la del estudio (27/10)", "",
        "> Hecho con `scripts/migraciones/2026_10_27_rubros_estudio.py` a partir de",
        "> `Listado_general_rubros_obra_formato_unificado.xlsx` (CONTEXTO-FACHADO.md §5.4 v1.13). Nada se",
        "> borra: el rubro viejo pasa a `inactivo` con `reemplazado_por`, y el tablero muestra los",
        "> movimientos viejos con el rubro nuevo. MOVIMIENTOS no se toca.", "",
        f"- Rubros nuevos agregados: **{len(p['agregar'])}**",
        f"- Rubros que ya estaban con el mismo nombre (toman el código): **{len(p['en_su_fila'])}**",
        f"- Viejos que pasan a inactivo (equivalente claro): **{len(p['inactivar'])}**",
        f"- Viejos **a confirmar con Gabriel** (siguen activos): **{len(p['a_confirmar'])}**", "",
        "## Viejo → nuevo (pasan a inactivo)", "",
        "| Rubro viejo | Rubro nuevo | Por qué |", "|---|---|---|",
    ]
    lineas += [f"| {v[0]} › {v[1]} | {nombre(c)} | {m} |" for _, v, c, m in sorted(p["inactivar"], key=lambda t: _orden_codigo(t[2]))]
    lineas += ["", "## A confirmar con Gabriel (siguen activos hasta que diga)", "",
               "| Rubro viejo | Propuesta | Por qué |", "|---|---|---|"]
    lineas += [f"| {v[0]} › {v[1]} | {nombre(c) if c in por_codigo else (c or '—')} | {m} |" for _, v, c, m in p["a_confirmar"]]
    lineas += ["", "## Ya estaban, con el mismo nombre (toman el código)", "",
               ", ".join(f"{x['codigo']} {x['rubro_1']} › {x['rubro_2']}" for _, x in sorted(p["en_su_fila"], key=lambda t: _orden_codigo(t[1]["codigo"]))),
               "", "## Contratistas", "",
               "El rubro habitual que quedó inactivo pasa al nuevo. Además:", ""]
    lineas += [f"- **{c}** → {nombre(cod)}: {m}" for c, (cod, m) in HABITUAL_FIJO.items()]
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main() -> None:
    from _comun import Migracion
    mig = Migracion(["RUBROS", "CONTRATISTAS", "ALIAS"], __doc__)
    for col in ("codigo", "estado", "reemplazado_por"):
        mig.asegurar_columna("RUBROS", col)
    nuevos = rubros_del_excel()
    por_codigo = {x["codigo"]: x for x in nuevos}
    p = plan(mig.tablas["RUBROS"], nuevos)
    if p["sin_mapa"]:
        sys.exit(f"Rubros viejos sin entrada en MAPA ni en PROPUESTA: {p['sin_mapa']}")

    for fila, x in p["en_su_fila"]:
        mig.poner("RUBROS", fila, "codigo", x["codigo"], POR_QUE)
        mig.poner("RUBROS", fila, "estado", "activo", POR_QUE)
    for x in p["agregar"]:
        if not mig.buscar("RUBROS", rubro_1=x["rubro_1"], rubro_2=x["rubro_2"]):
            mig.agregar("RUBROS", {**x, "estado": "activo", "reemplazado_por": ""}, POR_QUE)
    inactivos: dict[tuple, str] = {}
    for fila, viejo, codigo, motivo in p["inactivar"]:
        mig.poner("RUBROS", fila, "estado", "inactivo", f"{POR_QUE}: {motivo}")
        mig.poner("RUBROS", fila, "reemplazado_por", codigo, f"{POR_QUE}: {motivo}")
        inactivos[_clave(*viejo)] = codigo
    for fila, _, _, _ in p["a_confirmar"]:
        mig.poner("RUBROS", fila, "estado", "activo", f"{POR_QUE}: a confirmar con Gabriel")

    from app.maestros import normalizar
    for fila, reg in mig.registros("CONTRATISTAS"):
        codigo = None
        if reg.get("contratista") in HABITUAL_FIJO:
            codigo = HABITUAL_FIJO[reg["contratista"]][0]
        elif _clave(reg.get("rubro_habitual_1"), reg.get("rubro_habitual_2")) in inactivos:
            codigo = inactivos[_clave(reg.get("rubro_habitual_1"), reg.get("rubro_habitual_2"))]
        if codigo:
            x = por_codigo[codigo]
            mig.poner("CONTRATISTAS", fila, "rubro_habitual_1", x["rubro_1"], f"{POR_QUE}: {codigo}")
            mig.poner("CONTRATISTAS", fila, "rubro_habitual_2", x["rubro_2"], f"{POR_QUE}: {codigo}")
    for fila, reg in mig.registros("ALIAS"):
        if normalizar(reg.get("tipo")) != "rubro":
            continue
        viejo = [v for k, v in inactivos.items() if k[1] == normalizar(reg.get("valor_canonico"))]
        if len(viejo) == 1:
            mig.poner("ALIAS", fila, "valor_canonico", por_codigo[viejo[0]]["rubro_2"], f"{POR_QUE}: el rubro pasó a {viejo[0]}")

    print(f"Rubros: {len(p['agregar'])} nuevos, {len(p['en_su_fila'])} ya estaban (toman el código), "
          f"{len(p['inactivar'])} pasan a inactivo, {len(p['a_confirmar'])} a confirmar (siguen activos)")
    mig.terminar()


if __name__ == "__main__":
    main()
