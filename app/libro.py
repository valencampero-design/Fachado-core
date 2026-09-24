"""El libro: MOVIMIENTOS y ALIAS en el Sheet maestro.

Es una interfaz chica a propósito. /confirmar solo necesita leer MOVIMIENTOS, escribir una
fila y agregar un alias; con eso, los tests usan un libro en memoria y **nunca escriben en
el libro real**, que es append-only y no se limpia.
"""
from typing import Protocol

from app import sheets
from app.config import settings

# Hasta qué columna se lee MOVIMIENTOS. Holgado: las columnas nuevas van siempre al final.
_RANGO_MOVIMIENTOS = "MOVIMIENTOS!A:AZ"


class Libro(Protocol):
    def leer_movimientos(self) -> list[list]:
        """Todas las filas, la primera es el encabezado. Números como números."""
        ...

    def escribir_fila(self, numero: int, valores: list) -> None:
        """Escribe la fila `numero` completa (1 es el encabezado)."""
        ...

    def leer_alias(self) -> list[list]:
        ...

    def agregar_alias(self, fila: list) -> None:
        ...


class LibroSheets:
    """El Sheet maestro de verdad, con la service account."""

    def __init__(self, sheet_id: str | None = None):
        self.sheet_id = sheet_id or settings().sheet_id

    def leer_movimientos(self) -> list[list]:
        return sheets.leer_rango(self.sheet_id, _RANGO_MOVIMIENTOS)

    def escribir_fila(self, numero: int, valores: list) -> None:
        ultima = sheets.columna_a_letra(len(valores))
        sheets.escribir_rango(self.sheet_id, f"MOVIMIENTOS!A{numero}:{ultima}{numero}", [valores])

    def leer_alias(self) -> list[list]:
        return sheets.leer_rango(self.sheet_id, "ALIAS!A:C", formato="FORMATTED_VALUE")

    def agregar_alias(self, fila: list) -> None:
        sheets.agregar_filas(self.sheet_id, "ALIAS!A:C", [fila])
