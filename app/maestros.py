"""Carga y cachea los maestros: OBRAS, CONTRATISTAS, RUBROS, CUENTAS, ALIAS, USUARIOS.

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

HOJAS = ["OBRAS", "CONTRATISTAS", "RUBROS", "CUENTAS", "ALIAS", "USUARIOS", "ETAPAS"]

# Qué clase de cosa nombra un alias. NO es la clasificación del gasto: para decir «esta
# palabra significa personal» va tipo = tipo con valor_canonico = Personal (así están
# cargados «retiro», «casa» y «particular»).
TIPOS_ALIAS = {"contratista", "obra", "cuit", "tipo"}


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


def numero(valor) -> float:
    """Un número del Sheet: ya numérico (lectura sin formato) o texto argentino
    («4.032.391,70», «$ 300.000»). Vacío es cero."""
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = re.sub(r"[^\d,.\-]", "", str(valor or ""))
    if not texto:
        return 0.0
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", texto):
        texto = texto.replace(".", "")  # «300.000» son trescientos mil, no trescientos
    try:
        return float(texto)
    except ValueError:
        return 0.0


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

    @property
    def activo(self) -> bool:
        """§5.6: un inactivo no se propone por parecido; solo por nombre exacto, alias o CUIT."""
        return normalizar(self.estado) not in ("inactivo", "inactiva", "baja")


@dataclass
class Rubro:
    rubro_1: str
    rubro_2: str
    afecta: str  # obra | estructura | personal | otro


# Qué cuentas suman al saldo de caja del ESTUDIO (CONTEXTO-FACHADO.md §5.8, regla de oro:
# «suma Banco, Banco USD, Efectivo, Chequera y Mercado Pago»). Es una lista blanca a
# propósito: un tipo mal cargado en el Sheet queda AFUERA del saldo, no adentro. Sumar de
# más infla el saldo con plata ajena, que es el error que el sistema viene a evitar.
TIPOS_CUENTA_DEL_ESTUDIO = {"banco", "efectivo", "chequera", "billetera"}
# `caja_obra` es plata del comitente en poder del arquitecto y `externa` es plata que el
# comitente paga directo: las dos son de terceros.
TIPOS_CUENTA_FUERA_DEL_ESTUDIO = {"caja_obra", "externa"}
TIPOS_CUENTA = TIPOS_CUENTA_DEL_ESTUDIO | TIPOS_CUENTA_FUERA_DEL_ESTUDIO
# La cuenta de lo que paga el comitente directo (§5.9). El contexto la nombra: también es la
# cuenta de un depósito «en negro» (§5.17).
CUENTA_PAGADO_POR_COMITENTE = "Pagado por el comitente"


@dataclass
class Cuenta:
    nombre: str
    tipo: str  # banco | efectivo | chequera | billetera | caja_obra | externa
    moneda: str
    concilia_contra_banco: bool
    saldo_apertura: float = 0.0
    activa: bool = True  # nada se borra de los maestros: lo que no corresponde pasa a inactiva

    @property
    def suma_al_saldo_del_estudio(self) -> bool:
        """Falso para las cajas de obra (un pasivo, no patrimonio) y para cualquier tipo
        que no sea uno de los del estudio."""
        return self.tipo in TIPOS_CUENTA_DEL_ESTUDIO


@dataclass
class Alias:
    como_lo_dice: str
    valor_canonico: str
    tipo: str  # contratista | obra | cuit | tipo


@dataclass
class Usuario:
    """Quien le escribe al bot (CONTEXTO-FACHADO.md §5.13). Un teléfono que no está en
    USUARIOS nunca escribe en el libro.

    El acceso a lo personal es **por persona**, no por rol: lo decide `ve_personal`, y el `rol`
    no restringe nada (Petrus tiene las mismas atribuciones que el arquitecto).
    `auto_confirmar` decide el período de prueba (§5.12): mientras sea no, todo se confirma."""
    telefono: str  # solo dígitos, como llega de WhatsApp
    nombre: str
    rol: str       # titular | colaborador
    activo: bool
    ve_personal: bool = False
    auto_confirmar: bool = False


@dataclass
class Etapa:
    """Subdivisión de una obra que se certifica (CONTEXTO-FACHADO.md §5.15). `Lennon1` es la
    etapa 1 de Lennon. Una obra sin filas en ETAPAS no tiene etapas."""
    obra: str
    etapa: str
    descripcion: str
    activa: bool


@dataclass
class Maestros:
    obras: list[Obra]
    contratistas: list[Contratista]
    rubros: list[Rubro]
    cuentas: list[Cuenta]
    alias: list[Alias]
    usuarios: list[Usuario] = field(default_factory=list)
    etapas: list[Etapa] = field(default_factory=list)
    cargado_en: float = field(default_factory=time.time)
    advertencias: list[str] = field(default_factory=list)

    def etapas_de(self, obra: str | None) -> list[str]:
        """Las etapas activas de la obra, en el orden del Sheet. Vacía = la obra no tiene etapas."""
        n = normalizar(obra)
        return [e.etapa for e in self.etapas if e.activa and normalizar(e.obra) == n]

    def usuario(self, telefono: str | None) -> Usuario | None:
        """El usuario activo con ese teléfono, o None."""
        digitos = solo_digitos(telefono)
        return next((u for u in self.usuarios if u.activo and digitos and u.telefono == digitos), None)

    def obra(self, nombre: str | None) -> Obra | None:
        n = normalizar(nombre)
        return next((o for o in self.obras if normalizar(o.nombre) == n), None)

    def contratista(self, nombre: str | None) -> Contratista | None:
        n = normalizar(nombre)
        return next((c for c in self.contratistas if normalizar(c.nombre) == n), None)

    def rubro(self, rubro_1: str | None, rubro_2: str | None) -> Rubro | None:
        n1, n2 = normalizar(rubro_1), normalizar(rubro_2)
        return next((r for r in self.rubros if normalizar(r.rubro_1) == n1 and normalizar(r.rubro_2) == n2), None)

    def cuenta(self, nombre: str | None, incluir_inactivas: bool = False) -> Cuenta | None:
        """Solo cuentas activas, salvo para leer el pasado: los saldos sí tienen que ver los
        movimientos de una cuenta que después se inactivó."""
        n = normalizar(nombre)
        return next((c for c in self.cuentas
                     if normalizar(c.nombre) == n and (c.activa or incluir_inactivas)), None)

    def caja_de_obra(self, obra: str | None) -> Cuenta | None:
        """La «Caja obra <obra>» activa, si la obra tiene (§5.8). Si no, None: nunca se inventa."""
        c = self.cuenta(f"Caja obra {obra}") if obra else None
        return c if c and c.tipo == "caja_obra" else None

    def obra_de_caja(self, cuenta: str | None) -> Obra | None:
        """La inversa: de qué obra es una caja de obra. None si la cuenta no es una caja."""
        return next((o for o in self.obras if (c := self.caja_de_obra(o.nombre)) and normalizar(c.nombre) == normalizar(cuenta)), None)

    def cuentas_del_estudio(self) -> list[Cuenta]:
        """Las que suman al saldo de caja del estudio. Cualquier cálculo de saldo sale de
        acá: las cajas de obra y lo que paga el comitente quedan afuera (§5.8)."""
        return [c for c in self.cuentas if c.suma_al_saldo_del_estudio]


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
        if c.rubro_2 and not c.rubro_1:
            advertencias.append(f"CONTRATISTAS: «{c.nombre}» tiene rubro_habitual_2 «{c.rubro_2}» "
                                f"sin rubro_habitual_1: no se puede inferir el rubro")
        elif c.rubro_1 and not any(normalizar(r.rubro_1) == normalizar(c.rubro_1)
                                   and normalizar(r.rubro_2) == normalizar(c.rubro_2) for r in rubros):
            advertencias.append(f"CONTRATISTAS: «{c.nombre}» tiene rubro habitual "
                                f"«{c.rubro_1} / {c.rubro_2}» que no existe en RUBROS")

    cuentas = [Cuenta(r.get("cuenta", ""), normalizar(r.get("tipo")).replace(" ", "_"), r.get("moneda", "ARS"),
                      normalizar(r.get("concilia_contra_banco")) in ("si", "true", "verdadero"),
                      numero(r.get("saldo_apertura")),
                      normalizar(r.get("estado")) not in ("inactiva", "inactivo", "cerrada"))
               for r in _registros(crudo.get("CUENTAS", [])) if r.get("cuenta")]
    for c in cuentas:
        if not c.activa:
            continue
        if c.tipo not in TIPOS_CUENTA:
            advertencias.append(f"CUENTAS: «{c.nombre}» tiene tipo «{c.tipo}», que no existe "
                                f"({', '.join(sorted(TIPOS_CUENTA))}). No suma al saldo del estudio")
        if normalizar(c.nombre).replace(" ", "_") in TIPOS_CUENTA_FUERA_DEL_ESTUDIO:
            advertencias.append(f"CUENTAS: hay una cuenta llamada «{c.nombre}», que es un tipo, no un nombre. "
                                f"Una caja de obra va una fila por obra («Caja obra Moreno») con tipo caja_obra")
        if c.tipo == "caja_obra" and c.concilia_contra_banco:
            advertencias.append(f"CUENTAS: «{c.nombre}» es una caja de obra y no puede conciliar "
                                f"contra el banco: es plata del comitente, no del estudio")

    alias = [Alias(r.get("como_lo_dice", ""), r.get("valor_canonico", ""), normalizar(r.get("tipo")))
             for r in _registros(crudo.get("ALIAS", [])) if r.get("como_lo_dice")]
    # Un alias con un `tipo` que no está en el dominio no se aplica: sin esto, el motor lo
    # ignoraría en silencio y el alias parecería cargado cuando en realidad no hace nada.
    for a in alias:
        if a.tipo not in TIPOS_ALIAS:
            advertencias.append(
                f"ALIAS: «{a.como_lo_dice}» tiene tipo «{a.tipo}», que no existe "
                f"({', '.join(sorted(TIPOS_ALIAS))}). La fila NO se está aplicando")

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

    usuarios: list[Usuario] = []
    for r in _registros(crudo.get("USUARIOS", [])):
        nombre, telefono = r.get("nombre", ""), solo_digitos(r.get("telefono"))
        if not nombre:
            continue
        if not telefono:
            advertencias.append(f"USUARIOS: «{nombre}» no tiene teléfono: no puede confirmar nada")
        elif any(u.telefono == telefono for u in usuarios):
            advertencias.append(f"USUARIOS: el teléfono de «{nombre}» está repetido")
        si = ("si", "true", "verdadero", "1", "x")
        usuarios.append(Usuario(telefono, nombre, normalizar(r.get("rol")), normalizar(r.get("activo")) in si,
                                normalizar(r.get("ve_personal")) in si, normalizar(r.get("auto_confirmar")) in si))
    if not usuarios:
        advertencias.append("USUARIOS: la hoja está vacía o no existe: nadie puede confirmar")
    for hoja in crudo.get("_hojas_faltantes", []):
        advertencias.append(f"{hoja}: la hoja no existe en el Sheet. Correr scripts/preparar_sheet.py")

    etapas: list[Etapa] = []
    for r in _registros(crudo.get("ETAPAS", [])):
        obra, etapa = r.get("obra", ""), re.sub(r"\D", "", r.get("etapa", ""))
        if not (obra and etapa):
            continue
        canonica = next((o.nombre for o in obras if normalizar(o.nombre) == normalizar(obra)), None)
        if canonica is None:
            advertencias.append(f"ETAPAS: «{obra}» no está en OBRAS")
            continue
        etapas.append(Etapa(canonica, etapa, r.get("descripcion", ""),
                            normalizar(r.get("estado")) not in ("inactiva", "inactivo", "cerrada", "terminada")))

    return Maestros(obras, contratistas, rubros, cuentas, alias, usuarios, etapas, advertencias=advertencias)


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
    # Solo las hojas que existen: una hoja nueva que todavía no se creó (ETAPAS, por ejemplo)
    # no puede tirar abajo la lectura de todos los maestros.
    existentes = sheets.estructura(s.sheet_id)
    crudo = sheets.leer_hojas(s.sheet_id, [f"{h}!A:Z" for h in HOJAS if h in existentes])
    crudo["_hojas_faltantes"] = [h for h in HOJAS if h not in existentes]
    return crudo


def invalidar() -> None:
    """Descarta la caché: la próxima lectura va al Sheet. Después de escribir un alias, o no
    se ve hasta que venza el TTL."""
    global _cache
    with _lock:
        _cache = None


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
