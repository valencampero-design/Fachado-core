"""Correcciones de lo cargado hasta el 9/10 (handoff de la conversación del 9/10, H).

Todo por contraasiento (§5.19): nunca se edita una fila. Cada corrección anula la original
con /anular y recarga la fila correcta con /confirmar, con las mismas funciones del motor.

1. (opcional, `--con-ingreso-usd`) El ingreso de USD 20.000 de Lennon a su caja (28/09,
   capturas 4 a 7). Solo si Gabriel lo confirma; si no, queda en la lista de reenvíos.
2. Los pagos de Lennon cargados contra Efectivo pasan a la caja de obra (§5.8 v1.8): Luis
   Pereira M-000001 y Miguel Soto M-000008 y M-000010. Cada recibo dice el tipo de cambio
   (US$ 400 × 1425, US$ 6.600 × 1515, US$ 2.000 × 1535): con la caja en dólares es el tc de
   cada pago. M-000001 no tenía etapa: va la 1, la única en curso de Lennon.
3. Las fechas de M-000001 (7/02/2026) y M-000008 (5/08/2026) **no se cambian**: los recibos
   dicen exactamente eso («Sábado 7/02 de 2026», «Miércoles 05 de agosto de 2026», y los
   días de la semana coinciden). No fue una mala lectura.
4. P-000001 (Retiro/Sofi, 30/09): sin obra; contratista Sofía (la transferencia es a
   «FACHADO, SOFIA»; «Sofi» es Sofia Cervera por alias). P-000004 y P-000005: medio de pago
   Mercado Pago (decía «Otro»). El rubro de Edesur (Agua) no se toca: es una pregunta abierta.
5. M-000005 (Austral · Valentín Campero, 3/10): Gabriel contestó «400 dólares» y quedó en
   pesos (el bug de moneda, revisión cruzada del 9/10). Su comprobante (la foto de la fila
   191 de CAPTURA, que no quedó adjunta) es una transferencia de U$S 400,00 desde la caja de
   ahorro en dólares (op. 1973111147, «Cuota»): se recarga en USD, desde Banco USD, con el
   comprobante. El tc lo confirma Valen: `--tc-m000005 1450`; sin él, M-000005 no se toca.

La caja de Lennon ya está en dólares (`2026_10_09_caja_lennon_usd.py`, aplicado el 9/10).
Si no lo estuviera, el simulacro la simula en dólares y `--aplicar` se niega a correr.
**No aplicar hasta que Gabriel conteste las preguntas 1 a 3 del guion del 9/10.**

Simulacro por defecto: lee los dos libros reales (solo lectura) y corre todo sobre una
copia en memoria, sin Drive. Idempotente: cada corrección tiene su msg_id fijo, y volver a
correrlo con `--aplicar` no duplica nada.

    python scripts/migraciones/2026_10_09_correcciones.py                    (simulacro)
    python scripts/migraciones/2026_10_09_correcciones.py --con-ingreso-usd  (simulacro, con el 1)
    python scripts/migraciones/2026_10_09_correcciones.py --tc-m000005 1450  (simulacro, con el 5)
    python scripts/migraciones/2026_10_09_correcciones.py --aplicar [--con-ingreso-usd] [--tc-m000005 N]
"""
import argparse
import asyncio
import contextlib
import sys
from dataclasses import dataclass, field

sys.path.insert(0, ".")
from app import maestros  # noqa: E402
from app.anular import anular  # noqa: E402
from app.config import settings  # noqa: E402
from app.confirmar import ErrorConfirmar, confirmar  # noqa: E402
from app.libro import LibroSheets  # noqa: E402
from app.maestros import numero  # noqa: E402
from app.models import AnularIn, ConfirmarIn, FichaConfirmada  # noqa: E402
from app.saldos import como_dicts, saldo_obra  # noqa: E402

PREFIJO = "correccion-2026-10-09"  # msg_id fijo de cada corrección: idempotencia
CAJA = "Caja obra Lennon"


@dataclass
class Correccion:
    id_mov: str
    cambios: dict
    por_que: str
    extras: dict = field(default_factory=dict)
    pide_tc: bool = False  # el tc no está en el comprobante: lo confirma Valen (--tc-m000005)


