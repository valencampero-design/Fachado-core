"""El mismo hecho cargado dos veces (CONTEXTO-FACHADO.md §5.16).

Con dos usuarios, el mismo pago puede llegar por Gabriel y por Petrus. Es distinto de la
idempotencia por `msg_id`, que evita escribir dos veces el mismo *mensaje*: acá son dos
mensajes distintos que describen el mismo hecho.

| Fuerza    | Criterio |
|-----------|----------|
| fuerte    | Comparten una referencia del comprobante: número de operación, de cheque o sha256 |
| probable  | Mismo importe, fecha a ±3 días, y mismo contratista o misma obra |

**Nunca se descarta solo**, ni con coincidencia fuerte: se avisa y se pregunta. Hay pagos
distintos que coinciden en todo menos en la referencia (el cheque 510 y la transferencia a
Eco Aislación, confirmados como dos pagos por el arquitecto).
"""
from datetime import date

from app.filtros import es_cierre_semanal, sin_anulados
from app.maestros import normalizar, numero
from app.models import PosibleDuplicado

DIAS_DE_TOLERANCIA = 3
SEPARADOR_REFS = " | "


def referencias(valor) -> set[str]:
    """`ref_comprobante` guarda varias referencias separadas: «op:X | sha256:Y»."""
    return {r.strip().lower() for r in str(valor or "").split("|") if r.strip()}


def _fecha(valor) -> date | None:
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def buscar(campos: dict, libros: dict[str, list[dict]]) -> PosibleDuplicado | None:
    """El movimiento ya cargado que más se parece, o None. `libros` es {nombre: movimientos}
    y ya viene filtrado por lo que el usuario puede ver: el personal solo con `ve_personal`."""
    refs = referencias(campos.get("ref_comprobante"))
    importe = numero(campos.get("importe")) if campos.get("importe") not in (None, "") else None
    fecha = _fecha(campos.get("fecha"))
    contratista, obra = normalizar(campos.get("contratista")), normalizar(campos.get("obra"))
    # §5.18: un traspaso solo se compara con traspasos, por cuenta; un gasto nunca con la fila
    # de un traspaso (reponer la caja de Lennon no es pagarle a nadie en Lennon).
    es_traspaso = campos.get("tipo") == "TRASPASO"
    cuentas = {normalizar(campos.get("cuenta_origen")), normalizar(campos.get("cuenta_destino"))} - {""}

    candidatos: list[tuple[int, int, PosibleDuplicado]] = []
    for libro, movs in libros.items():
        for mov in sin_anulados(movs):
            if not mov.get("id_mov") or es_cierre_semanal(mov) or (mov.get("tipo") == "TRASPASO") != es_traspaso:
                continue
            fuerte = bool(refs & referencias(mov.get("ref_comprobante")))
            probable = False
            if not fuerte and importe is not None and fecha:
                f_mov = _fecha(mov.get("fecha"))
                parecido = normalizar(mov.get("cuenta")) in cuentas if es_traspaso else (
                    (contratista and normalizar(mov.get("contratista")) == contratista)
                    or (obra and normalizar(mov.get("obra")) == obra))
                probable = (
                    f_mov is not None
                    and abs(abs(numero(mov.get("importe"))) - importe) < 0.01
                    and abs((f_mov - fecha).days) <= DIAS_DE_TOLERANCIA
                    and bool(parecido)
                )
            if not (fuerte or probable):
                continue
            f_mov = _fecha(mov.get("fecha"))
            distancia = abs((f_mov - fecha).days) if f_mov and fecha else 999
            candidatos.append((0 if fuerte else 1, distancia, PosibleDuplicado(
                id_mov=str(mov["id_mov"]), cargado_por=str(mov.get("cargado_por") or "alguien"),
                fecha=str(mov.get("fecha") or ""), importe=numero(mov.get("importe")),
                fuerza="fuerte" if fuerte else "probable", libro=libro)))
    return min(candidatos, key=lambda c: (c[0], c[1]))[2] if candidatos else None


def texto_pregunta(dup: PosibleDuplicado, tipo: str, quien_pregunta: str | None) -> str:
    """«Petrus ya cargó un pago igual el 23/9. ¿Es el mismo?»"""
    f = _fecha(dup.fecha)
    if tipo == "CERTIFICADO":
        yo = quien_pregunta and normalizar(quien_pregunta) == normalizar(dup.cargado_por)
        return f"{'Ya cargaste' if yo else dup.cargado_por + ' ya cargó'} ese certificado ({dup.id_mov}). ¿Es el mismo?"
    cuando = f"el {f.day}/{f.month}" if f else ""
    que = "un cobro igual" if tipo == "INGRESO" else "un pago igual"
    if quien_pregunta and normalizar(quien_pregunta) == normalizar(dup.cargado_por):
        return f"Ya cargaste {que} {cuando} ({dup.id_mov}). ¿Es el mismo?"
    return f"{dup.cargado_por} ya cargó {que} {cuando} ({dup.id_mov}). ¿Es el mismo?"
