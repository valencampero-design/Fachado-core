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
    # §5.17: «depósito» es un pago informal a la cuenta de otra persona → PASANTE informal.
    "deposito": "PASANTE", "depositos": "PASANTE",
}
# Un ingreso que dice honorarios es del estudio; uno que dice certificado es de la obra (§5.8).
PALABRAS_HONORARIOS = {"hon", "honorario", "honorarios"}
PALABRAS_RUIDO = {"e", "y", "imputar", "ingresar", "ingresarlo", "registrar", "cargar", "tambien",
                  "como", "aparte", "separado", "correccion", "corregir"}
STOPWORDS_RUBRO = {"y", "de", "del", "la", "el", "los", "las", "a"}

# §5.12 v1.8: la palabra de tipo con un error de tipeo («INGRRSO», «ingrso»). Solo la primera
# palabra del mensaje, que es donde la escribe, y solo las largas: «pago» o «cobro» con un
# error se confundirían con cualquier cosa.
TIPOS_POR_PARECIDO = {"ingreso": "INGRESO", "egreso": "EGRESO", "traspaso": "TRASPASO", "deposito": "PASANTE",
                      "extraccion": "TRASPASO"}
UMBRAL_TIPO = 80
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
         "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
# «28 de septiembre», «28 de septiembre de 2026»
RE_FECHA_TEXTO = re.compile(r"\b(\d{1,2})\s+de\s+(" + "|".join(MESES) + r")(?:\s+(?:de\s+)?(\d{4}))?\b", re.I)
RE_FECHA = re.compile(r"(?<![\d$.,])(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})(?![\d])")
# «del 20/9»: día y mes sin año. El año es el del mensaje (o el anterior, si quedaría en el futuro).
RE_FECHA_SIN_ANIO = re.compile(r"(?:\bdel\s+)?(?<![\d/$.,])(\d{1,2})/(\d{1,2})(?![\d/])", re.I)
# §5.8: la palabra suelta «caja» equivale a la C pegada a la obra.
RE_CAJA = re.compile(r"\bcaja(?:\s+chica)?\b", re.I)
# §5.8 v1.8: en una obra con caja, «efectivo» es la caja; «efectivo del estudio» es el del estudio.
RE_EFECTIVO_ESTUDIO = re.compile(r"\b(efectivo|efvo)\s+del\s+estudio\b", re.I)
# §5.15: «etapa 1» escrito aparte, además de la forma pegada «Lennon1».
RE_ETAPA = re.compile(r"\betapa\s*(\d+)\b", re.I)
RE_IMPORTE_PESOS = re.compile(r"(?:u\$[sd]|usd|us\$|\$)\s*(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)", re.I)
# «400 dólares», «1.500 usd», «2000 pesos»: el número con la moneda escrita después (M-000005).
RE_IMPORTE_CON_MONEDA = re.compile(r"(?<![\d/.,])(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*"
                                   r"(?:u\$[sd]|usd|us\$|d[oó]lar(?:es)?|pesos)(?![a-z])", re.I)
RE_IMPORTE_SUELTO = re.compile(r"(?<![\d/])(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?)(?![\d/])")
RE_USD = re.compile(r"u\$[sd]|usd|us\$|d[oó]lar", re.I)
RE_CUENTA_USD = re.compile(r"\bbanco\s+(?:en\s+)?(?:usd|d[oó]lares)\b", re.I)
RE_CERTIFICADO = re.compile(r"^cert(?:ificado)?\b\s*(.*)$")
RE_DOS_MOVIMIENTOS = re.compile(r"\s+e\s+(?=(?:imputar|ingresar|registrar|cargar)\w*\b)", re.I)
RE_CORRECCION = re.compile(r"^\s*correcci[oó]n\s*!*\s*:?\s*", re.I)
RE_ALIAS = re.compile(r"^\s*([^=/]+?)\s*=\s*([^=/]+?)\s*$")
# §5.18: las frases de un traspaso, sobre el texto normalizado (sin tildes). Qué cuenta es el
# origen y cuál el destino lo decide interpretar.
RE_EXTRACCION = re.compile(r"\bextraccion\w*|\bcajero\b|\bsaque\b.*\befectivo\b|\bretir\w*\s+(?:de\s+)?(?:efectivo|cajero)\b")
RE_REPOSICION = re.compile(r"\brepus\w*|\brepon\w*|\breposicion\w*")
RE_PASE = re.compile(r"\bpase\b.*\b(?:a|al|hacia)\s+(?:la\s+|el\s+)?(?:caja|banco|efectivo|mercado pago|chequera)\b")