CORRECCIONES = [
    Correccion("M-000005", {"moneda": "USD", "importe": 400, "cuenta": "Banco USD", "medio_pago": "Transferencia",
                            "tipo_comprobante": "Transferencia",
                            "comprobante_url": "https://drive.google.com/file/d/1ESChzjC3uECJiRcFuawk8MuEgLdbXnAy/view",
                            "ref_comprobante": "op:1973111147", "descripcion": "Op. 1973111147 · Cuota"},
               "«400 dólares» quedó en pesos (bug de moneda). Comprobante: U$S 400,00 desde la CA en dólares",
               pide_tc=True),
    Correccion("M-000001", {"cuenta": CAJA, "medio_pago": "Efectivo", "tc": 1425, "etapa": "1"},
               "§5.8 v1.8: el efectivo de Lennon sale de su caja. Recibo: US$ 400 × 1425 = $ 570.000"),
    Correccion("M-000008", {"cuenta": CAJA, "medio_pago": "Efectivo", "tc": 1515},
               "§5.8 v1.8: el efectivo de Lennon sale de su caja. Recibo: US$ 6.600 × 1515 ≈ $ 10.000.000"),
    Correccion("M-000010", {"cuenta": CAJA, "medio_pago": "Efectivo", "tc": 1535},
               "§5.8 v1.8: el efectivo de Lennon sale de su caja. Recibo: US$ 2.000 × 1535 = $ 3.070.000"),
    Correccion("P-000001", {"obra": None, "etapa": None, "comitente": None, "contratista": "Sofia Cervera",
                            "item": "FACHADO, SOFIA", "tipo_gasto": "personal",
                            "rubro_1": "Personal", "rubro_2": "Familia"},
               "Retiro/Sofi: un personal no lleva obra; la transferencia es a «FACHADO, SOFIA», no a Tucu"),
    Correccion("P-000004", {"medio_pago": "Mercado Pago"}, "pagado desde Mercado Pago, no «Otro»"),
    Correccion("P-000005", {"medio_pago": "Mercado Pago"}, "pagado desde Mercado Pago, no «Otro» (el rubro Agua, abierto)"),
]

INGRESO_USD = {
    "tipo": "INGRESO", "fecha": "2026-09-28", "importe": 20000, "moneda": "USD", "tc": None, "obra": "Lennon",
    "etapa": "1", "cuenta": CAJA, "medio_pago": "Efectivo", "tipo_gasto": "obra", "tipo_comprobante": "Sin comprobante",
    "descripcion": "Adelanto de Lucas Lennon para la caja de obra (capturas 4 a 7 del 9/10)", "origen": "WHATSAPP",
}


@contextlib.contextmanager
def caja_en_dolares(simular: bool):
    """El simulacro corre con la caja en dólares aunque la migración no esté aplicada."""
    if not simular:
        yield
        return
    original = maestros._leer_crudo

    def crudo():
        d = original()
        for fila in d["CUENTAS"][1:]:
            if fila and fila[0] == CAJA:
                fila[2] = "USD"
        return d
    maestros._leer_crudo = crudo
    try:
        maestros.cargar(forzar=True)
        yield
    finally:
        maestros._leer_crudo = original
        maestros.cargar(forzar=True)


def resumen_lennon(libro, m) -> str:
    saldo, _ = saldo_obra(como_dicts(libro.leer_movimientos()), "Lennon", m)
    caja = saldo.caja_obra
    texto = (f"pagado con plata del estudio $ {saldo.pagado_con_plata_del_estudio:,.0f} · "
             f"pagado por el comitente $ {saldo.pagado_por_el_comitente:,.0f}")
    if caja:
        texto += (f" · caja ({caja.moneda}): ingresado {caja.ingresado:,.2f}, pagado {caja.pagado:,.2f}, "
                  f"por rendir {caja.por_rendir:,.2f}")
    return texto


async def correr(args) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    s = settings()
    m = maestros.cargar(forzar=True)
    caja = m.cuenta(CAJA)
    if caja is None:
        sys.exit(f"No está «{CAJA}» en CUENTAS")
    simular_usd = caja.moneda != "USD"
    if simular_usd and args.aplicar:
        sys.exit(f"«{CAJA}» sigue en {caja.moneda}: correr antes scripts/migraciones/2026_10_09_caja_lennon_usd.py --aplicar")
    if not s.personal_sheet_id:
        sys.exit("Falta FACHADO_PERSONAL_SHEET_ID: P-000001/4/5 están en el libro personal")

    estudio_real, personal_real = LibroSheets(), LibroSheets(s.personal_sheet_id)
    if args.aplicar:
        from app.main import obtener_archivador
        estudio, personal, archivador = estudio_real, personal_real, obtener_archivador()
    else:
        from tests.dobles import ArchivadorFalso, LibroMemoria

        def copia(lib):
            filas = lib.leer_movimientos()
            memoria = LibroMemoria(filas[0])
            memoria.filas = [list(f) for f in filas]
            return memoria
        estudio, personal, archivador = copia(estudio_real), copia(personal_real), ArchivadorFalso()

    print(f"{'APLICANDO' if args.aplicar else 'SIMULACRO'} · correcciones del 9/10 (handoff H)")
    if simular_usd:
        print(f"  («{CAJA}» todavía está en {caja.moneda} en el Sheet: el simulacro la toma en USD, como queda "
              f"después de la migración)")
    errores = 0
    with caja_en_dolares(simular_usd):
        m = maestros.cargar()
        print(f"\nLennon antes:   {resumen_lennon(estudio, m)}")
        if args.con_ingreso_usd:
            print("\n1 · Ingreso de USD 20.000 a la caja de Lennon (28/09)")
            errores += await recargar(None, INGRESO_USD, {}, f"{PREFIJO}-ingreso-usd-lennon", "Gabriel Fachado",
                                      estudio, personal, archivador, m, "adelanto del comitente a la caja (§5.8)")
        else:
            print("\n1 · Ingreso de USD 20.000: no se carga (falta que Gabriel lo confirme; usar --con-ingreso-usd)")
        print("\n2, 4 y 5 · Contraasientos y recargas")
        for c in CORRECCIONES:
            if c.pide_tc and not args.tc_m000005:
                print(f"  · {c.id_mov}: no se toca (falta el tc: --tc-m000005, lo confirma Valen)")
                continue
            if c.pide_tc:
                c = Correccion(c.id_mov, {**c.cambios, "tc": args.tc_m000005}, c.por_que, c.extras)
            errores += await corregir(c, estudio, personal, archivador, m)
        print(f"\nLennon después: {resumen_lennon(estudio, m)}")
    if not args.aplicar:
        print("\n(simulacro: no se escribió nada en los libros ni se movió nada en Drive. Correr con --aplicar)")
    return 1 if errores else 0


