"""Qué necesita el libro para escribir una ficha. **Una sola lista** para /interpretar y
/confirmar (CONTEXTO-FACHADO.md §5.7, v1.7: «nunca se ofrece Confirmar con un dato
obligatorio vacío»).

En el arranque del 29/09 las dos listas vivían en lugares distintos: /interpretar marcaba
`cuenta` como faltante sin preguntarla y /confirmar la rechazaba con 422. Si hace falta un
campo nuevo, se agrega acá y los dos lo ven.

- /interpretar: todo lo que esta lista pide y la ficha no trae va a `faltantes`, y cada
  faltante tiene su pregunta (`interpretar._completar_preguntas`).
- /confirmar: el primero que falte es un 422 con ese `campo`.
"""
from app.maestros import Maestros, normalizar

# La pregunta que completa cada campo, cuando no es el campo mismo. `tipo_gasto` lo resuelve
# la cascada con la obra o la pregunta de clasificación; el rubro se pregunta entero.
# §5.12 v1.8: el rubro se deduce de quién cobró y de si es de obra o personal; con una de
# estas preguntas abiertas, el rubro se pregunta (si hace falta) después de la respuesta.
PREGUNTAS_QUE_DEFINEN_EL_RUBRO = {"contratista", "inactivo", "clasificacion"}

PREGUNTAS_QUE_LO_COMPLETAN: dict[str, set[str]] = {
    "tipo_gasto": {"tipo_gasto", "clasificacion", "obra"},
    "rubro_1": {"rubro"} | PREGUNTAS_QUE_DEFINEN_EL_RUBRO,
    "rubro_2": {"rubro"} | PREGUNTAS_QUE_DEFINEN_EL_RUBRO,
    "contratista": {"contratista", "inactivo"},
    "tc": {"tipo_cambio"},
    "etapa": {"etapa", "activar_etapa"},
}


def vacio(valor) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def obligatorios(campos: dict, m: Maestros) -> list[str]:
    """Los campos que la ficha tiene que traer, en el orden en que se piden."""
    tipo = str(campos.get("tipo") or "").upper()
    obra = m.obra(campos.get("obra")) if not vacio(campos.get("obra")) else None
    con_etapa = ["etapa"] if obra and m.etapas_en_curso(obra.nombre) else []

    if tipo == "CERTIFICADO":
        return ["obra", "numero", "fecha", "saldo_a_cobrar"] + con_etapa

    if tipo == "TRASPASO":
        req = ["fecha", "importe", "cuenta_origen", "cuenta_destino"]
        monedas = {c.moneda for c in (m.cuenta(campos.get("cuenta_origen")), m.cuenta(campos.get("cuenta_destino"))) if c}
        if monedas - {"ARS"} or str(campos.get("moneda") or "ARS").upper() != "ARS":
            req.append("tc")  # §5.7: dólares ↔ pesos, siempre con tipo de cambio
        return req

    tipo_gasto = normalizar(campos.get("tipo_gasto"))
    req = ["fecha", "tipo", "importe", "moneda", "cuenta", "tipo_gasto"]
    if tipo == "EGRESO":
        # El contratista, solo en lo de obra (§5.8: cuánto lleva cada contratista en la obra).
        # Un gasto de estructura (el IVA, el banco) o personal puede no tenerlo; /confirmar
        # nunca lo exigió ahí. Pregunta abierta en el handoff del 30/09.
        req += ([] if tipo_gasto == "personal" else ["obra"]) + (["contratista"] if tipo_gasto == "obra" else [])
        req += ["rubro_1", "rubro_2"]
    elif tipo == "INGRESO":
        req += ["obra"]
    elif tipo == "PASANTE":
        req += ["obra", "contratista"]
    if necesita_tc(campos, m):
        req.append("tc")
    return req + con_etapa


def necesita_tc(campos: dict, m: Maestros) -> bool:
    """§5.7 y §5.8 v1.8. Un movimiento en dólares lleva tipo de cambio, salvo que entre o salga
    de una caja de obra en dólares: esa caja se lleva en dólares y no se convierte. Un pago en
    pesos desde una cuenta en dólares también lo lleva: la cuenta descuenta importe / tc."""
    moneda = str(campos.get("moneda") or "ARS").upper()
    cuenta = m.cuenta(campos.get("cuenta")) if not vacio(campos.get("cuenta")) else None
    if cuenta is not None and cuenta.moneda != "ARS":
        return moneda != cuenta.moneda or cuenta.tipo != "caja_obra"
    return moneda != "ARS"


def faltantes(campos: dict, m: Maestros) -> list[str]:
    return [c for c in obligatorios(campos, m) if vacio(campos.get(c))]


def cubierto(campo: str, preguntas_campos: set[str]) -> bool:
    """¿Alguna pregunta de la ficha completa este campo?"""
    return bool(PREGUNTAS_QUE_LO_COMPLETAN.get(campo, {campo}) & preguntas_campos)


def sin_pregunta(respuesta: dict) -> list[tuple[int, str]]:
    """El invariante de §5.7, sobre una respuesta de /interpretar (como dict): los faltantes que
    ninguna pregunta de su ficha completa. Tiene que dar vacío siempre; lo usan los tests."""
    salida = []
    for i, ficha in enumerate(respuesta.get("fichas") or []):
        suyas = {p["campo"] for p in respuesta.get("preguntas") or [] if int(p.get("ficha", 0)) == i}
        salida += [(i, c) for c in ficha.get("faltantes") or [] if not cubierto(c, suyas)]
    return salida
