"""Lo cargado en el libro personal con una obra del estudio pasa al estudio (reunión del 6/11,
CONTEXTO-FACHADO.md §5.14 v1.14 y §6 v1.14; handoff de la reunión, M1.2 y M2).

Con cada fila del libro personal que tiene una obra que **no** es de tipo `personal` (desde el
6/11, Gessel y Belelli son obras propias; y cualquier obra del estudio que haya quedado ahí):

1. En el **estudio**, una fila nueva con los mismos datos (fecha, importe, cuenta, medio,
   contratista, ítem y comprobante), `tipo_gasto = obra`, el comitente de OBRAS, el rubro
   traducido a la lista vigente (los rubros «a confirmar» quedan como están y se anotan) y en
   la descripción «pasado del libro personal (P-0000xx) el 7/11».
2. En el **personal**, el contraasiento de la original (§5.19: `anula` = id original).
3. Las dos filas nuevas se vinculan (`vinculo`): la del estudio apunta al contraasiento y el
   contraasiento a la del estudio.
4. El comprobante se mueve a la carpeta de la obra y se renombra con el id nuevo (`--mover`;
   el link no cambia).

El cierre semanal escribe después el ajuste a la baja de cada semana afectada (§5.14, §5.19):
`POST /cierre-semanal`. Este script no lo escribe.

**Lo dudoso no se mueve** (handoff, M2.2): se lista al final, para Valen. P-000001 tiene obra
Moreno, pero su comprobante es una transferencia a «FACHADO, SOFIA» desde la CA 48 y la de
Tucu/Moreno de esa tarde es otra (la de Orellana, M-000020): queda retenida.

Simulacro por defecto, sobre copias en memoria de los dos libros reales (solo lectura).
Idempotente: cada pase tiene su msg_id fijo (`pase-2026-11-07-<P>#0` y `#anula`).

    python scripts/migraciones/2026_11_07_pase_de_libro.py                (simulacro)
    python scripts/migraciones/2026_11_07_pase_de_libro.py --aplicar
    python scripts/migraciones/2026_11_07_pase_de_libro.py --aplicar --mover   (además, Drive)
"""
import argparse
import asyncio
import sys

sys.path.insert(0, ".")
from app import archivo, maestros  # noqa: E402
from app.comprobante import id_drive  # noqa: E402
from app.confirmar import _ahora_local, _leer_libro, _lock, _siguiente_id  # noqa: E402
from app.filtros import ORIGEN_ANULACION, es_anulacion, es_cierre_semanal  # noqa: E402
from app.maestros import Maestros, normalizar, numero  # noqa: E402

PREFIJO = "pase-2026-11-07"
DIA = "7/11"
# Las que tienen obra del estudio pero no se mueven, con el porqué (van a «Para Valen»).
RETENIDAS = {
    "P-000001": "el comprobante es una transferencia de $ 184.000 a «FACHADO, SOFIA» (CUIT 27-47181632-4) desde la "
                "CA 48, concepto «Varios», y el extracto la confirma; «Tucu/Moreno» era el texto de otro comprobante "
                "($ 200.000 a Orellana, ya cargado como M-000020). Pasarla a Moreno cargaría a la obra un pago a su hija",
}


def candidatas(personales: list[dict], m: Maestros) -> list[dict]:
    """Las filas vivas del libro personal con una obra que no es personal."""
    anuladas = {str(mv.get("anula")) for mv in personales if es_anulacion(mv)}
    salida = []
    for mv in personales:
        if es_anulacion(mv) or str(mv.get("id_mov")) in anuladas or not str(mv.get("obra") or "").strip():
            continue
        obra = m.obra(mv.get("obra"))
        if obra is not None and obra.tipo != "personal":
            salida.append(mv)
    return salida


def dudosas(personales: list[dict], m: Maestros) -> list[str]:
    """Para Valen (M2.2): filas personales sin obra con un rubro de obra, y un contratista que no
    coincide con el destinatario del comprobante («FACHADO, SOFIA» cargado como Sofía Cervera)."""
    anuladas = {str(mv.get("anula")) for mv in personales if es_anulacion(mv)}
    salida = []
    for mv in personales:
        if es_anulacion(mv) or str(mv.get("id_mov")) in anuladas or str(mv.get("obra") or "").strip():
            continue
        rubro = m.rubro(mv.get("rubro_1"), mv.get("rubro_2"))
        if rubro is not None and rubro.afecta in ("obra", "estructura"):
            salida.append(f"{mv['id_mov']} ({mv.get('fecha')}, {mv.get('importe')}, {mv.get('contratista') or mv.get('item')}): "
                          f"sin obra, rubro de {rubro.afecta} «{rubro.rubro_1} › {rubro.rubro_2}»")
        item, contratista = normalizar(mv.get("item")), normalizar(mv.get("contratista"))
        if "fachado" in item and "sofia" in item and "cervera" in contratista:
            salida.append(f"{mv['id_mov']} ({mv.get('fecha')}, {mv.get('importe')}): el comprobante dice «{mv.get('item')}» "
                          f"(la hija) y el contratista es «{mv.get('contratista')}»")
    return salida


