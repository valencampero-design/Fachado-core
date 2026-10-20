"""Las vistas del tablero y las cuentas corrientes por obra (CONTEXTO-FACHADO.md §5.21).

El tablero (Looker Studio) lee de hojas `VISTA_*` que el motor recalcula, no de MOVIMIENTOS
crudo: así no repite la lógica de anulados, cajas de obra, monedas, informales y personal.
Son **derivadas**: se reescriben enteras; MOVIMIENTOS nunca se toca.

- `VISTA_SALDOS`: por cuenta y por día, el saldo según el libro (cajas de obra aparte, en su
  moneda).
- `VISTA_OBRAS`: por obra, aportes del comitente, pagado con plata del estudio, pagado por el
  comitente, caja de obra, ejecutado, capital propio inmovilizado y semáforo.
- `VISTA_RUBROS`: mes × obra × rubro_1 × rubro_2 × tipo_gasto.
- `VISTA_PROVEEDORES`: mes × contratista × obra.
- `VISTA_DETALLE`: los movimientos vigentes, con el link al comprobante.
- `VISTA_PERSONAL`, en el libro personal: mes × rubro × destino.
- `CC_<OBRA>`: la cuenta corriente de **cada obra** de OBRAS (§5.21 v1.11: también las de
  proyecto y dirección, Austral y Jardín Maternal aunque esté cerrada), armada **desde las
  vistas de arriba** (decisión del 15/10: se escribe como valores en cada recálculo, no con
  fórmulas). Los **inmuebles personales** (Sur, Abucoque, Belelli, Gessel) tienen la suya en
  el **libro personal**, nunca en el Master (§5.13, §5.14).

Lo personal **nunca** entra en las vistas del Master: solo la línea semanal (§5.14).
Sin presupuestos (§5.21: etapa posterior).
"""
import logging
import re
from datetime import date, datetime

from app import maestros
from app.filtros import es_cierre_semanal, es_informal, sin_anulados
from app.libro import Libro
from app.maestros import Maestros, normalizar, numero
from app.saldos import como_dicts, en_moneda_de_la_cuenta, saldo_obra

logger = logging.getLogger(__name__)

DIAS_GRIS = 30
TIPOS_OBRA = ("obra_terceros", "obra_propia")


# ─── Qué entra ─────────────────────────────────────────────────────────────────

def _del_master(movs: list[dict]) -> list[dict]:
    """§5.14: en el Master, lo personal solo como la línea semanal."""
    return [mv for mv in sin_anulados(movs)
            if normalizar(mv.get("tipo_gasto")) != "personal" or es_cierre_semanal(mv)]


def _mes(fecha) -> str:
    return str(fecha or "")[:7]


def _pesos(mov: dict) -> float | None:
    """El importe en pesos: importe_ars si lo tiene (un movimiento en dólares a una caja en
    dólares no lo tiene: §5.8 v1.8)."""
    if str(mov.get("moneda") or "ARS").upper() == "ARS":
        return numero(mov.get("importe"))
    valor = mov.get("importe_ars")
    return numero(valor) if valor not in ("", None) else None


def _usd_sin_convertir(mov: dict) -> float:
    if str(mov.get("moneda") or "ARS").upper() != "ARS" and mov.get("importe_ars") in ("", None):
        return numero(mov.get("importe"))
    return 0.0


def obras_con_cc(m: Maestros) -> list:
    """§5.21 v1.11: todas las obras de OBRAS tienen cuenta corriente en el Master: las de
    terceros con cualquier servicio, las propias, Austral y las cerradas (Jardín Maternal, la
    de referencia). Una obra sin movimientos tiene igual su hoja, en cero. Los inmuebles
    personales no: van en el libro personal (`inmuebles_personales`)."""
    return [o for o in m.obras if o.tipo != "personal"]


def inmuebles_personales(m: Maestros) -> list:
    """Sur, Abucoque, Belelli, Gessel: su CC va en el libro personal (§5.13, §5.14)."""
    return [o for o in m.obras if o.tipo == "personal"]


def nombre_hoja_cc(obra: str) -> str:
    """«Grigera Galpón» → «CC_GRIGERA_GALPON» (las que ya existen: CC_LENNON, CC_GONZALO)."""
    return "CC_" + re.sub(r"\s+", "_", normalizar(obra)).upper()


# ─── Las vistas ────────────────────────────────────────────────────────────────

