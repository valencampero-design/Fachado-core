"""fachado-core: el motor de imputación de Fachado.

API HTTP sin estado. No sabe nada de WhatsApp: el gateway conversa, el motor interpreta.
"""
import hmac
import logging

from fastapi import Depends, FastAPI, Header, HTTPException

from app import maestros
from app.config import settings
from app.interpretar import interpretar
from app.models import InterpretarIn, InterpretarOut

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="fachado-core", version="0.1.0")


def verificar_api_key(x_api_key: str | None = Header(default=None)) -> None:
    esperada = settings().motor_api_key
    if not esperada:
        raise HTTPException(status_code=503, detail="MOTOR_API_KEY no está configurada")
    if not x_api_key or not hmac.compare_digest(x_api_key, esperada):
        raise HTTPException(status_code=401, detail="X-API-Key inválida")


@app.get("/salud")
def salud() -> dict:
    return {"ok": True}


@app.post("/interpretar", response_model=InterpretarOut, dependencies=[Depends(verificar_api_key)])
def post_interpretar(req: InterpretarIn) -> InterpretarOut:
    # `def` y no `async def`: Sheets, Drive y Anthropic son bloqueantes y FastAPI corre
    # los endpoints síncronos en un threadpool.
    return interpretar(req)


@app.post("/maestros/recargar", dependencies=[Depends(verificar_api_key)])
def post_recargar_maestros() -> dict:
    """Fuerza la relectura del Sheet (por ejemplo, después de cargar un alias nuevo)."""
    m = maestros.cargar(forzar=True)
    return {"obras": len(m.obras), "contratistas": len(m.contratistas), "rubros": len(m.rubros),
            "cuentas": len(m.cuentas), "alias": len(m.alias), "advertencias": m.advertencias}


# ─── Pendientes (fase 2) ───────────────────────────────────────────────────────
# POST /confirmar   recibe la ficha confirmada por el usuario, asigna id_mov, appendea a
#                   MOVIMIENTOS, mueve el adjunto a la carpeta de la obra y, si hubo
#                   alias_propuesto confirmado, lo agrega a ALIAS.
# POST /consultar   saldos y cuentas corrientes por obra.
# POST /conciliar   cruce BANCO_RAW ↔ MOVIMIENTOS.

@app.post("/confirmar", dependencies=[Depends(verificar_api_key)], status_code=501)
def post_confirmar() -> dict:
    raise HTTPException(status_code=501, detail="Todavía no implementado")


@app.post("/consultar", dependencies=[Depends(verificar_api_key)], status_code=501)
def post_consultar() -> dict:
    raise HTTPException(status_code=501, detail="Todavía no implementado")
