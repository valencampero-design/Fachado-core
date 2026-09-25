"""POST /confirmar: persiste una ficha que un usuario ya confirmó.

Orden, y por qué:

1. **Quién escribe.** El teléfono tiene que estar en USUARIOS; si no, 403 y nada se toca.
2. **La fila entera en memoria y validada.** Un append parcial deja el libro corrupto sin
   forma de saberlo después: o se escribe completa o no se escribe.
3. **Bajo el lock: idempotencia, `id_mov` y escritura.** Buscar el `msg_id`, calcular el
   siguiente `id_mov` y escribir tienen que ser una sola operación, o dos confirmaciones
   simultáneas —el bot tiene dos usuarios— sacan el mismo número.
4. **Fuera del lock, lo que puede fallar sin perder el movimiento**: mover el comprobante y
   escribir el alias devuelven advertencias, nunca un error. Perder el movimiento es peor
   que tener el comprobante en la carpeta equivocada.

El lock es de proceso: alcanza mientras el motor corra con un solo worker, que es como está
desplegado. Con dos réplicas haría falta otro mecanismo.
"""
import asyncio
import logging
import re
from datetime import date, datetime, timedelta, timezone

from app import archivo, maestros
from app.archivo import Archivador
from app.comprobante import id_drive
from app.config import settings
from app.libro import Libro
from app.maestros import TIPOS_ALIAS, Maestros, Usuario, normalizar, numero
from app.models import AliasPropuesto, ConfirmarIn, ConfirmarOut
from app.saldos import como_dicts, saldo_obra

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()

# Lo que /confirmar escribe además de las columnas de la ficha. Si el Sheet no las tiene, no
# se escribe nada: hay que correr scripts/preparar_sheet.py.
COLUMNAS_REQUERIDAS = ["id_mov", "fecha", "tipo", "importe", "moneda", "tc", "importe_ars", "obra",
                       "comitente", "cuenta", "origen", "concilia", "estado_conc", "comprobante_url",
                       "cargado_por", "ts", "tipo_gasto", "msg_id"]

# Pasan tal cual de la ficha: lo que el usuario vio y confirmó.
CAMPOS_DE_LA_FICHA = ["item", "contratista", "rubro_1", "rubro_2", "medio_pago", "pagado_por",
                      "tipo_comprobante", "descripcion", "comprobante_url", "ref_comprobante"]

TIPOS_GASTO = {"obra", "estructura", "personal"}
RE_ID_MOV = re.compile(r"^M-(\d+)$")


class ErrorConfirmar(Exception):
    def __init__(self, status: int, campo: str, detalle: str):
        super().__init__(detalle)
        self.status, self.campo, self.detalle = status, campo, detalle


def clave_idempotencia(msg_id: str, ficha_indice: int) -> str:
    """Lo que se guarda en la columna `msg_id`. Lleva el índice de la ficha porque un mensaje
    puede traer dos movimientos con el mismo wamid."""
    return f"{msg_id}#{ficha_indice}"


def _vacio(valor) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _ahora_local() -> str:
    tz = timezone(timedelta(hours=settings().utc_offset_horas))
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M")