def vista_saldos(movs: list[dict], m: Maestros) -> list[list]:
    """Por cuenta y por día. Las cuentas del estudio y las cajas de obra (en su moneda);
    «Pagado por el comitente» no es plata de nadie que se cuente (§5.9) y los informales no
    pasaron por ninguna caja (§5.17)."""
    filas = [["fecha", "cuenta", "tipo_cuenta", "moneda", "es_caja_de_obra", "movido_en_el_dia", "saldo"]]
    for cuenta in [c for c in m.cuentas if c.activa and c.tipo != "externa"]:
        por_dia: dict[str, float] = {}
        for mov in movs:
            if normalizar(mov.get("cuenta")) != normalizar(cuenta.nombre) or es_informal(mov):
                continue
            if cuenta.fecha_apertura and str(mov.get("fecha") or "")[:10] < cuenta.fecha_apertura:
                continue
            valor = en_moneda_de_la_cuenta(mov, cuenta.moneda)
            if valor is None:
                continue
            signo = -1 if mov.get("tipo") == "EGRESO" else 1
            valor = valor if mov.get("tipo") == "TRASPASO" else signo * abs(valor)
            dia = str(mov.get("fecha") or "")[:10]
            por_dia[dia] = por_dia.get(dia, 0.0) + valor
        saldo = cuenta.saldo_apertura
        for dia in sorted(por_dia):
            saldo += por_dia[dia]
            filas.append([dia, cuenta.nombre, cuenta.tipo, cuenta.moneda, "sí" if cuenta.tipo == "caja_obra" else "no",
                          round(por_dia[dia], 2), round(saldo, 2)])
    return filas


def vista_obras(movs: list[dict], m: Maestros, hoy: date) -> list[list]:
    filas = [["obra", "tipo", "servicio", "comitente", "aportes_comitente", "pagado_con_plata_del_estudio",
              "pagado_por_el_comitente", "saldo", "caja_moneda", "caja_ingresado", "caja_pagado", "caja_por_rendir",
              "ejecutado_total_ars", "ejecutado_usd_sin_convertir", "ventas", "capital_propio_inmovilizado",
              "ultimo_movimiento", "semaforo", "lleva_cc"]]
    con_cc = {o.nombre for o in obras_con_cc(m)}
    for obra in obras_con_cc(m):
        propios = [mv for mv in movs if normalizar(mv.get("obra")) == normalizar(obra.nombre)]
        s, _ = saldo_obra(propios, obra.nombre, m)
        egresos = [mv for mv in propios if mv.get("tipo") in ("EGRESO", "PASANTE")]
        ejecutado = round(sum(_pesos(mv) or 0.0 for mv in egresos), 2)
        ejecutado_usd = round(sum(_usd_sin_convertir(mv) for mv in egresos), 2)
        # Lo que la obra devolvió: en una obra propia, lo que entró (ventas, §5.21).
        ventas = round(sum(_pesos(mv) or 0.0 for mv in propios if mv.get("tipo") == "INGRESO"), 2) \
            if obra.tipo == "obra_propia" else 0.0
        # §5.21 (definición de A&C, a validar con Gabriel): obra propia → lo que puso el estudio
        # menos lo que devolvió; de terceros → lo pagado con plata del estudio menos lo
        # adelantado por el comitente, si es positivo.
        if obra.tipo == "obra_propia":
            capital = round(s.pagado_con_plata_del_estudio - ventas, 2)
        else:
            capital = round(max(0.0, s.pagado_con_plata_del_estudio - s.adelantado), 2)
        ultimo = max((str(mv.get("fecha") or "")[:10] for mv in propios), default="")
        caja = s.caja_obra
        if obra.tipo not in TIPOS_OBRA:
            capital = 0.0  # Austral: los indirectos del estudio no son capital en una obra
        rojo = (caja is not None and caja.por_rendir < 0) or (obra.tipo == "obra_terceros" and capital > 0)
        gris = not ultimo or (hoy - date.fromisoformat(ultimo)).days > DIAS_GRIS
        semaforo = "rojo" if rojo else "gris" if gris else "verde"
        filas.append([obra.nombre, obra.tipo, obra.servicio, obra.comitente, s.adelantado, s.pagado_con_plata_del_estudio,
                      s.pagado_por_el_comitente, s.saldo, caja.moneda if caja else "", caja.ingresado if caja else "",
                      caja.pagado if caja else "", caja.por_rendir if caja else "", ejecutado, ejecutado_usd, ventas,
                      capital, ultimo, semaforo, "sí" if obra.nombre in con_cc else "no"])
    return filas


