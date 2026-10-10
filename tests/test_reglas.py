"""Reglas de negocio que no se pueden romper, con el maestro del snapshot.

    python -m tests.test_reglas

Cada assert cita el punto de CONTEXTO-FACHADO.md que lo justifica. El corpus mide cuánto
resuelve el motor; esto verifica que lo que resuelve sea lo que el negocio decidió.
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def interpretar(texto: str, **extra):
    from app.interpretar import interpretar as _interpretar
    from app.models import InterpretarIn
    return _interpretar(InterpretarIn(texto=texto, fecha_mensaje="2026-09-18T12:00:00Z", **extra))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ.setdefault("MAESTROS_SNAPSHOT", str(RAIZ / "maestros_snapshot.json"))
    os.environ["LLM_HABILITADO"] = "false"
    from app import maestros
    from app.maestros import TIPOS_CUENTA_FUERA_DEL_ESTUDIO

    m = maestros.cargar(forzar=True)
    fallas: list[str] = []

    def check(descripcion: str, condicion, detalle: str = "") -> None:
        ok = bool(condicion)
        print(f"  {'PASA ' if ok else 'FALLA'}  {descripcion}{'' if ok else '  → ' + detalle}")
        if not ok:
            fallas.append(descripcion)

    print("\n§5.5 · Un apodo ambiguo pregunta, no elige el primero")
    for apodo, cuantos in (("Marce", 3), ("Marcelo", 2)):
        r = interpretar(f"{apodo}/Moreno")
        opciones = [p.opciones for p in r.preguntas if p.campo == "contratista"]
        check(f"«{apodo}» pregunta entre {cuantos}",
              r.fichas[0].campos["contratista"] is None and opciones and len(opciones[0]) == cuantos,
              f"contratista={r.fichas[0].campos['contratista']} preguntas={[(p.campo, p.opciones) for p in r.preguntas]}")
    for apellido, quien in (("Maragaño", "Marcelo Maragaño"), ("Orellana", "Marcelo Orellana"), ("Lalo", "Martínez Eduardo")):
        r = interpretar(f"{apellido}/Moreno")
        check(f"«{apellido}» resuelve solo a {quien}", r.fichas[0].campos["contratista"] == quien,
              f"dio {r.fichas[0].campos['contratista']}")

    print("\n§6 · Las cuatro obras propias son inversión, no consumo personal")
    for obra in [o.nombre for o in m.obras if o.tipo == "obra_propia"]:
        r = interpretar(f"Marcos Carpintero/{obra}")
        check(f"{obra} clasifica como obra", r.fichas[0].campos["tipo_gasto"] == "obra",
              f"dio {r.fichas[0].campos['tipo_gasto']} por {r.fichas[0].regla}")

    print("\n§5.4 · «Retiro» manda siempre y conserva el proveedor")
    r = interpretar("Electricidad Angostura/Retiro")
    check("Retiro gana sobre el contratista de obra",
          r.fichas[0].campos["tipo_gasto"] == "personal"
          and r.fichas[0].campos["contratista"] == "Electricidad Angostura"
          and not any(p.campo == "obra" for p in r.preguntas),
          f"{r.fichas[0].campos['tipo_gasto']} / {r.fichas[0].regla}")

    print("\n§5.8 · Las cajas de obra no suman al saldo del estudio")
    del_estudio = {c.nombre for c in m.cuentas_del_estudio()}
    check("«Pagado por el comitente» queda afuera", "Pagado por el comitente" not in del_estudio)
    check("Banco y Efectivo quedan adentro", {"Banco", "Efectivo"} <= del_estudio, f"son {sorted(del_estudio)}")
    check("`caja_obra` está en los tipos que no suman", "caja_obra" in TIPOS_CUENTA_FUERA_DEL_ESTUDIO)
    terceros = [o.nombre for o in m.obras if o.tipo == "obra_terceros" and o.estado == "activa"]
    check("cada obra de terceros activa tiene su caja de obra", all(m.caja_de_obra(o) for o in terceros),
          [o for o in terceros if not m.caja_de_obra(o)])
    # §5.8 v1.7: cualquier obra puede tener caja chica (Gonzalo tiene desde el 30/09). Lo que
    # no puede haber es una caja de una obra que no existe.
    cajas = [c.nombre for c in m.cuentas if c.tipo == "caja_obra" and c.activa]
    check("cada caja de obra es de una obra que existe", all(m.obra_de_caja(c) for c in cajas),
          [c for c in cajas if not m.obra_de_caja(c)])
    check("una cuenta inactiva no se puede usar", all(m.cuenta(c.nombre) is None for c in m.cuentas if not c.activa))

    print("\n§5.13 · Usuarios")
    check("todos los usuarios activos tienen teléfono", all(u.telefono for u in m.usuarios if u.activo),
          [u.nombre for u in m.usuarios if u.activo and not u.telefono])
    check("Petrus tiene las mismas atribuciones: ve lo personal",
          all(u.ve_personal for u in m.usuarios if u.activo), [(u.nombre, u.ve_personal) for u in m.usuarios])

    print("\n§5.11 · El certificado viaja en la ficha y no se pierde")
    r = interpretar("Ingreso $2.600.000 Moreno/ cert. 4 /efectivo")
    f = r.fichas[0]
    check("certificado 4 en extras y en la descripción",
          f.extras.get("certificado") == "4" and "Certificado 4" in (f.campos["descripcion"] or ""),
          f"extras={f.extras.get('certificado')} descripcion={f.campos['descripcion']}")
    check("el cobro dice a qué obra corresponde", f.campos["obra"] == "Moreno")

    # ── El gasto del lector de comprobantes (sin llamar al modelo: se reemplaza) ──
    print("\nEl lector de comprobantes: se mide y no se paga dos veces")
    import tempfile
    from pathlib import Path

    from app import comprobante, llm
    llamadas: list[int] = []

    def lector_falso(contenido, mime, texto):
        llamadas.append(1)
        return ({"importe": 1234.5, "fecha": "2026-10-09", "razon_social_destinatario": "PEREZ, ELIAS"},
                {"tipo": "comprobante", "modelo": "claude-sonnet-5-5", "input": 3000, "output": 200,
                 "cache_read": 0, "cache_write": 0})
    originales = (llm.extraer_comprobante, llm.disponible, os.environ.get("CACHE_COMPROBANTES"))
    llm.extraer_comprobante, llm.disponible = lector_falso, lambda: True
    os.environ["CACHE_COMPROBANTES"] = str(Path(tempfile.mkdtemp()) / "cache.json")  # settings() se relee siempre
    try:
        a = comprobante.leer_bytes(b"un-comprobante", "x.jpg", "image/jpeg")
        b = comprobante.leer_bytes(b"un-comprobante", "x.jpg", "image/jpeg")
        check("el uso de la lectura se guarda (antes se tiraba) y lleva el tipo «comprobante»",
              a.uso and a.uso.get("tipo") == "comprobante" and a.uso.get("input") == 3000, a.uso)
        check("el mismo archivo con el mismo modelo se lee de la caché: una sola llamada, mismos datos",
              len(llamadas) == 1 and b.uso.get("cache_local") and (b.importe, b.razon_social) == (1234.5, "PEREZ, ELIAS"),
              (len(llamadas), b.uso))
        check("costo estimado: 3.000 de entrada y 200 de salida en Sonnet 5.5 = USD 0,008",
              abs(llm.costo_usd(a.uso) - 0.008) < 1e-9, llm.costo_usd(a.uso))
    finally:
        llm.extraer_comprobante, llm.disponible = originales[0], originales[1]
        if originales[2] is None:
            os.environ.pop("CACHE_COMPROBANTES", None)
        else:
            os.environ["CACHE_COMPROBANTES"] = originales[2]

    print(f"\n{'TODO OK' if not fallas else str(len(fallas)) + ' FALLAS'}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
