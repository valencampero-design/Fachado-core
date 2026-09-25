"""POST /confirmar contra un libro en memoria (tests/dobles.py). NUNCA escribe en el Sheet
real: MOVIMIENTOS es append-only y una fila de prueba no se puede borrar.

    python -m tests.test_confirmar
"""
import asyncio
import contextlib
import json
import os
import sys
from pathlib import Path

from tests.dobles import ArchivadorFalso, LibroMemoria

RAIZ = Path(__file__).resolve().parent

# Filas reales del libro, para que los saldos se prueben contra datos verdaderos.
LENNON = [4032391.7, 3675000, 300000, 103050, 7000000, 7000000]   # pagado por el comitente
MORENO = [2600000, 566596, 2079000]                               # certificaciones: plata de la obra (§5.8)


def libro_con_filas_reales(encabezado: list[str], alias: list[list], demora: float = 0.0) -> LibroMemoria:
    libro = LibroMemoria(encabezado, alias, demora)
    filas = [("2026-09-02", "EGRESO", i, "Lennon", "Pagado por el comitente") for i in LENNON] + \
            [("2026-02-08", "INGRESO", i, "Moreno", "Caja obra Moreno") for i in MORENO]
    for n, (fecha, tipo, importe, obra, cuenta) in enumerate(filas, start=1):
        libro.sembrar(id_mov=f"M-{n:06d}", fecha=fecha, tipo=tipo, importe=importe, moneda="ARS", tc=1,
                      importe_ars=importe, obra=obra, cuenta=cuenta, origen="WHATSAPP")
    return libro


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ["MAESTROS_SNAPSHOT"] = str(RAIZ / "maestros_snapshot.json")
    os.environ["LLM_HABILITADO"] = "false"
    os.environ["MOTOR_API_KEY"] = "test-local"
    import logging
    logging.getLogger("app.confirmar").setLevel(logging.CRITICAL)  # el caso «Drive caído» loguea a propósito
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return asyncio.run(_correr())