def vista_rubros(movs: list[dict]) -> list[list]:
    acumulado: dict[tuple, list[float]] = {}
    for mv in movs:
        if mv.get("tipo") not in ("EGRESO", "PASANTE"):
            continue
        clave = (_mes(mv.get("fecha")), mv.get("obra") or "", mv.get("rubro_1") or "Sin rubro", mv.get("rubro_2") or "",
                 mv.get("tipo_gasto") or "")
        a = acumulado.setdefault(clave, [0.0, 0.0, 0])
        a[0] += _pesos(mv) or 0.0
        a[1] += _usd_sin_convertir(mv)
        a[2] += 1
    filas = [["mes", "obra", "rubro_1", "rubro_2", "tipo_gasto", "importe_ars", "importe_usd_sin_convertir", "cantidad"]]
    filas += [[*k, round(v[0], 2), round(v[1], 2), v[2]] for k, v in sorted(acumulado.items())]
    return filas


def vista_proveedores(movs: list[dict]) -> list[list]:
    acumulado: dict[tuple, list[float]] = {}
    for mv in movs:
        if mv.get("tipo") not in ("EGRESO", "PASANTE") or not mv.get("contratista") or es_cierre_semanal(mv):
            continue
        clave = (_mes(mv.get("fecha")), mv.get("contratista"), mv.get("obra") or "")
        a = acumulado.setdefault(clave, [0.0, 0.0, 0])
        a[0] += _pesos(mv) or 0.0
        a[1] += _usd_sin_convertir(mv)
        a[2] += 1
    filas = [["mes", "contratista", "obra", "importe_ars", "importe_usd_sin_convertir", "cantidad_pagos"]]
    filas += [[*k, round(v[0], 2), round(v[1], 2), v[2]] for k, v in sorted(acumulado.items())]
    return filas


COLUMNAS_DETALLE = ["id_mov", "fecha", "mes", "tipo", "obra", "etapa", "contratista", "item", "rubro_1", "rubro_2",
                    "tipo_gasto", "cuenta", "quien_pago", "moneda", "importe", "importe_ars", "tc", "descripcion",
                    "comprobante_url", "cargado_por", "estado_conc"]


def _quien_pago(mov: dict, m: Maestros) -> str:
    if mov.get("tipo") == "PASANTE":
        return "comitente"
    cuenta = m.cuenta(mov.get("cuenta"), incluir_inactivas=True)
    if cuenta is None:
        return ""
    return {"caja_obra": "caja de obra", "externa": "comitente"}.get(cuenta.tipo, "estudio")


def vista_detalle(movs: list[dict], m: Maestros) -> list[list]:
    filas = [list(COLUMNAS_DETALLE)]
    for mv in sorted(movs, key=lambda x: (str(x.get("fecha") or ""), str(x.get("id_mov") or ""))):
        fila = {c: mv.get(c, "") for c in COLUMNAS_DETALLE}
        fila["mes"], fila["quien_pago"] = _mes(mv.get("fecha")), _quien_pago(mv, m)
        filas.append([fila[c] if fila[c] is not None else "" for c in COLUMNAS_DETALLE])
    return filas


def vista_personal(movs: list[dict]) -> list[list]:
    """En el libro personal (§5.14, solo para quien tiene ve_personal): mes × rubro × destino."""
    acumulado: dict[tuple, list[float]] = {}
    for mv in sin_anulados(movs):
        if mv.get("tipo") not in ("EGRESO", "PASANTE"):
            continue
        clave = (_mes(mv.get("fecha")), mv.get("rubro_1") or "Sin rubro", mv.get("rubro_2") or "", mv.get("obra") or "")
        a = acumulado.setdefault(clave, [0.0, 0])
        a[0] += _pesos(mv) or 0.0
        a[1] += 1
    filas = [["mes", "rubro_1", "rubro_2", "destino", "importe_ars", "cantidad"]]
    filas += [[*k, round(v[0], 2), v[1]] for k, v in sorted(acumulado.items())]
    return filas


# ─── Cuentas corrientes por obra, desde las vistas ─────────────────────────────

def _registros(tabla: list[list]) -> list[dict]:
    return [dict(zip(tabla[0], f)) for f in tabla[1:]]