@dataclass
class Resolucion:
    categoria: str  # obra | contratista | rubro | cuenta | personal | certificado | ambiguo
    valor: str      # nombre canónico (rubro: "rubro_1 / rubro_2")
    metodo: str     # alias | exacto | palabra | difuso | cuit | llm
    token: str
    puntaje: float = 100.0
    opciones: list[str] = field(default_factory=list)  # para ambiguo
    # Solo para obras escritas con la sintaxis `<obra>[<etapa>][C]` (§5.15 y §5.8).
    etapa: str | None = None
    caja: bool = False


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
    etapa: str | None = None   # «etapa 1» escrito aparte
    caja: bool = False         # la palabra «caja»
    efectivo_estudio: bool = False  # «efectivo del estudio»: no es la caja de la obra (§5.8)
    honorarios: bool = False   # «hon», «honorarios»
    traspaso: str | None = None  # extraccion | reposicion | pase | explicito (§5.18)
    # Frases libres de las que se sacó una entidad («Lennon me pasó us$20.000 para la caja»): no
    # son un contratista desconocido, van a la descripción.
    libres: list[str] = field(default_factory=list)

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


def _fecha_sin_anio(d: str, m: str, hoy: date) -> FechaTexto | None:
    """«20/9»: el año del mensaje, salvo que la fecha quede en el futuro (entonces el anterior)."""
    try:
        f = date(hoy.year, int(m), int(d))
    except ValueError:
        return None
    if f > hoy:
        try:
            f = date(hoy.year - 1, int(m), int(d))
        except ValueError:
            return None
    return FechaTexto(f, f"{d}/{m}")


def _tipo_por_parecido(n: str) -> str | None:
    """«ingrrso» → INGRESO. Solo palabras de cinco letras o más, y solo si no son otra cosa."""
    if len(n) < 5 or n in PALABRAS_RUIDO:
        return None
    mejor = process.extractOne(n, list(TIPOS_POR_PARECIDO), scorer=fuzz.ratio)
    return TIPOS_POR_PARECIDO[mejor[0]] if mejor and mejor[1] >= UMBRAL_TIPO else None


