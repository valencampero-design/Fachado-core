"""Modelos Pydantic de entrada y salida del motor."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# Las columnas de MOVIMIENTOS que describe una ficha. La hoja real tiene además
# `cargado_por` y `ts`, que se completan al confirmar, no al interpretar.
# `tipo_gasto` (obra | estructura | personal) es un eje independiente del rubro: el rubro
# dice QUÉ se compró y `tipo_gasto` PARA QUIÉN fue. Lo decide la cascada, no el LLM.
COLUMNAS_MOVIMIENTOS: list[str] = [
    "id_mov", "fecha", "tipo", "importe", "moneda", "tc", "importe_ars", "obra", "item",
    "comitente", "contratista", "rubro_1", "rubro_2", "medio_pago", "cuenta", "pagado_por",
    "tipo_comprobante", "descripcion", "origen", "concilia", "id_banco", "estado_conc",
    "comprobante_url", "tipo_gasto",
    "etapa",            # §5.15: `Lennon1` es la etapa 1
    "informal",         # §5.17: «sí» en un depósito en negro; fuera del IVA y de la conciliación
    "ref_comprobante",  # §5.16: número de operación, de cheque o hash del archivo
]

# §5.11: la hoja CERTIFICADOS. Un certificado es un documento, no un gasto: no va a MOVIMIENTOS.
COLUMNAS_CERTIFICADOS: list[str] = [
    "obra", "etapa", "numero", "fecha", "saldo_a_cobrar", "fuente", "msg_id", "cargado_por", "comprobante_url",
]
# Lo que describe una ficha de tipo CERTIFICADO (`campos["tipo"] == "CERTIFICADO"`).
# §5.18: lo que describe una ficha de tipo TRASPASO. /confirmar la escribe como dos filas de
# MOVIMIENTOS vinculadas (columna `vinculo`), una por cuenta.
CAMPOS_FICHA_TRASPASO: list[str] = ["tipo", "fecha", "importe", "moneda", "tc", "importe_ars", "cuenta_origen",
                                    "cuenta_destino", "obra", "descripcion", "comprobante_url", "ref_comprobante"]
CAMPOS_FICHA_CERTIFICADO: list[str] = ["tipo", "obra", "etapa", "numero", "fecha", "saldo_a_cobrar", "fuente",
                                       "comprobante_url"]

# De dónde salió cada valor. El gateway lo muestra al lado del campo.
Origen = Literal["texto", "comprobante", "maestro", "inferido", "llm", "fecha_mensaje", "contexto_previo"]

Clasificacion = Literal["obra", "estructura", "personal"]


class Adjunto(BaseModel):
    url: str
    mime: str | None = None
    nombre: str | None = None  # nombre de archivo original, si el gateway lo tiene
    # El sha256 que WhatsApp manda en el payload del adjunto. Es la referencia más fuerte para
    # detectar que dos usuarios mandaron el mismo comprobante (§5.16). Si no viene, el motor lo
    # calcula cuando baja el archivo.
    sha256: str | None = None


class Respuesta(BaseModel):
    """La respuesta a una pregunta de la ficha (tanda 6.4). `valor` es una de las `opciones`
    que ofreció el motor, o texto libre si el usuario escribió otra cosa."""
    ficha: int = 0
    campo: str
    valor: str


class InterpretarIn(BaseModel):
    telefono: str | None = None
    texto: str = ""
    adjuntos: list[Adjunto] = Field(default_factory=list)
    fecha_mensaje: datetime | None = None
    contexto_previo: dict[str, Any] | None = None  # la ficha anterior (mismo formato que Ficha)
    # Se aplican sobre `contexto_previo`: el motor pone cada valor, vuelve a correr la cascada
    # y devuelve la ficha con las preguntas que sigan faltando.
    respuestas: list[Respuesta] = Field(default_factory=list)
    # N comprobantes con un solo texto (§5.12): el gateway llama una vez por comprobante con
    # el mismo texto y N. Con N > 1, importe y fecha salen del comprobante, no del texto.
    texto_compartido: int = Field(1, ge=1)


class Conflicto(BaseModel):
    campo: str
    valor_texto: Any = None
    valor_comprobante: Any = None
    detalle: str = ""


# Por qué se pregunta. `apodo_ambiguo` y `dual` son preguntas de diseño —el maestro dice
# que hay que preguntar—, no fallas del parser: el gateway puede mostrarlas distinto y la
# métrica del corpus las cuenta aparte.
MotivoPregunta = Literal["apodo_ambiguo", "dual", "conflicto", "falta_dato", "posible_duplicado", "inactivo"]


class Pregunta(BaseModel):
    campo: str
    texto: str
    opciones: list[str] = Field(default_factory=list)
    motivo: MotivoPregunta = "falta_dato"
    ficha: int = 0  # índice de la ficha a la que aplica


class PosibleDuplicado(BaseModel):
    """Un movimiento ya cargado que podría ser el mismo hecho (§5.16). Nunca se descarta solo:
    el usuario decide si es el mismo."""
    id_mov: str  # en un certificado, «Moreno etapa 1 · certificado 5» (la hoja no tiene id)
    cargado_por: str
    fecha: str
    importe: float
    fuerza: Literal["fuerte", "probable"]  # fuerte: misma referencia del comprobante
    libro: Literal["estudio", "personal", "certificados"]


class Ficha(BaseModel):
    campos: dict[str, Any]
    origen_campo: dict[str, str] = Field(default_factory=dict)
    faltantes: list[str] = Field(default_factory=list)
    conflictos: list[Conflicto] = Field(default_factory=list)
    confianza: float = 1.0
    # La regla de la cascada que decidió `campos["tipo_gasto"]`, para poder auditarla.
    regla: str | None = None
    # Datos que no tienen columna propia: certificado, fecha de pago del cheque,
    # número de operación, CUIT, alias propuesto, advertencias.
    extras: dict[str, Any] = Field(default_factory=dict)
    posible_duplicado: PosibleDuplicado | None = None
    # §5.12: el gateway obedece este campo. Mientras el usuario esté en período de prueba es
    # siempre true; después, false solo si el movimiento está completamente claro.
    requiere_confirmacion: bool = True


class AliasPropuesto(BaseModel):
    como_lo_dice: str = Field(min_length=1)
    valor_canonico: str = Field(min_length=1)
    tipo: str = "contratista"


class FichaConfirmada(BaseModel):
    """La ficha tal como salió de /interpretar, con lo que el usuario corrigió."""
    campos: dict[str, Any]
    extras: dict[str, Any] = Field(default_factory=dict)


class ConfirmarIn(BaseModel):
    msg_id: str = Field(min_length=1)  # wamid del mensaje que se confirma, no el del botón
    telefono: str = Field(min_length=1)
    ficha: FichaConfirmada
    # Un mensaje puede traer dos movimientos (dos fichas) con el mismo msg_id: el índice es
    # parte de la clave de idempotencia, o el segundo se tomaría por un reintento del primero.
    ficha_indice: int = Field(0, ge=0)
    alias_propuesto: AliasPropuesto | None = None


class CajaObra(BaseModel):
    ingresado: float
    pagado: float
    por_rendir: float  # si da negativo, el arquitecto puso plata propia (§5.8)


class SaldoObra(BaseModel):
    """El saldo de la obra solo cuenta la plata del estudio. Lo que pagó el comitente directo
    se informa aparte y no lo mueve: si no, Lennon parecería financiado por el estudio."""
    nombre: str
    adelantado: float
    pagado_con_plata_del_estudio: float
    pagado_por_el_comitente: float
    saldo: float
    caja_obra: CajaObra | None = None


class EstadoCertificado(BaseModel):
    """§5.11: un certificado como cuenta por cobrar."""
    obra: str
    etapa: str = ""
    numero: str
    fecha: str = ""
    saldo_a_cobrar: float
    cobrado: float
    pendiente: float
    cobros: list[str] = Field(default_factory=list)  # id_mov de los cobros que lo cancelan


class ConfirmarOut(BaseModel):
    id_mov: str  # en un certificado, «Moreno etapa 1 · certificado 5»
    fila: int
    # §5.18: en un traspaso, la segunda fila (la entrada en la cuenta de destino).
    id_mov_vinculado: str | None = None
    comprobante_url: str | None = None
    obra: SaldoObra | None = None
    # Al confirmar un certificado, o un cobro que nombra uno: cuánto queda por cobrar.
    certificado: EstadoCertificado | None = None
    alias_escrito: bool = False
    ya_existia: bool = False  # el msg_id ya estaba: se devuelve la fila que había
    libro: Literal["estudio", "personal", "certificados"] = "estudio"  # §5.14: dónde quedó escrito
    cargado_por: str
    advertencias: list[str] = Field(default_factory=list)


class MovimientoOut(BaseModel):
    """GET /movimientos/{id_mov}: una fila del libro, tal como está."""
    id_mov: str
    libro: Literal["estudio", "personal"]
    campos: dict[str, Any]
    anulado_por: str | None = None  # el id_mov del contraasiento, si lo anularon (§5.19)
    vinculado: str | None = None    # la otra fila de un traspaso (§5.18)


class AnularIn(BaseModel):
    telefono: str = Field(min_length=1)
    id_mov: str = Field(min_length=1)
    msg_id: str = Field(min_length=1)  # el wamid del mensaje que pide la corrección
    motivo: str = ""


class AnularOut(BaseModel):
    """§5.19: el contraasiento. La fila original no se toca."""
    id_mov_anulacion: str
    anula: str
    libro: Literal["estudio", "personal"]
    # Un traspaso se anula entero: el contraasiento de la otra fila y la fila que anula.
    id_mov_anulacion_vinculado: str | None = None
    anula_vinculado: str | None = None
    # Para que el gateway la mande como `contexto_previo` de la corrección.
    ficha_original: FichaConfirmada
    ya_existia: bool = False


class ConsultarIn(BaseModel):
    """Las tres preguntas del arquitecto (handoff del 25/09). `consulta`, `obra` y
    `contratista` pueden venir explícitos; si no, se sacan de `texto`."""
    telefono: str = Field(min_length=1)
    consulta: Literal["pagos", "gasto", "certificaciones"] | None = None
    texto: str = ""
    obra: str | None = None
    contratista: str | None = None


class ConsultarOut(BaseModel):
    consulta: Literal["pagos", "gasto", "certificaciones"] | None = None
    datos: dict[str, Any] = Field(default_factory=dict)
    texto: str  # listo para mandar por WhatsApp
    preguntas: list[Pregunta] = Field(default_factory=list)  # si falta algo para contestar
    advertencias: list[str] = Field(default_factory=list)


class InterpretarOut(BaseModel):
    # movimiento: hay fichas. consulta: el gateway llama a /consultar con el mismo texto.
    # otro: charla, una foto de obra; fichas y preguntas vacías, y el gateway responde el acuse
    # corto (§5.12). Ante la duda, movimiento.
    intencion: Literal["movimiento", "consulta", "otro"] = "movimiento"
    fichas: list[Ficha]
    preguntas: list[Pregunta] = Field(default_factory=list)
    requiere_confirmacion: bool = True  # true si alguna ficha lo requiere
    diagnostico: dict[str, Any] = Field(default_factory=dict)
