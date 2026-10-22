"""Seguridad del motor: la clave del gateway y los crons (incidente Railway, 22/10/2026).

Ver docs/seguridad/ en este repo y docs/seguridad/rotacion-2026-10-22.md en chatbot-contable.
"""
import hmac
import logging
import os

logger = logging.getLogger(__name__)


# ── La clave del gateway y los crons ──────────────────────────────────────────

def clave_que_coincide(recibida: str | None) -> str | None:
    """"actual" si `recibida` es MOTOR_API_KEY, "anterior" si es MOTOR_API_KEY_ANTERIOR, si no None.

    MOTOR_API_KEY_ANTERIOR existe solo durante una rotación: motor con las dos → gateway y crons
    con la nueva → sacar la anterior. Las dos comparaciones corren siempre (sin cortocircuito).
    """
    if not recibida:
        return None
    resultado = None
    for nombre, var in (("anterior", "MOTOR_API_KEY_ANTERIOR"), ("actual", "MOTOR_API_KEY")):
        esperada = os.getenv(var, "")
        if esperada and hmac.compare_digest(recibida.encode(), esperada.encode()):
            resultado = nombre
    return resultado