def parsear(texto: str, hoy: date | None = None) -> list[Segmento]:
    """`hoy` es la fecha del mensaje: sirve para completar el año de «20/9»."""
    hoy = hoy or date.today()
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
        for fm in list(RE_FECHA_SIN_ANIO.finditer(resto)):
            f = _fecha_sin_anio(fm.group(1), fm.group(2), hoy)
            if f:
                seg.fechas.append(f)
                resto = resto.replace(fm.group(0), " ", 1)
        # «28 de septiembre»: sin año, el del mensaje (o el anterior si quedaría en el futuro).
        for fm in list(RE_FECHA_TEXTO.finditer(resto)):
            dia, mes, anio = fm.group(1), str(MESES[normalizar(fm.group(2))]), fm.group(3)
            f = _parsear_fecha(dia, mes, anio) if anio else _fecha_sin_anio(dia, mes, hoy)
            if f:
                seg.fechas.append(f)
                resto = resto.replace(fm.group(0), " ", 1)

        if RE_EFECTIVO_ESTUDIO.search(resto):
            seg.efectivo_estudio = True
            resto = RE_EFECTIVO_ESTUDIO.sub(r"\1", resto)
        if RE_CAJA.search(resto):
            seg.caja = True
            resto = RE_CAJA.sub(" ", resto)
        me = RE_ETAPA.search(resto)
        if me:
            seg.etapa = me.group(1)
            resto = RE_ETAPA.sub(" ", resto)

        # «banco usd» es el nombre de una cuenta, no dice en qué moneda está el importe.
        if RE_USD.search(RE_CUENTA_USD.sub(" ", resto)):
            seg.moneda = "USD"
        im = RE_IMPORTE_PESOS.search(resto) or RE_IMPORTE_CON_MONEDA.search(resto) or RE_IMPORTE_SUELTO.search(resto)
        if im:
            seg.importe = parsear_importe(im.group(1))
            resto = resto[:im.start()] + " " + resto[im.end():]
        resto = re.sub(r"\b(?:total|importe|monto)\b|[?¿!¡]", " ", resto, flags=re.I)

        tokens = []
        primera = True
        for crudo in resto.split("/"):
            palabras = crudo.split()
            limpias = []
            for p in palabras:
                n = normalizar(p)
                tipo_parecido = _tipo_por_parecido(n) if primera and not seg.tipo_mov else None
                primera = False
                if n in PALABRAS_TIPO:
                    seg.tipo_mov = seg.tipo_mov or PALABRAS_TIPO[n]
                elif tipo_parecido:
                    seg.tipo_mov = tipo_parecido
                elif n in PALABRAS_HONORARIOS:
                    seg.honorarios = True
                elif n not in PALABRAS_RUIDO:
                    limpias.append(p)
            token = " ".join(limpias).strip(" .,;:-")
            if normalizar(token):
                tokens.append(token)
        # «retiro de efectivo» / «retiro cajero» es un traspaso, no un gasto personal.
        if re.search(r"retir\w*\s+(?:de\s+)?(?:efectivo|cajero)", parte, re.I):
            seg.tipo_mov = "TRASPASO"
            tokens = [t for t in tokens if normalizar(t) not in ("retiro", "retiro de efectivo", "retiro efectivo")]
        # §5.18: «saqué efectivo», «extracción», «repuse la caja de LennonC», «pasé a la caja».
        plano = normalizar(parte)
        for clase, patron in (("extraccion", RE_EXTRACCION), ("reposicion", RE_REPOSICION), ("pase", RE_PASE)):
            if patron.search(plano):
                seg.tipo_mov, seg.traspaso = "TRASPASO", clase
                break
        else:
            if seg.tipo_mov == "TRASPASO":
                seg.traspaso = "explicito"
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


def _obra_exacta(n: str, token: str, m: Maestros) -> Resolucion | None:
    """El token normalizado, entero, contra ALIAS de obra, OBRAS.obra y OBRAS.codigo."""
    for a in m.alias:
        if a.tipo == "obra" and normalizar(a.como_lo_dice) == n:
            return Resolucion("obra", _canonico_obra(m, a.valor_canonico), "alias", token)
    o = next((o for o in m.obras if n in (normalizar(o.nombre), normalizar(o.codigo))), None)
    return Resolucion("obra", o.nombre, "exacto", token) if o else None


def _obra_con_sufijo(n: str, token: str, m: Maestros) -> Resolucion | None:
    """`<obra>[<etapa>][C]` (§5.15 y §5.8): `lennon1c` → Lennon, etapa 1, caja.

    Se llega acá solo si el token entero no matcheó nada. Se prueba sacar una C final, un
    número final, o los dos, y **solo se acepta el recorte si lo que queda es una obra**: así
    una obra cuyo nombre termine en número o en «c» nunca se rompe."""
    intentos: list[tuple[str, str | None, bool]] = []
    if n.endswith("c"):
        intentos.append((n[:-1].rstrip(), None, True))
    for base, caja in ((n, False), (n[:-1].rstrip(), True) if n.endswith("c") else (None, False)):
        md = re.fullmatch(r"(.+?)\s*(\d+)", base) if base else None
        if md:
            intentos.append((md.group(1).rstrip(), md.group(2), caja))
    for base, etapa, caja in intentos:
        r = _obra_exacta(base, token, m)
        if r:
            r.etapa, r.caja = etapa, caja
            return r
    return None


