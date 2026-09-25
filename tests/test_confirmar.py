"""POST /confirmar contra un libro en memoria. NUNCA escribe en el Sheet real: MOVIMIENTOS
es append-only y una fila de prueba no se puede borrar.

    python -m tests.test_confirmar

El libro en memoria imita al Sheet en lo que importa: escribir la fila N pisa lo que había
en la fila N. Así, si el lock del id_mov fallara, se vería igual que en producción: dos
confirmaciones sacan el mismo número y la segunda borra a la primera.
"""
import asyncio
import contextlib
import json
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# Filas reales del libro al 24/09, para que los saldos se prueben contra datos verdaderos.
LENNON = [4032391.7, 3675000, 300000, 103050, 7000000, 7000000]   # pagado por el comitente
MORENO = [2600000, 566596, 2079000]                               # certificaciones: plata de la obra (§5.8)


class LibroMemoria:
    def __init__(self, encabezado: list[str], alias: list[list], demora: float = 0.0):
        self.encabezado = list(encabezado)
        self.filas: list[list] = [list(encabezado)]
        self.alias = [list(a) for a in alias]
        self.demora = demora
        n = 0
        for importe in LENNON:
            n += 1
            self._sembrar(n, "2026-09-02", "EGRESO", importe, "Lennon", "Pagado por el comitente")
        for importe in MORENO:
            n += 1
            self._sembrar(n, "2026-02-08", "INGRESO", importe, "Moreno", "Caja obra Moreno")

    def _sembrar(self, n, fecha, tipo, importe, obra, cuenta):
        fila = {"id_mov": f"M-{n:06d}", "fecha": fecha, "tipo": tipo, "importe": importe, "moneda": "ARS",
                "tc": 1, "importe_ars": importe, "obra": obra, "cuenta": cuenta, "origen": "WHATSAPP"}
        self.filas.append([fila.get(c, "") for c in self.encabezado])

    def leer_movimientos(self):
        time.sleep(self.demora)
        return [list(f) for f in self.filas]

    def escribir_fila(self, numero, valores):
        time.sleep(self.demora)
        while len(self.filas) < numero - 1:
            self.filas.append([])
        if len(self.filas) >= numero:
            self.filas[numero - 1] = list(valores)  # igual que el Sheet: pisa
        else:
            self.filas.append(list(valores))

    def leer_alias(self):
        return [list(a) for a in self.alias]

    def agregar_alias(self, fila):
        self.alias.append(list(fila))

    def movimientos(self) -> list[dict]:
        return [dict(zip(self.encabezado, f)) for f in self.filas[1:]]


class ArchivadorFalso:
    def __init__(self, fallar: bool = False):
        self.fallar = fallar
        self.movidos: list[tuple] = []
        self.avisos: list[str] = []

    def archivar(self, file_id, carpetas, nombre_base):
        if self.fallar:
            raise ConnectionError("Drive caído (simulado)")
        self.movidos.append((file_id, list(carpetas), nombre_base))
        return f"https://drive.google.com/file/d/{file_id}/view"


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
    from app.main import app, obtener_archivador, obtener_libro
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

    def preparar(demora=0.0, fallar_drive=False):
        libro = LibroMemoria(encabezado, snapshot["ALIAS"], demora)
        archivador = ArchivadorFalso(fallar_drive)
        app.dependency_overrides[obtener_libro] = lambda: libro
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
        print("\n3 · Un movimiento personal sin obra")
        libro, archivador = preparar()
        r = await confirmar("wamid.P1", ficha(obra=None, contratista="Marcelo Maragaño", rubro_1="Personal",
                                              rubro_2="Casa", cuenta="Banco", tipo_gasto="personal"))
        cuerpo = r.json()
        fila = libro.movimientos()[-1]
        check("se escribe", r.status_code == 200, cuerpo)
        check("con tipo_gasto = personal y sin obra", fila["tipo_gasto"] == "personal" and fila["obra"] == "", fila)
        check("el comprobante va a personal/2026-09/", archivador.movidos and archivador.movidos[-1][1] == ["personal", "2026-09"],
              archivador.movidos)
        check("el archivo empieza con el id_mov", archivador.movidos and archivador.movidos[-1][2].startswith(cuerpo["id_mov"] + " "),
              archivador.movidos)
        check("sin obra no hay saldo de obra", cuerpo["obra"] is None, cuerpo["obra"])
        check("Banco concilia: VERDADERO y PENDIENTE", fila["concilia"] == "VERDADERO" and fila["estado_conc"] == "PENDIENTE", fila)

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
