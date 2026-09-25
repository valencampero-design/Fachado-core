"""Corregir algo ya confirmado: el contraasiento (CONTEXTO-FACHADO.md §5.19).

El libro no se edita nunca. Para corregir un movimiento se escribe una fila que lo anula
—los mismos campos, el importe con signo contrario, `anula = <id_mov>`, `origen =
ANULACION`— y después la fila correcta, que se confirma por /confirmar como cualquier otra.
Queda el rastro de qué se cargó, quién lo corrigió y cuándo.

- El contraasiento va **al mismo libro** que la original, y solo lo pide quien tiene acceso a
  ese libro: lo personal, solo con `ve_personal`.
- **Un traspaso se anula entero**: anular cualquiera de sus dos filas escribe los dos
  contraasientos, vinculados entre sí, en una sola escritura.
- Lo derivado (saldos, consultas, duplicados, conciliación, cobros de certificados) saca el
  par original + contraasiento con `filtros.sin_anulados`.

Comparte el lock del id_mov con /confirmar: los dos sacan números del mismo libro.
"""
import asyncio

from app import maestros
from app.confirmar import SUFIJO_VINCULADA, ErrorConfirmar, _ahora_local, _leer_libro, _lock, _siguiente_id
from app.filtros import ORIGEN_ANULACION, es_anulacion, es_cierre_semanal
from app.libro import Libro
from app.maestros import Maestros, Usuario, normalizar, numero
from app.models import (CAMPOS_FICHA_TRASPASO, COLUMNAS_MOVIMIENTOS, AnularIn, AnularOut, FichaConfirmada,
                        MovimientoOut)
from app.saldos import como_dicts

SUFIJO_ANULACION = "anula"  # msg_id del contraasiento: `<wamid>#anula` (y `<wamid>#anulab` en un traspaso)


def _usuario(m: Maestros, telefono: str) -> Usuario:
    usuario = m.usuario(telefono)
    if usuario is None:
        raise ErrorConfirmar(403, "telefono", "Ese teléfono no está en USUARIOS")
    return usuario


def _libro_de(id_mov: str, libro: Libro, libro_personal: Libro | None, usuario: Usuario) -> tuple[str, Libro]:
    """El libro de un id_mov por su prefijo: M- el del estudio, P- el personal (§5.14)."""
    prefijo = id_mov.strip().upper()[:2]
    if prefijo == "P-":
        if not usuario.ve_personal:
            raise ErrorConfirmar(403, "id_mov", f"{usuario.nombre} no tiene acceso a lo personal (ve_personal = no)")
        if libro_personal is None:
            raise ErrorConfirmar(503, "libro_personal", "El libro personal no está configurado (FACHADO_PERSONAL_SHEET_ID)")
        return "personal", libro_personal
    if prefijo == "M-":
        return "estudio", libro
    raise ErrorConfirmar(404, "id_mov", f"«{id_mov}» no es un id_mov (M-000012 o P-000003)")


def _encontrar(movs: list[dict], id_mov: str, usuario: Usuario) -> dict:
    mov = next((mv for mv in movs if str(mv.get("id_mov") or "").upper() == id_mov.strip().upper()), None)
    if mov is None:
        raise ErrorConfirmar(404, "id_mov", f"No hay un movimiento {id_mov}")
    # Lo personal que quedó en el libro del estudio, de antes de separarlo (§5.14).
    if normalizar(mov.get("tipo_gasto")) == "personal" and not es_cierre_semanal(mov) and not usuario.ve_personal:
        raise ErrorConfirmar(403, "id_mov", f"{usuario.nombre} no tiene acceso a lo personal (ve_personal = no)")
    return mov


def _anulacion_de(movs: list[dict], id_mov: str) -> dict | None:
    return next((mv for mv in movs if str(mv.get("anula") or "").strip() == id_mov), None)


def movimiento(id_mov: str, telefono: str, libro: Libro, libro_personal: Libro | None) -> MovimientoOut:
    """GET /movimientos/{id_mov}: lo que el gateway muestra antes de corregir."""
    m = maestros.cargar()
    usuario = _usuario(m, telefono)
    nombre, lib = _libro_de(id_mov, libro, libro_personal, usuario)
    movs = como_dicts(lib.leer_movimientos())
    mov = _encontrar(movs, id_mov, usuario)
    anulacion = _anulacion_de(movs, str(mov["id_mov"]))
    return MovimientoOut(id_mov=str(mov["id_mov"]), libro=nombre, campos=mov,
                         anulado_por=str(anulacion["id_mov"]) if anulacion else None,
                         vinculado=str(mov.get("vinculo") or "") or None)


