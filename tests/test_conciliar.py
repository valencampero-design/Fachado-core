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
        check("una línea en dólares sin cargar no va a un lote (necesita el tc): va como ficha",
              not any(x["moneda"] == "USD" and x["lote"] for x in estudio.banco_dicts()))
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
