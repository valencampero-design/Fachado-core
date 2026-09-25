"""fachado-core: el motor de imputación de Fachado.

API HTTP sin estado. No sabe nada de WhatsApp: el gateway conversa, el motor interpreta y,
cuando un usuario confirma, escribe. `/interpretar` nunca escribe: esa separación es lo que
permite probar el parser sin ensuciar el libro.
"""
import hmac
import logging

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from app import maestros
from app.archivo import Archivador, ArchivadorDrive
from app.cierre import cierre_semanal
from app.config import settings
from app.confirmar import ErrorConfirmar, confirmar
from app.interpretar import interpretar
from app.libro import Libro, LibroSheets
from app.models import ConfirmarIn, ConfirmarOut, InterpretarIn, InterpretarOut

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="fachado-core", version="0.1.0")


def verificar_api_key(x_api_key: str | None = Header(default=None)) -> None:
    esperada = settings().motor_api_key
    if not esperada:
        raise HTTPException(status_code=503, detail="MOTOR_API_KEY no está configurada")
    if not x_api_key or not hmac.compare_digest(x_api_key, esperada):
        raise HTTPException(status_code=401, detail="X-API-Key inválida")


# ─── Dependencias: los tests las reemplazan por libros en memoria ─────────────

# Uno solo por proceso: el archivador recuerda la carpeta raíz de Drive.
_archivador = ArchivadorDrive()


def obtener_libro() -> Libro:
    return LibroSheets()


def obtener_libro_personal() -> Libro | None:
    """None mientras no exista «FACHADO — Personal» (§5.14)."""
    sid = settings().personal_sheet_id
    return LibroSheets(sid) if sid else None


def obtener_archivador() -> Archivador:
    return _archivador


@app.get("/salud")
def salud() -> dict:
    return {"ok": True}


@app.post("/interpretar", response_model=InterpretarOut, dependencies=[Depends(verificar_api_key)])
def post_interpretar(req: InterpretarIn, libro: Libro = Depends(obtener_libro),
                     libro_personal: Libro | None = Depends(obtener_libro_personal)) -> InterpretarOut:
    # `def` y no `async def`: Sheets, Drive y Anthropic son bloqueantes y FastAPI corre
    # los endpoints síncronos en un threadpool. Los libros solo se leen, para duplicados.
    return interpretar(req, libros={"estudio": libro, "personal": libro_personal})


@app.post("/maestros/recargar", dependencies=[Depends(verificar_api_key)])
def post_recargar_maestros() -> dict:
    """Fuerza la relectura del Sheet (por ejemplo, después de cargar un alias nuevo)."""
    m = maestros.cargar(forzar=True)
    return {"obras": len(m.obras), "contratistas": len(m.contratistas), "rubros": len(m.rubros),
            "cuentas": len(m.cuentas), "alias": len(m.alias), "usuarios": len(m.usuarios),
            "advertencias": m.advertencias}


@app.post("/confirmar", response_model=ConfirmarOut, dependencies=[Depends(verificar_api_key)])
async def post_confirmar(req: ConfirmarIn, libro: Libro = Depends(obtener_libro),
                         libro_personal: Libro | None = Depends(obtener_libro_personal),
                         archivador: Archivador = Depends(obtener_archivador)) -> ConfirmarOut:
    # `async def`: el lock del id_mov es un asyncio.Lock. Todo lo bloqueante (Sheets, Drive)
    # corre en threads adentro de `confirmar`.
    try:
        return await confirmar(req, libro, archivador, libro_personal)
    except ErrorConfirmar as e:
        raise HTTPException(status_code=e.status, detail={"campo": e.campo, "detalle": e.detalle})


class CierreIn(BaseModel):
    semana: str | None = None  # AAAA-Www; por defecto, la semana anterior


@app.post("/cierre-semanal", dependencies=[Depends(verificar_api_key)])
async def post_cierre_semanal(req: CierreIn | None = None, libro: Libro = Depends(obtener_libro),
                              libro_personal: Libro | None = Depends(obtener_libro_personal)) -> dict:
    """La línea semanal de gastos personales (§5.14). La dispara un cron de Railway los lunes
    a las 8 (scripts/cierre_semanal.py); también se puede llamar a mano. Es idempotente."""
    if libro_personal is None:
        raise HTTPException(status_code=503, detail="El libro personal no está configurado (FACHADO_PERSONAL_SHEET_ID)")
    try:
        return await cierre_semanal(libro, libro_personal, (req.semana if req else None))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ─── Pendientes ────────────────────────────────────────────────────────────────
# POST /consultar   saldos y cuentas corrientes por obra (app/saldos.py ya los calcula).
# POST /conciliar   cruce BANCO_RAW ↔ MOVIMIENTOS.


@app.post("/consultar", dependencies=[Depends(verificar_api_key)], status_code=501)
def post_consultar() -> dict:
    raise HTTPException(status_code=501, detail="Todavía no implementado")
