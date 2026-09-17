"""Texto libre → obra, contratista, rubro, cuenta. SIN LLM.

El usuario escribe `algo/algo`, pero el orden NO es fijo (`Sofia/Austral` y `Austral/Sofi`
son el mismo par). No se parsea por posición: se parte por `/` y cada token se resuelve
contra los diccionarios. El que matchea una obra es la obra, el que matchea un contratista
es el contratista.

Orden de resolución de cada token:
  1. exacto contra ALIAS, OBRAS (nombre y código), CONTRATISTAS, CUENTAS, RUBROS
  2. palabra: el token es una sola palabra que identifica a un único contratista o rubro
     («sofia» → Sofia Cervera, «club» → Club y deporte)
  3. difuso con rapidfuzz, umbral ≥ 88
Lo que queda sin resolver lo intenta el LLM (ver interpretar.py) o se pregunta.
"""
import re
from dataclasses import dataclass, field
from datetime import date

from rapidfuzz import fuzz, process

from app.maestros import Maestros, normalizar, solo_digitos

UMBRAL_DIFUSO = 88

# «Retiro» manda siempre (CONTEXTO-FACHADO.md §5.4): «Electricidad Angostura/Retiro» es
# material eléctrico para su casa, no una obra sin imputar. El proveedor se conserva, para
# poder separar dentro de su cuenta lo que fue obra de lo que fue personal.

# Palabras de instrucción que no son entidades.
PALABRAS_TIPO = {
    "ingreso": "INGRESO", "ingresos": "INGRESO", "cobro": "INGRESO",
    "pago": "EGRESO", "egreso": "EGRESO",
    "traspaso": "TRASPASO", "extraccion": "TRASPASO", "cajero": "TRASPASO",
}
PALABRAS_RUIDO = {"e", "y", "imputar", "ingresar", "ingresarlo", "registrar", "cargar", "tambien",
                  "como", "aparte", "separado", "correccion", "corregir"}
STOPWORDS_RUBRO = {"y", "de", "del", "la", "el", "los", "las", "a"}

RE_FECHA = re.compile(r"(?<![\d$.,])(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})(?![\d])")
RE_IMPORTE_PESOS = re.compile(r"(?:u\$s|usd|us\$|\$)\s*(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)", re.I)
RE_IMPORTE_SUELTO = re.compile(r"(?<![\d/])(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?)(?![\d/])")
RE_USD = re.compile(r"u\$s|usd|us\$|d[oó]lar", re.I)
RE_CERTIFICADO = re.compile(r"^cert(?:ificado)?\b\s*(.*)$")
RE_DOS_MOVIMIENTOS = re.compile(r"\s+e\s+(?=(?:imputar|ingresar|registrar|cargar)\w*\b)", re.I)
RE_CORRECCION = re.compile(r"^\s*correcci[oó]n\s*!*\s*:?\s*", re.I)
RE_ALIAS = re.compile(r"^\s*([^=/]+?)\s*=\s*([^=/]+?)\s*$")


@dataclass
class Resolucion:
    categoria: str  # obra | contratista | rubro | cuenta | personal | certificado | ambiguo
    valor: str      # nombre canónico (rubro: "rubro_1 / rubro_2")
    metodo: str     # alias | exacto | palabra | difuso | cuit | llm
    token: str
    puntaje: float = 100.0
    opciones: list[str] = field(default_factory=list)  # para ambiguo


@dataclass
class FechaTexto:
    valor: date
    original: str
    corregida: bool = False


@dataclass
class Segmento:
    """Un movimiento dentro del mensaje. Casi siempre hay uno solo."""
    texto: str
    tipo_mov: str | None = None
    importe: float | None = None
    moneda: str | None = None
    fechas: list[FechaTexto] = field(default_factory=list)
    fechas_invalidas: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    resueltos: list[Resolucion] = field(default_factory=list)
    sin_resolver: list[str] = field(default_factory=list)
    candidatos: dict[str, list[str]] = field(default_factory=dict)
    es_correccion: bool = False
    alias_propuesto: dict | None = None

    def de(self, categoria: str) -> list[Resolucion]:
        return [r for r in self.resueltos if r.categoria == categoria]

    def primero(self, categoria: str) -> Resolucion | None:
        return next(iter(self.de(categoria)), None)


# ─── Parseo del texto ──────────────────────────────────────────────────────────

def parsear_importe(texto: str) -> float | None:
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _parsear_fecha(d: str, m: str, a: str) -> FechaTexto | None:
    original = f"{d}/{m}/{a}"
    anio = int(a) + 2000 if len(a) == 2 else int(a)
    dia, mes = int(d), int(m)
    try:
        return FechaTexto(date(anio, mes, dia), original)
    except ValueError:
        pass
    # Dígitos invertidos: escribe 80/02/26 cuando quiso decir 08/02/26.
    for dia2, mes2 in ((int(d[::-1]), mes), (dia, int(m[::-1]))):
        try:
            return FechaTexto(date(anio, mes2, dia2), original, corregida=True)
        except ValueError:
            continue
    return None


