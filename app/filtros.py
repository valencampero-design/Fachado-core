"""Qué movimientos entran en cada cálculo que todavía no existe.

La posición de IVA y la conciliación bancaria no están construidas, pero lo que tienen que
excluir ya está decidido. Queda acá para que, cuando se escriban, no lo tengan que
redescubrir:

- **Los movimientos informales** (depósitos «en negro», §5.17) quedan fuera del IVA y de la
  conciliación.
- **La línea semanal de gastos personales** (§5.14) no concilia contra el banco: el banco se
  cruza contra las filas del libro personal, una por una. Si concilia la línea resumen, se
  cuenta dos veces.
"""
from app.maestros import normalizar

ORIGEN_CIERRE = "CIERRE"


def es_informal(mov: dict) -> bool:
    return normalizar(mov.get("informal")) in ("si", "true", "verdadero", "1", "x")


def es_cierre_semanal(mov: dict) -> bool:
    return str(mov.get("origen") or "").upper() == ORIGEN_CIERRE


def para_iva(movs: list[dict]) -> list[dict]:
    """Lo que puede entrar en la posición de IVA (§5.10): nunca un informal."""
    return [mov for mov in movs if not es_informal(mov)]


def para_conciliacion(movs: list[dict]) -> list[dict]:
    """Lo que se cruza contra el extracto: ni informales ni la línea semanal de personales."""
    return [mov for mov in movs if not es_informal(mov) and not es_cierre_semanal(mov)]