async def _correr() -> int:
    import httpx

    from app import confirmar as modulo_confirmar
    from app import maestros
    from app.main import app, obtener_archivador, obtener_libro, obtener_libro_personal
    from app.saldos import saldo_estudio

    snapshot = json.loads((RAIZ / "maestros_snapshot.json").read_text(encoding="utf-8"))
    # Como queda el Sheet después de scripts/preparar_sheet.py (tanda 6: vinculo y anula).
    encabezado = snapshot["MOVIMIENTOS"][0] + [c for c in ("vinculo", "anula") if c not in snapshot["MOVIMIENTOS"][0]]
    m = maestros.cargar(forzar=True)
    titular = next(u for u in m.usuarios if u.rol == "titular")  # de USUARIOS, no hardcodeado

    fallas: list[str] = []

    def check(descripcion, condicion, detalle=""):
        ok = bool(condicion)
        print(f"  {'PASA ' if ok else 'FALLA'}  {descripcion}{'' if ok else '  → ' + str(detalle)}")
        if not ok:
            fallas.append(descripcion)

    personal_actual = {"libro": None}

    def preparar(demora=0.0, fallar_drive=False, con_personal=True):
        libro = libro_con_filas_reales(encabezado, snapshot["ALIAS"], demora)
        personal = LibroMemoria(encabezado, demora=demora) if con_personal else None
        archivador = ArchivadorFalso(fallar_drive)
        personal_actual["libro"] = personal
        app.dependency_overrides[obtener_libro] = lambda: libro
        app.dependency_overrides[obtener_libro_personal] = lambda: personal
        app.dependency_overrides[obtener_archivador] = lambda: archivador
        return libro, archivador

    def ficha(**campos):
        base = {"fecha": "2026-09-20", "tipo": "EGRESO", "importe": 300000, "moneda": "ARS", "tc": 1,
                "obra": "Lennon", "contratista": "Felipe Andrés Scherer", "rubro_1": "Servicios de obra",
                "rubro_2": "Movimiento de suelos", "cuenta": "Pagado por el comitente", "tipo_gasto": "obra",
                "comprobante_url": "https://drive.google.com/file/d/1sOnWv79ya4qgOAweTfEDReSgFbNaETrd/view",
                "descripcion": "Transf. OFB", "origen": "WHATSAPP", "id_mov": None, "cargado_por": "bot"}
        base.update(campos)
        return {"campos": base, "extras": {}}

    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://motor",
                                 headers={"X-API-Key": "test-local"}, timeout=60) as cli:

        async def confirmar(msg_id, f, telefono=titular.telefono, **extra):
            return await cli.post("/confirmar", json={"msg_id": msg_id, "telefono": telefono, "ficha": f, **extra})

        # ── 1 · Idempotencia ──────────────────────────────────────────────────
        print("\n1 · Dos llamadas con el mismo msg_id producen una sola fila")
        libro, _ = preparar()
        antes = len(libro.filas)
        r1 = (await confirmar("wamid.AAA", ficha())).json()
        r2 = (await confirmar("wamid.AAA", ficha(importe=999))).json()
        check("una sola fila nueva", len(libro.filas) == antes + 1, f"{len(libro.filas) - antes} filas")
        check("la segunda devuelve la primera", r2["id_mov"] == r1["id_mov"] and r2["fila"] == r1["fila"]
              and r2["ya_existia"] and not r1["ya_existia"], (r1, r2))
        check("el id sigue la numeración del libro (M-000010)", r1["id_mov"] == "M-000010", r1["id_mov"])
        r3 = (await confirmar("wamid.AAA", ficha(importe=500000), ficha_indice=1)).json()
        check("mismo mensaje, segunda ficha (dos movimientos): es otra fila",
              r3["id_mov"] == "M-000011" and not r3["ya_existia"], r3)

        # ── 2 · Concurrencia ──────────────────────────────────────────────────
        print("\n2 · Diez confirmaciones concurrentes: diez id_mov distintos y consecutivos")
        libro, _ = preparar(demora=0.02)
        rs = await asyncio.gather(*[confirmar(f"wamid.C{i}", ficha(importe=1000 + i)) for i in range(10)])
        ids = sorted(r.json()["id_mov"] for r in rs)
        esperados = [f"M-{n:06d}" for n in range(10, 20)]
        check("diez ids distintos y consecutivos", ids == esperados, ids)
        en_libro = sorted(mov["id_mov"] for mov in libro.movimientos())[-10:]
        check("las diez filas están en el libro, ninguna pisada", en_libro == esperados, en_libro)

        libro, _ = preparar(demora=0.02)
        lock_real = modulo_confirmar._lock
        modulo_confirmar._lock = contextlib.nullcontext()  # sin el lock, a ver qué pasa
        try:
            rs = await asyncio.gather(*[confirmar(f"wamid.S{i}", ficha(importe=1000 + i)) for i in range(10)])
        finally:
            modulo_confirmar._lock = lock_real
        nuevas = len(libro.filas) - 1 - len(LENNON) - len(MORENO)
        ids_sin_lock = [r.json()["id_mov"] for r in rs]
        check(f"control: sin el lock se rompe ({nuevas} fila(s) para 10 confirmaciones, "
              f"{len(set(ids_sin_lock))} id distinto(s))", nuevas < 10 and len(set(ids_sin_lock)) < 10)

        # ── 3 · Personal sin obra ─────────────────────────────────────────────
        print("\n3 · Un movimiento personal sin obra: va al libro personal (§5.14)")
        libro, archivador = preparar()
        filas_estudio = len(libro.filas)
        personal_ficha = ficha(obra=None, contratista="Marcelo Maragaño", rubro_1="Personal",
                               rubro_2="Casa", cuenta="Banco", tipo_gasto="personal")
        r = await confirmar("wamid.P1", personal_ficha)
        cuerpo = r.json()
        personal = personal_actual["libro"]
        fila = personal.movimientos()[-1] if personal.movimientos() else {}
        check("se escribe en el libro personal, no en el del estudio",
              r.status_code == 200 and cuerpo.get("libro") == "personal" and len(libro.filas) == filas_estudio, cuerpo)
        check("con su propia secuencia: P-000001", cuerpo.get("id_mov") == "P-000001", cuerpo.get("id_mov"))
        check("con tipo_gasto = personal y sin obra", fila.get("tipo_gasto") == "personal" and fila.get("obra") == "", fila)
        check("el comprobante va a personal/2026-09/", archivador.movidos and archivador.movidos[-1][1] == ["personal", "2026-09"],
              archivador.movidos)
        check("el archivo empieza con el id_mov", archivador.movidos and archivador.movidos[-1][2].startswith(cuerpo["id_mov"] + " "),
              archivador.movidos)
        check("sin obra no hay saldo de obra", cuerpo["obra"] is None, cuerpo["obra"])
        check("Banco concilia: VERDADERO y PENDIENTE", fila.get("concilia") == "VERDADERO" and fila.get("estado_conc") == "PENDIENTE", fila)
        r2 = (await confirmar("wamid.P1", personal_ficha)).json()
        check("la idempotencia mira los dos libros: el reintento devuelve la fila personal",
              r2.get("ya_existia") and r2.get("id_mov") == "P-000001" and len(personal.filas) == 2, r2)

        print("\n3b · Acceso a lo personal y libro no configurado")
        from app.maestros import Usuario
        sin_personal = Usuario("5490000000001", "Reemplazo de prueba", "colaborador", True, ve_personal=False)
        m.usuarios.append(sin_personal)
        try:
            libro, _ = preparar()
            r = await confirmar("wamid.P2", personal_ficha, telefono=sin_personal.telefono)
            check("sin ve_personal: 403 y nada escrito en ningún libro",
                  r.status_code == 403 and len(personal_actual["libro"].filas) == 1, (r.status_code, r.json()))
            r = await confirmar("wamid.P3", ficha(), telefono=sin_personal.telefono)
            check("… pero lo del estudio lo confirma igual", r.status_code == 200 and r.json()["libro"] == "estudio", r.json())
        finally:
            m.usuarios.remove(sin_personal)
        libro, _ = preparar(con_personal=False)
        antes = len(libro.filas)
        r = await confirmar("wamid.P4", personal_ficha)
        check("sin FACHADO_PERSONAL_SHEET_ID: 503, y lo personal NO cae en el libro del estudio",
              r.status_code == 503 and len(libro.filas) == antes, (r.status_code, r.json()))
        r = await confirmar("wamid.P5", ficha())
        check("… y lo del estudio sigue funcionando", r.status_code == 200, r.json())

        print("\n3c · Cierre semanal (§5.14)")
        libro, _ = preparar()
        personal = personal_actual["libro"]
        for n, (fecha, importe, cuenta) in enumerate([("2026-09-22", 1000, "Banco"), ("2026-09-24", 2000, "Banco"),
                                                      ("2026-09-23", 500, "Efectivo"), ("2026-09-29", 9999, "Banco")], start=1):
            personal.sembrar(id_mov=f"P-{n:06d}", fecha=fecha, tipo="EGRESO", importe=importe, moneda="ARS", tc=1,
                             importe_ars=importe, cuenta=cuenta, tipo_gasto="personal", cargado_por=titular.nombre)
        antes_saldo = saldo_estudio(libro.movimientos(), m)["total"]
        r = (await cli.post("/cierre-semanal", json={"semana": "2026-W39"})).json()
        cierre = [mv for mv in libro.movimientos() if mv.get("origen") == "CIERRE"]
        check("una fila por cuenta: Banco 3.000 y Efectivo 500 (la semana siguiente no entra)",
              sorted((mv["cuenta"], mv["importe"]) for mv in cierre) == [("Banco", 3000), ("Efectivo", 500)], cierre)
        check("EGRESO, personal, no concilia, con la descripción de la semana",
              all(mv["tipo"] == "EGRESO" and mv["tipo_gasto"] == "personal" and mv["concilia"] == "FALSO"
                  and mv["descripcion"] == "Gastos personales · semana 2026-W39" for mv in cierre), cierre)
        check("el saldo del estudio baja por las líneas semanales, no por las filas personales",
              round(antes_saldo - saldo_estudio(libro.movimientos(), m)["total"], 2) == 3500)
        r = (await cli.post("/cierre-semanal", json={"semana": "2026-W39"})).json()
        check("idempotente: la segunda corrida no escribe nada", r["escritas"] == [], r)
        personal.sembrar(id_mov="P-000005", fecha="2026-09-25", tipo="EGRESO", importe=700, moneda="ARS", tc=1,
                         importe_ars=700, cuenta="Banco", tipo_gasto="personal", cargado_por="Petrus")
        r = (await cli.post("/cierre-semanal", json={"semana": "2026-W40"})).json()
        check("carga atrasada: la próxima corrida escribe un ajuste por la diferencia, sin editar la anterior",
              [(e["semana"], e["cuenta"], e["importe"], e["ajuste"]) for e in r["escritas"]]
              == [("2026-W39", "Banco", 700, True), ("2026-W40", "Banco", 9999, False)], r["escritas"])
        from app.filtros import para_conciliacion
        check("las líneas de cierre quedan fuera de la conciliación",
              not any(mv.get("origen") == "CIERRE" for mv in para_conciliacion(libro.movimientos())))

        # ── 4 · Pagado por el comitente ───────────────────────────────────────
        print("\n4 · «Pagado por el comitente» no mueve el saldo del estudio")
        libro, _ = preparar()
        antes = saldo_estudio(libro.movimientos(), m)["total"]
        cuerpo = (await confirmar("wamid.L1", ficha())).json()
        despues = saldo_estudio(libro.movimientos(), m)["total"]
        check("saldo del estudio igual antes y después", antes == despues, (antes, despues))
        o = cuerpo["obra"]
        check("Lennon: saldo 0, no −$22 millones", o["saldo"] == 0 and o["pagado_con_plata_del_estudio"] == 0, o)
        check("lo del comitente se informa aparte", abs(o["pagado_por_el_comitente"] - (sum(LENNON) + 300000)) < 0.01, o)
        fila = libro.movimientos()[-1]
        check("concilia FALSO y SOLO_CAJA", fila["concilia"] == "FALSO" and fila["estado_conc"] == "SOLO_CAJA", fila)
        check("comitente heredado de OBRAS", fila["comitente"] == "Lucas Mariano Lennon", fila["comitente"])
        check(f"cargado_por = «{titular.nombre}», nunca «bot»", fila["cargado_por"] == titular.nombre, fila["cargado_por"])
        check("origen WHATSAPP, id_mov del motor", fila["origen"] == "WHATSAPP" and fila["id_mov"] == cuerpo["id_mov"], fila)

        # ── 5 · Drive falla ───────────────────────────────────────────────────
        print("\n5 · Con Drive caído, la fila se escribe igual")
        libro, _ = preparar(fallar_drive=True)
        antes = len(libro.filas)
        r = await confirmar("wamid.D1", ficha())
        cuerpo = r.json()
        check("200 y la fila está", r.status_code == 200 and len(libro.filas) == antes + 1, (r.status_code, cuerpo))
        check("vuelve la advertencia", any("no se movió" in a for a in cuerpo["advertencias"]), cuerpo["advertencias"])

        # ── Errores: nada se escribe ──────────────────────────────────────────
        print("\nErrores: en ninguno se escribe nada")
        casos = [
            ("teléfono desconocido → 403", 403, "telefono", {"telefono": "5490000000000"}, ficha()),
            ("falta el importe → 422", 422, "importe", {}, ficha(importe=None)),
            ("obra inexistente → 422", 422, "obra", {}, ficha(obra="Obra Fantasma")),
            ("EGRESO sin tipo_gasto → 422", 422, "tipo_gasto", {}, ficha(tipo_gasto=None)),
            ("cuenta inexistente → 422", 422, "cuenta", {}, ficha(cuenta="Caja Chica")),
            ("TRASPASO a la misma cuenta → 422", 422, "cuenta_destino", {},
             ficha(tipo="TRASPASO", cuenta_origen="Banco", cuenta_destino="Banco")),
            ("TRASPASO sin cuenta de origen → 422", 422, "cuenta_origen", {},
             ficha(tipo="TRASPASO", cuenta_origen=None, cuenta_destino="Efectivo")),
            ("TRASPASO desde una cuenta inactiva → 422", 422, "cuenta_origen", {},
             ficha(tipo="TRASPASO", cuenta_origen="caja_obra", cuenta_destino="Efectivo")),
            ("TRASPASO desde «Pagado por el comitente» → 422", 422, "cuenta_origen", {},
             ficha(tipo="TRASPASO", cuenta_origen="Pagado por el comitente", cuenta_destino="Efectivo")),
            ("TRASPASO entre monedas → 422", 422, "cuenta_destino", {},
             ficha(tipo="TRASPASO", cuenta_origen="Banco", cuenta_destino="Banco USD")),
            ("USD sin tipo de cambio → 422", 422, "tc", {}, ficha(moneda="USD", tc=None)),
            ("PASANTE sin contratista → 422", 422, "contratista", {}, ficha(tipo="PASANTE", contratista=None)),
            ("la caja de otra obra → 422", 422, "cuenta", {}, ficha(cuenta="Caja obra Moreno")),
            ("una etapa en una obra sin etapas → 422", 422, "etapa", {}, ficha(etapa="1")),
        ]
        for descripcion, status, campo, extra, f in casos:
            libro, _ = preparar()
            antes = len(libro.filas)
            tel = extra.get("telefono", titular.telefono)
            r = await confirmar(f"wamid.E-{campo}", f, telefono=tel)
            detalle = r.json().get("detail", {})
            check(descripcion, r.status_code == status and detalle.get("campo") == campo and len(libro.filas) == antes,
                  (r.status_code, detalle, len(libro.filas) - antes))

        # ── Alias ─────────────────────────────────────────────────────────────
        print("\nEl alias que enseña el usuario")
        libro, _ = preparar()
        cuerpo = (await confirmar("wamid.A1", ficha(), alias_propuesto={
            "como_lo_dice": "Rodri", "valor_canonico": "Rodrigo Sanitarista", "tipo": "contratista"})).json()
        check("se escribe", cuerpo["alias_escrito"] and libro.alias[-1] == ["rodri", "Rodrigo Sanitarista", "contratista"],
              libro.alias[-1])
        cuerpo = (await confirmar("wamid.A2", ficha(), alias_propuesto={
            "como_lo_dice": "rodri", "valor_canonico": "Rodrigo Sanitarista", "tipo": "contratista"})).json()
        check("repetido idéntico no se duplica", not cuerpo["alias_escrito"], cuerpo)
        n_alias = len(libro.alias)
        cuerpo = (await confirmar("wamid.A3", ficha(), alias_propuesto={
            "como_lo_dice": "miguel", "valor_canonico": "Miguel Matuz", "tipo": "contratista"})).json()
        check("mismo apodo a otra persona: se agrega, no se pisa, y avisa que queda ambiguo",
              cuerpo["alias_escrito"] and len(libro.alias) == n_alias + 1
              and any("ambiguo" in a for a in cuerpo["advertencias"])
              and any(a[0] == "miguel" and a[1] == "Miguel Soto" for a in libro.alias), cuerpo)
        cuerpo = (await confirmar("wamid.A4", ficha(), alias_propuesto={
            "como_lo_dice": "fantasma", "valor_canonico": "Nadie", "tipo": "contratista"})).json()
        check("a un contratista inexistente: no se escribe, el movimiento sí", not cuerpo["alias_escrito"]
              and cuerpo["id_mov"] and any("no está en los maestros" in a for a in cuerpo["advertencias"]), cuerpo)

        # ── Certificado ───────────────────────────────────────────────────────
        print("\nEl certificado no se pierde al confirmar (§5.11)")
        libro, _ = preparar()
        f = ficha(tipo="INGRESO", obra="Moreno", contratista=None, cuenta="Caja obra Moreno", tipo_gasto="obra",
                  importe=2600000, comprobante_url=None, descripcion="Certificado 4")
        f["extras"] = {"certificado": "4"}
        cuerpo = (await confirmar("wamid.CERT", f)).json()
        fila = libro.movimientos()[-1]
        check("columna certificado = 4", fila.get("certificado") == "4", fila.get("certificado"))
        caja = cuerpo["obra"]["caja_obra"] or {}
        check("el cobro entra a la caja de Moreno, no al estudio (§5.8)",
              abs(caja.get("ingresado", 0) - (sum(MORENO) + 2600000)) < 0.01 and cuerpo["obra"]["adelantado"] == 0,
              cuerpo["obra"])
        check("un cobro de un certificado que no está en CERTIFICADOS: se escribe y avisa",
              cuerpo["certificado"] is None and any("no está cargado en CERTIFICADOS" in a for a in cuerpo["advertencias"]),
              cuerpo["advertencias"])

        # ── Tanda 6.1 · PASANTE ───────────────────────────────────────────────
        print("\n6.1 · Un depósito «en negro» se confirma (§5.17)")
        from app.filtros import para_conciliacion
        libro, _ = preparar()
        antes_saldo = saldo_estudio(libro.movimientos(), m)["total"]
        r = await confirmar("wamid.PAS1", ficha(tipo="PASANTE", obra="Moreno", contratista="Marcelo Maragaño",
                                                 cuenta="Banco", tipo_gasto=None, comprobante_url=None))
        cuerpo = r.json()
        fila = libro.movimientos()[-1]
        check("200: una sola fila PASANTE", r.status_code == 200 and fila["tipo"] == "PASANTE", (r.status_code, cuerpo))
        check("cuenta forzada a «Pagado por el comitente», informal VERDADERO, concilia FALSO",
              (fila["cuenta"], fila["informal"], fila["concilia"]) == ("Pagado por el comitente", "VERDADERO", "FALSO"), fila)
        check("tipo_gasto derivado de la obra cuando no viene", fila["tipo_gasto"] == "obra", fila["tipo_gasto"])
        check("no mueve el saldo del estudio", saldo_estudio(libro.movimientos(), m)["total"] == antes_saldo)
        check("suma a lo pagado por el comitente en la obra", cuerpo["obra"]["pagado_por_el_comitente"] == 300000, cuerpo["obra"])
        check("no aparece en lo que concilia", not any(mv["id_mov"] == fila["id_mov"] for mv in para_conciliacion(libro.movimientos())))

        # ── Tanda 6.2 · TRASPASO ──────────────────────────────────────────────
        print("\n6.2 · Un traspaso: dos filas vinculadas en una sola escritura (§5.18)")

        def ficha_traspaso(**campos):
            base = {"tipo": "TRASPASO", "fecha": "2026-09-22", "importe": 80000, "moneda": "ARS",
                    "cuenta_origen": "Efectivo", "cuenta_destino": "Caja obra Lennon", "comprobante_url": None}
            base.update(campos)
            return {"campos": base, "extras": {}}

        libro, _ = preparar()
        antes, escrituras = len(libro.filas), libro.escrituras
        saldo_antes = saldo_estudio(libro.movimientos(), m)
        r = await confirmar("wamid.TR1", ficha_traspaso())
        cuerpo = r.json()
        salida_f, entrada_f = libro.movimientos()[-2:]
        check("200: dos filas en UNA escritura", r.status_code == 200 and len(libro.filas) == antes + 2
              and libro.escrituras == escrituras + 1, (r.status_code, cuerpo))
        check("id_mov e id_mov_vinculado consecutivos (M-000010 y M-000011)",
              (cuerpo["id_mov"], cuerpo["id_mov_vinculado"]) == ("M-000010", "M-000011"), cuerpo)
        check("vinculadas entre sí, con msg_id <wamid>#0 y <wamid>#0b",
              salida_f["vinculo"] == "M-000011" and entrada_f["vinculo"] == "M-000010"
              and (salida_f["msg_id"], entrada_f["msg_id"]) == ("wamid.TR1#0", "wamid.TR1#0b"), (salida_f, entrada_f))
        check("salida negativa de Efectivo, entrada positiva en la caja de Lennon, mismo importe",
              (salida_f["cuenta"], salida_f["importe"], entrada_f["cuenta"], entrada_f["importe"])
              == ("Efectivo", -80000, "Caja obra Lennon", 80000) and salida_f["tipo"] == entrada_f["tipo"] == "TRASPASO",
              (salida_f, entrada_f))
        check("la fila de la caja lleva la obra; la de Efectivo, ninguna",
              entrada_f["obra"] == "Lennon" and salida_f["obra"] == "", (salida_f["obra"], entrada_f["obra"]))
        saldo_despues = saldo_estudio(libro.movimientos(), m)
        check("el efectivo del estudio baja 80.000 (la caja de obra no suma al estudio)",
              round(saldo_antes["por_cuenta"]["Efectivo"] - saldo_despues["por_cuenta"]["Efectivo"], 2) == 80000, saldo_despues)
        check("la caja de Lennon tiene 80.000 por rendir", cuerpo["obra"]["caja_obra"]["por_rendir"] == 80000, cuerpo["obra"])
        r2 = (await confirmar("wamid.TR1", ficha_traspaso(importe=1))).json()
        check("idempotente: el reintento devuelve el par, sin escribir",
              r2["ya_existia"] and (r2["id_mov"], r2["id_mov_vinculado"]) == ("M-000010", "M-000011")
              and len(libro.filas) == antes + 2, r2)
        libro, _ = preparar()
        antes_total = saldo_estudio(libro.movimientos(), m)["total"]
        await confirmar("wamid.TR2", ficha_traspaso(cuenta_origen="Banco", cuenta_destino="Efectivo", importe=50000))
        despues = saldo_estudio(libro.movimientos(), m)
        check("Banco → Efectivo: el total del estudio no cambia y cada cuenta se mueve",
              despues["total"] == antes_total and despues["por_cuenta"]["Banco"] == -50000
              and despues["por_cuenta"]["Efectivo"] == 50000, despues)
        banco = next(mv for mv in libro.movimientos() if mv["msg_id"] == "wamid.TR2#0")
        check("la fila del banco concilia sola (PENDIENTE); la del efectivo no",
              banco["concilia"] == "VERDADERO" and libro.movimientos()[-1]["concilia"] == "FALSO", banco)
        sin_vinculo = LibroMemoria([c for c in encabezado if c != "vinculo"])
        app.dependency_overrides[obtener_libro] = lambda: sin_vinculo
        r = await confirmar("wamid.TR3", ficha_traspaso())
        check("sin la columna «vinculo» en el Sheet: 500 y no escribe nada",
              r.status_code == 500 and len(sin_vinculo.filas) == 1, (r.status_code, r.json()))

        # ── Tanda 6.3 · contraasiento ─────────────────────────────────────────
        print("\n6.3 · Corregir algo confirmado: el contraasiento (§5.19)")
        from app.saldos import saldo_obra

        async def anular_(id_mov, msg_id, telefono=titular.telefono, motivo="otra obra"):
            return await cli.post("/anular", json={"telefono": telefono, "id_mov": id_mov, "msg_id": msg_id, "motivo": motivo})

        async def ver(id_mov, telefono=titular.telefono):
            return await cli.get(f"/movimientos/{id_mov}", params={"telefono": telefono})

        def pagos_a(contratista):
            return cli.post("/consultar", json={"telefono": titular.telefono, "consulta": "pagos", "contratista": contratista})

        libro, _ = preparar()
        saldo0 = saldo_estudio(libro.movimientos(), m)
        pagos0 = (await pagos_a("Felipe Andrés Scherer")).json()["datos"]["cantidad"]
        r = (await confirmar("wamid.MAL", ficha(cuenta="Banco", importe=300000))).json()
        check("se confirma un pago por error (M-000010)", r["id_mov"] == "M-000010", r)
        v = (await ver("M-000010")).json()
        check("GET /movimientos/M-000010: la fila, sin anular", v["libro"] == "estudio" and v["campos"]["importe"] == 300000
              and v["anulado_por"] is None, v)
        filas_antes = len(libro.filas)
        r = await anular_("M-000010", "wamid.CORR")
        a = r.json()
        contra = libro.movimientos()[-1]
        check("POST /anular: 200, M-000011 anula M-000010 en el libro del estudio",
              r.status_code == 200 and (a["id_mov_anulacion"], a["anula"], a["libro"]) == ("M-000011", "M-000010", "estudio"), a)
        check("el contraasiento: mismos campos, importe con signo contrario, anula, origen ANULACION, quién anuló",
              (contra["importe"], contra["anula"], contra["origen"], contra["cargado_por"], contra["obra"], contra["cuenta"])
              == (-300000, "M-000010", "ANULACION", titular.nombre, "Lennon", "Banco")
              and len(libro.filas) == filas_antes + 1, contra)
        original = next(mv for mv in libro.movimientos() if mv["id_mov"] == "M-000010")
        check("la original no se toca", original["importe"] == 300000 and not original.get("anula"), original)
        check("ficha_original sirve de contexto_previo: sus campos, sin id_mov",
              a["ficha_original"]["campos"]["obra"] == "Lennon" and a["ficha_original"]["campos"]["importe"] == 300000
              and a["ficha_original"]["campos"]["id_mov"] is None, a["ficha_original"])
        check("el saldo del estudio vuelve a ser el de antes", saldo_estudio(libro.movimientos(), m) == saldo0)
        lennon, _ = saldo_obra(libro.movimientos(), "Lennon", m)
        check("la cuenta corriente de Lennon, también", lennon.pagado_con_plata_del_estudio == 0, lennon)
        check("«cuántos pagos a Felipe» no cuenta ni la original ni la anulación",
              (await pagos_a("Felipe Andrés Scherer")).json()["datos"]["cantidad"] == pagos0)
        check("GET muestra quién la anuló", (await ver("M-000010")).json()["anulado_por"] == "M-000011")
        r2 = (await anular_("M-000010", "wamid.CORR")).json()
        check("idempotente por msg_id: el reintento devuelve el mismo contraasiento",
              r2["ya_existia"] and r2["id_mov_anulacion"] == "M-000011" and len(libro.filas) == filas_antes + 1, r2)
        r = await anular_("M-000010", "wamid.CORR2")
        check("anularla otra vez: 409 con la anulación existente",
              r.status_code == 409 and r.json()["detail"].get("id_mov_anulacion") == "M-000011", r.json())
        r = await anular_("M-000011", "wamid.CORR3")
        check("no se anula un contraasiento: 422", r.status_code == 422, r.json())
        r = await confirmar("wamid.CORR", ficha(cuenta="Banco", importe=300000, obra="Moreno", contratista="Marcelo Maragaño"))
        check("la fila correcta con el mismo wamid se escribe (no se toma por un reintento de la anulación)",
              r.status_code == 200 and not r.json()["ya_existia"] and r.json()["id_mov"] == "M-000012", r.json())
        check("GET de un id inexistente: 404", (await ver("M-999999")).status_code == 404)

        print("\n6.3 · Anular un traspaso anula las dos filas")
        libro, _ = preparar()
        caja0 = saldo_estudio(libro.movimientos(), m)
        t = (await confirmar("wamid.TRX", ficha_traspaso())).json()
        a = (await anular_(t["id_mov_vinculado"], "wamid.TRX-C")).json()
        nuevas = libro.movimientos()[-2:]
        check("anular la entrada escribe los dos contraasientos, vinculados, en una sola escritura",
              {a["anula"], a["anula_vinculado"]} == {t["id_mov"], t["id_mov_vinculado"]}
              and nuevas[0]["vinculo"] == nuevas[1]["id_mov"] and nuevas[1]["vinculo"] == nuevas[0]["id_mov"], (a, nuevas))
        lennon, _ = saldo_obra(libro.movimientos(), "Lennon", m)
        check("el efectivo del estudio y la caja de Lennon vuelven a cero",
              saldo_estudio(libro.movimientos(), m) == caja0 and (lennon.caja_obra is None or lennon.caja_obra.por_rendir == 0),
              (saldo_estudio(libro.movimientos(), m), lennon.caja_obra))
        check("ficha_original del traspaso: origen y destino, importe positivo",
              (a["ficha_original"]["campos"]["cuenta_origen"], a["ficha_original"]["campos"]["cuenta_destino"],
               a["ficha_original"]["campos"]["importe"]) == ("Efectivo", "Caja obra Lennon", 80000), a["ficha_original"])

        print("\n6.3 · Anular un personal: libro personal, acceso y cierre semanal")
        libro, _ = preparar()
        personal = personal_actual["libro"]
        p = (await confirmar("wamid.PERS", ficha(obra=None, contratista="Marcelo Maragaño", rubro_1="Personal",
                                                  rubro_2="Casa", cuenta="Banco", tipo_gasto="personal",
                                                  fecha="2026-09-22", importe=40000, comprobante_url=None))).json()
        await cli.post("/cierre-semanal", json={"semana": "2026-W39"})
        vigente = maestros.cargar()
        reemplazo = Usuario("5490000000003", "Reemplazo de prueba", "colaborador", True, ve_personal=False)
        vigente.usuarios.append(reemplazo)
        try:
            r = await anular_(p["id_mov"], "wamid.PERS-X", telefono=reemplazo.telefono)
            check("sin ve_personal: 403 al anular y al ver un P-",
                  r.status_code == 403 and (await ver(p["id_mov"], reemplazo.telefono)).status_code == 403
                  and len(personal.filas) == 2, r.json())
        finally:
            vigente.usuarios.remove(reemplazo)
        a = (await anular_(p["id_mov"], "wamid.PERS-C")).json()
        check("el contraasiento de un P- va al libro personal, con secuencia P-",
              (a["libro"], a["id_mov_anulacion"]) == ("personal", "P-000002") and personal.movimientos()[-1]["importe"] == -40000, a)
        r = (await cli.post("/cierre-semanal", json={"semana": "2026-W40"})).json()
        check("el próximo cierre escribe el ajuste de la semana del personal anulado",
              [(e["semana"], e["cuenta"], e["tipo"], e["importe"], e["ajuste"]) for e in r["escritas"]]
              == [("2026-W39", "Banco", "INGRESO", 40000, True)], r["escritas"])
        cierre = next(mv for mv in libro.movimientos() if mv.get("origen") == "CIERRE")
        r = await anular_(cierre["id_mov"], "wamid.CIERRE-X")
        check("la línea del cierre semanal no se anula a mano: 422", r.status_code == 422, r.json())

        sin_anula = LibroMemoria([c for c in encabezado if c != "anula"])
        sin_anula.sembrar(id_mov="M-000001", fecha="2026-09-01", tipo="EGRESO", importe=1, moneda="ARS", cuenta="Banco")
        app.dependency_overrides[obtener_libro] = lambda: sin_anula
        r = await anular_("M-000001", "wamid.SA")
        check("sin la columna «anula» en el Sheet: 500 y no escribe nada",
              r.status_code == 500 and len(sin_anula.filas) == 2, (r.status_code, r.json()))

        # ── Tanda 5 · CERTIFICADOS ────────────────────────────────────────────
        print("\nTanda 5 · el certificado va a CERTIFICADOS, no a MOVIMIENTOS (§5.11)")

        def ficha_cert(**campos):
            base = {"tipo": "CERTIFICADO", "obra": "Moreno", "etapa": None, "numero": "5", "fecha": "2026-09-20",
                    "saldo_a_cobrar": 3200000, "fuente": "PDF",
                    "comprobante_url": "https://drive.google.com/file/d/1CERTxxxxxxxxxxxxxxxxxxxxxx/view"}
            base.update(campos)
            return {"campos": base, "extras": {}}

        libro, archivador = preparar()
        antes = len(libro.filas)
        r = await confirmar("wamid.CERT5", ficha_cert())
        cuerpo = r.json()
        cert = libro.certificados[-1]
        check("200, libro = certificados, y MOVIMIENTOS no se toca",
              r.status_code == 200 and cuerpo["libro"] == "certificados" and len(libro.filas) == antes, (r.status_code, cuerpo))
        check("la fila: obra, etapa, número, fecha, saldo, fuente, msg_id, cargado_por, comprobante",
              cert[:6] == ["Moreno", "", "5", "2026-09-20", 3200000, "PDF"] and cert[6] == "wamid.CERT5#0"
              and cert[7] == titular.nombre and cert[8], cert)
        check("el PDF va a comprobantes/Moreno/certificados/",
              archivador.movidos and archivador.movidos[-1][1] == ["Moreno", "certificados"]
              and archivador.movidos[-1][2].startswith("Certificado 5 Moreno"), archivador.movidos)
        check("devuelve el estado: pendiente = saldo, nada cobrado",
              cuerpo["certificado"]["pendiente"] == 3200000 and cuerpo["certificado"]["cobrado"] == 0, cuerpo["certificado"])
        r2 = (await confirmar("wamid.CERT5", ficha_cert(saldo_a_cobrar=1))).json()
        check("idempotente: el reintento devuelve la misma fila", r2["ya_existia"] and r2["fila"] == cuerpo["fila"]
              and len(libro.certificados) == 2, r2)

        cobro = ficha(tipo="INGRESO", obra="Moreno", contratista=None, cuenta="Caja obra Moreno", tipo_gasto="obra",
                      importe=1200000, comprobante_url=None, descripcion="Certificado 5")
        cobro["extras"] = {"certificado": "5"}
        cuerpo = (await confirmar("wamid.COBRO5", cobro)).json()
        check("un cobro del certificado 5 lo cancela en parte: pendiente 2.000.000",
              cuerpo["certificado"] and cuerpo["certificado"]["cobrado"] == 1200000
              and cuerpo["certificado"]["pendiente"] == 2000000, cuerpo.get("certificado"))
        cobro["extras"] = {"certificado": "5 extras"}
        cuerpo = (await confirmar("wamid.COBRO5X", cobro)).json()
        check("el cobro de «5 extras» no cancela al certificado 5 (otra serie)", cuerpo["certificado"] is None, cuerpo)

        casos_cert = [
            ("Austral no se certifica → 422", "obra", ficha_cert(obra="Austral")),
            ("obra inexistente → 422", "obra", ficha_cert(obra="Lo Guercio")),
            ("sin número → 422", "numero", ficha_cert(numero="")),
            ("saldo cero → 422", "saldo_a_cobrar", ficha_cert(saldo_a_cobrar=0)),
            ("una etapa en una obra sin etapas → 422", "etapa", ficha_cert(etapa="2")),
        ]
        for descripcion, campo, f in casos_cert:
            libro, _ = preparar()
            r = await confirmar(f"wamid.EC-{campo}", f)
            detalle = r.json().get("detail", {})
            check(descripcion, r.status_code == 422 and detalle.get("campo") == campo and len(libro.certificados) == 1,
                  (r.status_code, detalle))

        # ── Tanda 5 · /consultar ──────────────────────────────────────────────
        print("\nTanda 5 · /consultar: las tres preguntas, filtradas por ve_personal")
        from app.maestros import Usuario
        libro, _ = preparar()
        personal = personal_actual["libro"]
        libro.sembrar(id_mov="M-000010", fecha="2026-09-10", tipo="EGRESO", importe=500000, moneda="ARS", tc=1,
                      importe_ars=500000, obra="Moreno", contratista="Marcelo Maragaño", rubro_1="Mano de obra",
                      cuenta="Caja obra Moreno", medio_pago="Efectivo", tipo_gasto="obra", cargado_por="Petrus")
        libro.sembrar(id_mov="M-000011", fecha="2026-09-12", tipo="EGRESO", importe=200000, moneda="ARS", tc=1,
                      importe_ars=200000, obra="Moreno", contratista="Marcelo Maragaño", rubro_1="Mano de obra",
                      cuenta="Banco", medio_pago="Transferencia", tipo_gasto="obra", cargado_por=titular.nombre)
        libro.sembrar(id_mov="M-000012", fecha="2026-09-01", tipo="EGRESO", importe=77000, moneda="ARS", tc=1,
                      importe_ars=77000, contratista="Marcelo Maragaño", rubro_1="Personal", cuenta="Banco",
                      tipo_gasto="personal", cargado_por=titular.nombre)  # personal viejo, en el libro del estudio
        personal.sembrar(id_mov="P-000001", fecha="2026-09-15", tipo="EGRESO", importe=90000, moneda="ARS", tc=1,
                         importe_ars=90000, contratista="Marcelo Maragaño", rubro_1="Personal", cuenta="Efectivo",
                         tipo_gasto="personal", cargado_por=titular.nombre)
        libro.certificados.append(["Moreno", "", "4", "2026-02-01", 3000000, "TEXTO", "w#0", "Petrus", ""])

        async def consultar(**cuerpo):
            return await cli.post("/consultar", json={"telefono": titular.telefono, **cuerpo})

        r = (await consultar(texto="¿Cuántos pagos se le hicieron a Marcelo Maragaño por la obra Moreno?")).json()
        check("pagos a X por obra Y: cantidad, total y detalle con quién cargó",
              r["consulta"] == "pagos" and r["datos"]["cantidad"] == 2 and r["datos"]["total"] == 700000
              and {d["cargado_por"] for d in r["datos"]["detalle"]} == {"Petrus", titular.nombre}, r["datos"])
        check("… con un texto para WhatsApp", "2 pagos, total $700.000" in r["texto"] and "Petrus" in r["texto"], r["texto"])
        r = (await consultar(consulta="pagos", contratista="Marcelo Maragaño")).json()
        check("sin obra, con ve_personal: suma lo personal de los dos libros",
              r["datos"]["cantidad"] == 4 and {d["libro"] for d in r["datos"]["detalle"]} == {"estudio", "personal"}, r["datos"])
        sin_personal = Usuario("5490000000002", "Reemplazo de prueba", "colaborador", True, ve_personal=False)
        vigente = maestros.cargar()  # el caso «teléfono desconocido» recargó la caché
        vigente.usuarios.append(sin_personal)
        try:
            r = (await consultar(consulta="pagos", contratista="Marcelo Maragaño", telefono=sin_personal.telefono)).json()
            check("sin ve_personal: ni el libro personal ni las filas personales del estudio",
                  r["datos"]["cantidad"] == 2 and {d["libro"] for d in r["datos"]["detalle"]} == {"estudio"}
                  and r["datos"]["total"] == 700000, r)
        finally:
            vigente.usuarios.remove(sin_personal)
        r = (await consultar(texto="pagos a Marce")).json()
        check("apodo ambiguo: repregunta, no adivina", r["preguntas"] and r["preguntas"][0].get("motivo") == "apodo_ambiguo", r)
        r = await consultar(texto="¿pagos?", telefono="5490000000000")
        check("teléfono desconocido → 403", r.status_code == 403, r.status_code)

        r = (await consultar(texto="¿Cuánto va gastado en cada obra, de mano de obra y de materiales?")).json()
        obras = {o["obra"]: o for o in r["datos"]["obras"]}
        check("gasto por obra: incluye lo que pagó el comitente, aparte",
              obras["Lennon"]["comitente"] == sum(LENNON) and obras["Lennon"]["estudio"] == 0, obras.get("Lennon"))
        check("… abierto por rubro_1 y por quién puso la plata",
              obras["Moreno"]["por_rubro"]["Mano de obra"] == {"total": 700000, "estudio": 200000, "caja_obra": 500000,
                                                               "comitente": 0}, obras["Moreno"]["por_rubro"])
        check("… el texto separa al comitente", "pagó el comitente" in r["texto"] and "*Lennon*" in r["texto"], r["texto"])

        for n, (cert_n, importe) in enumerate([("4", 1000000), ("9", 450000)], start=13):
            libro.sembrar(id_mov=f"M-{n:06d}", fecha="2026-09-14", tipo="INGRESO", importe=importe, moneda="ARS", tc=1,
                          importe_ars=importe, obra="Moreno", cuenta="Caja obra Moreno", tipo_gasto="obra",
                          certificado=cert_n, cargado_por="Petrus")
        r = (await consultar(texto="¿El comitente de Moreno pagó todas las certificaciones?")).json()
        g = r["datos"]["grupos"]
        check("certificaciones: certificado, cobrado y pendiente por obra y etapa",
              len(g) == 1 and (g[0]["obra"], g[0]["certificado"], g[0]["cobrado"], g[0]["pendiente"])
              == ("Moreno", 3000000, 1000000, 2000000), g)
        check("el cobro de un certificado no cargado (el 9) se muestra aparte y no se resta",
              [c["certificado"] for c in r["datos"]["cobros_sin_certificado"]] == ["9"]
              and "pendiente $2.000.000" in r["texto"] and "no está cargado" in r["texto"], r)

    app.dependency_overrides.clear()

    # ── Reintentos ante errores transitorios de Google ────────────────────────
    print("\nSheets devuelve 429 o 503: tres intentos con espera creciente")
    from googleapiclient.errors import HttpError

    from app import sheets

    class Respuesta:
        def __init__(self, status):
            self.status, self.reason = status, "simulado"

    class Pedido:
        def __init__(self, errores):
            self.errores, self.intentos = list(errores), 0

        def execute(self):
            self.intentos += 1
            if self.errores:
                raise HttpError(Respuesta(self.errores.pop(0)), b"{}")
            return {"ok": True}

    esperas_reales = sheets._ESPERAS
    sheets._ESPERAS = (0, 0)
    try:
        p = Pedido([429, 503])
        check("429 y 503 se reintentan y al tercero sale", sheets._ejecutar(p) == {"ok": True} and p.intentos == 3, p.intentos)
        p = Pedido([503, 503, 503])
        try:
            sheets._ejecutar(p)
            check("tres fallas seguidas se propagan", False, "no levantó")
        except HttpError:
            check("tres fallas seguidas se propagan (no reintenta para siempre)", p.intentos == 3, p.intentos)
        p = Pedido([400])
        try:
            sheets._ejecutar(p)
        except HttpError:
            check("un 400 no se reintenta", p.intentos == 1, p.intentos)
    finally:
        sheets._ESPERAS = esperas_reales

    print(f"\n{'TODO OK' if not fallas else str(len(fallas)) + ' FALLAS'}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
