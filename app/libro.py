"""El libro: MOVIMIENTOS, ALIAS y CERTIFICADOS en el Sheet maestro.

Es una interfaz chica a propósito. /confirmar solo necesita leer MOVIMIENTOS, escribir una
fila y agregar un alias; con eso, los tests usan un libro en memoria y **nunca escriben en
el libro real**, que es append-only y no se limpia.
"""
from typing import Protocol

from app import sheets
from app.config import settings
from app.maestros import normalizar

# Hasta qué columna se lee MOVIMIENTOS. Holgado: las columnas nuevas van siempre al final.
_RANGO_MOVIMIENTOS = "MOVIMIENTOS!A:AZ"
_RANGO_CERTIFICADOS = "CERTIFICADOS!A:Z"


class Libro(Protocol):
    def leer_movimientos(self) -> list[list]:
        """Todas las filas, la primera es el encabezado. Números como números."""
        ...

    def escribir_fila(self, numero: int, valores: list) -> None:
        """Escribe la fila `numero` completa (1 es el encabezado)."""
        ...

    def escribir_filas(self, numero: int, filas: list[list]) -> None:
        """Varias filas seguidas desde `numero`, en una sola escritura: las dos filas de un
        traspaso (§5.18) quedan las dos o ninguna."""
        ...

    def leer_alias(self) -> list[list]:
        ...

    def agregar_alias(self, fila: list) -> None:
        ...

    def leer_certificados(self) -> list[list]:
        """CERTIFICADOS (§5.11), la primera fila es el encabezado. Solo en el libro del estudio."""
        ...

    def reactivar_contratista(self, nombre: str) -> bool:
        """Pone `estado = activo` en CONTRATISTAS (§5.6). True si cambió algo. Es el maestro,
        no el libro: ahí sí se edita, y nada se borra."""
        ...

    def escribir_certificado(self, numero: int, valores: list) -> None:
        ...


class LibroSheets:
    """El Sheet maestro de verdad, con la service account."""

    def __init__(self, sheet_id: str | None = None):
        self.sheet_id = sheet_id or settings().sheet_id

    def leer_movimientos(self) -> list[list]:
        return sheets.leer_rango(self.sheet_id, _RANGO_MOVIMIENTOS)

    def escribir_fila(self, numero: int, valores: list) -> None:
        self.escribir_filas(numero, [valores])

    def escribir_filas(self, numero: int, filas: list[list]) -> None:
        ultima = sheets.columna_a_letra(max(len(f) for f in filas))
        sheets.escribir_rango(self.sheet_id, f"MOVIMIENTOS!A{numero}:{ultima}{numero + len(filas) - 1}", filas)

    def leer_alias(self) -> list[list]:
        return sheets.leer_rango(self.sheet_id, "ALIAS!A:C", formato="FORMATTED_VALUE")

    def agregar_alias(self, fila: list) -> None:
        sheets.agregar_filas(self.sheet_id, "ALIAS!A:C", [fila])

    def leer_certificados(self) -> list[list]:
        return sheets.leer_rango(self.sheet_id, _RANGO_CERTIFICADOS)

    def reactivar_contratista(self, nombre: str) -> bool:
        filas = sheets.leer_rango(self.sheet_id, "CONTRATISTAS!A:Z", formato="FORMATTED_VALUE")
        encabezado = [normalizar(x) for x in (filas[0] if filas else [])]
        if "contratista" not in encabezado or "estado" not in encabezado:
            raise ValueError("CONTRATISTAS no tiene las columnas «contratista» y «estado»")
        col, est = encabezado.index("contratista"), encabezado.index("estado")
        cambio = False
        # Todas las filas con ese nombre: CONTRATISTAS tiene repetidos que se fusionan al leer.
        for n, fila in enumerate(filas[1:], start=2):
            if len(fila) > col and normalizar(fila[col]) == normalizar(nombre) \
                    and normalizar(fila[est] if len(fila) > est else "") != "activo":
                sheets.escribir_rango(self.sheet_id, f"CONTRATISTAS!{sheets.columna_a_letra(est + 1)}{n}", [["activo"]])
                cambio = True
        return cambio

    def escribir_certificado(self, numero: int, valores: list) -> None:
        ultima = sheets.columna_a_letra(len(valores))
        sheets.escribir_rango(self.sheet_id, f"CERTIFICADOS!A{numero}:{ultima}{numero}", [valores])