def armar(original: dict, m: Maestros) -> tuple[dict, list[str]]:
    """La fila del estudio (sin id_mov ni vinculo todavía) y las notas del pase."""
    notas: list[str] = []
    obra = m.obra(original.get("obra"))
    cuenta = m.cuenta(original.get("cuenta"), incluir_inactivas=True)
    if cuenta is None or not cuenta.suma_al_saldo_del_estudio:
        raise ValueError(f"{original['id_mov']}: la cuenta «{original.get('cuenta')}» no es del estudio")
    if numero(original.get("importe")) <= 0 or original.get("tipo") != "EGRESO":
        raise ValueError(f"{original['id_mov']}: solo se pasan egresos con importe positivo")
    r1, r2 = original.get("rubro_1") or "", original.get("rubro_2") or ""
    rubro = m.rubro(r1, r2)
    vigente = m.vigente(rubro) if rubro is not None else None
    if rubro is None:
        notas.append(f"rubro «{r1} › {r2}» no está en RUBROS: queda como está")
    elif vigente is not rubro:
        notas.append(f"rubro «{r1} › {r2}» → «{vigente.rubro_1} › {vigente.rubro_2}» ({vigente.codigo})")
        r1, r2 = vigente.rubro_1, vigente.rubro_2
    elif not rubro.codigo:
        notas.append(f"rubro «{r1} › {r2}»: de los «a confirmar» (sin código en la lista del estudio), queda como está")
    if rubro is not None and rubro.afecta == "personal":
        notas.append(f"rubro personal «{r1} › {r2}» en una obra: revisar")
    if not str(original.get("contratista") or "").strip():
        notas.append(f"sin contratista en el original (ítem «{original.get('item')}»): queda igual")
    descripcion = " · ".join(x for x in (str(original.get("descripcion") or "").strip(),
                                          f"pasado del libro personal ({original['id_mov']}) el {DIA}") if x)
    fila = {**original,
            "comitente": obra.comitente, "rubro_1": r1, "rubro_2": r2, "tipo_gasto": "obra", "anula": "",
            "concilia": "VERDADERO" if cuenta.concilia_contra_banco else "FALSO",
            "estado_conc": "PENDIENTE" if cuenta.concilia_contra_banco else "SOLO_CAJA", "id_banco": "",
            "descripcion": descripcion, "ts": _ahora_local(), "msg_id": f"{PREFIJO}-{original['id_mov']}#0"}
    return fila, notas


async def pasar(original: dict, estudio, personal, m: Maestros) -> dict:
    """Escribe (o reconoce, si ya estaba) la fila del estudio y el contraasiento del personal.
    Primero la del estudio: si el contraasiento falla, la corrida siguiente lo completa."""
    clave_m, clave_p = f"{PREFIJO}-{original['id_mov']}#0", f"{PREFIJO}-{original['id_mov']}#anula"
    fila_m, notas = armar(original, m)
    async with _lock:
        enc_e, filas_e, movs_e = await asyncio.to_thread(_leer_libro, estudio, "estudio")
        enc_p, filas_p, movs_p = await asyncio.to_thread(_leer_libro, personal, "personal")
        for col in ("vinculo", "anula"):
            if col not in enc_e or col not in enc_p:
                raise RuntimeError(f"Falta la columna «{col}» en MOVIMIENTOS: correr scripts/preparar_sheet.py")
        ya_m = next((mv for mv in movs_e if mv.get("msg_id") == clave_m), None)
        ya_p = next((mv for mv in movs_p if mv.get("msg_id") == clave_p), None)
        otra = next((mv for mv in movs_p if str(mv.get("anula")) == original["id_mov"] and mv.get("msg_id") != clave_p), None)
        if otra:
            raise RuntimeError(f"{original['id_mov']} ya está anulado por {otra['id_mov']} (no por este pase): no se toca")
        id_m = ya_m["id_mov"] if ya_m else _siguiente_id(movs_e, "M")
        id_p = ya_p["id_mov"] if ya_p else _siguiente_id(movs_p, "P")
        fila_m.update(id_mov=id_m, vinculo=id_p)
        contra = {**original, "id_mov": id_p, "importe": -numero(original.get("importe")),
                  "importe_ars": -numero(original.get("importe_ars")), "anula": original["id_mov"],
                  "origen": ORIGEN_ANULACION, "ts": _ahora_local(), "msg_id": clave_p, "vinculo": id_m,
                  "descripcion": f"Anulación de {original['id_mov']} · pasado al libro del estudio como {id_m} el {DIA} "
                                 f"(§5.14 / §6 v1.14)"}
        if not ya_m:
            await asyncio.to_thread(estudio.escribir_filas, len(filas_e) + 1, [[fila_m.get(c, "") for c in enc_e]])
        if not ya_p:
            await asyncio.to_thread(personal.escribir_filas, len(filas_p) + 1, [[contra.get(c, "") for c in enc_p]])
    return {"original": original, "fila_m": ya_m or fila_m, "contra": ya_p or contra, "notas": notas,
            "ya_existia": bool(ya_m and ya_p)}