def cuenta_corriente(obra, vistas: dict[str, list[list]], m: Maestros, ahora: str) -> list[list]:
    """La hoja CC_<OBRA>, con la lógica de la planilla de Gabriel: encabezado, aportes del
    comitente, por contratista, por rubro y el detalle cronológico con el comprobante (y la
    etapa en las obras que tienen). Lee VISTA_OBRAS y VISTA_DETALLE, nada más."""
    resumen = next((r for r in _registros(vistas["VISTA_OBRAS"]) if r["obra"] == obra.nombre), None) or {}
    detalle = [r for r in _registros(vistas["VISTA_DETALLE"]) if r["obra"] == obra.nombre]
    con_etapas = any(e.obra == obra.nombre for e in m.etapas)
    caja = f"{resumen.get('caja_por_rendir')} {resumen.get('caja_moneda')}" if resumen.get("caja_moneda") else "sin caja"
    filas: list[list] = [
        [f"Cuenta corriente · {obra.nombre}", f"Comitente: {obra.comitente or '—'}", f"Actualizado: {ahora}"],
        ["Derivada: la escribe el motor (§5.21). No editar a mano: se reescribe cada noche."],
        [],
        ["Aportes del comitente", "Pagado con plata del estudio", "Pagado por el comitente", "Caja de obra (por rendir)",
         "Saldo", "Ejecutado total ($)", "Capital propio inmovilizado", "Semáforo"],
        [resumen.get("aportes_comitente", 0), resumen.get("pagado_con_plata_del_estudio", 0),
         resumen.get("pagado_por_el_comitente", 0), caja, resumen.get("saldo", 0), resumen.get("ejecutado_total_ars", 0),
         resumen.get("capital_propio_inmovilizado", 0), resumen.get("semaforo", "")],
        [],
        ["APORTES DEL COMITENTE"],
        ["fecha", "importe", "moneda", "cuenta", "descripcion", "comprobante"],
    ]
    for r in detalle:
        if r["tipo"] == "INGRESO":
            filas.append([r["fecha"], r["importe"], r["moneda"], r["cuenta"], r["descripcion"], r["comprobante_url"]])
    filas += [[], ["POR CONTRATISTA"], ["contratista", "cantidad de pagos", "total ($)", "total US$ sin convertir"]]
    por_contratista: dict[str, list[float]] = {}
    for r in detalle:
        if r["tipo"] in ("EGRESO", "PASANTE"):
            a = por_contratista.setdefault(r["contratista"] or "(sin contratista)", [0, 0.0, 0.0])
            a[0] += 1
            a[1] += _pesos(r) or 0.0
            a[2] += _usd_sin_convertir(r)
    filas += [[k, v[0], round(v[1], 2), round(v[2], 2)] for k, v in sorted(por_contratista.items(), key=lambda x: -x[1][1])]
    filas += [[], ["POR RUBRO"], ["rubro_1", "rubro_2", "total ($)", "total US$ sin convertir"]]
    por_rubro: dict[tuple, list[float]] = {}
    for r in detalle:
        if r["tipo"] in ("EGRESO", "PASANTE"):
            a = por_rubro.setdefault((r["rubro_1"] or "Sin rubro", r["rubro_2"] or ""), [0.0, 0.0])
            a[0] += _pesos(r) or 0.0
            a[1] += _usd_sin_convertir(r)
    filas += [[*k, round(v[0], 2), round(v[1], 2)] for k, v in sorted(por_rubro.items(), key=lambda x: -x[1][0])]
    cols = ["fecha", "id_mov", "tipo"] + (["etapa"] if con_etapas else []) + \
        ["contratista", "rubro_2", "quien_pago", "cuenta", "moneda", "importe", "importe_ars", "descripcion", "comprobante_url"]
    filas += [[], ["DETALLE CRONOLÓGICO"], cols]
    filas += [[r.get(c, "") for c in cols] for r in detalle]
    return filas


