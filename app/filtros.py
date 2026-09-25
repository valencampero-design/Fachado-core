"""Qué movimientos entran en cada cálculo.

La posición de IVA y la conciliación bancaria no están construidas, pero lo que tienen que
excluir ya está decidido. Queda acá para que, cuando se escriban, no lo tengan que
redescubrir:

- **Los movimientos informales** (depósitos «en negro», §5.17) quedan fuera del IVA y de la
  conciliación.
- **La línea semanal de gastos personales** (§5.14) no concilia contra el banco: el banco se
  cruza contra las filas del libro personal, una por una. Si concilia la línea resumen, se
  cuenta dos veces.
- **Un par anulado** (§5.19) —la fila original y su contraasiento— no entra en ningún cálculo
  derivado: saldos, consultas, duplicados, conciliación.
"""
from app.maestros import normalizar

ORIGEN_CIERRE = "CIERRE"
ORIGEN_ANULACION = "ANULACION"


def es_informal(mov: dict) -> bool:
    return normalizar(mov.get("informal")) in ("si", "true", "verdadero", "1", "x")


def es_cierre_semanal(mov: dict) -> bool:
    return str(mov.get("origen") or "").upper() == ORIGEN_CIERRE


def es_anulacion(mov: dict) -> bool:
    """El contraasiento de §5.19: lleva en `anula` el id_mov de la fila que anula."""
    return bool(str(mov.get("anula") or "").strip())


def sin_anulados(movs: list[dict]) -> list[dict]:
    """Sin los pares anulados: ni la fila original ni su contraasiento (§5.19). Como el
    contraasiento lleva el importe con signo contrario, las sumas darían igual con el par
    adentro; sacarlo hace que tampoco cuente en cantidades («cuántos pagos a X») ni en los
    cruces (duplicados, conciliación, cobros de certificados)."""
    anulados = {str(mov.get("anula")).strip() for mov in movs if es_anulacion(mov)}
    return [mov for mov in movs if not es_anulacion(mov) and str(mov.get("id_mov") or "") not in anulados]


def para_iva(movs: list[dict]) -> list[dict]:
    """Lo que puede entrar en la posición de IVA (§5.10): nunca un informal ni un anulado."""
    return [mov for mov in sin_anulados(movs) if not es_informal(mov)]


def para_conciliacion(movs: list[dict]) -> list[dict]:
    """Lo que se cruza contra el extracto: ni informales, ni la línea semanal de personales,
    ni el par original + contraasiento (§5.19: se concilia la fila correcta)."""
    return [mov for mov in sin_anulados(movs) if not es_informal(mov) and not es_cierre_semanal(mov)]