def mover_comprobante(res: dict, archivador) -> str:
    fila = res["fila_m"]
    file_id = id_drive(str(fila.get("comprobante_url") or ""))
    if not file_id:
        return "sin comprobante en Drive"
    try:
        archivador.archivar(file_id, archivo.carpetas(fila),
                            archivo.nombre_base(fila["id_mov"], {**fila, "importe": numero(fila.get("importe"))}))
        return f"movido a comprobantes/{'/'.join(archivo.carpetas(fila))}/ como «{archivo.nombre_base(fila['id_mov'], fila)}»"
    except Exception as e:  # noqa: BLE001 — lo escrito queda: el comprobante se mueve aparte
        return f"NO se movió ({type(e).__name__}: {e})"


async def correr(args) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    from app.config import settings
    from app.libro import LibroSheets
    s = settings()
    if not s.personal_sheet_id:
        sys.exit("Falta FACHADO_PERSONAL_SHEET_ID")
    m = maestros.cargar(forzar=True)
    real_e, real_p = LibroSheets(), LibroSheets(s.personal_sheet_id)
    if args.aplicar:
        estudio, personal = real_e, real_p
    else:
        from tests.dobles import LibroMemoria
        estudio, personal = LibroMemoria([]), LibroMemoria([])
        for copia, real in ((estudio, real_e), (personal, real_p)):
            filas = real.leer_movimientos()
            copia.encabezado, copia.filas = list(filas[0]), [list(f) for f in filas]
    from app.saldos import como_dicts
    movs_p = como_dicts(personal.leer_movimientos())
    todas = candidatas(movs_p, m)
    print(f"{'APLICANDO' if args.aplicar else 'SIMULACRO'} · filas del libro personal con una obra del estudio: "
          f"{', '.join(mv['id_mov'] for mv in todas) or 'ninguna'}\n")
    resultados, errores = [], 0
    for mv in todas:
        if mv["id_mov"] in RETENIDAS:
            print(f"  · {mv['id_mov']} ({mv.get('obra')}, {mv.get('fecha')}, {mv.get('importe')}): NO se mueve — "
                  f"{RETENIDAS[mv['id_mov']]}\n")
            continue
        try:
            res = await pasar(mv, estudio, personal, m)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {mv['id_mov']}: {e}\n")
            errores += 1
            continue
        resultados.append(res)
        f, c = res["fila_m"], res["contra"]
        print(f"  {'=' if res['ya_existia'] else '+'} {mv['id_mov']} ({f.get('fecha')}, {mv.get('importe')}, {f.get('obra')}, "
              f"{f.get('cuenta')}) → {f['id_mov']} en el estudio · contraasiento {c['id_mov']} en el personal")
        print(f"      rubro {f.get('rubro_1')} › {f.get('rubro_2')} · contratista «{f.get('contratista')}» · "
              f"ítem «{f.get('item')}» · medio {f.get('medio_pago')}")
        for nota in res["notas"]:
            print(f"      nota: {nota}")
        if args.mover and args.aplicar:
            from app.main import obtener_archivador
            print(f"      comprobante: {mover_comprobante(res, obtener_archivador())}")
        print()
    print("Dudosas (no se mueven, van a «Para Valen»):")
    for d in dudosas(movs_p, m) or ["ninguna"]:
        print(f"  · {d}")
    if not args.aplicar:
        print("\n(simulacro: no se escribió nada en los libros reales. Correr con --aplicar)")
    return 1 if errores else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true", help="escribir en los libros reales (sin esto, simulacro)")
    ap.add_argument("--mover", action="store_true", help="con --aplicar, mover y renombrar los comprobantes en Drive")
    return asyncio.run(correr(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