def _etapa_y_caja(obra: str, palabra: str, m: Maestros) -> tuple[str | None, bool]:
    """«extras» → (extras, False); «extrasc» → (extras, True); «ext» → (extras, False) si es
    inequívoco. La etapa tiene que existir en ETAPAS para esa obra."""
    e = m.etapa_por_nombre(obra, palabra)
    if e:
        return e, False
    if palabra.endswith("c") and len(palabra) > 1:
        e = m.etapa_por_nombre(obra, palabra[:-1])
        if e:
            return e, True
    return None, False


def _obra_pegada(n: str, token: str, m: Maestros) -> Resolucion | None:
    """«morenoextras», «morenoextrasc»: la obra con una etapa con nombre pegada."""
    claves = [(normalizar(a.como_lo_dice), _canonico_obra(m, a.valor_canonico)) for a in m.alias if a.tipo == "obra"]
    claves += [(normalizar(o.nombre), o.nombre) for o in m.obras] + [(normalizar(o.codigo), o.nombre) for o in m.obras]
    for clave, obra in sorted(claves, key=lambda c: -len(c[0])):
        if clave and n.startswith(clave) and len(n) > len(clave):
            etapa, caja = _etapa_y_caja(obra, n[len(clave):].strip(), m)
            if etapa:
                return Resolucion("obra", obra, "exacto", token, etapa=etapa, caja=caja)
    return None


def _obra_con_etapa(n: str, token: str, m: Maestros) -> Resolucion | None:
    """La etapa con nombre (§5.15 v1.7): `Moreno extras`, `Morenoextras`, `Moreno ext`,
    `MorenoC extras`, `Moreno extras C`. La obra primero y, después, solo palabras que sean
    una etapa de esa obra o la C: si sobra algo que no lo es, no es esto."""
    palabras = n.split()
    for k in range(len(palabras), 0, -1):
        cabeza, resto = " ".join(palabras[:k]), palabras[k:]
        r = _obra_exacta(cabeza, token, m) or _obra_con_sufijo(cabeza, token, m) or _obra_pegada(cabeza, token, m)
        if r is None or not (resto or r.etapa or r.caja):
            continue
        etapa, caja = r.etapa, r.caja
        for palabra in resto:
            if palabra == "c":
                caja = True
                continue
            nueva, con_c = _etapa_y_caja(r.valor, palabra, m) if not etapa else (None, False)
            if not nueva:
                break
            etapa, caja = nueva, caja or con_c
        else:
            r.etapa, r.caja = etapa, caja
            return r
    return None