def armar_fila(req: ConfirmarIn, m: Maestros, usuario: Usuario) -> tuple[dict, list[str]]:
    """La fila completa, por nombre de columna. 422 ante el primer problema; no escribe nada."""
    c = req.ficha.campos
    advertencias: list[str] = []

    def falta(campo: str, detalle: str = "") -> ErrorConfirmar:
        return ErrorConfirmar(422, campo, detalle or f"Falta «{campo}»")

    tipo = str(c.get("tipo") or "").upper()
    if tipo == "TRASPASO":
        raise falta("tipo", "Un TRASPASO todavía no se puede confirmar: MOVIMIENTOS tiene una sola "
                            "columna `cuenta` y un traspaso necesita origen y destino")
    if tipo == "PASANTE":
        raise falta("tipo", "Un PASANTE todavía no se puede confirmar: falta definir en el contexto qué "
                            "cuenta lleva (§5.17 dice que no toca la caja del estudio, pero no cuál es)")

    for campo in ("fecha", "tipo", "importe", "moneda", "cuenta"):
        if _vacio(c.get(campo)):
            raise falta(campo)
    if tipo not in ("INGRESO", "EGRESO"):
        raise falta("tipo", f"Tipo «{c['tipo']}» inválido: INGRESO o EGRESO")

    try:
        fecha = date.fromisoformat(str(c["fecha"])[:10]).isoformat()
    except ValueError:
        raise falta("fecha", f"Fecha «{c['fecha']}» inválida: se espera AAAA-MM-DD")

    importe = numero(c["importe"])
    if importe <= 0:
        raise falta("importe", f"Importe «{c['importe']}» inválido")

    moneda = str(c["moneda"]).upper()
    if moneda == "ARS":
        tc = 1
    else:
        tc = numero(c.get("tc"))
        if tc <= 0:
            raise falta("tc", f"Un movimiento en {moneda} necesita el tipo de cambio")

    cuenta = m.cuenta(c["cuenta"])
    if cuenta is None:
        raise falta("cuenta", f"La cuenta «{c['cuenta']}» no está en CUENTAS")

    obra = None
    if not _vacio(c.get("obra")):
        obra = m.obra(c["obra"])
        if obra is None:
            raise falta("obra", f"La obra «{c['obra']}» no está en OBRAS. Nunca se inventa una obra")

    tipo_gasto = None if _vacio(c.get("tipo_gasto")) else str(c["tipo_gasto"]).lower()
    if tipo_gasto and tipo_gasto not in TIPOS_GASTO:
        raise falta("tipo_gasto", f"«{c['tipo_gasto']}» no es obra, estructura ni personal")
    if tipo == "EGRESO" and not tipo_gasto:
        # La cascada siempre lo decide o pregunta: que llegue vacío a confirmar es un bug.
        raise falta("tipo_gasto", "Un EGRESO sin tipo_gasto es un bug de la cascada: no se escribe")
    if not obra and not tipo_gasto:
        raise falta("obra", "Hace falta la obra o el tipo_gasto (un gasto personal puede no tener obra)")

    # §5.8: una caja de obra solo mueve plata de su propia obra.
    if cuenta.tipo == "caja_obra":
        propia = m.caja_de_obra(obra.nombre) if obra else None
        if propia is None or propia.nombre != cuenta.nombre:
            raise falta("cuenta", f"«{cuenta.nombre}» es la caja de otra obra, no de "
                                  f"«{obra.nombre if obra else 'ninguna'}»")

    # §5.15: si la obra tiene etapas, hace falta cuál; si no tiene, no puede venir una.
    etapa = "" if _vacio(c.get("etapa")) else str(c["etapa"]).strip()
    etapas_obra = m.etapas_de(obra.nombre) if obra else []
    if etapa and not etapas_obra:
        raise falta("etapa", f"«{obra.nombre if obra else '—'}» no tiene etapas cargadas en ETAPAS")
    if etapas_obra and etapa not in etapas_obra:
        raise falta("etapa", f"«{obra.nombre}» tiene etapas {etapas_obra}: hace falta cuál" if not etapa
                    else f"«{obra.nombre}» no tiene una etapa {etapa}")

    if not _vacio(c.get("contratista")) and m.contratista(c["contratista"]) is None:
        advertencias.append(f"«{c['contratista']}» no está en CONTRATISTAS")

    concilia = cuenta.concilia_contra_banco
    fila = {campo: ("" if _vacio(c.get(campo)) else c[campo]) for campo in CAMPOS_DE_LA_FICHA}
    fila.update({
        "fecha": fecha,
        "tipo": tipo,
        "importe": importe,
        "moneda": moneda,
        "tc": tc,
        "importe_ars": round(importe * tc, 2),
        "obra": obra.nombre if obra else "",
        "comitente": obra.comitente if obra else "",   # se hereda de OBRAS, no se tipea
        "cuenta": cuenta.nombre,
        "origen": "WHATSAPP",
        "concilia": "VERDADERO" if concilia else "FALSO",
        "id_banco": "",
        "estado_conc": "PENDIENTE" if concilia else "SOLO_CAJA",
        "cargado_por": usuario.nombre,
        "ts": _ahora_local(),
        "tipo_gasto": tipo_gasto or "",
        "etapa": etapa,
        "informal": "sí" if normalizar(c.get("informal")) in ("si", "true", "verdadero", "1", "x") else "",
        "msg_id": clave_idempotencia(req.msg_id, req.ficha_indice),
        "certificado": str(req.ficha.extras.get("certificado") or ""),
    })
    return fila, advertencias


def _siguiente_id(movs: list[dict]) -> str:
    numeros = [int(mt.group(1)) for mov in movs if (mt := RE_ID_MOV.match(str(mov.get("id_mov", ""))))]
    return f"M-{max(numeros, default=0) + 1:06d}"


