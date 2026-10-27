"""Las vistas del tablero y las cuentas corrientes por obra (§5.21, handoff del 15/10), contra
libros en memoria. Nunca se escribe en el Sheet real.

    python -m tests.test_vistas
"""
import io
import json
import os
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ["MAESTROS_SNAPSHOT"] = str(RAIZ / "maestros_snapshot.json")
    os.environ["LLM_HABILITADO"] = "false"
    os.environ["MOTOR_API_KEY"] = "test-local"

    from fastapi.testclient import TestClient

    from app import maestros, vistas
    from app.main import app, obtener_libro, obtener_libro_personal
    from tests.dobles import LibroMemoria, cuenta_en_moneda

    fallas: list[str] = []

    def check(descripcion, condicion, detalle=""):
        ok = bool(condicion)
        print(f"  {'PASA ' if ok else 'FALLA'}  {descripcion}{'' if ok else '  → ' + str(detalle)[:600]}")
        if not ok:
            fallas.append(descripcion)

    snapshot = json.loads((RAIZ / "maestros_snapshot.json").read_text(encoding="utf-8"))
    encabezado = snapshot["MOVIMIENTOS"][0] + [c for c in ("vinculo", "anula") if c not in snapshot["MOVIMIENTOS"][0]]

    def preparar():
        estudio, personal = LibroMemoria(encabezado), LibroMemoria(encabezado)
        b = dict(origen="WHATSAPP", cargado_por="Gabriel Fachado")
        # Lennon: aporte a la caja en dólares, un pago en pesos con tc y uno en dólares
        estudio.sembrar(id_mov="M-000001", fecha="2026-10-01", tipo="INGRESO", importe=20000, moneda="USD", tc="",
                        importe_ars="", obra="Lennon", etapa="1", cuenta="Caja obra Lennon", tipo_gasto="obra", **b)
        estudio.sembrar(id_mov="M-000002", fecha="2026-10-03", tipo="EGRESO", importe=1450000, moneda="ARS", tc=1450,
                        importe_ars=1450000, obra="Lennon", etapa="1", contratista="Miguel Soto", rubro_1="Mano de obra",
                        rubro_2="Contratistas", cuenta="Caja obra Lennon", tipo_gasto="obra",
                        comprobante_url="https://drive.google.com/file/d/RECIBO/view", **b)
        estudio.sembrar(id_mov="M-000003", fecha="2026-10-09", tipo="EGRESO", importe=2000, moneda="USD", tc="",
                        importe_ars="", obra="Lennon", etapa="1", contratista="Miguel Soto", rubro_1="Mano de obra",
                        rubro_2="Contratistas", cuenta="Caja obra Lennon", tipo_gasto="obra", **b)
        # Lennon: el comitente pagó directo (§5.9) y un depósito «en negro» (§5.17)
        estudio.sembrar(id_mov="M-000004", fecha="2026-10-05", tipo="EGRESO", importe=500000, moneda="ARS", tc=1,
                        importe_ars=500000, obra="Lennon", contratista="Felipe Andrés Scherer", rubro_1="Servicios de obra",
                        rubro_2="Movimiento de suelos", cuenta="Pagado por el comitente", tipo_gasto="obra", **b)
        estudio.sembrar(id_mov="M-000005", fecha="2026-10-06", tipo="PASANTE", importe=100000, moneda="ARS", tc=1,
                        importe_ars=100000, obra="Lennon", contratista="Miguel Soto", cuenta="Pagado por el comitente",
                        informal="VERDADERO", tipo_gasto="obra", **b)
        # Gonzalo (propia): el estudio pone 300.000 y vende por 100.000
        estudio.sembrar(id_mov="M-000006", fecha="2026-10-02", tipo="EGRESO", importe=300000, moneda="ARS", tc=1,
                        importe_ars=300000, obra="Gonzalo", contratista="Tucu", rubro_1="Mano de obra", rubro_2="Jornales",
                        cuenta="Banco", tipo_gasto="obra", **b)
        estudio.sembrar(id_mov="M-000007", fecha="2026-10-08", tipo="INGRESO", importe=100000, moneda="ARS", tc=1,
                        importe_ars=100000, obra="Gonzalo", cuenta="Banco", tipo_gasto="obra", **b)
        # un par anulado (§5.19): no aparece en ninguna vista
        estudio.sembrar(id_mov="M-000008", fecha="2026-10-04", tipo="EGRESO", importe=777777, moneda="ARS", tc=1,
                        importe_ars=777777, obra="Gonzalo", contratista="Tucu", cuenta="Banco", tipo_gasto="obra", **b)
        estudio.sembrar(id_mov="M-000009", fecha="2026-10-04", tipo="EGRESO", importe=-777777, moneda="ARS", tc=1,
                        importe_ars=-777777, obra="Gonzalo", contratista="Tucu", cuenta="Banco", anula="M-000008", **b)
        # la línea semanal de personales (la única forma en que lo personal entra al Master)
        estudio.sembrar(id_mov="M-000010", fecha="2026-10-12", tipo="EGRESO", importe=50000, moneda="ARS", tc=1,
                        importe_ars=50000, cuenta="Banco", tipo_gasto="personal", **{**b, "origen": "CIERRE"})
        # una fila personal colada en el Master (no debería existir): no entra
        estudio.sembrar(id_mov="M-000011", fecha="2026-10-12", tipo="EGRESO", importe=12345, moneda="ARS", tc=1,
                        importe_ars=12345, cuenta="Banco", tipo_gasto="personal", rubro_1="Personal", rubro_2="Familia", **b)
        personal.sembrar(id_mov="P-000001", fecha="2026-10-10", tipo="EGRESO", importe=80000, moneda="ARS", tc=1,
                         importe_ars=80000, contratista="Sofía Fachado", rubro_1="Personal", rubro_2="Familia",
                         cuenta="Banco", tipo_gasto="personal", **b)
        personal.sembrar(id_mov="P-000002", fecha="2026-10-11", tipo="EGRESO", importe=30000, moneda="ARS", tc=1,
                         importe_ars=30000, obra="Belelli", contratista="Edesur", rubro_1="Servicios públicos",
                         rubro_2="Agua", cuenta="Mercado Pago", tipo_gasto="personal", **b)
        return estudio, personal

    with cuenta_en_moneda("Caja obra Lennon", "USD"):
        m = maestros.cargar()
        estudio, personal = preparar()
        hojas = vistas.calcular(estudio, personal, m, hoy=date(2026, 10, 15))
        master = hojas["master"]
        reg = lambda h: [dict(zip(master[h][0], f)) for f in master[h][1:]]  # noqa: E731

        print("\n§5.21 · Las vistas")
        cc_master = {h for h in master if h.startswith("CC_")}
        cc_personal = {h for h in hojas["personal"] if h.startswith("CC_")}
        check("hojas: VISTA_SALDOS, VISTA_OBRAS, VISTA_RUBROS, VISTA_PROVEEDORES, VISTA_DETALLE",
              {"VISTA_SALDOS", "VISTA_OBRAS", "VISTA_RUBROS", "VISTA_PROVEEDORES", "VISTA_DETALLE"} <= set(master),
              sorted(master))
        check("§5.21 v1.11: 13 CC_ en el Master (las 11 obras de §6, Austral y Jardín Maternal aunque esté cerrada)",
              cc_master == {"CC_LENNON", "CC_MORENO", "CC_CERRO_BAYO", "CC_LUMAIA", "CC_MUELLE_DE_PIEDRA", "CC_TONGA",
                            "CC_MOQUEHUE", "CC_GONZALO", "CC_HUA_HUAN", "CC_GRIGERA_GALPON", "CC_TRES_CERROS",
                            "CC_AUSTRAL", "CC_JARDIN_MATERNAL"}, sorted(cc_master))
        check("… y 4 en el libro personal (Sur, Abucoque, Belelli, Gessel); ninguna personal en el Master",
              cc_personal == {"CC_SUR", "CC_ABUCOQUE", "CC_BELELLI", "CC_GESSEL"} and not cc_master & cc_personal,
              sorted(cc_personal))
        cerro = master["CC_CERRO_BAYO"]
        check("una obra sin movimientos tiene igual su hoja, con los totales en cero (Cerro Bayo)",
              cerro[4][:3] == [0.0, 0.0, 0.0], cerro[4])
        belelli = hojas["personal"]["CC_BELELLI"]
        k = next(i for i, f in enumerate(belelli) if f[:1] == ["DETALLE CRONOLÓGICO"])
        check("CC_BELELLI (personal): el pago de Edesur en el detalle, con el mismo formato (por contratista, por rubro)",
              any("P-000002" in map(str, f) for f in belelli[k:]) and ["POR CONTRATISTA"] in belelli
              and ["POR RUBRO"] in belelli, belelli[:6])
        detalle = reg("VISTA_DETALLE")
        ids = {r["id_mov"] for r in detalle}
        check("VISTA_DETALLE: sin el par anulado y sin la fila personal colada; con la línea semanal",
              not ids & {"M-000008", "M-000009", "M-000011"} and "M-000010" in ids, sorted(ids))
        check("… con el link al comprobante y quién pagó (caja de obra, comitente, estudio)",
              next(r for r in detalle if r["id_mov"] == "M-000002")["comprobante_url"].endswith("RECIBO/view")
              and {r["id_mov"]: r["quien_pago"] for r in detalle}["M-000004"] == "comitente"
              and {r["id_mov"]: r["quien_pago"] for r in detalle}["M-000003"] == "caja de obra")
        saldos = reg("VISTA_SALDOS")
        caja = [r for r in saldos if r["cuenta"] == "Caja obra Lennon"]
        check("VISTA_SALDOS: la caja de Lennon en dólares, día por día: 20.000 → 19.000 → 17.000",
              [(r["fecha"], r["saldo"], r["moneda"]) for r in caja]
              == [("2026-10-01", 20000, "USD"), ("2026-10-03", 19000, "USD"), ("2026-10-09", 17000, "USD")], caja)
        check("… «Pagado por el comitente» no es una cuenta con saldo",
              not any(r["cuenta"] == "Pagado por el comitente" for r in saldos))
        obras = {r["obra"]: r for r in reg("VISTA_OBRAS")}
        lennon, gonzalo = obras["Lennon"], obras["Gonzalo"]
        check("VISTA_OBRAS Lennon: pagado por el comitente 600.000 (directo + informal), caja US$ 17.000, sin "
              "capital propio, verde",
              (lennon["pagado_por_el_comitente"], lennon["caja_moneda"], lennon["caja_por_rendir"],
               lennon["capital_propio_inmovilizado"], lennon["semaforo"]) == (600000, "USD", 17000, 0, "verde"), lennon)
        check("… ejecutado en pesos (lo que tiene importe_ars) y aparte lo que está en dólares sin convertir",
              (lennon["ejecutado_total_ars"], lennon["ejecutado_usd_sin_convertir"]) == (2050000, 2000), lennon)
        check("Gonzalo (propia): capital propio = lo que puso el estudio menos lo que devolvió (300.000 − 100.000)",
              (gonzalo["pagado_con_plata_del_estudio"], gonzalo["ventas"], gonzalo["capital_propio_inmovilizado"])
              == (300000, 100000, 200000), gonzalo)
        check("semáforo: una obra sin movimientos en 30 días es gris (Moquehue)", obras["Moquehue"]["semaforo"] == "gris")
        con_estudio_financiando = vistas.vista_obras(
            [{"obra": "Moreno", "tipo": "EGRESO", "importe": 5000, "importe_ars": 5000, "moneda": "ARS", "cuenta": "Banco",
              "fecha": "2026-10-14"}], m, date(2026, 10, 15))
        moreno = dict(zip(con_estudio_financiando[0], next(f for f in con_estudio_financiando[1:] if f[0] == "Moreno")))
        check("… y una de terceros donde el estudio pagó más de lo que adelantó el comitente es roja",
              (moreno["capital_propio_inmovilizado"], moreno["semaforo"]) == (5000, "rojo"), moreno)
        rubros = reg("VISTA_RUBROS")
        check("VISTA_RUBROS: mes × obra × rubro × tipo_gasto, en pesos y lo que está en dólares aparte",
              any(r["mes"] == "2026-10" and r["obra"] == "Lennon" and r["rubro_2"] == "Contratista principal"
                  and r["importe_ars"] == 1450000 and r["importe_usd_sin_convertir"] == 2000 for r in rubros), rubros)
        prov = reg("VISTA_PROVEEDORES")
        miguel = [r for r in prov if r["contratista"] == "Miguel Soto" and r["obra"] == "Lennon"]
        check("VISTA_PROVEEDORES: Miguel Soto en Lennon, 3 pagos (dos de la caja y el depósito informal)",
              miguel and miguel[0]["cantidad_pagos"] == 3, miguel)
        vp = [dict(zip(hojas["personal"]["VISTA_PERSONAL"][0], f)) for f in hojas["personal"]["VISTA_PERSONAL"][1:]]
        check("VISTA_PERSONAL (en el libro personal): mes × rubro × destino",
              {(r["rubro_2"], r["destino"], r["importe_ars"]) for r in vp} == {("Familia", "", 80000), ("Agua", "Belelli", 30000)}, vp)
        print("\n§5.4 v1.13 · los rubros viejos se muestran con la lista del estudio (27/10)")
        lennon_r = next(r for r in rubros if r["obra"] == "Lennon" and r["rubro_2"] == "Contratista principal")
        check("VISTA_RUBROS: el pago cargado con «Mano de obra › Contratistas» (inactivo) sale como 2.1 Contratista "
              "principal, con codigo y rubro_general; ninguna fila con un rubro inactivo",
              (lennon_r["codigo"], lennon_r["rubro_general"]) == ("2.1", "Mano de obra")
              and not any(m.rubro(r["rubro_1"], r["rubro_2"]) is not None and not m.rubro(r["rubro_1"], r["rubro_2"]).activo
                          for r in rubros), lennon_r)
        det2 = {r["id_mov"]: r for r in reg("VISTA_DETALLE")}
        check("VISTA_DETALLE: el movimiento M-000002 (Contratistas) con el rubro nuevo, codigo 2.1 y rubro_general",
              (det2["M-000002"]["rubro_2"], det2["M-000002"]["codigo"], det2["M-000002"]["rubro_general"])
              == ("Contratista principal", "2.1", "Mano de obra"), det2["M-000002"])
        cc_l = master["CC_LENNON"]
        i_r = next(i for i, f in enumerate(cc_l) if f[:1] == ["POR RUBRO"])
        check("CC_LENNON, «POR RUBRO»: con el rubro nuevo, nunca el viejo",
              any("Contratista principal" in map(str, f) for f in cc_l[i_r:]) and not any("Contratistas" in map(str, f)
                                                                                           for f in cc_l[i_r:]), cc_l[i_r:i_r + 5])
        check("VISTA_PERSONAL: rubro_general «Retiros» (en el maestro sigue siendo «Personal»), codigo y mes_fecha",
              all(r["rubro_general"] == "Retiros" for r in vp) and all("mes_fecha" in r for r in vp), vp)
        check("lo personal nunca en las vistas del Master: ni Sofía Fachado ni Edesur",
              "Sofía Fachado" not in json.dumps(master, ensure_ascii=False) and "Edesur" not in json.dumps(master))

        print("\n§5.21 · CC_<OBRA> desde las vistas")
        cc = master["CC_LENNON"]
        check("CC_LENNON: encabezado con aportes, pagado con plata del estudio, pagado por el comitente, caja en su "
              "moneda y saldo", cc[3][:5] == ["Aportes del comitente", "Pagado con plata del estudio",
                                               "Pagado por el comitente", "Caja de obra (por rendir)", "Saldo"]
              and cc[4][2] == 600000 and cc[4][3] == "17000.0 USD", cc[3:5])
        bloques = [f[0] for f in cc if f and f[0] in ("APORTES DEL COMITENTE", "POR CONTRATISTA", "POR RUBRO",
                                                      "DETALLE CRONOLÓGICO")]
        check("… bloques: aportes · por contratista · por rubro · detalle cronológico",
              bloques == ["APORTES DEL COMITENTE", "POR CONTRATISTA", "POR RUBRO", "DETALLE CRONOLÓGICO"], bloques)
        i = next(i for i, f in enumerate(cc) if f[:1] == ["DETALLE CRONOLÓGICO"])
        check("… el detalle lleva la etapa (Lennon tiene) y el comprobante",
              "etapa" in cc[i + 1] and "comprobante_url" in cc[i + 1] and len(cc) - i - 2 == 5, cc[i + 1])
        g = master["CC_GONZALO"]
        j = next(i for i, f in enumerate(g) if f[:1] == ["DETALLE CRONOLÓGICO"])
        check("CC_GONZALO: sin columna de etapa y sin el par anulado", "etapa" not in g[j + 1]
              and not any("M-000008" in map(str, f) for f in g), g[j + 1])

        print("\n§5.21 v1.11 · El tablero que pidió Gabriel (handoff del 20/10, M4)")
        check("hojas nuevas: VISTA_OBRAS_MES y VISTA_GENERAL", {"VISTA_OBRAS_MES", "VISTA_GENERAL"} <= set(master), sorted(master))
        om = {(r["obra"], r["mes"]): r for r in reg("VISTA_OBRAS_MES")}
        lm = om.get(("Lennon", "2026-10"), {})
        check("VISTA_OBRAS_MES Lennon 2026-10: lo que pagó directo el comitente (600.000) es ingreso y pago (§5.9: "
              "no aparece como si el estudio financiara la obra); pagos 2.050.000",
              (lm.get("pagado_directo_por_el_comitente"), lm.get("ingresos"), lm.get("pagos"), lm.get("saldo_mes"))
              == (600000, 600000, 2050000, -1450000), lm)
        check("… lo que está en dólares sin convertir, aparte: entró US$ 20.000 a la caja, salieron US$ 2.000",
              (lm.get("ingresos_usd_sin_convertir"), lm.get("pagos_usd_sin_convertir"),
               lm.get("saldo_acumulado_usd_sin_convertir")) == (20000, 2000, 18000), lm)
        gm = om.get(("Gonzalo", "2026-10"), {})
        check("Gonzalo 2026-10: ingresos 100.000 (lo que entró), pagos 300.000, saldo −200.000; mes_fecha 2026-10-01",
              (gm.get("ingresos"), gm.get("pagos"), gm.get("saldo_acumulado"), gm.get("mes_fecha"))
              == (100000, 300000, -200000, "2026-10-01"), gm)
        check("… una obra sin movimientos no tiene filas", not any(o == "Cerro Bayo" for o, _ in om))
        serie = vistas.vista_obras_mes([
            {"obra": "Moreno", "tipo": "INGRESO", "importe": 1000, "importe_ars": 1000, "moneda": "ARS", "cuenta": "Banco",
             "rubro_1": "Ingresos", "rubro_2": "Honorarios", "fecha": "2026-08-20"},
            {"obra": "Moreno", "tipo": "INGRESO", "importe": 5000, "importe_ars": 5000, "moneda": "ARS",
             "cuenta": "Caja obra Moreno", "fecha": "2026-08-25"},
            {"obra": "Moreno", "tipo": "EGRESO", "importe": 4000, "importe_ars": 4000, "moneda": "ARS",
             "cuenta": "Caja obra Moreno", "fecha": "2026-10-02"}], m, date(2026, 11, 3))
        sm = [dict(zip(serie[0], f)) for f in serie[1:]]
        check("S5: honorarios y aportes del comitente (también a la caja de obra) son ingresos, cada uno en su columna; "
              "los meses sin movimientos van en cero hasta el actual, con el saldo acumulado",
              [(r["mes"], r["honorarios_cobrados"], r["aportes_comitente"], r["pagos"], r["saldo_acumulado"]) for r in sm]
              == [("2026-08", 1000, 5000, 0, 6000), ("2026-09", 0, 0, 0, 6000), ("2026-10", 0, 0, 4000, 2000),
                  ("2026-11", 0, 0, 0, 2000)], sm)

        gen = reg("VISTA_GENERAL")
        hoy_ = gen[-1]
        check("VISTA_GENERAL: una fila por día desde el primer movimiento (1/10) hasta hoy; solo la de hoy con es_hoy",
              [r["fecha"] for r in gen][0] == "2026-10-01" and len(gen) == 15 and hoy_["fecha"] == "2026-10-15"
              and [r["es_hoy"] for r in gen].count("sí") == 1 and hoy_["es_hoy"] == "sí", [r["fecha"] for r in gen])
        check("… saldo por cuenta según el libro: Banco −250.000 (−300.000 + 100.000 − 50.000 de la línea semanal); "
              "cajas de obra en dólares US$ 17.000, aparte",
              (hoy_["saldo_banco"], hoy_["cajas_obra_usd"], hoy_["cajas_obra_ars"], hoy_["saldo_mercado_pago"])
              == (-250000, 17000, 0, 0), hoy_)
        dia5 = next(r for r in gen if r["fecha"] == "2026-10-05")
        check("… ingresos y pagos del mes hasta ese día (el 5/10: 500.000 contra 2.250.000; el 15: 700.000 contra 2.350.000)",
              (dia5["ingresos_mes"], dia5["pagos_mes"], hoy_["ingresos_mes"], hoy_["pagos_mes"])
              == (500000, 2250000, 700000, 2350000), (dia5, hoy_))
        check("… capital propio total (Gonzalo 200.000) y las obras en rojo y en gris, como VISTA_OBRAS",
              hoy_["capital_propio_inmovilizado"] == 200000 and hoy_["obras_en_rojo"] == 0
              and hoy_["obras_en_gris"] == sum(1 for r in reg("VISTA_OBRAS") if r["semaforo"] == "gris")
              and "Moquehue" in hoy_["obras_en_gris_lista"], hoy_)
        check("… sin saldo de apertura cargado, la diferencia contra el banco va vacía (no dice nada)",
              hoy_["diferencia_libro_banco_ars"] == "" and hoy_["ultimo_extracto"] == "", hoy_)
        import copy
        import dataclasses
        abierto = copy.copy(m)
        abierto.cuentas = [dataclasses.replace(c, saldo_apertura=1000000.0, fecha_apertura="2026-10-01") if c.nombre == "Banco"
                           else c for c in m.cuentas]
        movs_ = vistas._del_master(vistas.como_dicts(estudio.leer_movimientos()))
        linea = {"cuenta_banco": "CA $ 273-125852351-000", "fecha": "2026-10-10", "saldo": 760000, "orden": 0,
                 "importado_ts": "2026-10-11 09:00:00", "moneda": "ARS", "origen": "banco_patagonia"}
        g2 = vistas.vista_general(movs_, abierto, date(2026, 10, 15), vistas.vista_saldos(movs_, abierto),
                                  [linea, {**linea, "cuenta_banco": "CC $ 273-125852351-000", "saldo": 40000}])
        d2 = {f[0]: dict(zip(g2[0], f)) for f in g2[1:]}
        check("… con saldo de apertura: libro − banco del último extracto, sumando las cuentas del banco de Banco "
              "(el 10/10: 800.000 − 800.000 = 0; el 15/10: 750.000 − 800.000 = −50.000; antes del extracto, vacía)",
              (d2["2026-10-09"]["diferencia_libro_banco_ars"], d2["2026-10-10"]["diferencia_libro_banco_ars"],
               d2["2026-10-15"]["diferencia_libro_banco_ars"], d2["2026-10-15"]["ultimo_extracto"])
              == ("", 0, -50000, "2026-10-10"), [(k, v["saldo_banco"], v["diferencia_libro_banco_ars"]) for k, v in d2.items()])

        con_obra = [h for h in master if h.startswith("VISTA_") and "obra" in master[h][0]]
        valores_obra = {h: {f[master[h][0].index("obra")] for f in master[h][1:]} for h in con_obra}
        check("selector de obra: el campo se llama «obra» en VISTA_OBRAS, VISTA_OBRAS_MES, VISTA_RUBROS, "
              "VISTA_PROVEEDORES y VISTA_DETALLE, siempre texto y nunca vacío («Sin obra»)",
              set(con_obra) == {"VISTA_OBRAS", "VISTA_OBRAS_MES", "VISTA_RUBROS", "VISTA_PROVEEDORES", "VISTA_DETALLE"}
              and all(isinstance(v, str) and v for vs in valores_obra.values() for v in vs)
              and "Sin obra" in valores_obra["VISTA_RUBROS"]
              and valores_obra["VISTA_OBRAS_MES"] <= valores_obra["VISTA_OBRAS"], valores_obra)
        check("VISTA_RUBROS sin rubros vacíos: el depósito informal sin rubro va como «Sin rubro» en rubro_1 y rubro_2",
              all(r["rubro_1"] and r["rubro_2"] for r in rubros)
              and any(r["rubro_1"] == "Sin rubro" and r["rubro_2"] == "Sin rubro" and r["obra"] == "Lennon" for r in rubros),
              [(r["obra"], r["rubro_1"], r["rubro_2"]) for r in rubros])

        print("\n§5.21 · POST /vistas/recalcular")
        app.dependency_overrides[obtener_libro] = lambda: estudio
        app.dependency_overrides[obtener_libro_personal] = lambda: personal
        rs = TestClient(app).post("/vistas/recalcular", json={"simulacro": True}, headers={"X-API-Key": "test-local"})
        check("simulacro: dice qué hojas y cuántas filas escribiría, y no escribe nada",
              rs.status_code == 200 and rs.json().get("simulacro") is True and not estudio.hojas and not personal.hojas
              and rs.json()["escribiria"]["VISTA_GENERAL"] >= 15
              and set(rs.json()["escribiria"]) == set(master) | {f"personal:{h}" for h in hojas["personal"]},
              (rs.status_code, rs.text[:300]))
        app.dependency_overrides[obtener_libro] = lambda: estudio
        app.dependency_overrides[obtener_libro_personal] = lambda: personal
        movs_antes = [list(f) for f in estudio.filas]
        r = TestClient(app).post("/vistas/recalcular", headers={"X-API-Key": "test-local"})
        check("escribe las hojas derivadas en el Master y las personales (VISTA_PERSONAL, su detalle, sus CC_) en el personal",
              r.status_code == 200 and set(estudio.hojas) == set(master) and set(personal.hojas) == set(hojas["personal"])
              and {"VISTA_PERSONAL", "VISTA_DETALLE", "CC_BELELLI"} <= set(personal.hojas),
              (r.status_code, r.text[:300]))
        check("… y nunca toca MOVIMIENTOS", estudio.filas == movs_antes)
        r2 = TestClient(app).post("/vistas/recalcular", headers={"X-API-Key": "test-local"})
        check("es idempotente: dos corridas dejan lo mismo (salvo la hora en las CC)",
              r2.json()["escritas"] == r.json()["escritas"])
        app.dependency_overrides.clear()

    print("\n§5.21 · scripts/recalcular_vistas.py (el cron): código de salida y mensaje claro")
    import httpx

    from scripts import recalcular_vistas as cron

    class Salida(io.StringIO):
        def reconfigure(self, **_):
            pass

    def correr(respuesta, argv=(), entorno=True):
        enviados = []

        def post(url, json=None, headers=None, timeout=None):
            enviados.append(json)
            if isinstance(respuesta, Exception):
                raise respuesta
            return respuesta

        viejo = (cron.httpx.post, sys.argv, sys.stdout, os.environ.get("MOTOR_URL"))
        cron.httpx.post, sys.argv, sys.stdout = post, ["recalcular_vistas.py", *argv], Salida()
        if entorno:
            os.environ["MOTOR_URL"] = "https://motor.test"
        else:
            os.environ.pop("MOTOR_URL", None)
        try:
            codigo, texto = cron.main(), sys.stdout.getvalue()
        finally:
            cron.httpx.post, sys.argv, sys.stdout = viejo[:3]
            if viejo[3] is None:
                os.environ.pop("MOTOR_URL", None)
            else:
                os.environ["MOTOR_URL"] = viejo[3]
        return codigo, texto, enviados

    pedido = httpx.Request("POST", "https://motor.test/vistas/recalcular")
    ok = httpx.Response(200, json={"escritas": {"VISTA_GENERAL": 15, "CC_LENNON": 30}}, request=pedido)
    c, t, env = correr(ok)
    check("todo bien: 0 y la lista de hojas escritas", c == 0 and "VISTA_GENERAL: 15 filas" in t and env == [{"simulacro": False}], t)
    c, t, env = correr(httpx.Response(200, json={"simulacro": True, "escribiria": {"VISTA_OBRAS": 13}}, request=pedido),
                       ["--simulacro"])
    check("--simulacro: le pide al motor que no escriba y muestra lo que escribiría",
          c == 0 and env == [{"simulacro": True}] and "Simulacro: escribiría 1 hojas" in t, t)
    c, t, _ = correr(httpx.ReadTimeout("tardó", request=pedido))
    check("el motor tarda: código 3 y «ERROR: … no terminó en 600 s»", c == 3 and t.startswith("ERROR") and "600 s" in t, t)
    c, t, _ = correr(httpx.ConnectError("sin red", request=pedido))
    check("el motor no contesta: código 3 y ERROR", c == 3 and t.startswith("ERROR: no pude llegar"), t)
    c, t, _ = correr(httpx.Response(500, json={"detail": "Sheets caído"}, request=pedido))
    check("el motor contesta error: código 1 y el detalle", c == 1 and "500" in t and "Sheets caído" in t, t)
    c, t, _ = correr(httpx.Response(401, json={"detail": "X-API-Key inválida"}, request=pedido))
    check("clave equivocada: código 1 y la pista (sin mostrar la clave)", c == 1 and "no coincide" in t and "test-local" not in t, t)
    c, t, _ = correr(httpx.Response(502, text="<html>Bad gateway</html>", request=pedido))
    check("respuesta que no es JSON: código 1", c == 1 and "502" in t, t)
    c, t, _ = correr(ok, entorno=False)
    check("falta MOTOR_URL: código 2 y qué variable falta", c == 2 and "MOTOR_URL" in t and "MOTOR_API_KEY" not in t, t)

    print(f"\n{'TODO OK' if not fallas else str(len(fallas)) + ' FALLAS'}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
