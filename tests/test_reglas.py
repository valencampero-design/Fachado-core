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

    print("\n§5.11 · El certificado viaja en la ficha y no se pierde")
    r = interpretar("Ingreso $2.600.000 Moreno/ cert. 4 /efectivo")
    f = r.fichas[0]
    check("certificado 4 en extras y en la descripción",
          f.extras.get("certificado") == "4" and "Certificado 4" in (f.campos["descripcion"] or ""),
          f"extras={f.extras.get('certificado')} descripcion={f.campos['descripcion']}")
    check("el cobro dice a qué obra corresponde", f.campos["obra"] == "Moreno")

    print(f"\n{'TODO OK' if not fallas else str(len(fallas)) + ' FALLAS'}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
