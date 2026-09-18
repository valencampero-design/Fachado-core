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
]

# De dónde salió cada valor. El gateway lo muestra al lado del campo.
Origen = Literal["texto", "comprobante", "maestro", "inferido", "llm", "fecha_mensaje", "contexto_previo"]

Clasificacion = Literal["obra", "estructura", "personal"]


class Adjunto(BaseModel):
    url: str
    mime: str | None = None
    nombre: str | None = None  # nombre de archivo original, si el gateway lo tiene


class InterpretarIn(BaseModel):
    telefono: str | None = None
    texto: str = ""
    adjuntos: list[Adjunto] = Field(default_factory=list)
    fecha_mensaje: datetime | None = None
    contexto_previo: dict[str, Any] | None = None  # la ficha anterior (mismo formato que Ficha)


class Conflicto(BaseModel):
    campo: str
    valor_texto: Any = None
    valor_comprobante: Any = None
    detalle: str = ""


# Por qué se pregunta. `apodo_ambiguo` y `dual` son preguntas de diseño —el maestro dice
# que hay que preguntar—, no fallas del parser: el gateway puede mostrarlas distinto y la
# métrica del corpus las cuenta aparte.
MotivoPregunta = Literal["apodo_ambiguo", "dual", "conflicto", "falta_dato"]


class Pregunta(BaseModel):
    campo: str
    texto: str
    opciones: list[str] = Field(default_factory=list)
    motivo: MotivoPregunta = "falta_dato"
    ficha: int = 0  # índice de la ficha a la que aplica


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


class InterpretarOut(BaseModel):
    fichas: list[Ficha]
    preguntas: list[Pregunta] = Field(default_factory=list)
    diagnostico: dict[str, Any] = Field(default_factory=dict)
