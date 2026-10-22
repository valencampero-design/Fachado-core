"""Lista las filas de MOVIMIENTOS escritas desde una hora dada. SOLO LECTURA: no escribe nada.

Para el incidente de Railway (docs/seguridad/rotacion-2026-10-22.md en chatbot-contable): ver si
alguna fila del Master o de «FACHADO — Personal» no la escribió el bot.

    railway run --service web python scripts/movimientos_desde.py
    python scripts/movimientos_desde.py --desde 2026-10-21T07:00Z      # el default
    python scripts/movimientos_desde.py --csv salida.csv               # además, a un CSV local

Lee con la service account (GOOGLE_CREDENTIALS_JSON o GOOGLE_CREDENTIALS_PATH) los libros de
FACHADO_SHEET_ID y FACHADO_PERSONAL_SHEET_ID. Ojo: si la service account ya se rotó, usar la nueva.

Qué muestra, por libro:
- cada fila con `ts` (hora local de la carga, UTC−3) desde el corte, con cargado_por, origen y
  msg_id;
- marcadas con «!», las que no tienen la forma de lo que escribe el motor: msg_id vacío o que no
  empieza con wamid. / cierre: / banco:, origen que no es WHATSAPP/CIERRE/ANULACION/BANCO,
  cargado_por que no está en USUARIOS, o sin ts;
- las filas sin ts o con un ts anterior al corte que están DESPUÉS de una fila nueva: el libro es
  append-only, así que eso es una fila agregada a mano con una hora vieja (o editada).

No reemplaza el historial de versiones del Sheet (Archivo → Historial de versiones): una celda
editada en una fila vieja no se ve acá.
"""
import argparse
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app import seguridad, sheets  # noqa: E402
from app.config import settings  # noqa: E402

COLUMNAS = ["id_mov", "ts", "fecha", "tipo", "importe", "moneda", "obra", "contratista", "cuenta", "cargado_por",
            "origen", "msg_id", "anula"]
# Lo que escribe el motor (app/confirmar.py, cierre.py, anular.py, conciliar.py). Una migración o
# los saldos de apertura pueden escribir otra cosa: si aparece, mirarla, no es por sí sola un ataque.
ORIGENES_DEL_MOTOR = {"WHATSAPP", "CIERRE", "ANULACION", "BANCO"}
PREFIJOS_MSG_ID = ("wamid.", "cierre:", "banco:")


def _corte(texto: str, offset_horas: int) -> datetime:
    """El corte en hora local del libro (el ts se escribe en hora local, sin zona)."""
    t = texto.strip().upper().replace("Z", "+00:00")
    dt = datetime.fromisoformat(t)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(timedelta(hours=offset_horas))).replace(tzinfo=None)


def _ts(valor) -> datetime | None:
    texto = str(valor or "").strip()
    for formato in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None


def _usuarios(sheet_id: str) -> set[str]:
    filas = sheets.leer_rango(sheet_id, "USUARIOS!A:Z", formato="FORMATTED_VALUE")
    if not filas:
        return set()
    enc = [str(c).strip().lower() for c in filas[0]]
    if "nombre" not in enc:
        return set()
    i = enc.index("nombre")
    return {str(f[i]).strip() for f in filas[1:] if len(f) > i and str(f[i]).strip()}


def _rara(fila: dict, usuarios: set[str]) -> list[str]:
    motivos = []
    msg = str(fila.get("msg_id") or "")
    if not msg:
        motivos.append("sin msg_id")
    elif not msg.startswith(PREFIJOS_MSG_ID):
        motivos.append("msg_id que no es wamid./cierre:/banco:")
    origen = str(fila.get("origen") or "").strip().upper()
    if origen and origen not in ORIGENES_DEL_MOTOR:
        motivos.append(f"origen {origen}")
    quien = str(fila.get("cargado_por") or "").strip()
    if usuarios and quien and quien not in usuarios:
        motivos.append("cargado_por fuera de USUARIOS")
    if not quien:
        motivos.append("sin cargado_por")
    if _ts(fila.get("ts")) is None:
        motivos.append("sin ts")
    return motivos


