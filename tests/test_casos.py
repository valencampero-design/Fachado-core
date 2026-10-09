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
    from app.interpretar import interpretar as _interpretar
    from app.maestros import Etapa
    from app.obligatorios import sin_pregunta

    # §5.7 (v1.7): cada ficha de cada caso de este archivo pasa por el invariante «ningún
    # obligatorio vacío sin su pregunta». Se junta todo y se chequea al final.
    rotas_invariante: list[tuple[str, list]] = []

    def interpretar(req, *a, **kw):
        r = _interpretar(req, *a, **kw)
        rotas = sin_pregunta(r.model_dump())
        if rotas:
            rotas_invariante.append((req.texto or "(adjunto)", rotas))
        return r
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
        """Mientras dura el caso, esas obras tienen exactamente estas etapas, todas en curso
        (las del snapshot de esas obras se sacan y después vuelven)."""
        obras = {obra for obra, _ in pares}
        antes = list(m.etapas)
        m.etapas[:] = [e for e in m.etapas if e.obra not in obras] + [Etapa(obra, etapa, "", "en curso") for obra, etapa in pares]
        try:
            yield
        finally:
            m.etapas[:] = antes

    def campos_de(r, *nombres):
        return [p.campo for p in r.preguntas if p.campo in nombres]

    # ── Tanda 2 · el token de obra ────────────────────────────────────────────
    print("\nTanda 2 · <obra>[<etapa>][C] (§5.15, §5.8)")
    with con_etapas(("Lennon", "1")):
        r, f, c = leer("Barba/Lennon1C")
        check("Barba/Lennon1C → Lennon, etapa 1, Caja obra Lennon",
              c["obra"] == "Lennon" and c["etapa"] == "1" and c["cuenta"] == "Caja obra Lennon", c)
    r, f, c = leer("Barba/LennonC")
    check("Barba/LennonC → Lennon, Caja obra Lennon, y la etapa 1 del maestro (única en curso, v1.7)",
          c["obra"] == "Lennon" and c["etapa"] == "1" and f.origen_campo.get("etapa") == "maestro"
          and c["cuenta"] == "Caja obra Lennon", (c, f.origen_campo.get("etapa")))
    r, f, c = leer("Barba/Hua Huan1")
    check("una etapa en una obra sin etapas (Hua Huan) → etapa vacía y advertencia",
          c["obra"] == "Hua Huan" and not c["etapa"] and any("no tiene etapas" in a for a in f.extras.get("advertencias", [])),
          (c["etapa"], f.extras.get("advertencias")))
    r, f, c = leer("barba/lennon1c")
    check("mayúsculas y minúsculas dan igual", c["obra"] == "Lennon" and c["cuenta"] == "Caja obra Lennon", c)
    r, f, c = leer("Barba/Lennon/caja")
    check("la palabra suelta «caja» equivale a la C", c["cuenta"] == "Caja obra Lennon", c["cuenta"])
    r, f, c = leer("Barba/Hua HuanC")
    check("C en una obra sin caja (Hua Huan): no inventa la cuenta, pregunta y avisa",
          not c["cuenta"] and campos_de(r, "cuenta") and any("no tiene caja" in a for a in f.extras.get("advertencias", [])),
          (c["cuenta"], [p.texto for p in r.preguntas]))
    with con_etapas(("Lennon", "1"), ("Lennon", "2")):
        r, f, c = leer("Barba/Lennon")
        preg = [p for p in r.preguntas if p.campo == "etapa"]
        check("obra con etapas y el mensaje no dice cuál: pregunta con una opción por etapa",
              preg and preg[0].opciones == ["1", "2"], [(p.campo, p.opciones) for p in r.preguntas])
    r, f, c = leer("Barba/Hua Huan")
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
    check("… pero como corrección de un cobro (corpus fila 77) sigue siendo el cobro: certificado 4 de la etapa "
          "extras (§5.11 v1.7)",
          c["tipo"] == "INGRESO" and c["obra"] == "Moreno" and r.fichas[0].extras.get("certificado") == "4"
          and c["etapa"] == "extras", (c, r.fichas[0].extras.get("certificado")))
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
    check("si el texto dice obra y etapa, manda el texto: Moreno etapa 2, y como es futura pregunta si la activa",
          (f.campos["obra"], f.campos["etapa"]) == ("Moreno", "2") and campos_de(r, "activar_etapa"),
          (f.campos, [p.campo for p in r.preguntas]))
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

    # ── Tanda 6.4 · intención, respuestas, texto compartido ───────────────────
    from app.models import Respuesta

    def responder(r_previa, *pares, ficha=0, **kw):
        previa = r_previa.fichas[ficha].model_dump()
        return interpretar(InterpretarIn(fecha_mensaje="2026-09-25T12:00:00Z", telefono=titular.telefono, contexto_previo=previa,
                                         respuestas=[Respuesta(ficha=ficha, campo=cp, valor=v) for cp, v in pares]), **kw)

    print("\nTanda 6.4 · intencion: movimiento, consulta u otro (§5.12)")
    for texto, esperada in [
        ("¿Cuánto le pagué a Felipe J?", "consulta"),
        ("¿Cuántos pagos se le hicieron a Marcelo por la obra Moreno?", "consulta"),
        ("¿El comitente pagó todas las certificaciones?", "consulta"),
        ("después te paso el ticket", "otro"),
        ("gracias", "otro"),
        ("Pago Moreno", "movimiento"),
        ("Luis", "movimiento"),               # una palabra suelta puede ser un contratista nuevo: ante la duda
        ("Felipe J/Lennon", "movimiento"),
    ]:
        r = interpretar(InterpretarIn(texto=texto, fecha_mensaje="2026-09-25T12:00:00Z"))
        check(f"«{texto}» → {esperada}", r.intencion == esperada and (esperada == "movimiento" or (not r.fichas and not r.preguntas)),
              (r.intencion, len(r.fichas), [p.campo for p in r.preguntas]))
    foto = Adjunto(url="https://drive.google.com/file/d/FOTOOBRAxxxxxxxxxxxxxxxxxx/view", mime="image/jpeg", nombre="IMG_2031.jpg")
    r = interpretar(InterpretarIn(texto="", adjuntos=[foto]), lector=lector_con())
    check("una foto sin texto y sin nada de un comprobante (una foto de obra) → otro", r.intencion == "otro" and not r.fichas, r.intencion)

    def no_leido(adj):
        d = comprobante.DatosComprobante(url=adj.url, nombre_archivo=adj.nombre or "")
        d.error = "adjunto_no_leido"
        return d
    r = interpretar(InterpretarIn(texto="", adjuntos=[foto]), lector=no_leido)
    check("… pero si no se pudo leer, no se sabe: movimiento", r.intencion == "movimiento" and r.fichas, r.intencion)

    print("\nTanda 6.4 · comprobante solo, sin texto")
    transf = Adjunto(url="https://drive.google.com/file/d/TRANSFSOLAxxxxxxxxxxxxxxxxx/view", mime="application/pdf",
                     nombre="comprobante.pdf")
    r, f = leer_con("", adjuntos=[transf], lector=lector_con(importe=300000, fecha="2026-09-02", cuit="20-40613900-0"))
    check("importe, fecha y contratista (por CUIT) del comprobante; pregunta la obra",
          r.intencion == "movimiento" and (f.campos["importe"], f.campos["fecha"], f.campos["contratista"])
          == (300000, "2026-09-02", "Felipe Andrés Scherer")
          and f.origen_campo["importe"] == "comprobante" and campos_de(r, "obra"), (f.campos, [p.campo for p in r.preguntas]))

    print("\nTanda 6.4 · respuestas: el valor se aplica y la cascada vuelve a correr")
    r0 = interpretar(InterpretarIn(texto="Marce/Moreno", fecha_mensaje="2026-09-25T12:00:00Z"))
    r1 = responder(r0, ("contratista", "Marcelo Maragaño"))
    c1 = r1.fichas[0].campos
    check("«Marce/Moreno» + contratista = Marcelo Maragaño → sin preguntar el apodo, rubro inferido, obra",
          c1["contratista"] == "Marcelo Maragaño" and c1["tipo_gasto"] == "obra" and c1["rubro_2"]
          and not campos_de(r1, "contratista"), (c1, [p.campo for p in r1.preguntas]))
    r0 = interpretar(InterpretarIn(texto="Felipe J", fecha_mensaje="2026-09-25T12:00:00Z"))
    r1 = responder(r0, ("obra", "Lennon"))
    check("sin obra + obra = Lennon → tipo_gasto obra, comitente del maestro, sin preguntas",
          (r1.fichas[0].campos["obra"], r1.fichas[0].campos["tipo_gasto"], r1.fichas[0].campos["comitente"])
          == ("Lennon", "obra", "Lucas Mariano Lennon") and not campos_de(r1, "obra"), r1.fichas[0].campos)
    r2 = responder(r1, ("obra", "Sur"))
    check("cambiar la obra a un inmueble personal (Sur) cambia tipo_gasto a personal: corre la cascada",
          r2.fichas[0].campos["tipo_gasto"] == "personal", (r2.fichas[0].campos["tipo_gasto"], r2.fichas[0].regla))
    r3 = responder(r0, ("obra", "lenon"))
    check("texto libre en vez de una opción: se resuelve con el diccionario («lenon» → Lennon)",
          r3.fichas[0].campos["obra"] == "Lennon", r3.fichas[0].campos["obra"])
    r0 = interpretar(InterpretarIn(texto="Austral/Sofi", fecha_mensaje="2026-09-25T12:00:00Z"))
    check("dual con obra: pregunta clasificación", campos_de(r0, "clasificacion"), [p.campo for p in r0.preguntas])
    rp, ro = responder(r0, ("clasificacion", "Personal")), responder(r0, ("clasificacion", "Obra"))
    check("… «Personal» → personal; «Obra» → el tipo de Austral (estructura)",
          rp.fichas[0].campos["tipo_gasto"] == "personal" and ro.fichas[0].campos["tipo_gasto"] == "estructura"
          and not campos_de(ro, "clasificacion"), (rp.fichas[0].campos["tipo_gasto"], ro.fichas[0].campos["tipo_gasto"]))
    ro2 = responder(ro, ("importe", "$120.000"))
    check("… y la respuesta queda para la ronda siguiente (no vuelve a preguntar clasificación)",
          not campos_de(ro2, "clasificacion") and ro2.fichas[0].campos["importe"] == 120000, [p.campo for p in ro2.preguntas])
    r0, f0 = leer_con("Ecoaislaciones/Lennon $999", adjuntos=[cheque_510], lector=lector_con(importe=4032391.7, fecha="2026-08-27"))
    r1 = responder(r0, ("importe", "$4.032.391,70"))
    f1 = r1.fichas[0]
    check("conflicto de importe + respuesta → se usa, y la fecha sigue siendo «del comprobante»",
          f1.campos["importe"] == 4032391.7 and not campos_de(r1, "importe") and f1.origen_campo.get("fecha") == "comprobante",
          (f1.campos["importe"], f1.origen_campo))
    estudio = libro(transferencia_eco)
    r0, f0 = leer_con("Ecoaislaciones/Lennon", estudio=estudio, adjuntos=[cheque_510],
                      lector=lector_con(importe=4032391.7, fecha="2026-08-27"))
    r1 = responder(r0, ("duplicado", "Es otro"), libros={"estudio": estudio, "personal": None})
    check("duplicado + «Es otro» → no vuelve a preguntar", campos_de(r0, "duplicado") and not campos_de(r1, "duplicado"),
          [p.campo for p in r1.preguntas])
    r0 = interpretar(InterpretarIn(texto="traspaso Banco/Efectivo $5.000", fecha_mensaje="2026-09-25T12:00:00Z"))
    r1 = responder(r0, ("cuenta_origen", "Efectivo"))
    check("traspaso con dos cuentas sin dirección + origen = Efectivo → destino Banco",
          (r1.fichas[0].campos["cuenta_origen"], r1.fichas[0].campos["cuenta_destino"]) == ("Efectivo", "Banco")
          and not r1.preguntas, (r1.fichas[0].campos, r1.preguntas))
    with con_etapas(("Lennon", "1"), ("Lennon", "2")):
        r0 = interpretar(InterpretarIn(texto="Barba/Lennon", fecha_mensaje="2026-09-25T12:00:00Z"))
        r1 = responder(r0, ("etapa", "2"))
        check("etapa: pregunta y respuesta", campos_de(r0, "etapa") and r1.fichas[0].campos["etapa"] == "2"
              and not campos_de(r1, "etapa"), r1.fichas[0].campos["etapa"])

    print("\nTanda 6.4 · texto_compartido: N comprobantes, un texto")
    r, f = leer_con("Felipe J/Lennon $500.000", adjuntos=[transf], lector=lector_con(importe=300000, fecha="2026-09-02"))
    check("con N = 1, importe del texto contra el del comprobante es conflicto", any(k.campo == "importe" for k in f.conflictos))
    r = interpretar(InterpretarIn(texto="Felipe J/Lennon $500.000", fecha_mensaje="2026-09-25T12:00:00Z", adjuntos=[transf],
                                  texto_compartido=2), lector=lector_con(importe=300000, fecha="2026-09-02"))
    f = r.fichas[0]
    check("con N = 2, importe y fecha del comprobante, sin conflicto; obra y contratista del texto",
          (f.campos["importe"], f.campos["fecha"], f.campos["obra"], f.campos["contratista"])
          == (300000, "2026-09-02", "Lennon", "Felipe Andrés Scherer") and not f.conflictos, (f.campos, f.conflictos))
    r = interpretar(InterpretarIn(texto="Felipe J/Lennon $500.000", fecha_mensaje="2026-09-25T12:00:00Z", adjuntos=[transf],
                                  texto_compartido=2), lector=lector_con(fecha="2026-09-02"))
    check("… y si ese comprobante no trae importe, pregunta (no usa el del texto)",
          r.fichas[0].campos["importe"] is None and campos_de(r, "importe"), (r.fichas[0].campos["importe"], r.preguntas))

    # ── Tanda 6.5 · contratistas inactivos ────────────────────────────────────
    from app import resolver as res_mod
    from app.interpretar import _validar

    print("\nTanda 6.5 · contratistas inactivos (§5.6)")
    r, f, c = leer("Mercado Libre/Moreno")
    check("nombre exacto de un inactivo: se reconoce y pregunta «¿lo reactivo?»",
          c["contratista"] == "Mercado Libre" and any(p.motivo == "inactivo" and p.opciones == ["Reactivar", "Es otro"]
                                                      for p in r.preguntas), (c["contratista"], r.preguntas))
    for texto in ("Mercado/Moreno", "Mercadolibre/Moreno"):
        r, f, c = leer(texto)
        check(f"«{texto}»: por palabra única o por parecido, un inactivo no se propone", c["contratista"] != "Mercado Libre",
              c["contratista"])
    check("el LLM tampoco puede devolverlo", _validar("contratista", "Mercado Libre", m) is None)
    check("ni aparece como opción de una pregunta", "Mercado Libre" not in res_mod.candidatos("mercado", m, "contratista", 20))
    check("con el flag de históricos, sí se reconoce por parecido («mercadolibre»)",
          any(x.valor == "Mercado Libre" for x in res_mod.resolver_token("mercadolibre", m, incluir_inactivos=True))
          and not res_mod.resolver_token("mercadolibre", m))
    r0 = interpretar(InterpretarIn(texto="Mercado Libre/Moreno", fecha_mensaje="2026-09-25T12:00:00Z"))
    r1 = responder(r0, ("inactivo", "Reactivar"))
    check("«Reactivar» → extras.reactivar, sin volver a preguntar",
          r1.fichas[0].extras.get("reactivar") is True and not any(p.motivo == "inactivo" for p in r1.preguntas), r1.preguntas)
    r2 = responder(r0, ("inactivo", "Es otro"))
    check("«Es otro» → se descarta y pregunta a quién se le pagó",
          r2.fichas[0].campos["contratista"] is None and campos_de(r2, "contratista")
          and not any(p.motivo == "inactivo" for p in r2.preguntas), (r2.fichas[0].campos["contratista"], r2.preguntas))

    # ── Tanda 6.7 · el LLM sabe quién escribe ─────────────────────────────────
    from app import llm

    print("\nTanda 6.7 · el prompt nombra a quien escribe (§5.13)")
    petrus = next((u for u in m.usuarios if u.rol != "titular" and u.activo), None)
    capturado: dict = {}

    def llamar_falso(system, content, schema, max_tokens=4000):
        capturado["system"], capturado["content"] = system[0]["text"], content
        return {"tokens": [], "rubro_sugerido": None}, {}

    disponible_real, llamar_real = llm.disponible, llm._llamar
    llm.disponible, llm._llamar = (lambda: True), llamar_falso
    try:
        interpretar(InterpretarIn(texto="Pepito Gomez/Lennon", telefono=petrus.telefono, fecha_mensaje="2026-09-25T12:00:00Z"))
    finally:
        llm.disponible, llm._llamar = disponible_real, llamar_real
    check(f"si escribe {petrus.nombre}, el mensaje al LLM lo nombra (de USUARIOS) y dice que «pagué» es el estudio",
          f"Escribe: {petrus.nombre}." in capturado.get("content", "") and "pagó el estudio" in capturado["content"],
          capturado.get("content"))
    check(f"«Retiro» sigue siendo lo personal del titular ({titular.nombre})",
          f"lo personal de {titular.nombre}" in capturado["content"], capturado["content"])
    check("el system (cacheado, igual para todos) ya no dice «el arquitecto»", "arquitecto" not in capturado["system"].split("OBRAS")[0])

    # ── Fix del arranque (30/09) · 1.1 a 1.3: la cuenta ───────────────────────
    print("\nFix del arranque · 1.1 de qué cuenta salió (§5.7 v1.7)")
    transf_gonzalo = Adjunto(url="https://drive.google.com/file/d/TRANSFGONZALOxxxxxxxxxxxxx/view", mime="application/pdf",
                             nombre="comprobante.pdf")
    r, f = leer_con("Maragaño/Gonzalo", adjuntos=[transf_gonzalo],
                    lector=lector_con(importe=30000, fecha="2026-09-29", medio_pago="Transferencia"))
    check("comprobante de transferencia + «Maragaño/Gonzalo» → cuenta Banco, del comprobante, sin faltantes",
          (f.campos["cuenta"], f.origen_campo.get("cuenta"), f.campos["medio_pago"]) == ("Banco", "comprobante", "Transferencia")
          and not f.faltantes and not r.preguntas, (f.campos["cuenta"], f.origen_campo.get("cuenta"), f.faltantes, r.preguntas))
    r, f, c = leer("Metro Gas/Grigera Galpón 11.750")
    check("«Metro Gas/Grigera Galpón 11.750», sin comprobante → Banco / transferencia «supuesto», sin preguntar",
          (c["cuenta"], f.origen_campo.get("cuenta"), c["medio_pago"], f.origen_campo.get("medio_pago"))
          == ("Banco", "supuesto", "Transferencia", "supuesto")
          and not f.faltantes and not r.preguntas and "Cuenta asumida: Banco" in f.extras.get("advertencias", []),
          (c["cuenta"], f.origen_campo, f.faltantes, r.preguntas))
    r, f, c = leer("Barba/Hua Huan/efectivo $20.000")
    check("«/efectivo» en el texto manda: Efectivo, no el supuesto",
          c["cuenta"] == "Efectivo" and f.origen_campo.get("cuenta") != "supuesto", (c["cuenta"], f.origen_campo.get("cuenta")))
    for medio, esperada in (("Cheque", "Chequera"), ("Mercado Pago", "Mercado Pago"), ("Débito automático", "Banco")):
        r, f = leer_con("Barba/Hua Huan", adjuntos=[transf_gonzalo],
                        lector=lector_con(importe=5000, fecha="2026-09-29", medio_pago=medio))
        check(f"comprobante de {medio} → {esperada}", (f.campos["cuenta"], f.origen_campo.get("cuenta")) == (esperada, "comprobante"),
              (f.campos["cuenta"], f.origen_campo.get("cuenta")))
    r, f = leer_con("Barba/Hua Huan", adjuntos=[transf_gonzalo],
                    lector=lector_con(importe=500, fecha="2026-09-29", medio_pago="Transferencia", moneda="USD"))
    check("transferencia en dólares → Banco USD", f.campos["cuenta"] == "Banco USD", f.campos["cuenta"])
    r, f = leer_con("Felipe J/Lennon", adjuntos=[transf_gonzalo],
                    lector=lector_con(importe=300000, fecha="2026-09-02", medio_pago="Transferencia", cuit_originante="20-13851988-1"))
    check("Lennon, comprobante pagado por el comitente (su CUIT es el originante) → «Pagado por el comitente»",
          (f.campos["cuenta"], f.origen_campo.get("cuenta")) == ("Pagado por el comitente", "comprobante"), f.campos["cuenta"])
    r, f, c = leer("Felipe J/Lennon $300.000")
    check("Lennon sin comprobante → «Pagado por el comitente» por la obra (OBRAS.cuenta_habitual), no el supuesto",
          (c["cuenta"], f.origen_campo.get("cuenta")) == ("Pagado por el comitente", "maestro") and not f.faltantes,
          (c["cuenta"], f.origen_campo.get("cuenta"), f.faltantes))
    r, f, c = leer("Barba/LennonC $10.000")
    check("la C de la caja sigue mandando", c["cuenta"] == "Caja obra Lennon", c["cuenta"])
    r, f, c = leer("Deposito Marcelo Maragaño/Moreno $300.000")
    check("un depósito no se toca: «Pagado por el comitente»", c["cuenta"] == "Pagado por el comitente", c["cuenta"])

    # ── Fix del arranque · 2 etapas (§5.15 v1.7) ──────────────────────────────
    print("\nFix del arranque · 2 etapas: Lennon 1 en curso; Moreno 1 y extras en curso")
    r, f, c = leer("Barba/Lennon $10.000")
    check("Lennon sin etapa → etapa 1 (la única en curso), origen maestro, sin preguntar",
          c["etapa"] == "1" and f.origen_campo.get("etapa") == "maestro" and not campos_de(r, "etapa"), (c["etapa"], r.preguntas))
    r, f, c = leer("Marcelo Maragaño/Moreno $10.000")
    etapa_p = [p for p in r.preguntas if p.campo == "etapa"]
    check("Moreno sin etapa → pregunta «¿Etapa 1 o extras?» con las dos en curso",
          not c["etapa"] and etapa_p and etapa_p[0].opciones == ["1", "extras"], [(p.campo, p.opciones) for p in r.preguntas])
    for texto in ("Marcelo Maragaño/Moreno extras $1", "Marcelo Maragaño/Morenoextras $1", "Marcelo Maragaño/Moreno ext $1",
                  "Marcelo Maragaño/Moreno/extras $1"):
        r, f, c = leer(texto)
        check(f"«{texto.split('$')[0].strip()}» → etapa extras", c["etapa"] == "extras" and not campos_de(r, "etapa"), c["etapa"])
    for texto in ("Marcelo Maragaño/MorenoC extras $1", "Marcelo Maragaño/Moreno extras C $1"):
        r, f, c = leer(texto)
        check(f"«{texto.split('$')[0].strip()}» → etapa extras y la caja de Moreno",
              (c["etapa"], c["cuenta"]) == ("extras", "Caja obra Moreno"), (c["etapa"], c["cuenta"]))
    r, f, c = leer("Barba/Lennon2 $10.000")
    activar = [p for p in r.preguntas if p.campo == "activar_etapa"]
    check("«Lennon2» (futura) → pregunta «La etapa 2 de Lennon figura como futura, ¿la paso a en curso?»",
          c["etapa"] == "2" and activar and "futura" in activar[0].texto and activar[0].opciones == ["Sí", "No"],
          [(p.campo, p.texto) for p in r.preguntas])
    r_si = responder(r, ("activar_etapa", "Sí"))
    check("… «Sí» → extras.activar_etapa = 2, sin más preguntas de etapa",
          r_si.fichas[0].extras.get("activar_etapa") == "2" and r_si.fichas[0].campos["etapa"] == "2"
          and not campos_de(r_si, "etapa", "activar_etapa"), (r_si.fichas[0].extras, r_si.preguntas))
    r_no = responder(r, ("activar_etapa", "No"))
    check("… «No» → vuelve a la etapa en curso (1)", r_no.fichas[0].campos["etapa"] == "1", r_no.fichas[0].campos["etapa"])
    r, f, c = leer("Ingreso Moreno/cert 4 extras $500.000")
    check("«cert 4 extras» → certificado 4 de la etapa extras (§5.11 v1.7)",
          (f.extras.get("certificado"), c["etapa"]) == ("4", "extras"), (f.extras.get("certificado"), c["etapa"]))
    r, f, c = leer("Ingreso Moreno/cert 4 $500.000")
    check("«cert 4» en Moreno → pregunta la etapa (dos en curso)", campos_de(r, "etapa") and not c["etapa"], r.preguntas)
    r, f, c = leer("Certificado 5 Moreno extras $3.200.000")
    check("certificado por texto: «Certificado 5 Moreno extras» → etapa extras, número 5",
          (c["tipo"], c["numero"], c["etapa"]) == ("CERTIFICADO", "5", "extras"), c)

    # ── Fix del arranque · 3 dólares (§5.7 v1.7) ──────────────────────────────
    print("\nFix del arranque · 3 dólares: siempre se pregunta el tipo de cambio")
    r0 = interpretar(InterpretarIn(texto="Barba/Hua Huan u$s 500", fecha_mensaje="2026-09-29T15:00:00Z"))
    tc_p = [p for p in r0.preguntas if p.campo == "tipo_cambio"]
    check("egreso en dólares → pregunta «¿A qué tipo de cambio?», texto libre (sin botones), cuenta Banco USD",
          tc_p and not tc_p[0].opciones and r0.fichas[0].campos["cuenta"] == "Banco USD", (r0.preguntas, r0.fichas[0].campos["cuenta"]))
    for valor, esperado in (("1.450", 1450.0), ("1450", 1450.0), ("1450,50", 1450.5)):
        r1 = responder(r0, ("tipo_cambio", valor))
        c1 = r1.fichas[0].campos
        check(f"… «{valor}» → tc {esperado}, importe_ars = 500 × tc", (c1["tc"], c1["importe_ars"]) == (esperado, round(500 * esperado, 2))
              and not campos_de(r1, "tipo_cambio"), (c1["tc"], c1["importe_ars"]))
    r1 = responder(r0, ("tipo_cambio", "mil cuatrocientos"))
    check("… una respuesta que no es un número no se usa: vuelve a preguntar", campos_de(r1, "tipo_cambio")
          and not r1.fichas[0].campos["tc"], (r1.fichas[0].campos["tc"], r1.diagnostico["advertencias"]))
    r, f, c = leer("pasé 1.000 dólares del banco usd al banco")
    check("traspaso Banco USD → Banco: pregunta el tipo de cambio (antes era un 422)",
          (c["cuenta_origen"], c["cuenta_destino"], c["moneda"]) == ("Banco USD", "Banco", "USD") and campos_de(r, "tipo_cambio"), c)
    r, f, c = leer("pasé $1.450.000 del banco al banco usd")
    check("«banco usd» es el nombre de la cuenta: el importe sigue en pesos", c["moneda"] == "ARS", c["moneda"])

    # ── Fix del arranque · 4 maestro ──────────────────────────────────────────
    print("\nFix del arranque · 4 Gessel y «belleli» (§6 v1.7)")
    for texto, obra in (("Edesur/Gessel", "Gessel"), ("Edesur/gessel", "Gessel"), ("Metrogas/Belleli", "Belelli")):
        r, f, c = leer(texto + " $10.000")
        check(f"«{texto}» → {obra}, inmueble personal: circuito personal (R1)",
              (c["obra"], c["tipo_gasto"]) == (obra, "personal"), (c["obra"], c["tipo_gasto"], f.regla))

    # ── Conversación (9/10) · D: pocas preguntas (§5.12 v1.8) ─────────────────
    print("\nConversación · D «Lennon/Miguel» + comprobante = cero preguntas (§5.12 v1.8)")
    recibo_miguel = Adjunto(url="https://drive.google.com/file/d/RECIBOMIGUELxxxxxxxxxxxxx/view", mime="image/jpeg",
                            nombre="recibo.jpg")
    leido_miguel = dict(importe=7084000, fecha="2026-10-03", razon_social="Miguel Soto", medio_pago="Efectivo",
                        tipo_comprobante="Recibo")
    con_historia = libro(dict(id_mov="M-000010", fecha="2026-10-07", tipo="EGRESO", importe=3070000, obra="Lennon",
                              contratista="Miguel Soto", rubro_1="Mano de obra", rubro_2="Contratistas",
                              cuenta="Efectivo", tipo_gasto="obra", cargado_por="Gabriel Fachado"))
    r, f = leer_con("Lennon/Miguel", estudio=con_historia, adjuntos=[recibo_miguel], lector=lector_con(**leido_miguel))
    c = f.campos
    check("«Lennon/Miguel» + el recibo → cero preguntas (el criterio de aceptación)", not r.preguntas,
          [(p.campo, p.texto) for p in r.preguntas])
    check("… Miguel Soto, importe y fecha del recibo, rubro el último usado con él (supuesto)",
          (c["contratista"], c["importe"], c["fecha"], c["rubro_2"], f.origen_campo.get("rubro_2"))
          == ("Miguel Soto", 7084000, "2026-10-03", "Contratistas", "supuesto"), (c, f.origen_campo))
    r, f = leer_con("Lennon/Miguel", estudio=libro(), adjuntos=[recibo_miguel], lector=lector_con(**leido_miguel))
    rubro_p = [p for p in r.preguntas if p.campo == "rubro"]
    primeros_de_rubros = [x.rubro_2 for x in m.rubros if x.afecta == "obra"][:10]
    check("sin historia ni rubro habitual: solo se pregunta el rubro, con las opciones más usadas (no los primeros 10 de "
          "RUBROS)", rubro_p and [p.campo for p in r.preguntas] == ["rubro"] and "Contratistas" in rubro_p[0].opciones[:3]
          and rubro_p[0].opciones != primeros_de_rubros, [(p.campo, p.opciones[:5]) for p in r.preguntas])

    r = interpretar(InterpretarIn(texto="INGRRSO/28 de septiembre,  Lennon me paso us$20.000 Para ingresar a caja chica, "
                                        "efectivo", fecha_mensaje="2026-10-05T03:19:00Z"))  # la hora real del mensaje
    f, c = r.fichas[0], r.fichas[0].campos
    check("captura 4: INGRESO (typo), Lennon (del texto libre), USD 20.000, fecha 28/9, caja de Lennon, sin preguntar "
          "a quién se le pagó",
          (c["tipo"], c["obra"], c["moneda"], c["importe"], c["fecha"]) == ("INGRESO", "Lennon", "USD", 20000, "2026-09-28")
          and c["cuenta"] and c["cuenta"].startswith("Caja obra Lennon") and not campos_de(r, "contratista", "obra", "concepto"),
          (c, [p.campo for p in r.preguntas]))
    for texto, tipo in (("ingrso Moreno/cert 4 $1.000", "INGRESO"), ("Egreso Barba/Hua Huan $1.000", "EGRESO"),
                        ("INGRESO Lennon $1.000", "INGRESO")):
        r, f, c = leer(texto)
        check(f"«{texto.split()[0]}» → {tipo}", c["tipo"] == tipo, c["tipo"])
    r, f, c = leer("Ingreso Lennon $100.000")
    concepto = [p for p in r.preguntas if p.campo == "concepto"]
    check("un ingreso en Lennon sin decir qué es: la pregunta incluye «Adelanto para la caja de obra», y nunca a quién se "
          "le pagó", concepto and "Adelanto para la caja de obra" in concepto[0].opciones and not campos_de(r, "contratista"),
          [(p.campo, p.opciones) for p in r.preguntas])
    r1 = responder(r, ("concepto", "Adelanto para la caja de obra"))
    check("… «Adelanto para la caja de obra» → entra a la caja de Lennon",
          (r1.fichas[0].campos["cuenta"] or "").startswith("Caja obra Lennon"), r1.fichas[0].campos["cuenta"])

    transf_sofi = Adjunto(url="https://drive.google.com/file/d/TRANSFSOFIxxxxxxxxxxxxxxx/view", mime="image/jpeg",
                          nombre="t.jpg")
    r, f = leer_con("Retiro/Sofi", adjuntos=[transf_sofi],
                    lector=lector_con(importe=184000, fecha="2026-09-30", medio_pago="Transferencia"))
    c = f.campos
    check("captura 1: «Retiro/Sofi» + comprobante → personal, sin obra, rubro Familia (supuesto), cero preguntas",
          (c["tipo_gasto"], c["obra"], c["rubro_2"], f.origen_campo.get("rubro_2")) == ("personal", None, "Familia", "supuesto")
          and not r.preguntas, (c, [p.campo for p in r.preguntas]))
    r0 = interpretar(InterpretarIn(texto="Retiro/Sofi", fecha_mensaje="2026-09-30T19:17:00Z"))
    r1 = responder(r0, ("importe", "184000"))
    check("… y si se pregunta algo (el importe), la respuesta no hace aparecer la obra: lo personal se mantiene",
          r1.fichas[0].campos["tipo_gasto"] == "personal" and not campos_de(r1, "obra", "clasificacion"),
          (r1.fichas[0].campos["tipo_gasto"], [p.campo for p in r1.preguntas]))
    r, f, c = leer("Retiro/Sofi/Moreno $1.000")
    check("un personal no lleva la obra de un tercero (P-000001): la obra se descarta y se avisa",
          c["tipo_gasto"] == "personal" and c["obra"] is None and any("personal" in a for a in f.extras.get("advertencias", [])),
          (c["obra"], f.extras.get("advertencias")))
    r, f, c = leer("Edesur/Belleli $1.000")
    check("… pero un inmueble personal sí (Belelli)", c["obra"] == "Belelli", c["obra"])

    print("\nConversación · F «efectivo» en una obra con caja = esa caja (§5.8 v1.8)")
    caja_lennon = m.caja_de_obra("Lennon")
    r, f, c = leer("Lennon/Miguel efectivo $500.000")
    check("«Lennon/Miguel efectivo» (sin la C, como escribe Gabriel) → Miguel Soto, sale de la caja de Lennon",
          (c["contratista"], c["cuenta"], c["medio_pago"]) == ("Miguel Soto", caja_lennon.nombre, "Efectivo"),
          (c["contratista"], c["cuenta"], c["medio_pago"], [p.campo for p in r.preguntas]))
    r, f, c = leer("Lennon/Miguel/efectivo del estudio $500.000")
    check("«efectivo del estudio» → la cuenta Efectivo, no la caja", c["cuenta"] == "Efectivo", c["cuenta"])
    r, f = leer_con("Lennon/Miguel", estudio=con_historia, adjuntos=[recibo_miguel], lector=lector_con(**leido_miguel))
    check("«Lennon/Miguel» + un recibo en efectivo → la caja de Lennon, cero preguntas (test 2 del handoff)",
          f.campos["cuenta"] == caja_lennon.nombre and not r.preguntas,
          (f.campos["cuenta"], [(p.campo, p.texto) for p in r.preguntas]))
    sin_caja = next(o.nombre for o in m.obras if o.estado != "cerrada" and o.tipo in ("obra_terceros", "obra_propia")
                    and m.caja_de_obra(o.nombre) is None)
    r, f, c = leer(f"{sin_caja}/Miguel efectivo $500.000")
    check(f"una obra sin caja ({sin_caja}): «efectivo» sigue siendo el Efectivo del estudio", c["cuenta"] == "Efectivo",
          (c["obra"], c["cuenta"]))
    r, f, c = leer("Lennon/Juan Perez $1.000")
    check("«Juan Perez» no se parte en palabras: sigue siendo un contratista desconocido", c["contratista"] is None
          and campos_de(r, "contratista"), (c["contratista"], [p.campo for p in r.preguntas]))

    print("\nFix del arranque · 1.2 el invariante, sobre todos los casos de este archivo")
    check(f"ninguna ficha devolvió un faltante sin su pregunta ({len(rotas_invariante)} con problemas)",
          not rotas_invariante, rotas_invariante)

    print(f"\n{'TODO OK' if not fallas else str(len(fallas)) + ' FALLAS'}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
