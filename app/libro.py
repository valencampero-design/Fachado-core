"""El libro: MOVIMIENTOS, ALIAS y CERTIFICADOS en el Sheet maestro.

Es una interfaz chica a propósito. /confirmar solo necesita leer MOVIMIENTOS, escribir una
fila y agregar un alias; con eso, los tests usan un libro en memoria y **nunca escriben en
el libro real**, que es append-only y no se limpia.
"""
from typing import Protocol

from app import sheets
from app.config import settings

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

    def escribir_certificado(self, numero: int, valores: list) -> None:
        ultima = sheets.columna_a_letra(len(valores))
        sheets.escribir_rango(self.sheet_id, f"CERTIFICADOS!A{numero}:{ultima}{numero}", [valores])