def escribir_alias(libro: Libro, m: Maestros, propuesto: AliasPropuesto) -> tuple[bool, list[str]]:
    """Agrega el alias a ALIAS. Nunca pisa uno existente: si ya hay otra fila con el mismo
    `como_lo_dice` apuntando a otro lado, se agrega igual y el resolver va a preguntar."""
    tipo = normalizar(propuesto.tipo)
    como = propuesto.como_lo_dice.strip().lower()
    if tipo not in TIPOS_ALIAS:
        return False, [f"Alias no escrito: el tipo «{propuesto.tipo}» no existe ({', '.join(sorted(TIPOS_ALIAS))})"]
    if tipo in ("contratista", "cuit"):
        destino = m.contratista(propuesto.valor_canonico)
    elif tipo == "obra":
        destino = m.obra(propuesto.valor_canonico)
    else:
        destino = None
    if tipo != "tipo" and destino is None:
        return False, [f"Alias no escrito: «{propuesto.valor_canonico}» no está en los maestros"]
    canonico = destino.nombre if destino else propuesto.valor_canonico

    existentes = [f for f in libro.leer_alias()[1:] if f and normalizar(f[0]) == normalizar(como)]
    if any(len(f) > 2 and normalizar(f[1]) == normalizar(canonico) and normalizar(f[2]) == tipo for f in existentes):
        return False, []  # ya estaba: nada que hacer
    avisos = []
    if existentes:
        otros = ", ".join(f"«{f[1]}»" for f in existentes if len(f) > 1)
        avisos.append(f"«{como}» ya apuntaba a {otros}: queda ambiguo y el bot va a preguntar")
    libro.agregar_alias([como, canonico, tipo])
    maestros.invalidar()
    return True, avisos


async def confirmar(req: ConfirmarIn, libro: Libro, archivador: Archivador) -> ConfirmarOut:
    m = await asyncio.to_thread(maestros.cargar)
    usuario = m.usuario(req.telefono)
    if usuario is None:
        # Puede ser un usuario recién cargado que la caché todavía no ve: se relee una vez.
        m = await asyncio.to_thread(maestros.cargar, True)
        usuario = m.usuario(req.telefono)
    if usuario is None:
        raise ErrorConfirmar(403, "telefono", "Ese teléfono no está en USUARIOS: no escribe en el libro")

    fila, advertencias = armar_fila(req, m, usuario)
    clave = fila["msg_id"]

    async with _lock:
        filas = await asyncio.to_thread(libro.leer_movimientos)
        encabezado = [str(x) for x in filas[0]] if filas else []
        faltan = [col for col in COLUMNAS_REQUERIDAS if col not in encabezado]
        if faltan:
            raise ErrorConfirmar(500, "MOVIMIENTOS", f"Faltan columnas en MOVIMIENTOS: {faltan}. "
                                                     "Correr scripts/preparar_sheet.py")
        movs = como_dicts(filas)
        existente = next(((n, mov) for n, mov in enumerate(movs, start=2) if mov.get("msg_id") == clave), None)
        if existente:
            numero_fila, fila = existente
            ya_existia = True
        else:
            fila["id_mov"] = _siguiente_id(movs)
            numero_fila = len(filas) + 1
            no_escritas = sorted(set(fila) - set(encabezado))
            if no_escritas:
                advertencias.append(f"Columnas que no existen en MOVIMIENTOS y no se escribieron: {no_escritas}")
            valores = [fila.get(col, "") for col in encabezado]
            await asyncio.to_thread(libro.escribir_fila, numero_fila, valores)
            movs.append(fila)
            ya_existia = False

    # ── Lo que puede fallar sin perder el movimiento ──────────────────────────
    comprobante_url = fila.get("comprobante_url") or None
    file_id = id_drive(comprobante_url) if comprobante_url else None
    if file_id:
        try:
            comprobante_url = await asyncio.to_thread(
                archivador.archivar, file_id, archivo.carpetas(fila), archivo.nombre_base(fila["id_mov"], fila))
            avisos = getattr(archivador, "avisos", None)
            if avisos:  # se consumen: son de esta operación, no de las siguientes
                advertencias += avisos
                avisos.clear()
        except Exception as e:  # noqa: BLE001 — cualquier falla de Drive es una advertencia
            logger.exception("No se pudo mover el comprobante de %s", fila["id_mov"])
            advertencias.append(f"El movimiento quedó escrito pero el comprobante no se movió "
                                f"({type(e).__name__}): sigue en la carpeta de captura")
    elif comprobante_url:
        advertencias.append("El comprobante no es un link de Drive: no se movió")

    alias_escrito = False
    if req.alias_propuesto:
        try:
            alias_escrito, avisos = await asyncio.to_thread(escribir_alias, libro, m, req.alias_propuesto)
            advertencias += avisos
        except Exception as e:  # noqa: BLE001
            logger.exception("No se pudo escribir el alias")
            advertencias.append(f"El movimiento quedó escrito pero el alias no ({type(e).__name__})")

    saldo = None
    if fila.get("obra"):
        saldo, avisos = saldo_obra(movs, fila["obra"], m)
        advertencias += avisos

    return ConfirmarOut(id_mov=fila["id_mov"], fila=numero_fila, comprobante_url=comprobante_url, obra=saldo,
                        alias_escrito=alias_escrito, ya_existia=ya_existia,
                        cargado_por=str(fila.get("cargado_por") or usuario.nombre), advertencias=advertencias)
