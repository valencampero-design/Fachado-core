"""Saldos derivados del libro. El saldo no se guarda: se calcula (CONTEXTO-FACHADO.md §5.1).

Dos reglas que no se pueden romper (§5.8 y §5.9):

- **El saldo de caja del estudio solo suma las cuentas del estudio.** Las cajas de obra son
  plata del comitente en poder del arquitecto y «Pagado por el comitente» es plata que nunca
  pasó por el estudio. Las dos quedan afuera: sumarlas infla el saldo con plata ajena.
- **El saldo de una obra solo cuenta la plata del estudio.** Lo que el comitente pagó directo
  se informa aparte. Si se restara, Lennon aparecería con −$22 millones, como si el estudio
  estuviera financiando la obra, y es falso.
"""
from app.maestros import Maestros, normalizar, numero
from app.models import CajaObra, SaldoObra

TIPOS_QUE_MUEVEN_SALDO = ("INGRESO", "EGRESO")


def como_dicts(filas: list[list]) -> list[dict]:
    """Las filas de MOVIMIENTOS (la primera es el encabezado) como dicts por columna."""
    if not filas:
        return []
    encabezado = [str(c) for c in filas[0]]
    return [{c: (f[i] if i < len(f) else "") for i, c in enumerate(encabezado)} for f in filas[1:] if any(f)]


def _signo(mov: dict) -> int:
    return 1 if mov.get("tipo") == "INGRESO" else -1


def saldo_estudio(movs: list[dict], m: Maestros) -> dict:
    """Saldo por cuenta del estudio y total. Nunca incluye `caja_obra` ni `externa`."""
    por_cuenta = {c.nombre: c.saldo_apertura for c in m.cuentas_del_estudio()}
    claves = {normalizar(n): n for n in por_cuenta}
    for mov in movs:
        nombre = claves.get(normalizar(mov.get("cuenta")))
        if nombre and mov.get("tipo") in TIPOS_QUE_MUEVEN_SALDO:
            por_cuenta[nombre] += _signo(mov) * numero(mov.get("importe_ars"))
    return {"por_cuenta": por_cuenta, "total": round(sum(por_cuenta.values()), 2)}


def saldo_obra(movs: list[dict], obra: str, m: Maestros) -> tuple[SaldoObra, list[str]]:
    """Los tres números de la obra, más la caja de obra si tiene movimientos.
    Devuelve también advertencias por movimientos con una cuenta que no está en CUENTAS."""
    adelantado = pagado_estudio = pagado_comitente = caja_in = caja_out = 0.0
    hay_caja = False
    advertencias: list[str] = []
    n_obra = normalizar(obra)
    for mov in movs:
        if normalizar(mov.get("obra")) != n_obra:
            continue
        importe = numero(mov.get("importe_ars"))
        if mov.get("tipo") == "PASANTE":
            # §5.17: una sola fila que suma a lo adelantado y a lo pagado de la obra. No toca
            # ninguna cuenta del estudio, así que el saldo de la obra no se mueve.
            adelantado += importe
            pagado_estudio += importe
            continue
        if mov.get("tipo") not in TIPOS_QUE_MUEVEN_SALDO:
            continue
        cuenta = m.cuenta(mov.get("cuenta"), incluir_inactivas=True)
        if cuenta is None:
            advertencias.append(f"{mov.get('id_mov')}: la cuenta «{mov.get('cuenta')}» no está en CUENTAS; "
                                f"no entra en el saldo de {obra}")
        elif cuenta.tipo == "caja_obra":
            hay_caja = True
            if mov["tipo"] == "INGRESO":
                caja_in += importe
            else:
                caja_out += importe
        elif cuenta.tipo == "externa":
            if mov["tipo"] == "EGRESO":
                pagado_comitente += importe
        elif mov["tipo"] == "INGRESO":
            adelantado += importe
        else:
            pagado_estudio += importe

    saldo = SaldoObra(
        nombre=obra,
        adelantado=round(adelantado, 2),
        pagado_con_plata_del_estudio=round(pagado_estudio, 2),
        pagado_por_el_comitente=round(pagado_comitente, 2),
        saldo=round(adelantado - pagado_estudio, 2),
        caja_obra=CajaObra(ingresado=round(caja_in, 2), pagado=round(caja_out, 2),
                           por_rendir=round(caja_in - caja_out, 2)) if hay_caja else None,
    )
    return saldo, advertencias
