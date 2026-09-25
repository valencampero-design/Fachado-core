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
    check("Deposito Marcelo/Moreno → PASANTE, informal = VERDADERO, Moreno",
          c["tipo"] == "PASANTE" and c["informal"] == "VERDADERO" and c["obra"] == "Moreno", (c["tipo"], c["informal"], c["obra"]))
    r, f, c = leer("Depósito Felipe J/Lennon $150.000")
    check("con tilde también, en «Pagado por el comitente», sin conciliar (§5.17 v1.6)",
          c["tipo"] == "PASANTE" and c["cuenta"] == "Pagado por el comitente" and c["concilia"] == "FALSO",
          (c["tipo"], c["cuenta"], c["concilia"]))
    r, f, c = leer("Depósito Felipe J/Lennon/Banco $150.000")
    check("aunque el texto diga otra cuenta: la fija el motor y avisa",
          c["cuenta"] == "Pagado por el comitente" and any("Pagado por el comitente" in a for a in f.extras.get("advertencias", [])),
          (c["cuenta"], f.extras.get("advertencias")))
    pasante = {"id_mov": "M-X", "tipo": "PASANTE", "obra": "Moreno", "importe_ars": 300000, "informal": "VERDADERO",
               "cuenta": "Pagado por el comitente"}
    normal = {"id_mov": "M-Y", "tipo": "EGRESO", "obra": "Moreno", "importe_ars": 1000, "informal": "", "cuenta": "Banco"}
    antes, _ = saldo_obra([normal], "Moreno", m)
    despues, _ = saldo_obra([normal, pasante], "Moreno", m)
    check("el pasante suma como pago del comitente, y el saldo de la obra no se mueve",
          despues.pagado_por_el_comitente - antes.pagado_por_el_comitente == 300000
          and despues.adelantado == antes.adelantado and despues.saldo == antes.saldo, (antes, despues))
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

    # ── Tanda 5 · certificados ────────────────────────────────────────────────
    from app import certificados
    from tests.dobles import ENCABEZADO_CERTIFICADOS

    print("\nTanda 5 · el certificado por texto: documento, no gasto (§5.11)")
    with con_etapas(("Moreno", "1")):
        r, f, c = leer("Certificado 5 Moreno1 $3.200.000")
        check("Certificado 5 Moreno1 $3.200.000 → CERTIFICADO, Moreno, etapa 1, número 5, $3.200.000",
              (c["tipo"], c["obra"], c["etapa"], c["numero"], c["saldo_a_cobrar"]) == ("CERTIFICADO", "Moreno", "1", "5", 3200000), c)
        check("… con fuente TEXTO, la fecha del mensaje y sin preguntas",
              c["fuente"] == "TEXTO" and c["fecha"] == "2026-09-25" and not r.preguntas, (c, r.preguntas))
        check("… y sin columnas de gasto: no tiene cuenta, contratista ni rubro",
              not {"cuenta", "contratista", "rubro_1", "importe"} & set(c), sorted(c))
    with con_etapas(("Lennon", "1")):
        r, f, c = leer("cert 2 etapa 1 Lennon 1.500.000 del 20/9")
        check("cert 2 etapa 1 Lennon 1.500.000 del 20/9 → Lennon, etapa 1, número 2, fecha 2026-09-20",
              (c["tipo"], c["obra"], c["etapa"], c["numero"], c["saldo_a_cobrar"], c["fecha"])
              == ("CERTIFICADO", "Lennon", "1", "2", 1500000, "2026-09-20"), c)
    r, f, c = leer("Ingreso Moreno/cert. 4/efectivo $2.600.000")
    check("«Ingreso Moreno/cert. 4» sigue siendo el cobro, no un certificado",
          c["tipo"] == "INGRESO" and c["cuenta"] == "Caja obra Moreno" and f.extras.get("certificado") == "4", c)
    r, f, c = leer("Cert. 4 extras")
    check("«Cert. 4 extras» suelto: CERTIFICADO número «4 extras», pregunta la obra",
          c["tipo"] == "CERTIFICADO" and c["numero"] == "4 extras" and campos_de(r, "obra"), (c, r.preguntas))
    previo = interpretar(InterpretarIn(texto="Ingreso Moreno/cert 4 $566.596", fecha_mensaje="2026-09-25T12:00:00Z")).fichas[0]
    r = interpretar(InterpretarIn(texto="Cert. 4 extras", fecha_mensaje="2026-09-25T12:00:00Z",
                                  contexto_previo=previo.model_dump()))
    c = r.fichas[0].campos
    check("… pero como corrección de un cobro (corpus fila 77) sigue siendo el cobro, con el número corregido",
          c["tipo"] == "INGRESO" and c["obra"] == "Moreno" and r.fichas[0].extras.get("certificado") == "4 extras", c)
    r, f, c = leer("Certificado 3 Austral $100.000")
    check("«Austral» en un certificado nunca es la obra de indirectos: pregunta la obra",
          not c["obra"] and campos_de(r, "obra"), (c["obra"], f.extras.get("advertencias")))
    r, f, c = leer("Certificado Moreno $500.000")
    check("sin número: lo pregunta", c["obra"] == "Moreno" and campos_de(r, "numero"), [p.campo for p in r.preguntas])

    print("\nTanda 5 · el PDF de ejemplo (tests/fixtures/cert_loguercio_etapa3.pdf)")
    pdf = (RAIZ / "fixtures" / "cert_loguercio_etapa3.pdf").read_bytes()
    adj_cert = Adjunto(url="https://drive.google.com/file/d/CERTLOGUERCIOxxxxxxxxxxxx/view", mime="application/pdf",
                       nombre="cert_loguercio_etapa3.pdf")

    def lector_pdf(adj):
        d = comprobante.DatosComprobante(url=adj.url, nombre_archivo=adj.nombre or "", sha256=adj.sha256)
        return comprobante.leer_bytes(pdf, adj.nombre, "application/pdf", d)

    r, f = leer_con("", adjuntos=[adj_cert], lector=lector_pdf)
    c = f.campos
    check("sin texto → ficha CERTIFICADO con fuente PDF", c["tipo"] == "CERTIFICADO" and c["fuente"] == "PDF", c)
    check("saldo_a_cobrar 3.402.032,64 (el punto 7, anclado en el rótulo)", c["saldo_a_cobrar"] == 3402032.64, c["saldo_a_cobrar"])
    check("número 1 y fecha 2024-02-19 (día y mes sin cero)", c["numero"] == "1" and c["fecha"] == "2024-02-19", c)
    check("la obra pregunta: Lo Guercio no es comitente de ninguna obra",
          not c["obra"] and any(p.campo == "obra" and "Lo Guercio" in p.texto for p in r.preguntas), [p.texto for p in r.preguntas])
    check("… y no toma «Austral» (la constructora) ni «tres cerros» (la ubicación) como obra",
          c["obra"] not in ("Austral", "Tres Cerros"), c["obra"])
    check("la etapa pregunta: el cuerpo dice 2 y el archivo 3, no elige",
          not c["etapa"] and any(k.campo == "etapa" for k in f.conflictos)
          and any(p.campo == "etapa" and set(p.opciones) == {"2", "3"} for p in r.preguntas), (f.conflictos, r.preguntas))
    ctrl = f.extras["certificado_pdf"]["control"]
    check("control 5 + 6 = 7: pasa por $0,01 de redondeo, sin advertencia",
          ctrl["diferencia"] <= 1 and not any("suma" in a for a in f.extras.get("advertencias", [])), ctrl)
    check("el punto 6 sin separador de miles (348143,38) se lee bien", ctrl["incremento"] == 348143.38, ctrl)
    check("ningún otro monto del documento va a la ficha",
          set(c) == set(("tipo", "obra", "etapa", "numero", "fecha", "saldo_a_cobrar", "fuente", "comprobante_url")), sorted(c))
    check("el certificado no se toma como comprobante de pago: sin importe ni LLM",
          f.extras["comprobante"].get("importe") is None and not r.diagnostico["uso_llm"], f.extras["comprobante"])

    r, f = leer_con("Moreno etapa 2", adjuntos=[adj_cert], lector=lector_pdf)
    check("si el texto dice obra y etapa, manda el texto", (f.campos["obra"], f.campos["etapa"]) == ("Moreno", None)
          and any("no tiene etapas" in a for a in f.extras.get("advertencias", [])), (f.campos, f.extras.get("advertencias")))
    with con_etapas(("Moreno", "2"), ("Moreno", "3")):
        r, f = leer_con("Moreno2", adjuntos=[adj_cert], lector=lector_pdf)
        check("… con etapas cargadas: Moreno etapa 2, sin conflicto de etapa",
              (f.campos["obra"], f.campos["etapa"]) == ("Moreno", "2") and not f.conflictos, (f.campos, f.conflictos))
    r, f = leer_con("Certificado 7 Moreno", adjuntos=[adj_cert], lector=lector_pdf)
    check("número del texto contra número del PDF: conflicto, pregunta",
          any(k.campo == "numero" for k in f.conflictos) and not f.campos["numero"], f.conflictos)

    texto_mal = "Sr. Juan\nOBRA: Casa\n5 Sub. Total de certificación de obra (2-3-4): 1.000,00\n" \
                "6 Incremento CAC 10% 100,00\n7 Saldo a cancelar en la presente certificación (5+6): 1.200,00\n" \
                "CERTIFICADO AUSTRAL Nº: 3 FECHA: 1/3/2025"
    d = certificados.parsear(texto_mal)
    check("control 5 + 6 ≠ 7 por más de $1 → advertencia", any("suma" in a for a in d.advertencias), d.advertencias)

    print("\nTanda 5 · el mismo certificado cargado dos veces")
    estudio = libro()
    estudio.certificados.append([dict(obra="Moreno", numero="5", fecha="2026-09-20", saldo_a_cobrar=3200000,
                                      cargado_por="Petrus").get(k, "") for k in ENCABEZADO_CERTIFICADOS])
    r, f = leer_con("Certificado 5 Moreno $3.200.000", estudio=estudio)
    check("misma obra, etapa y número → posible_duplicado fuerte y pregunta, sin descartar",
          f.posible_duplicado and f.posible_duplicado.libro == "certificados"
          and any(p.motivo == "posible_duplicado" and "Petrus" in p.texto for p in r.preguntas), (f.posible_duplicado, r.preguntas))
    r, f = leer_con("Certificado 5 extras Moreno $3.200.000", estudio=estudio)
    check("«5 extras» es otra serie: no es el mismo", f.posible_duplicado is None, f.posible_duplicado)

    # ── Tanda 6.2 · traspasos ─────────────────────────────────────────────────
    print("\nTanda 6.2 · traspasos: origen y destino (§5.18)")
    for texto, esperado in [
        ("saqué efectivo $50.000", ("Banco", "Efectivo")),
        ("Extracción 100.000", ("Banco", "Efectivo")),
        ("retiro de efectivo 30.000", ("Banco", "Efectivo")),
        ("repuse la caja de LennonC con efectivo 80.000", ("Efectivo", "Caja obra Lennon")),
        ("pasé de la caja de obra Moreno al banco 1.000.000", ("Caja obra Moreno", "Banco")),
    ]:
        r, f, c = leer(texto)
        check(f"«{texto}» → {esperado[0]} → {esperado[1]}",
              c["tipo"] == "TRASPASO" and (c["cuenta_origen"], c["cuenta_destino"]) == esperado and not r.preguntas,
              (c.get("cuenta_origen"), c.get("cuenta_destino"), [p.campo for p in r.preguntas]))
    r, f, c = leer("repuse la caja de LennonC $80.000")
    check("«repuse la caja de LennonC»: destino la caja (la C es la caja, §5.8), pregunta de dónde sale",
          c["cuenta_destino"] == "Caja obra Lennon" and c["obra"] == "Lennon" and campos_de(r, "cuenta_origen")
          and not campos_de(r, "obra", "contratista", "rubro"), (c, [p.campo for p in r.preguntas]))
    r, f, c = leer("pasé a la caja 20.000")
    check("«pasé a la caja»: «la caja» sola no se adivina, pregunta las dos cuentas",
          set(campos_de(r, "cuenta_origen", "cuenta_destino")) == {"cuenta_origen", "cuenta_destino"}, [p.campo for p in r.preguntas])
    r, f, c = leer("traspaso Banco/Efectivo $5.000")
    check("«traspaso Banco/Efectivo»: nombra las dos sin dirección, pregunta de cuál sale con esas dos",
          any(p.campo == "cuenta_origen" and set(p.opciones) == {"Banco", "Efectivo"} for p in r.preguntas), r.preguntas)
    r, f, c = leer("Barba/LennonC")
    check("un pago con la caja chica sigue siendo un EGRESO, no un traspaso", c["tipo"] == "EGRESO", c["tipo"])

    print(f"\n{'TODO OK' if not fallas else str(len(fallas)) + ' FALLAS'}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
