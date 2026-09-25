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

    print(f"\n{'TODO OK' if not fallas else str(len(fallas)) + ' FALLAS'}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