def cuenta_corriente_personal(inmueble, detalle: list[list], ahora: str) -> list[list]:
    """La CC_<INMUEBLE> en el libro personal: el mismo formato que la de una obra, sin el
    bloque de aportes del comitente (no hay comitente). Lee el detalle personal, nada más."""
    filas_detalle = [r for r in _registros(detalle) if r["obra"] == inmueble.nombre]
    pagos = [r for r in filas_detalle if r["tipo"] in ("EGRESO", "PASANTE")]
    ultimo = max((str(r["fecha"])[:10] for r in filas_detalle), default="")
    filas: list[list] = [
        [f"Cuenta corriente · {inmueble.nombre}", "Inmueble personal (§5.14)", f"Actualizado: {ahora}"],
        ["Derivada: la escribe el motor (§5.21). No editar a mano: se reescribe cada noche."],
        [],
        ["Pagado ($)", "Pagado en US$ sin convertir", "Cantidad de pagos", "Último movimiento"],
        [round(sum(_pesos(r) or 0.0 for r in pagos), 2), round(sum(_usd_sin_convertir(r) for r in pagos), 2),
         len(pagos), ultimo],
        [],
        ["POR CONTRATISTA"], ["contratista", "cantidad de pagos", "total ($)", "total US$ sin convertir"],
    ]
    por_contratista: dict[str, list[float]] = {}
    for r in pagos:
        a = por_contratista.setdefault(r["contratista"] or "(sin contratista)", [0, 0.0, 0.0])
        a[0] += 1
        a[1] += _pesos(r) or 0.0
        a[2] += _usd_sin_convertir(r)
    filas += [[k, v[0], round(v[1], 2), round(v[2], 2)] for k, v in sorted(por_contratista.items(), key=lambda x: -x[1][1])]
    filas += [[], ["POR RUBRO"], ["rubro_1", "rubro_2", "total ($)", "total US$ sin convertir"]]
    por_rubro: dict[tuple, list[float]] = {}
    for r in pagos:
        a = por_rubro.setdefault((r["rubro_1"] or "Sin rubro", r["rubro_2"] or "Sin rubro"), [0.0, 0.0])
        a[0] += _pesos(r) or 0.0
        a[1] += _usd_sin_convertir(r)
    filas += [[*k, round(v[0], 2), round(v[1], 2)] for k, v in sorted(por_rubro.items(), key=lambda x: -x[1][0])]
    cols = ["fecha", "id_mov", "tipo", "contratista", "rubro_2", "cuenta", "moneda", "importe", "importe_ars",
            "descripcion", "comprobante_url"]
    filas += [[], ["DETALLE CRONOLÓGICO"], cols]
    filas += [[r.get(c, "") for c in cols] for r in filas_detalle]
    return filas


# ─── El recálculo ──────────────────────────────────────────────────────────────

def calcular(libro: Libro, libro_personal: Libro | None, m: Maestros | None = None,
             hoy: date | None = None) -> dict[str, dict[str, list[list]]]:
    """{"master": {hoja: filas}, "personal": {hoja: filas}}: todo lo que se escribiría."""
    m = m or maestros.cargar()
    hoy = hoy or date.today()
    movs = _del_master(como_dicts(libro.leer_movimientos()))
    master = {
        "VISTA_SALDOS": vista_saldos(movs, m),
        "VISTA_OBRAS": vista_obras(movs, m, hoy),
        "VISTA_RUBROS": vista_rubros(movs),
        "VISTA_PROVEEDORES": vista_proveedores(movs),
        "VISTA_DETALLE": vista_detalle(movs, m),
    }
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    for obra in obras_con_cc(m):
        master[nombre_hoja_cc(obra.nombre)] = cuenta_corriente(obra, master, m, ahora)
    personal = {}
    if libro_personal is not None:
        movs_p = sin_anulados(como_dicts(libro_personal.leer_movimientos()))
        personal["VISTA_PERSONAL"] = vista_personal(movs_p)
        personal["VISTA_DETALLE"] = vista_detalle(movs_p, m)  # el detalle personal, en su libro
        for inmueble in inmuebles_personales(m):
            personal[nombre_hoja_cc(inmueble.nombre)] = cuenta_corriente_personal(inmueble, personal["VISTA_DETALLE"], ahora)
    return {"master": master, "personal": personal}


def recalcular(libro: Libro, libro_personal: Libro | None, solo_cc: bool = False) -> dict:
    """POST /vistas/recalcular (y scripts/crear_cc_obras.py con `solo_cc`): escribe las hojas.
    Devuelve {hoja: filas escritas}."""
    hojas = calcular(libro, libro_personal)
    escritas = {}
    for hoja, filas in hojas["master"].items():
        if solo_cc and not hoja.startswith("CC_"):
            continue
        libro.escribir_hoja(hoja, filas)
        escritas[hoja] = len(filas) - 1
    if libro_personal is not None:
        for hoja, filas in hojas["personal"].items():
            if solo_cc and not hoja.startswith("CC_"):
                continue
            libro_personal.escribir_hoja(hoja, filas)
            escritas[f"personal:{hoja}"] = len(filas) - 1
    return {"escritas": escritas}
