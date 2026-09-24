"""Dónde queda cada comprobante una vez confirmado.

    comprobantes/<obra>/<AAAA-MM>/<id_mov> <contratista> <importe>.<ext>

- **El nombre empieza con el `id_mov`**: desde la fila se llega al archivo y al revés, sin
  depender del link.
- **Subcarpeta por mes**, para que no se junten mil archivos en un directorio.
- **Personal** va a `personal/<AAAA-MM>/`; **sin obra** va a `_sin-imputar/<AAAA-MM>/`.
  Nunca se pierde un comprobante por una duda de imputación.

Mover no cambia el id del archivo en Drive: el link que quedó en la fila sigue sirviendo.
"""
import logging
import re
import threading
from typing import Protocol

from app import sheets
from app.config import settings

logger = logging.getLogger(__name__)

CARPETA_RAIZ = "comprobantes"
CARPETA_PERSONAL = "personal"
CARPETA_SIN_IMPUTAR = "_sin-imputar"


def carpetas(campos: dict) -> list[str]:
    mes = str(campos.get("fecha") or "")[:7] or "sin-fecha"
    if campos.get("tipo_gasto") == "personal":
        return [CARPETA_PERSONAL, mes]
    if campos.get("obra"):
        return [str(campos["obra"]), mes]
    return [CARPETA_SIN_IMPUTAR, mes]


def _importe_legible(importe: float) -> str:
    entero, dec = f"{importe:,.2f}".split(".")
    entero = entero.replace(",", ".")
    return f"${entero}" if dec == "00" else f"${entero},{dec}"


def nombre_base(id_mov: str, campos: dict) -> str:
    """Sin extensión: la pone el archivador, que sabe qué archivo es."""
    quien = campos.get("contratista") or campos.get("item") or campos.get("obra") or "sin contratista"
    nombre = f"{id_mov} {quien} {_importe_legible(float(campos.get('importe') or 0))}"
    return re.sub(r'[\\/:*?"<>|]+', " ", nombre).strip()


class Archivador(Protocol):
    def archivar(self, file_id: str, carpetas: list[str], nombre_base: str) -> str:
        """Mueve el archivo a comprobantes/<carpetas...>/ con ese nombre. Devuelve el link."""
        ...


class ArchivadorDrive:
    """Drive con OAuth de usuario. La carpeta raíz tiene que haberla creado esta app:
    `drive.file` no ve carpetas creadas a mano."""

    def __init__(self):
        self._raiz: str | None = settings().drive_carpeta_comprobantes_id or None
        self._lock = threading.Lock()
        self.avisos: list[str] = []

    def _carpeta_raiz(self) -> str:
        with self._lock:
            if not self._raiz:
                self._raiz = sheets.carpeta_drive(CARPETA_RAIZ, None)
                self.avisos.append(f"Se usó la carpeta «{CARPETA_RAIZ}» de la raíz del Drive ({self._raiz}). "
                                   f"Cargar DRIVE_CARPETA_COMPROBANTES_ID={self._raiz} para fijarla")
            return self._raiz

    def archivar(self, file_id: str, carpetas: list[str], nombre_base: str) -> str:
        padre = self._carpeta_raiz()
        for nombre in carpetas:
            padre = sheets.carpeta_drive(nombre, padre)
        actual = sheets.metadata_drive(file_id).get("name", "")
        extension = actual.rsplit(".", 1)[1] if "." in actual else ""
        nombre = f"{nombre_base}.{extension}" if extension else nombre_base
        return sheets.mover_drive(file_id, padre, nombre)