def resolver_token(token: str, m: Maestros, incluir_inactivos: bool = False) -> list[Resolucion]:
    """`incluir_inactivos` es para la migración de históricos (§5.6): en la carga diaria un
    contratista inactivo solo coincide por nombre exacto, alias exacto o CUIT, y ahí el bot
    pregunta si se reactiva; nunca por palabra única ni por parecido."""
    n = normalizar(token)

    def vigente(nombre: str) -> bool:
        c = m.contratista(nombre)
        return incluir_inactivos or c is None or c.activo
    if not n:
        return []

    cert = RE_CERTIFICADO.match(n)
    if cert:
        detalle = re.sub(r"^\W*cert(?:ificado)?\.?\s*", "", token, flags=re.I).strip()
        # «Certificado 5 Moreno1»: sin «/», la obra queda pegada al número. Se suelta desde el
        # final todo lo que sea una obra; lo que queda es el certificado («4 extras» sigue entero).
        # Puede no quedar nada: «Certificado Moreno» es un certificado sin número.
        palabras, obras = detalle.split(), []
        while palabras:
            for k in (3, 2, 1):
                if len(palabras) < k:
                    continue
                cola = " ".join(palabras[-k:])
                r = _obra_exacta(normalizar(cola), cola, m) or _obra_con_sufijo(normalizar(cola), cola, m) \
                    or _obra_con_etapa(normalizar(cola), cola, m)
                if r:
                    obras.insert(0, r)
                    del palabras[-k:]
                    break
            else:
                break
        detalle = " ".join(palabras)
        return [Resolucion("certificado", detalle if obras else (detalle or cert.group(1)), "exacto", token)] + obras

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
    activas = [c for c in m.cuentas if c.activa]
    cuentas = [c for c in activas if n == normalizar(c.nombre)] or \
              [c for c in activas if len(n) >= 4 and normalizar(c.nombre).startswith(n)]
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

    # 1b. La obra con etapa y/o caja pegadas: `Lennon1C`, `Moreno extras`, `MorenoC extras`.
    r = _obra_con_sufijo(n, token, m) or _obra_con_etapa(n, token, m)
    if r:
        return [r]

    # 2. Una palabra que identifica a un único contratista o rubro.
    if " " not in n and len(n) >= 3:
        rubros = [r for r in m.rubros
                  if n in set(normalizar(r.rubro_2).split()) - STOPWORDS_RUBRO]
        if len(rubros) == 1:
            return [Resolucion("rubro", _rubro_valor(rubros[0]), "palabra", token, 90)]
        if len(n) >= 4:
            contratistas = [c for c in m.contratistas if normalizar(c.nombre).split()[0] == n and vigente(c.nombre)]
            if len(contratistas) == 1 and not any(normalizar(o.nombre).split()[0] == n for o in m.obras):
                return [Resolucion("contratista", contratistas[0].nombre, "palabra", token, 90)]

    # 3. Difuso.
    claves: dict[str, tuple[str, str]] = {}
    for o in m.obras:
        claves[normalizar(o.nombre)] = ("obra", o.nombre)
        claves.setdefault(normalizar(o.codigo), ("obra", o.nombre))
    for c in m.contratistas:
        if vigente(c.nombre):
            claves.setdefault(normalizar(c.nombre), ("contratista", c.nombre))
    for a in m.alias:
        if a.tipo == "contratista" and vigente(a.valor_canonico):
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


@dataclass
class Hallazgo:
    """Una entidad encontrada dentro de una frase, con las palabras que ocupa."""
    inicio: int
    fin: int  # exclusivo
    resolucion: Resolucion


def escanear(texto: str, m: Maestros, max_palabras: int = 4) -> tuple[list[str], list[Hallazgo]]:
    """Entidades dentro de una frase sin «/» («repuse la caja de LennonC con efectivo»,
    «¿cuántos pagos a Felipe J por Lennon?»): ventanas de hasta `max_palabras` palabras
    contra el diccionario, las más largas primero. Solo coincidencias firmes —alias, exacto,
    una palabra que identifica a uno solo— y los ambiguos, para preguntar; nada difuso ni LLM.
    Devuelve las palabras normalizadas y los hallazgos en el orden del texto."""
    palabras = normalizar(texto).split()
    usadas: set[int] = set()
    hallazgos: list[Hallazgo] = []
    for k in range(max_palabras, 0, -1):
        for i in range(len(palabras) - k + 1):
            if usadas & set(range(i, i + k)):
                continue
            firmes = [r for r in resolver_token(" ".join(palabras[i:i + k]), m)
                      if (r.categoria == "ambiguo" and r.metodo != "difuso")
                      or (r.categoria in ("obra", "contratista", "cuenta") and r.metodo in ("alias", "exacto", "palabra"))]
            if firmes:
                hallazgos += [Hallazgo(i, i + k, r) for r in firmes]
                usadas |= set(range(i, i + k))
    return palabras, sorted(hallazgos, key=lambda h: h.inicio)