def ficha_original(mov: dict, vinculado: dict | None) -> FichaConfirmada:
    """La ficha de lo que se anula, en el formato de /interpretar, para usarla como
    `contexto_previo` de la corrección."""
    if mov.get("tipo") == "TRASPASO":
        salida, entrada = sorted([mov, vinculado or {}], key=lambda f: numero(f.get("importe")))
        campos = {c: (salida.get(c) if salida.get(c) not in ("", None) else None) for c in CAMPOS_FICHA_TRASPASO}
        campos.update({"importe": abs(numero(salida.get("importe"))), "importe_ars": abs(numero(salida.get("importe_ars"))),
                       "cuenta_origen": salida.get("cuenta") or None, "cuenta_destino": entrada.get("cuenta") or None,
                       "obra": salida.get("obra") or entrada.get("obra") or None})
        return FichaConfirmada(campos=campos, extras={})
    campos = {c: (mov.get(c) if mov.get(c) not in ("", None) else None) for c in COLUMNAS_MOVIMIENTOS}
    campos["id_mov"] = None
    extras = {"certificado": str(mov["certificado"])} if mov.get("certificado") not in ("", None) else {}
    return FichaConfirmada(campos=campos, extras=extras)


async def anular(req: AnularIn, libro: Libro, libro_personal: Libro | None) -> AnularOut:
    m = await asyncio.to_thread(maestros.cargar)
    usuario = _usuario(m, req.telefono)
    nombre, lib = _libro_de(req.id_mov, libro, libro_personal, usuario)
    # Una clave propia: el mismo wamid («corregir M-000012 …») puede confirmar después la fila
    # correcta con `<wamid>#0`, y esa no puede tomarse por un reintento de la anulación.
    clave = f"{req.msg_id}#{SUFIJO_ANULACION}"

    async with _lock:
        encabezado, filas, movs = await asyncio.to_thread(_leer_libro, lib, nombre)
        if "anula" not in encabezado:
            raise ErrorConfirmar(500, "MOVIMIENTOS", f"Falta la columna «anula» en MOVIMIENTOS del libro {nombre}. "
                                                     "Correr scripts/preparar_sheet.py")
        original = _encontrar(movs, req.id_mov, usuario)
        id_original = str(original["id_mov"])
        vinculado = None
        if original.get("tipo") == "TRASPASO" and original.get("vinculo"):
            vinculado = next((mv for mv in movs if mv.get("id_mov") == original["vinculo"]), None)

        # Idempotencia por msg_id: el reintento devuelve el contraasiento que ya escribió.
        previo = next((mv for mv in movs if mv.get("msg_id") == clave), None)
        if previo:
            otro = next((mv for mv in movs if mv.get("msg_id") == clave + SUFIJO_VINCULADA), None)
            return AnularOut(id_mov_anulacion=str(previo["id_mov"]), anula=str(previo["anula"]), libro=nombre,
                             id_mov_anulacion_vinculado=str(otro["id_mov"]) if otro else None,
                             anula_vinculado=str(otro["anula"]) if otro else None,
                             ficha_original=ficha_original(original, vinculado), ya_existia=True)

        if es_anulacion(original):
            raise ErrorConfirmar(422, "id_mov", f"{id_original} es un contraasiento: no se anula una anulación")
        if es_cierre_semanal(original):
            raise ErrorConfirmar(422, "id_mov", f"{id_original} es la línea semanal de gastos personales: se "
                                                "recalcula sola. Hay que anular el movimiento personal")
        existente = _anulacion_de(movs, id_original)
        if existente:
            raise ErrorConfirmar(409, "id_mov", f"{id_original} ya estaba anulado por {existente['id_mov']}",
                                 datos={"id_mov_anulacion": str(existente["id_mov"])})

        objetivos = [original] + ([vinculado] if vinculado and not _anulacion_de(movs, str(vinculado["id_mov"])) else [])
        nuevas: list[dict] = []
        for i, fila in enumerate(objetivos):
            contra = {**fila,
                      "id_mov": _siguiente_id(movs + nuevas, "M" if nombre == "estudio" else "P"),
                      "importe": -numero(fila.get("importe")), "importe_ars": -numero(fila.get("importe_ars")),
                      "anula": str(fila["id_mov"]), "origen": ORIGEN_ANULACION, "cargado_por": usuario.nombre,
                      "ts": _ahora_local(), "msg_id": clave + (SUFIJO_VINCULADA if i else ""), "vinculo": "",
                      "descripcion": f"Anulación de {fila['id_mov']}" + (f" · {req.motivo.strip()}" if req.motivo.strip() else "")}
            nuevas.append(contra)
        if len(nuevas) == 2:
            nuevas[0]["vinculo"], nuevas[1]["vinculo"] = nuevas[1]["id_mov"], nuevas[0]["id_mov"]
        await asyncio.to_thread(lib.escribir_filas, len(filas) + 1,
                                [[f.get(col, "") for col in encabezado] for f in nuevas])

    segunda = nuevas[1] if len(nuevas) == 2 else None
    return AnularOut(id_mov_anulacion=nuevas[0]["id_mov"], anula=id_original, libro=nombre,
                     id_mov_anulacion_vinculado=segunda["id_mov"] if segunda else None,
                     anula_vinculado=segunda["anula"] if segunda else None,
                     ficha_original=ficha_original(original, vinculado), ya_existia=False)
