"""El libro: MOVIMIENTOS, ALIAS, CERTIFICADOS y BANCO_RAW en el Sheet maestro.

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
_RANGO_BANCO = "BANCO_RAW!A:Z"


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

    def activar_etapa(self, obra: str, etapa: str) -> bool:
        """Pone `estado = en curso` en la fila de ETAPAS (§5.15). True si cambió algo."""
        ...

    def agregar_contratista(self, valores: dict) -> bool:
        """Da de alta un contratista nuevo en CONTRATISTAS (§5.6 v1.9), por nombre de columna.
        False si ya había uno con ese nombre: nunca se duplica."""
        ...

    def escribir_certificado(self, numero: int, valores: list) -> None:
        ...

    def leer_banco(self) -> list[list]:
        """BANCO_RAW (§5.20), la primera fila es el encabezado. Solo en el Master."""
        ...

    def agregar_banco(self, filas: list[list]) -> None:
        ...

    def actualizar_banco(self, cambios: list[tuple[int, dict]]) -> None:
        """(número de fila, {columna: valor}): cambia esas celdas de BANCO_RAW, por columna."""
        ...

    def marcar_conciliado(self, numero_fila: int, valores: dict) -> None:
        """§5.20: la única escritura sobre una fila ya escrita de MOVIMIENTOS. Solo `id_banco` y
        `estado_conc`, por columna: el hecho no cambia, cambia si ya se lo vio en el banco."""
        ...

    def escribir_hoja(self, hoja: str, filas: list[list]) -> None:
        """§5.21: reescribe una hoja derivada entera (VISTA_*, CC_*). Nunca MOVIMIENTOS."""
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

    def agregar_contratista(self, valores: dict) -> bool:
        filas = sheets.leer_rango(self.sheet_id, "CONTRATISTAS!A:Z", formato="FORMATTED_VALUE")
        encabezado = [str(x) for x in (filas[0] if filas else [])]
        claves = [normalizar(x) for x in encabezado]
        if "contratista" not in claves:
            raise ValueError("CONTRATISTAS no tiene la columna «contratista»")
        col = claves.index("contratista")
        if any(len(f) > col and normalizar(f[col]) == normalizar(valores.get("contratista")) for f in filas[1:]):
            return False
        fila = [str(valores.get(c, "")) for c in claves]
        sheets.agregar_filas(self.sheet_id, f"CONTRATISTAS!A:{sheets.columna_a_letra(len(fila))}", [fila])
        return True

    def activar_etapa(self, obra: str, etapa: str) -> bool:
        filas = sheets.leer_rango(self.sheet_id, "ETAPAS!A:Z", formato="FORMATTED_VALUE")
        encabezado = [normalizar(x) for x in (filas[0] if filas else [])]
        if not {"obra", "etapa", "estado"} <= set(encabezado):
            raise ValueError("ETAPAS no tiene las columnas «obra», «etapa» y «estado»")
        co, ce, cs = (encabezado.index(x) for x in ("obra", "etapa", "estado"))
        cambio = False
        for n, fila in enumerate(filas[1:], start=2):
            celda = lambda i: fila[i] if len(fila) > i else ""  # noqa: E731
            if normalizar(celda(co)) == normalizar(obra) and normalizar(celda(ce)) == normalizar(etapa) \
                    and normalizar(celda(cs)) != "en curso":
                sheets.escribir_rango(self.sheet_id, f"ETAPAS!{sheets.columna_a_letra(cs + 1)}{n}", [["en curso"]])
                cambio = True
        return cambio

    def escribir_certificado(self, numero: int, valores: list) -> None:
        ultima = sheets.columna_a_letra(len(valores))
        sheets.escribir_rango(self.sheet_id, f"CERTIFICADOS!A{numero}:{ultima}{numero}", [valores])

    # ── §5.20: BANCO_RAW y las columnas de control de MOVIMIENTOS ────────────────
    def leer_banco(self) -> list[list]:
        return sheets.leer_rango(self.sheet_id, _RANGO_BANCO, formato="FORMATTED_VALUE")

    def agregar_banco(self, filas: list[list]) -> None:
        if filas:
            sheets.agregar_filas(self.sheet_id, f"BANCO_RAW!A:{sheets.columna_a_letra(max(len(f) for f in filas))}", filas)

    def _escribir_celdas(self, hoja: str, encabezado: list, cambios: list[tuple[int, dict]]) -> None:
        nombres = [str(x) for x in encabezado]
        for numero, valores in cambios:
            for columna, valor in valores.items():
                if columna not in nombres:
                    raise ValueError(f"{hoja} no tiene la columna «{columna}»: correr scripts/preparar_sheet.py")
                letra = sheets.columna_a_letra(nombres.index(columna) + 1)
                sheets.escribir_rango(self.sheet_id, f"{hoja}!{letra}{numero}", [[valor]])

    def actualizar_banco(self, cambios: list[tuple[int, dict]]) -> None:
        encabezado = (sheets.leer_rango(self.sheet_id, "BANCO_RAW!1:1", formato="FORMATTED_VALUE") or [[]])[0]
        self._escribir_celdas("BANCO_RAW", encabezado, cambios)

    def marcar_conciliado(self, numero_fila: int, valores: dict) -> None:
        if set(valores) - {"id_banco", "estado_conc"}:
            raise ValueError("Conciliar solo escribe id_banco y estado_conc (§5.20)")
        encabezado = (sheets.leer_rango(self.sheet_id, "MOVIMIENTOS!1:1", formato="FORMATTED_VALUE") or [[]])[0]
        self._escribir_celdas("MOVIMIENTOS", encabezado, [(numero_fila, valores)])

    # ── §5.21: hojas derivadas (VISTA_*, CC_*), se reescriben enteras ────────────
    def escribir_hoja(self, hoja: str, filas: list[list]) -> None:
        sheets.reemplazar_hoja(self.sheet_id, hoja, filas)