def candidatos(token: str, m: Maestros, categoria: str, limite: int = 3) -> list[str]:
    """Las opciones más parecidas, para armar una pregunta con botones."""
    n = normalizar(token)
    if categoria == "obra":
        nombres = [o.nombre for o in m.obras if o.estado != "cerrada"]
    else:
        nombres = [c.nombre for c in m.contratistas if c.activo]  # un inactivo no se propone (§5.6)
    if not n:
        return nombres[:limite]
    return [nombres[i] for _, _, i in process.extract(n, [normalizar(x) for x in nombres],
                                                        scorer=fuzz.WRatio, limit=limite)]


def resolver_segmento(seg: Segmento, m: Maestros, incluir_inactivos: bool = False) -> Segmento:
    for token in seg.tokens:
        resoluciones = resolver_token(token, m, incluir_inactivos)
        if resoluciones:
            vistos = {(r.categoria, r.valor) for r in seg.resueltos}
            seg.resueltos += [r for r in resoluciones if (r.categoria, r.valor) not in vistos]
        else:
            seg.sin_resolver.append(token)
    # §5.12 v1.8: «28 de septiembre, Lennon me pasó us$20.000 para la caja chica, efectivo». Una
    # frase de tres palabras o más que no resolvió entera se recorre por palabras: la obra, el
    # contratista y la cuenta que nombre (solo coincidencias firmes) se usan, y la frase va a la
    # descripción en vez de tomarse por un contratista desconocido.
    # Dos palabras («Lennon/Miguel efectivo», lo que escribe Gabriel): solo si cada palabra
    # resuelve firme por sí sola; «Juan Pérez» sigue siendo un contratista desconocido.
    for token in list(seg.sin_resolver):
        n_palabras = len(normalizar(token).split())
        if n_palabras < 2:
            continue
        hallazgos = escanear(token, m)[1]
        if n_palabras == 2 and (len(hallazgos) != 2 or any(h.fin - h.inicio != 1 for h in hallazgos)):
            continue
        nuevas = []
        for h in hallazgos:
            r = h.resolucion
            if r.categoria in ("obra", "contratista", "cuenta") and not seg.primero(r.categoria) \
                    and all(x.categoria != r.categoria for x in nuevas):
                nuevas.append(r)
        if n_palabras == 2 and len(nuevas) != 2:
            continue
        if nuevas:
            seg.resueltos += nuevas
            seg.sin_resolver.remove(token)
            if n_palabras >= 3:
                seg.libres.append(token)
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


def contratista_por_razon_social(razon_social: str | None, m: Maestros) -> str | None:
    """La razón social de un comprobante es el nombre legal: «MARAGANO GUERR MARCELO
    ALFREDO» es Marcelo Maragaño. La ñ ya la pliega `normalizar` (ñ → n: los comprobantes la
    pierden). Empareja si todas las palabras del nombre del contratista (dos o más) están en
    la razón social, en cualquier orden; la última puede venir cortada. Solo si hay uno."""
    palabras = normalizar(razon_social).split()
    if not palabras:
        return None

    def esta(w: str) -> bool:
        return w in palabras or (len(w) >= 4 and any(len(p) >= 4 and w.startswith(p) for p in palabras[-1:]))

    candidatos = [c.nombre for c in m.contratistas if c.activo
                  and len(nombre := normalizar(c.nombre).split()) >= 2 and all(esta(w) for w in nombre)]
    return candidatos[0] if len(candidatos) == 1 else None


def obra_por_cuit_comitente(cuit: str | None, m: Maestros) -> str | None:
    digitos = solo_digitos(cuit)
    if len(digitos) != 11:
        return None
    return next((o.nombre for o in m.obras if solo_digitos(o.cuit_comitente) == digitos), None)
