"""La línea semanal de gastos personales (CONTEXTO-FACHADO.md §5.14).

Lo personal vive en «FACHADO — Personal». Para cerrar la caja del estudio, una vez por semana
se escribe en el libro del estudio **una fila por cuenta** («Gastos personales · semana
2026-W39») que resume todos los egresos personales de esa semana: el estudio ve cuánto salió,
no en qué.

Reglas:

- **Idempotente por semana y cuenta.** Lo ya cerrado se calcula sumando las filas de cierre
  que ya existen; correrlo dos veces no escribe nada nuevo.
- **Cargas atrasadas.** Si entra un personal con fecha de una semana ya cerrada, la próxima
  corrida escribe una fila de **ajuste** por la diferencia. Nunca se edita una fila anterior:
  el libro es append-only. Por eso cada corrida revisa todas las semanas hasta la pedida, no
  solo la última: también recupera una semana que el cron se haya salteado.
- **No concilia contra el banco** (`concilia = FALSO`): el banco se cruza contra las filas del
  libro personal, una por una. Si conciliara la línea resumen, se contaría dos veces.

Comparte el lock del id_mov con /confirmar: los dos sacan números del mismo libro.
"""
import asyncio
import re
from datetime import date, datetime, timedelta, timezone

from app import maestros
from app.confirmar import _lock, _siguiente_id
from app.config import settings
from app.filtros import ORIGEN_CIERRE, es_cierre_semanal
from app.libro import Libro
from app.maestros import numero
from app.saldos import como_dicts

RE_CLAVE = re.compile(r"^cierre:(\d{4}-W\d{2}):(.+)#(\d+)$")
CARGADO_POR = "Cierre semanal"


def _hoy_local() -> datetime:
    return datetime.now(timezone(timedelta(hours=settings().utc_offset_horas)))


def semana_de(f: date) -> str:
    anio, semana, _ = f.isocalendar()
    return f"{anio}-W{semana:02d}"


def semana_anterior() -> str:
    return semana_de(_hoy_local().date() - timedelta(days=7))


def domingo_de(semana: str) -> date:
    anio, num = semana.split("-W")
    return date.fromisocalendar(int(anio), int(num), 7)


def _fecha(valor) -> date | None:
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


async def cierre_semanal(libro: Libro, libro_personal: Libro, semana: str | None = None) -> dict:
    semana = semana or semana_anterior()
    if not re.fullmatch(r"\d{4}-W\d{2}", semana):
        raise ValueError(f"Semana «{semana}» inválida: se espera AAAA-Www, por ejemplo 2026-W39")
    m = await asyncio.to_thread(maestros.cargar)
    advertencias: list[str] = []

    async with _lock:
        personales = como_dicts(await asyncio.to_thread(libro_personal.leer_movimientos))
        filas = await asyncio.to_thread(libro.leer_movimientos)
        encabezado = [str(x) for x in filas[0]]
        movs = como_dicts(filas)

        # Lo personal de cada semana, por cuenta. Solo egresos, y solo de semanas ya terminadas.
        gastado: dict[tuple[str, str], list[float]] = {}
        for mov in personales:
            f = _fecha(mov.get("fecha"))
            if mov.get("tipo") != "EGRESO" or f is None or semana_de(f) > semana:
                continue
            cuenta = m.cuenta(mov.get("cuenta"), incluir_inactivas=True)
            if cuenta is None or not cuenta.suma_al_saldo_del_estudio:
                advertencias.append(f"{mov.get('id_mov')}: la cuenta «{mov.get('cuenta')}» no es del estudio; "
                                    f"no entra en el cierre")
                continue
            acum = gastado.setdefault((semana_de(f), cuenta.nombre), [0.0, 0.0])
            acum[0] += numero(mov.get("importe"))
            acum[1] += numero(mov.get("importe_ars"))

        # Lo ya cerrado, por semana y cuenta, sumando las filas de cierre existentes.
        cerrado: dict[tuple[str, str], tuple[float, int]] = {}
        for mov in movs:
            mt = RE_CLAVE.match(str(mov.get("msg_id") or "")) if es_cierre_semanal(mov) else None
            if not mt:
                continue
            clave = (mt.group(1), mt.group(2))
            signo = 1 if mov.get("tipo") == "EGRESO" else -1
            total, n = cerrado.get(clave, (0.0, 0))
            cerrado[clave] = (total + signo * numero(mov.get("importe")), n + 1)

        escritas = []
        for clave in sorted(set(gastado) | set(cerrado)):
            sem, nombre_cuenta = clave
            importe, importe_ars = gastado.get(clave, [0.0, 0.0])
            ya, n = cerrado.get(clave, (0.0, 0))
            diferencia = round(importe - ya, 2)
            if abs(diferencia) < 0.01:
                continue
            cuenta = m.cuenta(nombre_cuenta, incluir_inactivas=True)
            tc = round(importe_ars / importe, 6) if cuenta.moneda != "ARS" and importe else 1
            ajuste = n > 0
            fila = {
                "id_mov": _siguiente_id(movs, "M"),
                "fecha": domingo_de(sem).isoformat(),
                "tipo": "EGRESO" if diferencia > 0 else "INGRESO",   # un ajuste a la baja devuelve
                "importe": abs(diferencia),
                "moneda": cuenta.moneda,
                "tc": tc,
                "importe_ars": round(abs(diferencia) * tc, 2),
                "cuenta": cuenta.nombre,
                "descripcion": f"Gastos personales · semana {sem}" + (" · ajuste por carga atrasada" if ajuste else ""),
                "origen": ORIGEN_CIERRE,
                "concilia": "FALSO",
                "estado_conc": "SOLO_CAJA",
                "tipo_gasto": "personal",
                "cargado_por": CARGADO_POR,
                "ts": _hoy_local().strftime("%Y-%m-%d %H:%M"),
                "msg_id": f"cierre:{sem}:{cuenta.nombre}#{n}",
            }
            numero_fila = len(filas) + 1
            valores = [fila.get(col, "") for col in encabezado]
            await asyncio.to_thread(libro.escribir_fila, numero_fila, valores)
            filas.append(valores)
            movs.append(fila)
            escritas.append({"id_mov": fila["id_mov"], "semana": sem, "cuenta": cuenta.nombre, "tipo": fila["tipo"],
                             "importe": fila["importe"], "ajuste": ajuste, "fila": numero_fila})

    return {"semana": semana, "escritas": escritas,
            "cuentas": sorted({c for _, c in gastado}), "advertencias": advertencias}
