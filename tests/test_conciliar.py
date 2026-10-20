"""Conciliación con el banco (§5.20, handoff del 15/10), contra libros en memoria.

Los cuatro extractos reales de agosto (tests/fixtures/CompartirDetalleMovimiento-*.xlsx) se
importan a un libro en memoria sembrado con movimientos que coinciden, ambiguos y faltantes.
Nunca se escribe en el Sheet real.

    python -m tests.test_conciliar
"""
import asyncio
import glob
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ["MAESTROS_SNAPSHOT"] = str(RAIZ / "maestros_snapshot.json")
    os.environ["LLM_HABILITADO"] = "false"
    os.environ["LEER_ADJUNTOS"] = "false"
    os.environ["MOTOR_API_KEY"] = "test-local"
    return asyncio.run(_correr())


async def _correr() -> int:
    import httpx

    from app import maestros
    from app.extracto import ExtractoNoReconocido, leer_extracto
    from app.main import app, obtener_archivador, obtener_descargador, obtener_libro, obtener_libro_personal
    from tests.dobles import ArchivadorFalso, LibroMemoria

    fallas: list[str] = []

    def check(descripcion, condicion, detalle=""):
        ok = bool(condicion)
        print(f"  {'PASA ' if ok else 'FALLA'}  {descripcion}{'' if ok else '  → ' + str(detalle)[:600]}")
        if not ok:
            fallas.append(descripcion)

    m = maestros.cargar(forzar=True)
    titular = next(u for u in m.usuarios if u.rol == "titular")
    snapshot = json.loads((RAIZ / "maestros_snapshot.json").read_text(encoding="utf-8"))
    encabezado = snapshot["MOVIMIENTOS"][0] + [c for c in ("vinculo", "anula") if c not in snapshot["MOVIMIENTOS"][0]]
    archivos = {Path(f).name: Path(f).read_bytes() for f in sorted(glob.glob(str(RAIZ / "fixtures" / "CompartirDetalle*.xlsx")))}

    # ── 1 · El parser ─────────────────────────────────────────────────────────
    print("\n1 · El extracto de Banco Patagonia → líneas")
    leidas = {n: leer_extracto(b) for n, b in archivos.items()}
    check("los 4 archivos de muestra: 16, 122, 11 y 13 líneas", [len(v) for v in leidas.values()] == [16, 122, 11, 13],
          [len(v) for v in leidas.values()])
    check("cada línea tiene su hash_id y ninguno se repite",
          len({x.hash_id for v in leidas.values() for x in v}) == sum(len(v) for v in leidas.values()))
    check("cuentas: CA $ 273…, CA $ 48…, CC $ 273… en pesos; CA U$S 273… en dólares",
          [(v[0].cuenta_banco, v[0].moneda) for v in leidas.values()] ==
          [("CA $ 273-125852351-000", "ARS"), ("CA $ 48-69556582-001", "ARS"), ("CC $ 273-125852351-000", "ARS"),
           ("CA U$S 273-125852351-000", "USD")], [(v[0].cuenta_banco, v[0].moneda) for v in leidas.values()])
    maragano = next(x for v in leidas.values() for x in v if "MARAGAÑO" in x.descripcion)
    check("«TRANSFERENCIA ENTRE CUENTAS VAR 20929415044 MARAGAÑO GUERRERO MARCELO» → CUIT, nombre y −$ 300.000",
          (maragano.cuit, maragano.nombre, maragano.importe, maragano.fecha)
          == ("20929415044", "MARAGAÑO GUERRERO MARCELO", -300000.0, "2026-08-18"), maragano)
    primera = leidas["CompartirDetalleMovimiento-20260820091012.xlsx"][0]
    check("importes con espacio duro y signo («-$ 2,14», «US$ 200,00»), fechas dd/mm/aaaa",
          (primera.fecha, primera.importe, primera.saldo) == ("2026-08-19", -346283.99, 882242.86), primera)
    try:
        leer_extracto(b"esto no es un excel")
        check("un archivo que no es un extracto → ExtractoNoReconocido", False)
    except ExtractoNoReconocido:
        check("un archivo que no es un extracto → ExtractoNoReconocido", True)

    # ── El libro de prueba ────────────────────────────────────────────────────
    def preparar():
        estudio, personal = LibroMemoria(encabezado), LibroMemoria(encabezado)
        base = dict(moneda="ARS", tc=1, cuenta="Banco", origen="WHATSAPP", cargado_por=titular.nombre,
                    concilia="VERDADERO", estado_conc="PENDIENTE")
        # fuerte: el comitente de Cerro Bayo (30-64086161-0) acredita 6 días después
        estudio.sembrar(id_mov="M-000001", fecha="2026-08-12", tipo="INGRESO", importe=1155407.37, importe_ars=1155407.37,
                        obra="Cerro Bayo", **base)
        # probable: mismo importe, un día antes, uno solo
        estudio.sembrar(id_mov="M-000002", fecha="2026-08-17", tipo="EGRESO", importe=300000, importe_ars=300000,
                        obra="Moreno", contratista="Marcelo Maragaño", **base)
        # ambiguo: dos pagos de $ 73.500 alrededor del 18/08 (DUPUY VICTOR JAVIER)
        for i, f in ((3, "2026-08-17"), (4, "2026-08-19")):
            estudio.sembrar(id_mov=f"M-{i:06d}", fecha=f, tipo="EGRESO", importe=73500, importe_ars=73500, obra="Lennon", **base)
        # la línea semanal de personales nunca se cruza (§5.20); tiene el mismo importe que COMPRAS PATAGONIA 24
        estudio.sembrar(id_mov="M-000005", fecha="2026-08-19", tipo="EGRESO", importe=346283.99, importe_ars=346283.99,
                        tipo_gasto="personal", **{**base, "origen": "CIERRE"})
        # un par anulado (§5.19) no se cruza aunque coincida (180.000 a Fachado Juan Manuel)
        estudio.sembrar(id_mov="M-000006", fecha="2026-08-18", tipo="EGRESO", importe=180000, importe_ars=180000,
                        obra="Lennon", **base)
        estudio.sembrar(id_mov="M-000007", fecha="2026-08-18", tipo="EGRESO", importe=-180000, importe_ars=-180000,
                        anula="M-000006", **base)
        # lo personal se cruza fila por fila contra el libro personal
        personal.sembrar(id_mov="P-000001", fecha="2026-08-18", tipo="EGRESO", importe=180000, importe_ars=180000,
                         tipo_gasto="personal", contratista="Juan Manuel", **base)
        # en el libro y no en el banco hace más de una semana
        estudio.sembrar(id_mov="M-000008", fecha="2026-08-01", tipo="EGRESO", importe=999999, importe_ars=999999,
                        obra="Lennon", **base)
        return estudio, personal

    def montar(estudio, personal):
        app.dependency_overrides[obtener_libro] = lambda: estudio
        app.dependency_overrides[obtener_libro_personal] = lambda: personal
        app.dependency_overrides[obtener_archivador] = lambda: ArchivadorFalso()
        app.dependency_overrides[obtener_descargador] = lambda: (lambda adj: archivos[adj.nombre])

    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://motor", headers={"X-API-Key": "test-local"},
                                 timeout=120) as cli:
        async def extracto(nombre):
            return await cli.post("/conciliar/extracto", json={"telefono": titular.telefono, "adjunto": {
                "url": f"https://drive.google.com/file/d/{nombre[-20:-5]}xxxxxxxxxx/view", "nombre": nombre,
                "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}})

        # ── 2 · Desde el 1/11 ─────────────────────────────────────────────────
        print("\n2 · Antes de CONCILIACION_DESDE (1/11): se importa como ANTERIOR, sin preguntas")
        os.environ.pop("CONCILIACION_DESDE", None)
        estudio, personal = preparar()
        montar(estudio, personal)
        r = (await extracto("CompartirDetalleMovimiento-20260820091012.xlsx")).json()
        check("las 122 líneas de agosto quedan ANTERIOR: ni conciliadas, ni lotes, ni fichas, ni ambiguas",
              r["importadas"] == 122 and r["anteriores"] == 122 and not r["pendientes"] and not r["lotes"]
              and not r["ambiguas"] and all(x["estado"] == "ANTERIOR" for x in estudio.banco_dicts()),
              {k: r[k] for k in ("importadas", "anteriores", "conciliadas")})
        check("… y no se marcó ningún movimiento", not estudio.conciliados and not personal.conciliados)

        # ── 3 · La conciliación ───────────────────────────────────────────────
        print("\n3 · Conciliar (CONCILIACION_DESDE = 2026-07-01, para probar con agosto)")
        os.environ["CONCILIACION_DESDE"] = "2026-07-01"
        estudio, personal = preparar()
        montar(estudio, personal)
        r = (await extracto("CompartirDetalleMovimiento-20260820091012.xlsx")).json()
        banco = {x["hash_id"]: x for x in estudio.banco_dicts()}
        por_desc = lambda texto: [x for x in banco.values() if texto in x["descripcion"]]  # noqa: E731
        cerro = por_desc("CERRO BAYO")
        check("fuerte: el ingreso de Cerro Bayo por el CUIT del comitente (6 días después) → CONCILIADO M-000001",
              cerro and all(x["estado"] == "CONCILIADO" for x in cerro) and {x["id_mov"] for x in cerro} >= {"M-000001"},
              [(x["estado"], x["id_mov"]) for x in cerro])
        mar = por_desc("MARAGAÑO")[0]
        check("probable: $ 300.000 a Maragaño, mismo importe y un día de diferencia, uno solo → CONCILIADO M-000002",
              (mar["estado"], mar["id_mov"]) == ("CONCILIADO", "M-000002"), (mar["estado"], mar["id_mov"]))
        dup = por_desc("DUPUY")[0]
        check("ambiguo: $ 73.500 con dos candidatos → A_REVISAR con M-000003 y M-000004",
              dup["estado"] == "A_REVISAR" and set(dup["candidatos"].split(", ")) == {"M-000003", "M-000004"}, dup)
        amb = next((a for a in r["ambiguas"] if a["hash_id"] == dup["hash_id"]), None)
        check("… y vuelve en «ambiguas» con su texto («puede ser M-000003 o M-000004»)",
              amb and amb["candidatos"] == ["M-000003", "M-000004"] and "M-000003 o M-000004" in amb["texto"], amb)
        juanma = [x for x in por_desc("FACHADO JUAN MAN") if numero_(x["debito"]) == 180000][0]
        check("lo personal se cruza contra el libro personal (P-000001), no contra el par anulado del estudio",
              (juanma["estado"], juanma["id_mov"]) == ("CONCILIADO", "P-000001") and personal.conciliados
              and not any(f in (7, 8) for f, _ in estudio.conciliados), (juanma["estado"], juanma["id_mov"], estudio.conciliados))
        compras = [x for x in por_desc("COMPRAS PATAGONIA 24") if numero_(x["debito"]) == 346283.99][0]
        check("la línea semanal de personales nunca se cruza: «COMPRAS PATAGONIA 24» queda SIN_CARGAR",
              compras["estado"] == "SIN_CARGAR", compras["estado"])
        filas_marcadas = {f for f, _ in estudio.conciliados}
        check("la conciliación escribe solo id_banco y estado_conc en las filas del libro",
              all(set(v) == {"id_banco", "estado_conc"} for _, v in estudio.conciliados + personal.conciliados)
              and filas_marcadas == {2, 3}, estudio.conciliados)
        movs = {mv["id_mov"]: mv for mv in estudio.movimientos()}
        check("… y M-000002 queda con su id_banco y CONCILIADO; el resto de la fila igual",
              movs["M-000002"]["estado_conc"] == "CONCILIADO" and movs["M-000002"]["id_banco"] == mar["hash_id"]
              and movs["M-000002"]["importe"] == 300000 and movs["M-000002"]["contratista"] == "Marcelo Maragaño",
              movs["M-000002"])
        lotes = {x["tipo"]: x for x in r["lotes"]}
        check("gastos bancarios e impuestos en un lote; MercadoLibre sin comprobante en otro",
              "gastos_bancarios" in lotes and "meli_personal" in lotes and lotes["meli_personal"]["cantidad"] >= 1
              and "gastos bancarios por $" in lotes["gastos_bancarios"]["texto"], {k: v["texto"] for k, v in lotes.items()})
        check("… cada lote trae «detalle»: una línea corta por movimiento, para «Ver detalle»",
              all(len(x["detalle"]) == x["cantidad"] and " · " in x["detalle"][0] for x in r["lotes"]),
              lotes["gastos_bancarios"]["detalle"][:2])
        pend = r["pendientes"]
        check("el resto: una ficha por línea, «Vi un pago de $ … que no tengo cargado.», con su interpretación",
              pend and all(p["texto"].startswith(("Vi un pago de $", "Vi un ingreso de $")) and p["interpretacion"]["fichas"]
                           for p in pend), pend[:1])
        f0 = pend[0]["interpretacion"]["fichas"][0]
        check("… armada como un comprobante: importe, fecha, cuenta Banco, extras.id_banco = el hash",
              f0["extras"].get("id_banco") == pend[0]["hash_id"] and f0["campos"]["cuenta"] == "Banco"
              and f0["campos"]["importe"] and f0["campos"]["fecha"], {k: f0["campos"][k] for k in ("importe", "fecha", "cuenta")})
        check("conteos y resumen: importadas, conciliadas, a revisar, sin cargar; saldo según libro y banco",
              (r["importadas"], r["repetidas"], r["anteriores"]) == (122, 0, 0) and r["conciliadas"] >= 3
              and r["a_revisar"] == 1 and r["resumen"]["saldo_banco"] == 882242.86
              and "Banco: libro" in r["texto"], {k: r[k] for k in ("importadas", "conciliadas", "a_revisar", "sin_cargar")})
        check("lo del libro que no aparece en el banco hace más de una semana se cuenta (M-000008)",
              r["sin_banco"] >= 1 and "M-000008" in r["sin_banco_detalle"], (r["sin_banco"], r["sin_banco_detalle"]))

        print("\n4 · Reimportar el mismo extracto no cambia nada")
        antes = ([list(f) for f in estudio.banco], list(estudio.conciliados), [list(f) for f in estudio.filas])
        r2 = (await extracto("CompartirDetalleMovimiento-20260820091012.xlsx")).json()
        check("0 importadas, 122 repetidas; BANCO_RAW y MOVIMIENTOS iguales",
              (r2["importadas"], r2["repetidas"]) == (0, 122) and estudio.banco == antes[0]
              and estudio.conciliados == antes[1] and estudio.filas == antes[2], (r2["importadas"], r2["repetidas"]))
        check("… y lo pendiente es lo mismo", len(r2["pendientes"]) == len(pend) and r2["lotes"] == r["lotes"])

        print("\n5 · Los cuatro extractos juntos: cuentas en pesos y en dólares")
        for nombre in archivos:
            await extracto(nombre)
        r3 = (await cli.get("/conciliar/pendientes", params={"telefono": titular.telefono})).json()
        por_cuenta = {c["cuenta"]: c for c in r3["resumen"]["por_cuenta"]}
        check("Banco suma las tres cuentas en pesos del banco; Banco USD, la de dólares (US$ 11,01)",
              len(por_cuenta["Banco"]["cuentas_banco"]) == 3 and por_cuenta["Banco USD"]["saldo_banco"] == 11.01
              and por_cuenta["Banco USD"]["moneda"] == "USD", {k: (v["saldo_banco"], len(v["cuentas_banco"])) for k, v in por_cuenta.items()})
        usd = [x for x in r3["lotes"] if x["moneda"] == "USD"]
        check("S2 (20/10): los gastos bancarios en dólares van en un lote aparte, con requiere_tc",
              usd and all(x["tipo"] == "gastos_bancarios" and x["requiere_tc"] for x in usd)
              and all(not x["requiere_tc"] and x["tc_sugerido"] is None for x in r3["lotes"] if x["moneda"] == "ARS"),
              [(x["tipo"], x["moneda"], x["requiere_tc"], x["tc_sugerido"]) for x in r3["lotes"]])
        from app.conciliar import resumen_banco
        rb = resumen_banco(estudio, personal)
        check("el resumen del lunes (/cierre-semanal → resumen_banco): saldos por cuenta y cuánto queda pendiente",
              rb and {c["cuenta"] for c in rb["por_cuenta"]} == {"Banco", "Banco USD"} and rb["pendientes"] > 0
              and "sin_banco" in rb, rb and {k: rb[k] for k in ("saldo_libro", "saldo_banco", "pendientes")})

        print("\n6 · Lotes, asignar, ignorar y /confirmar de una línea")
        hs = lotes["gastos_bancarios"]["hash_ids"]
        r4 = (await cli.post("/conciliar/lote", json={"telefono": titular.telefono, "tipo": "gastos_bancarios",
                                                       "hash_ids": hs})).json()
        nuevos = [mv for mv in estudio.movimientos() if mv["id_mov"] in r4.get("escritos", [])]
        check("«Cargar todo» los gastos bancarios: un movimiento por línea, estructura (Austral), Impuestos y tasas › "
              "Bancarios, conciliado con su línea",
              len(nuevos) == len(hs) and all(mv["obra"] == "Austral" and mv["rubro_2"] == "Bancarios"
                                             and mv["estado_conc"] == "CONCILIADO" and mv["id_banco"] in hs for mv in nuevos)
              and all(x["estado"] == "CONCILIADO" for x in estudio.banco_dicts() if x["hash_id"] in hs),
              (r4, nuevos[:1]))
        r5 = (await cli.post("/conciliar/lote", json={"telefono": titular.telefono, "tipo": "gastos_bancarios",
                                                       "hash_ids": hs})).json()
        check("… repetirlo no duplica (msg_id «banco:<hash_id>»)",
              not r5["escritos"] and len([mv for mv in estudio.movimientos() if mv["id_banco"] in hs]) == len(hs), r5)
        hm = lotes["meli_personal"]["hash_ids"]
        r6 = (await cli.post("/conciliar/lote", json={"telefono": titular.telefono, "tipo": "meli_personal",
                                                       "hash_ids": hm})).json()
        pm = [mv for mv in personal.movimientos() if mv["id_mov"] in r6.get("escritos", [])]
        check("MeLi sin comprobante → libro personal, Personal › Consumos (gasto personal sin clasificar)",
              len(pm) == len(hm) and all(mv["tipo_gasto"] == "personal" and mv["rubro_2"] == "Consumos" for mv in pm), r6)
        r7 = (await cli.post("/conciliar/lote", json={"telefono": titular.telefono, "tipo": "asignar",
                                                       "hash_ids": [dup["hash_id"]], "id_mov": "M-000004"})).json()
        dup2 = next(x for x in estudio.banco_dicts() if x["hash_id"] == dup["hash_id"])
        movs = {mv["id_mov"]: mv for mv in estudio.movimientos()}
        check("«asignar» la ambigua a M-000004: la línea CONCILIADO y M-000004 con su id_banco",
              (dup2["estado"], dup2["id_mov"]) == ("CONCILIADO", "M-000004") and movs["M-000004"]["id_banco"] == dup["hash_id"]
              and movs["M-000003"]["estado_conc"] != "CONCILIADO", (r7, dup2["estado"]))
        p0 = r["pendientes"][0]
        ficha = p0["interpretacion"]["fichas"][0]
        ficha["campos"].update({k: v for k, v in {"obra": ficha["campos"]["obra"] or "Lennon",
                                                  "contratista": ficha["campos"]["contratista"] or "Miguel Soto",
                                                  "rubro_1": ficha["campos"]["rubro_1"] or "Mano de obra",
                                                  "rubro_2": ficha["campos"]["rubro_2"] or "Contratistas",
                                                  "etapa": ficha["campos"]["etapa"] or "1",
                                                  "tipo_gasto": ficha["campos"]["tipo_gasto"] or "obra"}.items()})
        rc = await cli.post("/confirmar", json={"msg_id": f"banco:{p0['hash_id']}", "telefono": titular.telefono,
                                                "ficha": {"campos": ficha["campos"], "extras": ficha["extras"]}})
        linea = next(x for x in estudio.banco_dicts() if x["hash_id"] == p0["hash_id"])
        check("/confirmar de una línea sin cargar (msg_id «banco:<hash_id>») escribe y marca la línea CONCILIADO",
              rc.status_code == 200 and (linea["estado"], linea["id_mov"]) == ("CONCILIADO", rc.json()["id_mov"]),
              (rc.status_code, rc.text[:300], linea["estado"]))
        r8 = (await cli.get("/conciliar/pendientes", params={"telefono": titular.telefono})).json()
        check("… y deja de estar en pendientes", all(x["hash_id"] != p0["hash_id"] for x in r8["pendientes"]))
        r9 = (await cli.post("/conciliar/lote", json={"telefono": titular.telefono, "tipo": "ignorar",
                                                       "hash_ids": [r8["pendientes"][0]["hash_id"]]})).json()
        check("«ignorar» saca la línea de lo pendiente",
              all(x["hash_id"] != r8["pendientes"][0]["hash_id"]
                  for x in (await cli.get("/conciliar/pendientes", params={"telefono": titular.telefono})).json()["pendientes"]),
              r9)

        # ── 8 · 20/10: Mercado Pago, traspasos entre cuentas propias, lote en US$, estado ──
        print("\n8 · 20/10: el PDF de Mercado Pago, los pases entre cuentas propias y el lote en dólares")
        os.environ["CONCILIACION_DESDE"] = "2026-10-01"
        armados = {Path(f).name: Path(f).read_bytes() for f in glob.glob(str(RAIZ / "fixtures" / "armado-octubre-*"))}
        estudio, personal = preparar()
        # lo que el libro ya tiene: el pago a Grimau desde Mercado Pago (con el ID de la operación del
        # comprobante) y un pago del 31/10 con tc 1460 (el tc sugerido del lote en dólares)
        estudio.sembrar(id_mov="M-000009", fecha="2026-10-30", tipo="EGRESO", importe=165700, moneda="ARS", tc=1,
                        importe_ars=165700, obra="Lennon", contratista="Miguel Soto", cuenta="Mercado Pago",
                        ref_comprobante="op:81234567893", origen="WHATSAPP", cargado_por=titular.nombre,
                        concilia="VERDADERO", estado_conc="PENDIENTE")
        estudio.sembrar(id_mov="M-000010", fecha="2026-10-31", tipo="EGRESO", importe=1460000, moneda="ARS", tc=1460,
                        importe_ars=1460000, obra="Lennon", contratista="Miguel Soto", cuenta="Caja obra Lennon",
                        origen="WHATSAPP", cargado_por=titular.nombre, ts="2026-10-31 10:00:00")
        montar(estudio, personal)
        app.dependency_overrides[obtener_descargador] = lambda: (lambda adj: armados[adj.nombre])
        rm = (await extracto("armado-octubre-mercado-pago.pdf")).json()
        check("el PDF de Mercado Pago entra por /conciliar/extracto: origen mercado_pago, cuenta_banco «Mercado Pago»",
              (rm.get("origen"), rm.get("cuenta_banco"), rm.get("importadas")) == ("mercado_pago", "Mercado Pago", 5), rm)
        grimau = next(x for x in estudio.banco_dicts() if "Grimau" in x["descripcion"])
        check("… el ID de la operación es el match fuerte contra el comprobante de Mercado Pago (M-000009)",
              (grimau["estado"], grimau["id_mov"], grimau["ref"]) == ("CONCILIADO", "M-000009", "81234567893"), grimau)
        lotes_mp = {(x["tipo"], x["moneda"]): x for x in rm["lotes"]}
        check("S3: rendimientos y retenciones de Mercado Pago con los gastos bancarios; la compra de Mercado Libre a "
              "meli_personal", lotes_mp.get(("gastos_bancarios", "ARS"), {}).get("cantidad") == 2
              and lotes_mp.get(("meli_personal", "ARS"), {}).get("cantidad") == 1, list(lotes_mp))
        check("… el pase del banco a Mercado Pago todavía no tiene par (falta el extracto del banco): queda como línea",
              any(p["tipo"] == "linea" and "Fachado" in p["texto"] for p in rm["pendientes"]),
              [(p["tipo"], p["texto"]) for p in rm["pendientes"]])
        rx = {}
        for nombre in ("armado-octubre-CC.xlsx", "armado-octubre-CA.xlsx", "armado-octubre-USD.xlsx"):
            rx[nombre] = (await extracto(nombre)).json()
        ca = (await cli.get("/conciliar/pendientes", params={"telefono": titular.telefono})).json()
        internas = [x for x in estudio.banco_dicts() if x["estado"] == "INTERNA"]
        check("S4: el pase CA → CC del mismo día queda INTERNA las dos líneas, sin movimiento ni pregunta",
              len(internas) == 2 and {x["cuenta_banco"] for x in internas} == {"CA $ 273-125852351-000", "CC $ 273-125852351-000"}
              and not any("PROPIAS" in p["texto"] for p in ca["pendientes"]), [(x["cuenta_banco"], x["estado"]) for x in internas])
        check("… la respuesta del extracto que completó el par lo cuenta en «internas»; reimportar no lo vuelve a contar",
              rx["armado-octubre-CA.xlsx"]["internas"] == 1
              and rx["armado-octubre-CA.xlsx"]["cuenta_banco"] == "CA $ 273-125852351-000"
              and (await extracto("armado-octubre-CA.xlsx")).json()["internas"] == 0,
              {k: v.get("internas") for k, v in rx.items()})
        traspasos = [p for p in ca["pendientes"] if p["tipo"] == "traspaso"]
        mp_par = next((p for p in traspasos if "Mercado Pago" in p["texto"]), None)
        check("Banco → Mercado Pago: una sola ficha de traspaso con las dos líneas (no dos movimientos sueltos)",
              mp_par and len(mp_par["hash_ids"]) == 2 and mp_par["texto"].startswith("Vi que pasaste $ 300.000 de Banco a Mercado Pago")
              and not any(p["tipo"] == "linea" and "300.000" in p["texto"] for p in ca["pendientes"]),
              [(p["tipo"], p["texto"]) for p in ca["pendientes"]])
        fm = mp_par["interpretacion"]["fichas"][0] if mp_par else {"campos": {}}
        check("… la ficha: TRASPASO de Banco a Mercado Pago, $ 300.000, extras.ids_banco = [la que sale, la que entra]",
              (fm["campos"].get("tipo"), fm["campos"].get("cuenta_origen"), fm["campos"].get("cuenta_destino"),
               fm["campos"].get("importe")) == ("TRASPASO", "Banco", "Mercado Pago", 300000.0)
              and fm.get("extras", {}).get("ids_banco") == mp_par["hash_ids"], fm["campos"])
        cambio = next((p for p in traspasos if "US$" in p["texto"]), None)
        fc = cambio["interpretacion"]["fichas"][0]["campos"] if cambio else {}
        check("pesos → dólares: ficha de traspaso con el tc del par (145.000 / 100 = 1.450), sin preguntar",
              cambio and (fc.get("cuenta_origen"), fc.get("cuenta_destino"), fc.get("tc"), fc.get("importe")) ==
              ("Banco", "Banco USD", 1450.0, 145000.0) and "TC 1.450" in cambio["texto"]
              and not cambio["interpretacion"]["preguntas"], (cambio and cambio["texto"], fc))
        usd = next((x for x in ca["lotes"] if x["moneda"] == "USD"), None)
        check("el lote en US$: requiere_tc, y el tc sugerido es el que el libro usó ese día (1460, string)",
              usd and usd["requiere_tc"] and usd["tc_sugerido"] == "1460" and "US$" in usd["texto"], usd)

        print("\n9 · 20/10: confirmar los traspasos y el lote en dólares")
        rt = await cli.post("/confirmar", json={"msg_id": f"banco:{mp_par['hash_ids'][0]}", "telefono": titular.telefono,
                                                "ficha": {"campos": fm["campos"], "extras": fm["extras"]}})
        filas_t = [mv for mv in estudio.movimientos() if mv["id_mov"] in (rt.json().get("id_mov"), rt.json().get("id_mov_vinculado"))]
        marcadas = [x for x in estudio.banco_dicts() if x["hash_id"] in mp_par["hash_ids"]]
        check("/confirmar del traspaso (msg_id «banco:<a>», extras.ids_banco): dos filas, cada una con su id_banco, y las "
              "dos líneas CONCILIADO",
              rt.status_code == 200 and len(filas_t) == 2 and {mv["id_banco"] for mv in filas_t} == set(mp_par["hash_ids"])
              and all(mv["estado_conc"] == "CONCILIADO" for mv in filas_t) and all(x["estado"] == "CONCILIADO" for x in marcadas),
              (rt.status_code, rt.text[:300], [(mv["cuenta"], mv["id_banco"][:8]) for mv in filas_t]))
        rcam = await cli.post("/confirmar", json={"msg_id": f"banco:{cambio['hash_ids'][0]}", "telefono": titular.telefono,
                                                  "ficha": {"campos": fc, "extras": cambio["interpretacion"]["fichas"][0]["extras"]}})
        dol = next((mv for mv in estudio.movimientos() if mv["id_mov"] == rcam.json().get("id_mov_vinculado")), {})
        check("… el de pesos a dólares: la fila en Banco USD por US$ 100 con tc 1450",
              rcam.status_code == 200 and (dol.get("cuenta"), dol.get("moneda"), dol.get("importe"), dol.get("tc"))
              == ("Banco USD", "USD", 100.0, 1450.0), (rcam.status_code, rcam.text[:200], dol))
        r_sin = await cli.post("/conciliar/lote", json={"telefono": titular.telefono, "tipo": "gastos_bancarios",
                                                         "hash_ids": usd["hash_ids"]})
        check("el lote en US$ sin tipo_cambio → 422 {campo: tipo_cambio}",
              r_sin.status_code == 422 and r_sin.json()["detail"]["campo"] == "tipo_cambio", (r_sin.status_code, r_sin.text[:200]))
        r_con = (await cli.post("/conciliar/lote", json={"telefono": titular.telefono, "tipo": "gastos_bancarios",
                                                          "hash_ids": usd["hash_ids"], "tipo_cambio": "1.450"})).json()
        filas_usd = [mv for mv in estudio.movimientos() if mv["id_mov"] in r_con.get("escritos", [])]
        check("… con «1.450» (string): una fila por línea en Banco USD, con ese tc, conciliada",
              len(filas_usd) == 2 and all((mv["cuenta"], mv["moneda"], mv["tc"], mv["estado_conc"]) ==
                                          ("Banco USD", "USD", 1450.0, "CONCILIADO") for mv in filas_usd), (r_con, filas_usd[:1]))
        antes = ([list(f) for f in estudio.banco], [list(f) for f in estudio.filas])
        for nombre in armados:
            await extracto(nombre)
        check("reimportar los cuatro archivos armados no cambia nada", estudio.banco == antes[0] and estudio.filas == antes[1])

        print("\n10 · 20/10: GET /conciliar/estado")
        from datetime import date as _date
        from app import conciliar as _c
        est = _c.estado(titular.telefono, estudio, hoy=_date(2026, 10, 30))
        check("semana desde el lunes 26/10; fuentes de CUENTAS (las cuatro del banco y Mercado Pago)",
              est["semana_desde"] == "2026-10-26" and len(est["fuentes"]) == 5
              and {f["rotulo"] for f in est["fuentes"]} == {"CA $ 273", "CC $", "CA $ 48", "CA U$S", "Mercado Pago"},
              [(f["rotulo"], f["al_dia"]) for f in est["fuentes"]])
        check("… falta solo la CA $ 48 (no llegó nada de la semana): «Me faltan: CA $ 48»",
              est["faltan"] == ["CA $ 48"] and est["texto"] == "Me faltan: CA $ 48", (est["faltan"], est["texto"]))
        re_ = await cli.get("/conciliar/estado", params={"telefono": titular.telefono})
        check("el endpoint responde con la misma forma", re_.status_code == 200 and {"semana_desde", "fuentes", "faltan", "texto"}
              <= set(re_.json()), re_.text[:200])
        orden_inverso = LibroMemoria(encabezado)
        app.dependency_overrides[obtener_libro] = lambda: orden_inverso
        for nombre in ("armado-octubre-CA.xlsx", "armado-octubre-mercado-pago.pdf"):
            await extracto(nombre)
        ri = (await cli.get("/conciliar/pendientes", params={"telefono": titular.telefono})).json()
        check("Banco → Mercado Pago en orden inverso (primero el banco, después Mercado Pago): la misma ficha de traspaso",
              any(p["tipo"] == "traspaso" and "Mercado Pago" in p["texto"] for p in ri["pendientes"]),
              [(p["tipo"], p["texto"]) for p in ri["pendientes"]])
        muestra_real = Path("C:/Users/valen/OneDrive/Documentos/A&C/Fachado/Archivos Muestra/Muestra 3")
        pdfs_reales = sorted(muestra_real.glob("*.pdf")) if muestra_real.exists() else []
        if not pdfs_reales:
            print("  SKIP   la muestra real de Mercado Pago (Archivos Muestra/Muestra 3/) todavía no está")
        else:
            try:
                reales = leer_extracto(pdfs_reales[0].read_bytes())
                check(f"la muestra real de Mercado Pago ({pdfs_reales[0].name}) se lee", reales and reales[0].origen == "mercado_pago",
                      len(reales))
            except ExtractoNoReconocido as e:
                check(f"la muestra real de Mercado Pago ({pdfs_reales[0].name}) se lee", False, e)

        print("\n7 · Errores")
        app.dependency_overrides[obtener_descargador] = lambda: (lambda adj: b"no es un excel")
        rx = await extracto("CompartirDetalleMovimiento-roto.xlsx")
        check("un archivo que no es un extracto → 422 {campo: adjunto}",
              rx.status_code == 422 and rx.json()["detail"]["campo"] == "adjunto", (rx.status_code, rx.text[:200]))
        ry = await cli.post("/conciliar/extracto", json={"telefono": "000", "adjunto": {"url": "x", "nombre": "y"}})
        check("un teléfono que no está en USUARIOS → 403", ry.status_code == 403, ry.status_code)

    os.environ.pop("CONCILIACION_DESDE", None)
    app.dependency_overrides.clear()
    print(f"\n{'TODO OK' if not fallas else str(len(fallas)) + ' FALLAS'}")
    return 1 if fallas else 0


def numero_(v) -> float:
    from app.maestros import numero
    return numero(v)


if __name__ == "__main__":
    sys.exit(main())
