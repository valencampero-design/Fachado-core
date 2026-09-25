"""Los casos nuevos del handoff del 25/09, con el resultado esperado.

    python -m tests.test_casos

No son mensajes del corpus (el corpus es real y no se toca): son los ejemplos con los que el
proyecto definió cada regla. Corren contra el maestro del snapshot, sin LLM y sin escribir en
ningún Sheet. Donde un caso necesita etapas cargadas, se agregan al maestro en memoria.
"""
import contextlib
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ["MAESTROS_SNAPSHOT"] = str(RAIZ / "maestros_snapshot.json")
    os.environ["LLM_HABILITADO"] = "false"
    os.environ["LEER_ADJUNTOS"] = "false"

    from app import maestros
    from app.filtros import para_conciliacion, para_iva
    from app.interpretar import interpretar
    from app.maestros import Etapa
    from app.models import InterpretarIn
    from app.saldos import saldo_estudio, saldo_obra

    m = maestros.cargar(forzar=True)
    fallas: list[str] = []

    def check(descripcion, condicion, detalle=""):
        ok = bool(condicion)
        print(f"  {'PASA ' if ok else 'FALLA'}  {descripcion}{'' if ok else '  → ' + str(detalle)}")
        if not ok:
            fallas.append(descripcion)

    def leer(texto):
        r = interpretar(InterpretarIn(texto=texto, fecha_mensaje="2026-09-25T12:00:00Z"))
        f = r.fichas[0]
        return r, f, f.campos

    @contextlib.contextmanager
    def con_etapas(*pares):
        """Etapas cargadas solo mientras dura el caso: ETAPAS arranca vacía en el Sheet."""
        agregadas = [Etapa(obra, etapa, "", True) for obra, etapa in pares]
        m.etapas.extend(agregadas)
        try:
            yield
        finally:
            for e in agregadas:
                m.etapas.remove(e)

    def campos_de(r, *nombres):
        return [p.campo for p in r.preguntas if p.campo in nombres]

    # ── Tanda 2 · el token de obra ────────────────────────────────────────────
    print("\nTanda 2 · <obra>[<etapa>][C] (§5.15, §5.8)")
    with con_etapas(("Lennon", "1")):
        r, f, c = leer("Barba/Lennon1C")
        check("Barba/Lennon1C → Lennon, etapa 1, Caja obra Lennon",
              c["obra"] == "Lennon" and c["etapa"] == "1" and c["cuenta"] == "Caja obra Lennon", c)
    r, f, c = leer("Barba/LennonC")
    check("Barba/LennonC → Lennon, sin etapa, Caja obra Lennon",
          c["obra"] == "Lennon" and not c["etapa"] and c["cuenta"] == "Caja obra Lennon", c)
    r, f, c = leer("Barba/Lennon1")
    check("Barba/Lennon1 con Lennon sin etapas → etapa vacía y advertencia",
          c["obra"] == "Lennon" and not c["etapa"] and any("no tiene etapas" in a for a in f.extras.get("advertencias", [])),
          (c["etapa"], f.extras.get("advertencias")))
    r, f, c = leer("barba/lennon1c")
    check("mayúsculas y minúsculas dan igual", c["obra"] == "Lennon" and c["cuenta"] == "Caja obra Lennon", c)
    r, f, c = leer("Barba/Lennon/caja")
    check("la palabra suelta «caja» equivale a la C", c["cuenta"] == "Caja obra Lennon", c["cuenta"])
    r, f, c = leer("Barba/GonzaloC")
    check("C en una obra sin caja (obra propia): no inventa la cuenta, pregunta y avisa",
          not c["cuenta"] and campos_de(r, "cuenta") and any("no tiene caja" in a for a in f.extras.get("advertencias", [])),
          (c["cuenta"], [p.texto for p in r.preguntas]))
    with con_etapas(("Lennon", "1"), ("Lennon", "2")):
        r, f, c = leer("Barba/Lennon")
        preg = [p for p in r.preguntas if p.campo == "etapa"]
        check("obra con etapas y el mensaje no dice cuál: pregunta con una opción por etapa",
              preg and preg[0].opciones == ["1", "2"], [(p.campo, p.opciones) for p in r.preguntas])
    r, f, c = leer("Barba/Lennon")
    check("obra sin etapas: nunca pregunta la etapa", not campos_de(r, "etapa"), [p.campo for p in r.preguntas])

    print("\nTanda 2 · ingresos de obras administradas (§5.8)")
    r, f, c = leer("Ingreso Moreno/cert. 4/efectivo $2.600.000")
    check("Ingreso Moreno/cert. 4/efectivo → INGRESO, Caja obra Moreno, certificado 4",
          c["tipo"] == "INGRESO" and c["cuenta"] == "Caja obra Moreno" and f.extras.get("certificado") == "4"
          and c["medio_pago"] == "Efectivo", (c["tipo"], c["cuenta"], c["medio_pago"], f.extras.get("certificado")))
    r, f, c = leer("Ingreso Moreno/honorarios $500.000")
    check("Ingreso Moreno/honorarios → INGRESO a la caja del estudio, sin preguntar el concepto",
          c["tipo"] == "INGRESO" and (not c["cuenta"] or m.cuenta(c["cuenta"]).suma_al_saldo_del_estudio)
          and not campos_de(r, "concepto"), (c["cuenta"], [p.campo for p in r.preguntas]))
    r, f, c = leer("Ingreso Moreno $1.000.000")
    check("ingreso en obra administrada que no dice certificado ni honorarios: pregunta",
          campos_de(r, "concepto") and c["cuenta"] != "Caja obra Moreno", [p.campo for p in r.preguntas])

    print("\nTanda 2 · depósitos en negro (§5.17)")
    r, f, c = leer("Deposito Marcelo/Moreno $300.000")
    check("Deposito Marcelo/Moreno → PASANTE, informal = sí, Moreno",
          c["tipo"] == "PASANTE" and c["informal"] == "sí" and c["obra"] == "Moreno", (c["tipo"], c["informal"], c["obra"]))
    r, f, c = leer("Depósito Felipe J/Lennon $150.000")
    check("con tilde también, y sin cuenta: no toca la caja del estudio",
          c["tipo"] == "PASANTE" and not c["cuenta"], (c["tipo"], c["cuenta"]))
    pasante = {"id_mov": "M-X", "tipo": "PASANTE", "obra": "Moreno", "importe_ars": 300000, "informal": "sí", "cuenta": ""}
    normal = {"id_mov": "M-Y", "tipo": "EGRESO", "obra": "Moreno", "importe_ars": 1000, "informal": "", "cuenta": "Banco"}
    antes, _ = saldo_obra([normal], "Moreno", m)
    despues, _ = saldo_obra([normal, pasante], "Moreno", m)
    check("el pasante suma a lo adelantado y a lo pagado, y el saldo de la obra no se mueve",
          despues.adelantado - antes.adelantado == 300000
          and despues.pagado_con_plata_del_estudio - antes.pagado_con_plata_del_estudio == 300000
          and despues.saldo == antes.saldo, (antes, despues))
    check("no toca el saldo del estudio",
          saldo_estudio([normal], m)["total"] == saldo_estudio([normal, pasante], m)["total"])
    check("queda fuera del IVA y de la conciliación",
          para_iva([normal, pasante]) == [normal] and para_conciliacion([normal, pasante]) == [normal])

    # ── Tanda 3 · duplicados entre usuarios y período de prueba ──────────────
    import json

    from app import comprobante
    from app.maestros import Usuario
    from app.models import Adjunto
    from tests.dobles import LibroMemoria

    encabezado = json.loads((RAIZ / "maestros_snapshot.json").read_text(encoding="utf-8"))["MOVIMIENTOS"][0]
    titular = next(u for u in m.usuarios if u.rol == "titular")

    def libro(*filas):
        lib = LibroMemoria(encabezado)
        for f in filas:
            lib.sembrar(**f)
        return lib

    def lector_con(**leido):
        """Un comprobante «leído» sin bajar nada: nombre de archivo real más los datos dados."""
        def lector(adj):
            d = comprobante.DatosComprobante(url=adj.url, nombre_archivo=adj.nombre or "", sha256=adj.sha256)
            d.completar(comprobante.parsear_nombre(adj.nombre or ""), "nombre_archivo")
            d.completar(leido, "pdf_texto")
            return d
        return lector

    def leer_con(texto, estudio=None, personal=None, telefono=None, adjuntos=(), lector=None):
        r = interpretar(InterpretarIn(texto=texto, fecha_mensaje="2026-09-25T12:00:00Z",
                                      telefono=telefono or titular.telefono, adjuntos=list(adjuntos)),
                        libros={"estudio": estudio or libro(), "personal": personal}, lector=lector)
        return r, r.fichas[0]

    transferencia_eco = dict(id_mov="M-000001", fecha="2026-08-27", tipo="EGRESO", importe=4032391.7,
                             obra="Lennon", contratista="Eco Aislación SRL", cargado_por="Gabriel Fachado",
                             ref_comprobante="op:LR8S9fk909")
    cheque_510 = Adjunto(url="https://drive.google.com/file/d/CHEQUE510xxxxxxxxxxxxxxxx/view", mime="application/pdf",
                         nombre="Cheque510_ECO AISLACION SRL_30715065157.pdf")

    print("\nTanda 3 · el mismo hecho cargado dos veces (§5.16)")
    r, f = leer_con("Ecoaislaciones/Lennon", estudio=libro(transferencia_eco), adjuntos=[cheque_510],
                    lector=lector_con(importe=4032391.7, fecha="2026-08-27"))
    dup = f.posible_duplicado
    check("cheque 510 vs transferencia a Eco Aislación: probable, pregunta y NO se fusiona",
          dup and dup.fuerza == "probable" and dup.id_mov == "M-000001" and f.campos["importe"] == 4032391.7
          and any(p.campo == "duplicado" and p.motivo == "posible_duplicado" for p in r.preguntas),
          (dup, [p.campo for p in r.preguntas]))
    check("la ficha nueva guarda su propia referencia (el cheque), distinta de la del libro",
          "cheque:510" in (f.campos["ref_comprobante"] or ""), f.campos["ref_comprobante"])

    austral_1 = dict(id_mov="M-000010", fecha="2026-09-04", tipo="EGRESO", importe=150000, obra="Austral",
                     cargado_por="Gabriel Fachado")
    r, f = leer_con("AUSTRAL/IVA $150.000 04/09/26", estudio=libro(austral_1))
    check("el segundo AUSTRAL/IVA del 4/9: probable, pregunta",
          f.posible_duplicado and f.posible_duplicado.fuerza == "probable", f.posible_duplicado)
    check("el texto dice quién lo cargó y cuándo",
          any("Ya cargaste un pago igual el 4/9" in p.texto for p in r.preguntas), [p.texto for p in r.preguntas])

    de_petrus = dict(transferencia_eco, cargado_por="Petrus", ref_comprobante="sha256:abc123")
    r, f = leer_con("Ecoaislaciones/Lennon", estudio=libro(de_petrus),
                    adjuntos=[Adjunto(url="https://drive.google.com/file/d/OTROxxxxxxxxxxxxxxxxxxxxx/view", sha256="abc123")],
                    lector=lector_con(importe=999, fecha="2026-09-20"))
    check("mismo archivo (sha256), aunque cambie todo lo demás: fuerte",
          f.posible_duplicado and f.posible_duplicado.fuerza == "fuerte", f.posible_duplicado)
    check("«Petrus ya cargó un pago igual el 27/8»",
          any(p.texto.startswith("Petrus ya cargó un pago igual el 27/8") for p in r.preguntas), [p.texto for p in r.preguntas])

    r, f = leer_con("AUSTRAL/IVA $999.999 04/09/26", estudio=libro(austral_1))
    check("otro importe: no es duplicado", f.posible_duplicado is None, f.posible_duplicado)

    sin_personal = Usuario("5490000000001", "Reemplazo de prueba", "colaborador", True, ve_personal=False)
    m.usuarios.append(sin_personal)
    try:
        personal = libro(dict(austral_1, id_mov="P-000001"))
        r, f = leer_con("AUSTRAL/IVA $150.000 04/09/26", personal=personal, telefono=sin_personal.telefono)
        check("quien no ve lo personal no recibe duplicados del libro personal", f.posible_duplicado is None, f.posible_duplicado)
        r, f = leer_con("AUSTRAL/IVA $150.000 04/09/26", personal=personal)
        check("quien lo ve, sí", f.posible_duplicado and f.posible_duplicado.libro == "personal", f.posible_duplicado)
    finally:
        m.usuarios.remove(sin_personal)

    print("\nTanda 3 · período de prueba (§5.12)")
    felipe = Adjunto(url="https://drive.google.com/file/d/FELIPExxxxxxxxxxxxxxxxxxx/view", mime="application/pdf")
    claro = lector_con(importe=300000, fecha="2026-09-02", cuit="20-40613900-0")
    r, f = leer_con("Felipe J/Lennon", adjuntos=[felipe], lector=claro)
    check("auto_confirmar = no (los dos usuarios hoy): siempre requiere confirmación",
          f.requiere_confirmacion and r.requiere_confirmacion)
    auto = Usuario("5490000000002", "Usuario con alta", "colaborador", True, ve_personal=True, auto_confirmar=True)
    m.usuarios.append(auto)
    try:
        r, f = leer_con("Felipe J/Lennon", adjuntos=[felipe], lector=claro, telefono=auto.telefono)
        check("auto_confirmar = sí y todo claro: no requiere confirmación",
              not f.requiere_confirmacion and not r.requiere_confirmacion,
              (f.origen_campo.get("importe"), [p.campo for p in r.preguntas], f.conflictos))
        r, f = leer_con("Felipe J/Lennon", adjuntos=[felipe], lector=claro, telefono=auto.telefono,
                        estudio=libro(dict(id_mov="M-000003", fecha="2026-09-02", tipo="EGRESO", importe=300000,
                                           obra="Lennon", contratista="Felipe Andrés Scherer", cargado_por="Petrus")))
        check("… pero con posible duplicado, sí requiere", f.requiere_confirmacion, f.posible_duplicado)
        r, f = leer_con("Barba/Lennon", telefono=auto.telefono)
        check("… y sin comprobante, también", f.requiere_confirmacion)
    finally:
        m.usuarios.remove(auto)

    print(f"\n{'TODO OK' if not fallas else str(len(fallas)) + ' FALLAS'}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
