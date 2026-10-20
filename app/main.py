"""fachado-core: el motor de imputación de Fachado.

API HTTP sin estado. No sabe nada de WhatsApp: el gateway conversa, el motor interpreta y,
cuando un usuario confirma, escribe. `/interpretar` nunca escribe: esa separación es lo que
permite probar el parser sin ensuciar el libro.
"""
import hmac
import logging

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from app import conciliar, maestros, vistas
from app.anular import anular, movimiento
from app.archivo import Archivador, ArchivadorDrive
from app.cierre import cierre_semanal
from app.config import settings
from app.confirmar import ErrorConfirmar, confirmar
from app.consultas import ErrorConsulta, consultar
from app.interpretar import interpretar
from app.libro import Libro, LibroSheets
from app.models import (Adjunto, AnularIn, AnularOut, ConfirmarIn, ConfirmarOut, ConsultarIn, ConsultarOut, InterpretarIn,
                        InterpretarOut, MovimientoOut)

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
        raise _http(e)


def _http(e: ErrorConfirmar) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"campo": e.campo, "detalle": e.detalle, **e.datos})


@app.get("/movimientos/{id_mov}", response_model=MovimientoOut, dependencies=[Depends(verificar_api_key)])
def get_movimiento(id_mov: str, telefono: str, libro: Libro = Depends(obtener_libro),
                   libro_personal: Libro | None = Depends(obtener_libro_personal)) -> MovimientoOut:
    """Una fila del libro, para mostrarla antes de corregirla (§5.19). 404 si no existe; 403
    si es personal y quien pregunta no tiene `ve_personal`."""
    try:
        return movimiento(id_mov, telefono, libro, libro_personal)
    except ErrorConfirmar as e:
        raise _http(e)


@app.post("/anular", response_model=AnularOut, dependencies=[Depends(verificar_api_key)])
async def post_anular(req: AnularIn, libro: Libro = Depends(obtener_libro),
                      libro_personal: Libro | None = Depends(obtener_libro_personal)) -> AnularOut:
    """El contraasiento de §5.19. 409 si ya estaba anulado (el detalle trae la anulación)."""
    try:
        return await anular(req, libro, libro_personal)
    except ErrorConfirmar as e:
        raise _http(e)


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
        salida = await cierre_semanal(libro, libro_personal, (req.semana if req else None))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # §5.20: el resumen del banco también el lunes. Si falla, el cierre ya quedó hecho.
    try:
        salida["resumen_banco"] = conciliar.resumen_banco(libro, libro_personal)
    except Exception as e:  # noqa: BLE001
        logging.getLogger(__name__).exception("No se pudo armar el resumen del banco")
        salida["resumen_banco"] = None
        salida.setdefault("advertencias", []).append(f"Sin resumen del banco ({type(e).__name__})")
    return salida


@app.post("/consultar", response_model=ConsultarOut, dependencies=[Depends(verificar_api_key)])
def post_consultar(req: ConsultarIn, libro: Libro = Depends(obtener_libro),
                   libro_personal: Libro | None = Depends(obtener_libro_personal)) -> ConsultarOut:
    """Las tres preguntas del arquitecto: pagos a un contratista, gasto por obra y rubro,
    certificaciones cobradas y pendientes. Solo lee; lo personal, según `ve_personal`."""
    try:
        return consultar(req, libro, libro_personal)
    except ErrorConsulta as e:
        raise HTTPException(status_code=e.status, detail=e.detalle)


# ─── Conciliación con el banco (§5.20, contratos en §3 del handoff del 15/10) ───

class ConciliarExtractoIn(BaseModel):
    telefono: str
    adjunto: Adjunto


class ConciliarLoteIn(BaseModel):
    telefono: str
    tipo: str  # gastos_bancarios | meli_personal | asignar | ignorar
    hash_ids: list[str]
    id_mov: str | None = None  # solo con «asignar»


def obtener_descargador():
    """Baja el extracto de Drive. Los tests lo reemplazan por un archivo local."""
    return conciliar.leer_desde_drive


def _http_conciliar(e: conciliar.ErrorConciliar) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"campo": e.campo, "detalle": e.detalle})


@app.post("/conciliar/extracto", dependencies=[Depends(verificar_api_key)])
def post_conciliar_extracto(req: ConciliarExtractoIn, libro: Libro = Depends(obtener_libro),
                            libro_personal: Libro | None = Depends(obtener_libro_personal),
                            descargar=Depends(obtener_descargador)) -> dict:
    """Importa el extracto (idempotente por línea), concilia y devuelve el resumen y lo
    pendiente: lotes, ambiguas y una ficha por línea sin cargar. 422 si no es un extracto."""
    try:
        contenido = descargar(req.adjunto)
        return conciliar.procesar_extracto(contenido, req.telefono, libro, libro_personal)
    except conciliar.ErrorConciliar as e:
        raise _http_conciliar(e)


@app.get("/conciliar/pendientes", dependencies=[Depends(verificar_api_key)])
def get_conciliar_pendientes(telefono: str, libro: Libro = Depends(obtener_libro),
                             libro_personal: Libro | None = Depends(obtener_libro_personal)) -> dict:
    """Lo que sigue abierto del banco, con la misma forma que /conciliar/extracto."""
    try:
        return conciliar.pendientes(telefono, libro, libro_personal)
    except conciliar.ErrorConciliar as e:
        raise _http_conciliar(e)


@app.post("/conciliar/lote", dependencies=[Depends(verificar_api_key)])
async def post_conciliar_lote(req: ConciliarLoteIn, libro: Libro = Depends(obtener_libro),
                              libro_personal: Libro | None = Depends(obtener_libro_personal),
                              archivador: Archivador = Depends(obtener_archivador)) -> dict:
    """Confirma un lote (gastos bancarios, MeLi personal), asigna una ambigua a su movimiento
    o ignora líneas. Cada línea cargada usa /confirmar con msg_id «banco:<hash_id>»."""
    try:
        return await conciliar.lote(req.telefono, req.tipo, req.hash_ids, req.id_mov, libro, libro_personal, archivador)
    except conciliar.ErrorConciliar as e:
        raise _http_conciliar(e)


# ─── Vistas del tablero (§5.21) ────────────────────────────────────────────────

@app.post("/vistas/recalcular", dependencies=[Depends(verificar_api_key)])
def post_vistas_recalcular(libro: Libro = Depends(obtener_libro),
                           libro_personal: Libro | None = Depends(obtener_libro_personal)) -> dict:
    """Reescribe las hojas derivadas del tablero (VISTA_* y la CC_<OBRA> de cada obra en el
    Master; VISTA_PERSONAL, VISTA_DETALLE y las CC_ de los inmuebles en el libro personal). Nunca
    toca MOVIMIENTOS. Lo dispara un cron cada noche (scripts/recalcular_vistas.py)."""
    return vistas.recalcular(libro, libro_personal)
