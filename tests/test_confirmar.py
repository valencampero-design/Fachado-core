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
    encabezado = snapshot["MOVIMIENTOS"][0]
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
            ("TRASPASO todavía no → 422", 422, "tipo", {}, ficha(tipo="TRASPASO")),
            ("USD sin tipo de cambio → 422", 422, "tc", {}, ficha(moneda="USD", tc=None)),
            ("PASANTE, sin cuenta definida en el contexto → 422", 422, "tipo", {}, ficha(tipo="PASANTE", cuenta=None)),
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