async def corregir(c: Correccion, estudio, personal, archivador, m) -> int:
    lib = personal if c.id_mov.startswith("P-") else estudio
    original = next((mv for mv in como_dicts(lib.leer_movimientos()) if mv.get("id_mov") == c.id_mov), None)
    if original is None:
        print(f"  ✗ {c.id_mov}: no está en el libro")
        return 1
    usuario = next((u for u in m.usuarios if u.nombre == original.get("cargado_por")), None) \
        or next(u for u in m.usuarios if u.rol == "titular")
    msg_id = f"{PREFIJO}-{c.id_mov}"
    try:
        an = await anular(AnularIn(telefono=usuario.telefono, id_mov=c.id_mov, msg_id=msg_id, motivo=c.por_que),
                          estudio, personal)
    except ErrorConfirmar as e:
        print(f"  ✗ {c.id_mov}: no se pudo anular ({e.status} {e.campo}: {e.detalle})")
        return 1
    print(f"  · {c.id_mov} anulado por {an.id_mov_anulacion}{' (ya estaba)' if an.ya_existia else ''}")
    return await recargar(c.id_mov, an.ficha_original.campos, c.cambios, msg_id, usuario.nombre,
                          estudio, personal, archivador, m, c.por_que, an.ficha_original.extras)


async def recargar(id_mov, campos: dict, cambios: dict, msg_id: str, nombre_usuario: str, estudio, personal,
                   archivador, m, por_que: str, extras: dict | None = None) -> int:
    usuario = next(u for u in m.usuarios if u.nombre == nombre_usuario)
    nuevos = {**campos, **cambios, "id_mov": None}
    if nuevos.get("moneda") == "ARS" and "tc" in cambios:
        nuevos["importe_ars"] = nuevos["importe"]
    ficha = FichaConfirmada(campos=nuevos, extras=dict(extras or {}))
    try:
        r = await confirmar(ConfirmarIn(msg_id=msg_id, telefono=usuario.telefono, ficha=ficha), estudio, archivador,
                            personal)
    except ErrorConfirmar as e:
        print(f"  ✗ {id_mov or 'nuevo'}: no se pudo recargar ({e.status} {e.campo}: {e.detalle})")
        return 1
    distintos = {k: (campos.get(k), v) for k, v in cambios.items() if str(campos.get(k) or "") != str(v or "")}
    detalle = ", ".join(f"{k}: «{a or ''}» → «{b or ''}»" for k, (a, b) in distintos.items()) if id_mov else \
        ", ".join(f"{k}={v}" for k, v in campos.items() if v not in (None, ""))
    print(f"    {'recargado' if id_mov else 'cargado'} como {r.id_mov}{' (ya estaba)' if r.ya_existia else ''}: {detalle}")
    print(f"      por qué: {por_que}")
    if r.advertencias:
        print(f"      avisos: {'; '.join(r.advertencias)}")
    if r.obra and r.obra.caja_obra and numero(cambios.get("tc")) > 1:
        print(f"      la caja descuenta US$ {numero(campos.get('importe')) / numero(cambios['tc']):,.2f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true", help="escribir en los libros reales (sin esto, simulacro)")
    ap.add_argument("--tc-m000005", type=float, metavar="TC",
                    help="el tipo de cambio de M-000005 (U$S 400 del 3/10), confirmado por Valen")
    ap.add_argument("--con-ingreso-usd", action="store_true",
                    help="cargar también el ingreso de USD 20.000 del 28/09 (solo si Gabriel lo confirmó)")
    return asyncio.run(correr(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