def revisar(nombre: str, sheet_id: str, corte: datetime, usuarios: set[str], salida_csv) -> int:
    print(f"\n══ {nombre}")
    filas = sheets.leer_rango(sheet_id, "MOVIMIENTOS!A:AZ", formato="FORMATTED_VALUE")
    if not filas:
        print("  (vacío)")
        return 0
    enc = [str(c).strip() for c in filas[0]]
    registros = [(n, dict(zip(enc, f))) for n, f in enumerate(filas[1:], start=2) if any(str(c).strip() for c in f)]
    print(f"  {len(registros)} filas en total; la última es la {registros[-1][0] if registros else '-'}")

    nuevas, fuera_de_orden = [], []
    vista_una_nueva = False
    for n, fila in registros:
        t = _ts(fila.get("ts"))
        if t is not None and t >= corte:
            nuevas.append((n, fila))
            vista_una_nueva = True
        elif vista_una_nueva:
            fuera_de_orden.append((n, fila, "sin ts" if t is None else f"ts {fila.get('ts')} anterior al corte"))

    print(f"  {len(nuevas)} filas con ts desde {corte:%Y-%m-%d %H:%M} (hora local)")
    raras = 0
    for n, fila in nuevas:
        motivos = _rara(fila, usuarios)
        raras += bool(motivos)
        marca = "!" if motivos else " "
        print(f"  {marca} fila {n:>5}  {fila.get('id_mov', ''):<10} {fila.get('ts', ''):<16} {fila.get('tipo', ''):<9}"
              f" {fila.get('importe', ''):>14} {fila.get('moneda', ''):<3}  cargado_por={fila.get('cargado_por', '')!s:<18}"
              f" origen={fila.get('origen', '')!s:<9} msg_id={fila.get('msg_id', '')}"
              + (f"   ← {', '.join(motivos)}" if motivos else ""))
        if salida_csv:
            salida_csv.writerow([nombre, n] + [fila.get(c, "") for c in COLUMNAS] + ["; ".join(motivos)])
    if fuera_de_orden:
        print(f"  ! {len(fuera_de_orden)} filas DESPUÉS de una fila nueva pero sin ts nuevo (¿agregadas a mano?):")
        for n, fila, motivo in fuera_de_orden:
            print(f"  ! fila {n:>5}  {fila.get('id_mov', ''):<10} cargado_por={fila.get('cargado_por', '')} "
                  f"msg_id={fila.get('msg_id', '')}   ← {motivo}")
            if salida_csv:
                salida_csv.writerow([nombre, n] + [fila.get(c, "") for c in COLUMNAS] + [motivo])
    return raras + len(fuera_de_orden)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    seguridad.instalar_filtro_logs()
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--desde", default="2026-10-21T07:00Z", help="ISO 8601; sin zona = UTC (default: 2026-10-21T07:00Z)")
    p.add_argument("--csv", help="además, guardar las filas listadas en este CSV")
    args = p.parse_args()
    s = settings()
    if not s.sheet_id:
        print("Falta FACHADO_SHEET_ID")
        return 2
    corte = _corte(args.desde, s.utc_offset_horas)
    print(f"Corte: {args.desde} = {corte:%Y-%m-%d %H:%M} hora local (UTC{s.utc_offset_horas:+d}). Solo lectura.")
    try:
        usuarios = _usuarios(s.sheet_id)
    except Exception as e:  # noqa: BLE001
        print(f"No pude leer USUARIOS ({type(e).__name__}): no se marca cargado_por")
        usuarios = set()
    archivo = open(args.csv, "w", newline="", encoding="utf-8") if args.csv else None
    escritor = csv.writer(archivo) if archivo else None
    if escritor:
        escritor.writerow(["libro", "fila"] + COLUMNAS + ["motivo"])
    marcadas = 0
    try:
        libros = [("Master «FACHADO — Gestión de Obras»", s.sheet_id)]
        if s.personal_sheet_id:
            libros.append(("«FACHADO — Personal»", s.personal_sheet_id))
        else:
            print("FACHADO_PERSONAL_SHEET_ID vacía: no se revisa el libro personal")
        for nombre, sid in libros:
            try:
                marcadas += revisar(nombre, sid, corte, usuarios, escritor)
            except Exception as e:  # noqa: BLE001
                print(f"  No pude leer {nombre}: {seguridad.redactar(type(e).__name__ + ': ' + str(e))[:200]}")
                marcadas += 1
    finally:
        if archivo:
            archivo.close()
    print(f"\n{marcadas} fila(s) para mirar a mano" if marcadas else "\nNinguna fila con forma rara.")
    return 1 if marcadas else 0


if __name__ == "__main__":
    sys.exit(main())