def parsear(texto: str) -> list[Segmento]:
    texto = (texto or "").strip()
    if not texto:
        return [Segmento(texto="")]

    es_correccion = bool(RE_CORRECCION.match(texto))
    texto = RE_CORRECCION.sub("", texto)

    # «Rodrigo = Rodrigo sanitarista»: está enseñando un alias.
    m = RE_ALIAS.match(texto)
    if m:
        seg = Segmento(texto=texto, es_correccion=True, tokens=[m.group(2).strip()])
        seg.alias_propuesto = {"como_lo_dice": normalizar(m.group(1)), "dice": m.group(2).strip()}
        return [seg]

    segmentos = []
    for parte in RE_DOS_MOVIMIENTOS.split(texto):
        seg = Segmento(texto=parte.strip(), es_correccion=es_correccion)
        resto = parte

        for fm in list(RE_FECHA.finditer(resto)):
            f = _parsear_fecha(*fm.groups())
            if f:
                seg.fechas.append(f)
            else:
                seg.fechas_invalidas.append(fm.group(0))
        resto = RE_FECHA.sub(" ", resto)

        if RE_USD.search(resto):
            seg.moneda = "USD"
        im = RE_IMPORTE_PESOS.search(resto) or RE_IMPORTE_SUELTO.search(resto)
        if im:
            seg.importe = parsear_importe(im.group(1))
            resto = resto[:im.start()] + " " + resto[im.end():]
        resto = re.sub(r"\b(?:total|importe|monto)\b|[?¿!¡]", " ", resto, flags=re.I)

        tokens = []
        for crudo in resto.split("/"):
            palabras = crudo.split()
            limpias = []
            for p in palabras:
                n = normalizar(p)
                if n in PALABRAS_TIPO:
                    seg.tipo_mov = seg.tipo_mov or PALABRAS_TIPO[n]
                elif n not in PALABRAS_RUIDO:
                    limpias.append(p)
            token = " ".join(limpias).strip(" .,;:-")
            if normalizar(token):
                tokens.append(token)
        # «retiro de efectivo» / «retiro cajero» es un traspaso, no un gasto personal.
        if re.search(r"retir\w*\s+(?:de\s+)?(?:efectivo|cajero)", parte, re.I):
            seg.tipo_mov = "TRASPASO"
            tokens = [t for t in tokens if normalizar(t) not in ("retiro", "retiro de efectivo", "retiro efectivo")]
        seg.tokens = tokens
        segmentos.append(seg)
    return segmentos


# ─── Resolución de tokens ──────────────────────────────────────────────────────

def _canonico_contratista(m: Maestros, nombre: str) -> str:
    c = m.contratista(nombre)
    return c.nombre if c else nombre


def _canonico_obra(m: Maestros, nombre: str) -> str:
    o = m.obra(nombre)
    return o.nombre if o else nombre


def _rubro_valor(r) -> str:
    return f"{r.rubro_1} / {r.rubro_2}" if r.rubro_2 else r.rubro_1


