"""Corre el corpus real contra /interpretar y reporta aciertos.

    python -m tests.test_corpus                 # maestros del snapshot, con LLM
    python -m tests.test_corpus --sin-llm       # solo diccionario
    python -m tests.test_corpus --sheet         # maestros del Sheet real (requiere OAuth)
    python -m tests.test_corpus --url http://localhost:8000   # contra un motor corriendo

Métrica del proyecto: % de mensajes que resuelven obra y contratista sin preguntar, en total
y **por usuario** (CONTEXTO-FACHADO.md §5.13: el corpus es del arquitecto; cómo escribe Petrus
no se sabe todavía). Si el CSV trae una columna `telefono`, cada fila se atribuye a ese
usuario; si no, al titular de USUARIOS. El teléfono nunca está escrito en el código.

El corpus es la hoja CAPTURA: una fila por evento de WhatsApp. Un texto y sus adjuntos
llegan como filas separadas, a veces el adjunto ANTES que el texto. Acá se reagrupan en
mensajes (lo que en producción hará el gateway): cada adjunto sin caption va con el texto
más cercano dentro de VENTANA_ADJUNTO segundos.
"""
import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
VENTANA_ADJUNTO = 90
VENTANA_CORRECCION = 120


@dataclass
class Mensaje:
    ts: datetime
    texto: str
    adjuntos: list[dict] = field(default_factory=list)
    es_correccion: bool = False
    filas: list[int] = field(default_factory=list)
    telefono: str = ""


def agrupar(filas: list[dict], telefono_por_defecto: str) -> list[Mensaje]:
    """Agrupa por usuario: el adjunto de uno nunca se pega al texto de otro, y una corrección
    corrige el mensaje anterior de la misma persona."""
    por_usuario: dict[str, list[tuple[int, dict]]] = {}
    for i, f in enumerate(filas, start=2):
        por_usuario.setdefault((f.get("telefono") or "").strip() or telefono_por_defecto, []).append((i, f))
    mensajes = [msg for tel, suyas in por_usuario.items() for msg in _agrupar_uno(suyas, tel)]
    return sorted(mensajes, key=lambda m: m.ts)


def _agrupar_uno(filas: list[tuple[int, dict]], telefono: str) -> list[Mensaje]:
    mensajes: list[Mensaje] = []
    sueltos: list[tuple[int, datetime, dict]] = []
    for i, f in filas:
        if f["tipo"] == "unsupported":
            continue
        ts = datetime.fromisoformat(f["timestamp_utc"])
        texto = (f["texto"] or f["caption"] or f["transcripcion"] or "").strip()
        adjunto = {"url": f["archivo_url"], "mime": f["mime"]} if f["tipo"] in ("image", "document", "audio") else None
        if texto:
            mensajes.append(Mensaje(ts, texto, [adjunto] if adjunto else [], filas=[i], telefono=telefono))
        elif adjunto:
            sueltos.append((i, ts, adjunto))

    anterior = None
    for msg in mensajes:
        sin_barra = "/" not in re.sub(r"\d{1,2}/\d{1,2}/\d{2,4}", "", msg.texto)
        # Un texto corto sin «/» que llega enseguida del anterior corrige al anterior, salvo
        # que sea un movimiento nuevo («Pago Moreno») o traiga su propio adjunto al lado.
        movimiento_nuevo = re.match(r"^\s*(pago|ingreso)\b", msg.texto, re.I)
        adjunto_al_lado = any(0 <= (ts - msg.ts).total_seconds() <= 10 for _, ts, _ in sueltos)
        msg.es_correccion = bool(
            re.match(r"^\s*correcci[oó]n", msg.texto, re.I)
            or re.fullmatch(r"\s*\d{1,2}/\d{1,2}/\d{2,4}\s*", msg.texto)
            or "=" in msg.texto
            or (sin_barra and not msg.adjuntos and not movimiento_nuevo and not adjunto_al_lado and anterior
                and (msg.ts - anterior.ts).total_seconds() <= VENTANA_CORRECCION)
        )
        anterior = msg

    anclas = [m for m in mensajes if not m.es_correccion]
    for i, ts, adjunto in sueltos:
        cerca = [(abs((m.ts - ts).total_seconds()), m) for m in anclas]
        cerca = [(d, m) for d, m in cerca if d <= VENTANA_ADJUNTO]
        if cerca:
            _, m = min(cerca, key=lambda x: (x[0], x[1].ts))
            m.adjuntos.append(adjunto)
            m.filas.append(i)
        else:
            mensajes.append(Mensaje(ts, "", [adjunto], filas=[i], telefono=telefono))
    return mensajes


