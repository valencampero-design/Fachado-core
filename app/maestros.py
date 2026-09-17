"""Carga y cachea los maestros: OBRAS, CONTRATISTAS, RUBROS, CUENTAS, ALIAS.

El motor lee el Sheet, no lo define. Las columnas se mapean por encabezado, no por
posición, para que agregar una columna en la planilla no rompa nada.

La caché es de la fuente de verdad (con TTL), no estado de conversación.
"""
import json
import logging
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field

from app.config import settings

logger = logging.getLogger(__name__)

HOJAS = ["OBRAS", "CONTRATISTAS", "RUBROS", "CUENTAS", "ALIAS"]


def normalizar(texto: str | None) -> str:
    """Minúsculas, sin acentos, sin puntuación, espacios colapsados."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9ñ ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def solo_digitos(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")


@dataclass
class Obra:
    nombre: str
    codigo: str
    tipo: str  # obra_terceros | obra_propia | estructura | personal
    servicio: str
    comitente: str
    estado: str
    cuit_comitente: str
    notas: str


@dataclass
class Contratista:
    nombre: str
    cuits: list[str]
    rubro_1: str
    rubro_2: str
    estado: str
    notas: str
    dual: bool


@dataclass
class Rubro:
    rubro_1: str
    rubro_2: str
    afecta: str  # obra | estructura | personal | otro


@dataclass
class Cuenta:
    nombre: str
    tipo: str
    moneda: str
    concilia_contra_banco: bool


@dataclass
class Alias:
    como_lo_dice: str
    valor_canonico: str
    tipo: str  # contratista | obra | cuit | tipo


@dataclass
class Maestros:
    obras: list[Obra]
    contratistas: list[Contratista]
    rubros: list[Rubro]
    cuentas: list[Cuenta]
    alias: list[Alias]
    cargado_en: float = field(default_factory=time.time)
    advertencias: list[str] = field(default_factory=list)

    def obra(self, nombre: str | None) -> Obra | None:
        n = normalizar(nombre)
        return next((o for o in self.obras if normalizar(o.nombre) == n), None)

    def contratista(self, nombre: str | None) -> Contratista | None:
        n = normalizar(nombre)
        return next((c for c in self.contratistas if normalizar(c.nombre) == n), None)

    def rubro(self, rubro_1: str | None, rubro_2: str | None) -> Rubro | None:
        n1, n2 = normalizar(rubro_1), normalizar(rubro_2)
        return next((r for r in self.rubros if normalizar(r.rubro_1) == n1 and normalizar(r.rubro_2) == n2), None)

    def cuenta(self, nombre: str | None) -> Cuenta | None:
        n = normalizar(nombre)
        return next((c for c in self.cuentas if normalizar(c.nombre) == n), None)


# ─── Parseo de filas crudas ────────────────────────────────────────────────────

def _registros(filas: list[list[str]]) -> list[dict[str, str]]:
    """Convierte filas (la primera es encabezado) en dicts por nombre de columna."""
    if not filas:
        return []
    encabezado = [normalizar(h).replace(" ", "_") for h in filas[0]]
    salida = []
    for fila in filas[1:]:
        registro = {col: (str(fila[i]).strip() if i < len(fila) and fila[i] is not None else "")
                    for i, col in enumerate(encabezado) if col}
        if any(registro.values()):
            salida.append(registro)
    return salida


def _es_dual(registro: dict[str, str]) -> bool:
    # Columna `dual` si la planilla la tiene; si no, la palabra DUAL en las notas.
    if normalizar(registro.get("dual")) in ("si", "sí", "true", "x", "1", "dual"):
        return True
    return bool(re.search(r"\bdual\b", normalizar(registro.get("notas"))))


def construir(crudo: dict[str, list[list[str]]]) -> Maestros:
    advertencias: list[str] = []

    obras = [
        Obra(r.get("obra", ""), r.get("codigo", ""), normalizar(r.get("tipo")).replace(" ", "_"),
             r.get("servicio", ""), r.get("comitente", ""), normalizar(r.get("estado")),
             r.get("cuit_comitente", ""), r.get("notas", ""))
        for r in _registros(crudo.get("OBRAS", [])) if r.get("obra")
    ]

    # CONTRATISTAS tiene filas repetidas (se pegó la reunión 3 al final). Se fusionan por
    # nombre normalizado: los valores no vacíos de filas posteriores completan/pisan.
    por_nombre: dict[str, Contratista] = {}
    for r in _registros(crudo.get("CONTRATISTAS", [])):
        nombre = r.get("contratista", "")
        if not nombre:
            continue
        clave = normalizar(nombre)
        cuit = r.get("cuit", "")
        nuevo = Contratista(nombre, [cuit] if cuit else [], r.get("rubro_habitual_1", ""),
                            r.get("rubro_habitual_2", ""), normalizar(r.get("estado")), r.get("notas", ""),
                            _es_dual(r))
        previo = por_nombre.get(clave)
        if previo is None:
            por_nombre[clave] = nuevo
            continue
        advertencias.append(f"CONTRATISTAS: «{nombre}» está repetido; se fusionan las filas")
        previo.nombre = nombre if any(ord(c) > 127 for c in nombre) else previo.nombre
        previo.cuits += [c for c in nuevo.cuits if c not in previo.cuits]
        if nuevo.rubro_1:
            previo.rubro_1, previo.rubro_2 = nuevo.rubro_1, nuevo.rubro_2
        previo.estado = nuevo.estado or previo.estado
        previo.notas = " | ".join(n for n in (previo.notas, nuevo.notas) if n)
        previo.dual = previo.dual or nuevo.dual
    contratistas = list(por_nombre.values())

    rubros = [Rubro(r.get("rubro_1", ""), r.get("rubro_2", ""), normalizar(r.get("afecta")))
              for r in _registros(crudo.get("RUBROS", [])) if r.get("rubro_1")]
    for c in contratistas:
        if c.rubro_1 and not any(normalizar(r.rubro_1) == normalizar(c.rubro_1)
                                 and normalizar(r.rubro_2) == normalizar(c.rubro_2) for r in rubros):
            advertencias.append(f"CONTRATISTAS: «{c.nombre}» tiene rubro habitual "
                                f"«{c.rubro_1} / {c.rubro_2}» que no existe en RUBROS")

    cuentas = [Cuenta(r.get("cuenta", ""), normalizar(r.get("tipo")), r.get("moneda", "ARS"),
                      normalizar(r.get("concilia_contra_banco")) in ("si", "true", "verdadero"))
               for r in _registros(crudo.get("CUENTAS", [])) if r.get("cuenta")]

    alias = [Alias(r.get("como_lo_dice", ""), r.get("valor_canonico", ""), normalizar(r.get("tipo")))
             for r in _registros(crudo.get("ALIAS", [])) if r.get("como_lo_dice")]

    # Los CUIT que figuran en ALIAS se suman al contratista canónico.
    for a in alias:
        if a.tipo == "cuit":
            c = next((c for c in contratistas if normalizar(c.nombre) == normalizar(a.valor_canonico)), None)
            if c and solo_digitos(a.como_lo_dice) not in map(solo_digitos, c.cuits):
                c.cuits.append(a.como_lo_dice)
    for a in alias:
        if a.tipo == "contratista" and not any(normalizar(c.nombre) == normalizar(a.valor_canonico) for c in contratistas):
            advertencias.append(f"ALIAS: «{a.como_lo_dice}» apunta a «{a.valor_canonico}», que no está en CONTRATISTAS")
        if a.tipo == "obra" and not any(normalizar(o.nombre) == normalizar(a.valor_canonico) for o in obras):
            advertencias.append(f"ALIAS: «{a.como_lo_dice}» apunta a la obra «{a.valor_canonico}», que no está en OBRAS")

    return Maestros(obras, contratistas, rubros, cuentas, alias, advertencias=advertencias)


# ─── Carga con caché ───────────────────────────────────────────────────────────

_lock = threading.Lock()
_cache: Maestros | None = None


def _leer_crudo() -> dict[str, list[list[str]]]:
    s = settings()
    if s.maestros_snapshot:
        with open(s.maestros_snapshot, encoding="utf-8") as f:
            return json.load(f)
    if not s.sheet_id:
        raise RuntimeError("Falta FACHADO_SHEET_ID (o MAESTROS_SNAPSHOT para correr offline)")
    from app import sheets
    return sheets.leer_hojas(s.sheet_id, [f"{h}!A:Z" for h in HOJAS])


def cargar(forzar: bool = False) -> Maestros:
    global _cache
    ttl = settings().maestros_ttl_segundos
    with _lock:
        if forzar or _cache is None or time.time() - _cache.cargado_en > ttl:
            try:
                _cache = construir(_leer_crudo())
                logger.info("Maestros cargados: %d obras, %d contratistas, %d rubros, %d alias",
                            len(_cache.obras), len(_cache.contratistas), len(_cache.rubros), len(_cache.alias))
            except Exception:
                if _cache is None:
                    raise
                # Si el Sheet no responde, seguir con la última copia buena.
                logger.exception("No se pudieron recargar los maestros; se usa la copia en caché")
                _cache.cargado_en = time.time()
        return _cache