def resolver_token(token: str, m: Maestros) -> list[Resolucion]:
    n = normalizar(token)
    if not n:
        return []

    cert = RE_CERTIFICADO.match(n)
    if cert:
        detalle = re.sub(r"^\W*cert(?:ificado)?\.?\s*", "", token, flags=re.I).strip()
        return [Resolucion("certificado", detalle or cert.group(1), "exacto", token)]

    salida: list[Resolucion] = []

    # Marcadores de destino personal: salen de ALIAS con tipo = tipo y valor Personal.
    for a in m.alias:
        if a.tipo == "tipo" and normalizar(a.como_lo_dice) == n and normalizar(a.valor_canonico) == "personal":
            salida.append(Resolucion("personal", "Personal", "alias", token))

    # 1. Exacto. ALIAS primero (es lo que el usuario enseñó), después los maestros.
    exactos: list[Resolucion] = []
    for a in m.alias:
        if normalizar(a.como_lo_dice) != n:
            continue
        if a.tipo == "contratista":
            exactos.append(Resolucion("contratista", _canonico_contratista(m, a.valor_canonico), "alias", token))
        elif a.tipo == "obra":
            exactos.append(Resolucion("obra", _canonico_obra(m, a.valor_canonico), "alias", token))
    if not exactos:
        exactos += [Resolucion("obra", o.nombre, "exacto", token) for o in m.obras
                    if n in (normalizar(o.nombre), normalizar(o.codigo))]
        exactos += [Resolucion("contratista", c.nombre, "exacto", token) for c in m.contratistas
                    if n == normalizar(c.nombre)]
    cuentas = [c for c in m.cuentas if n == normalizar(c.nombre)] or \
              [c for c in m.cuentas if len(n) >= 4 and normalizar(c.nombre).startswith(n)]
    if len(cuentas) == 1:
        exactos.append(Resolucion("cuenta", cuentas[0].nombre, "exacto", token))
    rubros = [r for r in m.rubros if n == normalizar(r.rubro_2)]
    if len(rubros) == 1:
        exactos.append(Resolucion("rubro", _rubro_valor(rubros[0]), "exacto", token))

    entidades = [r for r in exactos if r.categoria in ("obra", "contratista")]
    if len({(r.categoria, r.valor) for r in entidades}) > 1:
        # Matchea obra y contratista a la vez (o dos distintos): se pregunta.
        return salida + [Resolucion("ambiguo", "", "exacto", token,
                                    opciones=[f"{r.categoria}: {r.valor}" for r in entidades])]
    if exactos:
        return salida + exactos
    if salida:  # era solo un marcador personal
        return salida

    # 2. Una palabra que identifica a un único contratista o rubro.
    if " " not in n and len(n) >= 3:
        rubros = [r for r in m.rubros
                  if n in set(normalizar(r.rubro_2).split()) - STOPWORDS_RUBRO]
        if len(rubros) == 1:
            return [Resolucion("rubro", _rubro_valor(rubros[0]), "palabra", token, 90)]
        if len(n) >= 4:
            contratistas = [c for c in m.contratistas if normalizar(c.nombre).split()[0] == n]
            if len(contratistas) == 1 and not any(normalizar(o.nombre).split()[0] == n for o in m.obras):
                return [Resolucion("contratista", contratistas[0].nombre, "palabra", token, 90)]

    # 3. Difuso.
    claves: dict[str, tuple[str, str]] = {}
    for o in m.obras:
        claves[normalizar(o.nombre)] = ("obra", o.nombre)
        claves.setdefault(normalizar(o.codigo), ("obra", o.nombre))
    for c in m.contratistas:
        claves.setdefault(normalizar(c.nombre), ("contratista", c.nombre))
    for a in m.alias:
        if a.tipo == "contratista":
            claves.setdefault(normalizar(a.como_lo_dice), ("contratista", _canonico_contratista(m, a.valor_canonico)))
        elif a.tipo == "obra":
            claves.setdefault(normalizar(a.como_lo_dice), ("obra", _canonico_obra(m, a.valor_canonico)))
    for r in m.rubros:
        claves.setdefault(normalizar(r.rubro_2), ("rubro", _rubro_valor(r)))
    claves.pop("", None)

    matches = process.extract(n, list(claves), scorer=fuzz.ratio, limit=3)
    buenos = [(k, s) for k, s, _ in matches if s >= UMBRAL_DIFUSO]
    if buenos:
        mejor = max(s for _, s in buenos)
        empatados = {claves[k] for k, s in buenos if s == mejor}
        if len(empatados) == 1:
            cat, valor = empatados.pop()
            return [Resolucion(cat, valor, "difuso", token, mejor)]
        return [Resolucion("ambiguo", "", "difuso", token, mejor, opciones=[f"{c}: {v}" for c, v in empatados])]
    return []


def candidatos(token: str, m: Maestros, categoria: str, limite: int = 3) -> list[str]:
    """Las opciones más parecidas, para armar una pregunta con botones."""
    n = normalizar(token)
    if categoria == "obra":
        nombres = [o.nombre for o in m.obras if o.estado != "cerrada"]
    else:
        nombres = [c.nombre for c in m.contratistas]
    if not n:
        return nombres[:limite]
    return [nombres[i] for _, _, i in process.extract(n, [normalizar(x) for x in nombres],
                                                        scorer=fuzz.WRatio, limit=limite)]


def resolver_segmento(seg: Segmento, m: Maestros) -> Segmento:
    for token in seg.tokens:
        resoluciones = resolver_token(token, m)
        if resoluciones:
            vistos = {(r.categoria, r.valor) for r in seg.resueltos}
            seg.resueltos += [r for r in resoluciones if (r.categoria, r.valor) not in vistos]
        else:
            seg.sin_resolver.append(token)
    return seg


def contratista_por_cuit(cuit: str | None, m: Maestros) -> str | None:
    """Un contratista puede tener varios CUIT; el CUIT no es clave única del proveedor,
    siempre se resuelve al nombre canónico."""
    digitos = solo_digitos(cuit)
    if len(digitos) != 11:
        return None
    for c in m.contratistas:
        if digitos in map(solo_digitos, c.cuits):
            return c.nombre
    return None


def obra_por_cuit_comitente(cuit: str | None, m: Maestros) -> str | None:
    digitos = solo_digitos(cuit)
    if len(digitos) != 11:
        return None
    return next((o.nombre for o in m.obras if solo_digitos(o.cuit_comitente) == digitos), None)