# ─── Casos que tienen que pasar ────────────────────────────────────────────────

def _p(resp, campo):
    return any(p["campo"] == campo for p in resp["preguntas"])


CASOS = {
    "Felipe J/Lennon": lambda r, f: f["campos"]["obra"] == "Lennon" and f["campos"]["contratista"] == "Felipe Andrés Scherer",
    "Austral/Sofi": lambda r, f: f["campos"]["obra"] == "Austral" and f["campos"]["contratista"] == "Sofia Cervera" and _p(r, "clasificacion"),
    "Retiro/club/cuota 3 esquí": lambda r, f: f["campos"]["tipo_gasto"] == "personal" and f["campos"]["rubro_2"] == "Club y deporte",
    # CONTEXTO-FACHADO.md §5.4: «Retiro» manda siempre. Es material eléctrico para su casa,
    # no una obra sin imputar; el proveedor se conserva y no se pregunta la obra.
    "Electricidad Angostura/Retiro": lambda r, f: f["campos"]["tipo_gasto"] == "personal"
                                                  and f["campos"]["contratista"] == "Electricidad Angostura"
                                                  and f["campos"]["obra"] is None and not _p(r, "obra"),
    # CONTEXTO-FACHADO.md §5.8: las certificaciones de Moreno son plata de la obra y van a su
    # caja, no a la del estudio. «/efectivo» dice cómo se cobró, no a qué cuenta entra.
    "Ingreso $2.600.000 Moreno/ cert. 4 /efectivo": lambda r, f: f["campos"]["tipo"] == "INGRESO" and f["campos"]["importe"] == 2600000
                                                                 and f["campos"]["obra"] == "Moreno" and f["extras"].get("certificado") == "4"
                                                                 and f["campos"]["cuenta"] == "Caja obra Moreno"
                                                                 and f["campos"]["medio_pago"] == "Efectivo",
    "Maragaño/Retiro/casa": lambda r, f: f["campos"]["tipo_gasto"] == "personal" and f["campos"]["rubro_2"] == "Casa"
                                         and f["campos"]["contratista"] == "Marcelo Maragaño",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-llm", action="store_true", help="solo diccionario")
    ap.add_argument("--sheet", action="store_true", help="leer maestros del Sheet real")
    ap.add_argument("--url", help="URL de un motor corriendo (si no, se llama in-process)")
    ap.add_argument("--adjuntos", action="store_true", help="bajar y leer los adjuntos (requiere OAuth)")
    ap.add_argument("--salida", default=str(RAIZ / "salida" / "corpus.json"))
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    import logging
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)

    if not args.sheet:
        os.environ["MAESTROS_SNAPSHOT"] = str(RAIZ / "maestros_snapshot.json")
    if args.sin_llm:
        os.environ["LLM_HABILITADO"] = "false"
    if not args.adjuntos:
        os.environ["LEER_ADJUNTOS"] = "false"
    os.environ.setdefault("MOTOR_API_KEY", "test-local")

    if args.url:
        import httpx
        cliente = httpx.Client(base_url=args.url, timeout=120)
    else:
        from fastapi.testclient import TestClient

        from app.main import app, obtener_libro, obtener_libro_personal
        from tests.dobles import LibroMemoria
        # Libros vacíos: la búsqueda de duplicados (§5.16) no puede depender de lo que haya en
        # el libro real, o la métrica dejaría de ser reproducible.
        encabezado = json.loads((RAIZ / "maestros_snapshot.json").read_text(encoding="utf-8"))["MOVIMIENTOS"][0]
        app.dependency_overrides[obtener_libro] = lambda: LibroMemoria(encabezado)
        app.dependency_overrides[obtener_libro_personal] = lambda: LibroMemoria(encabezado)
        cliente = TestClient(app)
    headers = {"X-API-Key": os.environ["MOTOR_API_KEY"]}

    from app import maestros
    m = maestros.cargar()
    titular = next((u for u in m.usuarios if u.rol == "titular"), None)
    if titular is None:
        print("No hay titular en USUARIOS: no se sabe a quién atribuir el corpus")
        return 1
    nombres = {u.telefono: u.nombre for u in m.usuarios}

    with open(RAIZ / "corpus.csv", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    mensajes = agrupar(filas, titular.telefono)

    resultados = []
    previa: dict[str, dict] = {}  # la última ficha de cada usuario
    for msg in mensajes:
        cuerpo = {
            "telefono": msg.telefono,
            "texto": msg.texto,
            "adjuntos": msg.adjuntos,
            "fecha_mensaje": msg.ts.isoformat(),
            "contexto_previo": previa.get(msg.telefono) if msg.es_correccion else None,
        }
        resp = cliente.post("/interpretar", json=cuerpo, headers=headers)
        resp.raise_for_status()
        r = resp.json()
        resultados.append({"mensaje": msg, "respuesta": r})
        if msg.texto:
            previa[msg.telefono] = r["fichas"][0]

    # ── Métricas ───────────────────────────────────────────────────────────────
    con_texto = [x for x in resultados if x["mensaje"].texto]
    solo_adjunto = [x for x in resultados if not x["mensaje"].texto]
    nuevos = [x for x in con_texto if not x["mensaje"].es_correccion]

    def sin_pregunta(x, campos):
        return not any(p["campo"] in campos for p in x["respuesta"]["preguntas"])

    def usa_llm(x):
        return x["respuesta"]["diagnostico"].get("uso_llm")

    # Un dual y un apodo ambiguo preguntan porque el maestro dice que hay que preguntar:
    # son diseño, no fallas del parser.
    def deliberada(x):
        preguntas = x["respuesta"]["preguntas"]
        de_imputacion = [p for p in preguntas if p["campo"] in ("obra", "clasificacion", "contratista")]
        return bool(de_imputacion) and all(p["motivo"] in ("dual", "apodo_ambiguo") for p in de_imputacion)

    def medir(nuevos: list) -> dict:
        ambos = [x for x in nuevos if sin_pregunta(x, {"obra", "clasificacion", "contratista"})]
        return {
            "n": len(nuevos),
            "obra": [x for x in nuevos if sin_pregunta(x, {"obra", "clasificacion"})],
            "contratista": [x for x in nuevos if sin_pregunta(x, {"contratista"})],
            "ambos": ambos,
            "diseno": [x for x in nuevos if x in ambos or deliberada(x)],
            "duales": [x for x in nuevos if any(p["motivo"] == "dual" for p in x["respuesta"]["preguntas"])],
            "ambiguos": [x for x in nuevos if any(p["motivo"] == "apodo_ambiguo" for p in x["respuesta"]["preguntas"])],
        }

    total = medir(nuevos)
    obra_ok, contr_ok, ambos_ok = total["obra"], total["contratista"], total["ambos"]
    ambos_ok_sin_duales, duales, ambiguos = total["diseno"], total["duales"], total["ambiguos"]
    con_llm = [x for x in con_texto if usa_llm(x)]
    n = total["n"]

    def pct(a, n=n):
        return f"{len(a)}/{n} ({100 * len(a) / n:.0f}%)" if n else "0/0"

    modo = "solo diccionario" if args.sin_llm else "diccionario + LLM"
    print(f"\nCorpus: {len(filas)} filas → {len(resultados)} mensajes "
          f"({len(nuevos)} con texto, {len(con_texto) - len(nuevos)} correcciones, {len(solo_adjunto)} adjuntos sin texto)")
    print(f"Modo: {modo}\n")
    print(f"{'texto':<62} {'tipo':<8} {'clasif':<10} {'obra':<12} {'contratista':<24} {'rubro_2':<16} {'preguntas':<22} llm")
    print("─" * 165)
    for x in con_texto:
        r = x["respuesta"]
        for i, f in enumerate(r["fichas"]):
            c = f["campos"]
            preg = ",".join(p["campo"] for p in r["preguntas"] if p["ficha"] == i)
            marca = "↺ " if x["mensaje"].es_correccion else ""
            texto = (marca + x["mensaje"].texto) if i == 0 else "  └ 2º movimiento"
            # Una ficha CERTIFICADO (§5.11) no tiene columnas de gasto: de ahí los .get.
            print(f"{texto[:61]:<62} {(c.get('tipo') or '')[:8]:<8} {c.get('tipo_gasto') or '—':<10} {(c.get('obra') or '—')[:11]:<12} "
                  f"{(c.get('contratista') or '—')[:23]:<24} {(c.get('rubro_2') or '—')[:15]:<16} {preg or '—':<22} "
                  f"{'sí' if usa_llm(x) and i == 0 else ''}")

    print(f"\nMensajes nuevos con texto: {n} (las correcciones se evalúan aparte, llegan con contexto_previo)")
    print(f"  Obra/destino resuelto sin preguntar:  {pct(obra_ok)}")
    print(f"  Contratista resuelto sin preguntar:   {pct(contr_ok)}")
    print(f"  Obra Y contratista sin preguntar:     {pct(ambos_ok)}")
    print(f"  ídem, con las preguntas de diseño:    {pct(ambos_ok_sin_duales)}  "
          f"({len(duales)} duales + {len(ambiguos)} apodos ambiguos, que preguntan a propósito)")
    print(f"  Necesitaron LLM:                      {len(con_llm)}/{len(con_texto)}  "
          f"(solo diccionario: {len(con_texto) - len(con_llm)})")
    print(f"  Adjuntos sin texto (no se pueden imputar sin leer el comprobante): {len(solo_adjunto)}")

    print("\nPor usuario (obra y contratista sin preguntar · con las preguntas de diseño):")
    for tel in sorted({x["mensaje"].telefono for x in nuevos}):
        suyos = medir([x for x in nuevos if x["mensaje"].telefono == tel])
        print(f"  {nombres.get(tel, 'desconocido (' + tel + ')'):<22} {pct(suyos['ambos'], suyos['n']):<14} · "
              f"{pct(suyos['diseno'], suyos['n'])}")

    fallas = [x for x in nuevos if x not in ambos_ok]
    if fallas:
        print("\nPreguntaron obra o contratista:")
        for x in fallas:
            preg = "; ".join(f"{p['campo']}: {p['texto']}" for p in x["respuesta"]["preguntas"]
                             if p["campo"] in ("obra", "clasificacion", "contratista"))
            print(f"  fila {x['mensaje'].filas[0]:>3}  {x['mensaje'].texto!r:<50} → {preg}")

    print("\nCasos obligatorios:")
    fallidos = 0
    for texto, chequeo in CASOS.items():
        x = next((x for x in con_texto if x["mensaje"].texto == texto), None)
        ok = bool(x) and chequeo(x["respuesta"], x["respuesta"]["fichas"][0])
        fallidos += not ok
        detalle = ""
        if x and not ok:
            f = x["respuesta"]["fichas"][0]
            c = f["campos"]
            detalle = (f"  → tipo={c.get('tipo')} tipo_gasto={c.get('tipo_gasto')} obra={c.get('obra')} contratista={c.get('contratista')} "
                       f"rubro={c.get('rubro_2')} preguntas={[p['campo'] for p in x['respuesta']['preguntas']]} regla={f['regla']}")
        print(f"  {'PASA ' if ok else 'FALLA'}  {texto}{detalle}")

    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    with open(salida, "w", encoding="utf-8") as f:
        json.dump([{"filas": x["mensaje"].filas, "texto": x["mensaje"].texto, "es_correccion": x["mensaje"].es_correccion,
                    "adjuntos": x["mensaje"].adjuntos, "respuesta": x["respuesta"]} for x in resultados],
                  f, ensure_ascii=False, indent=2, default=str)
    print(f"\nDetalle completo: {salida}")
    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main())
