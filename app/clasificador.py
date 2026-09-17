"""La cascada obra / estructura / personal. SIN LLM.

Son reglas de negocio: tienen que ser deterministas y auditables. Se evalúan en orden y
gana la primera que matchea. Cada resultado lleva el nombre de la regla que lo decidió.
"""
from dataclasses import dataclass

from app.maestros import Contratista, Maestros, Obra, Rubro

CLASIFICACION_POR_TIPO_OBRA = {
    "obra_terceros": "obra",
    "obra_propia": "obra",
    "estructura": "estructura",
    "personal": "personal",
}


@dataclass
class Resultado:
    clasificacion: str | None  # obra | estructura | personal | None (hay que preguntar)
    regla: str
    preguntar: str | None = None  # "clasificacion" | "obra" | None


def clasificar(
    m: Maestros,
    tipo_mov: str,
    obra: Obra | None,
    contratista: Contratista | None,
    rubro: Rubro | None,
    marcador_personal_fuerte: bool,
    marcador_personal_debil: bool,
) -> Resultado:
    if tipo_mov == "TRASPASO":
        # Sacar plata del cajero es un traspaso entre cuentas, no un gasto.
        return Resultado(None, "T: traspaso entre cuentas, no se clasifica")

    # 1. El destino manda sobre el proveedor: casa / particular / obra personal.
    if marcador_personal_fuerte or (obra and obra.tipo == "personal"):
        return Resultado("personal", "R1: destino personal (casa, particular u obra personal)")

    if tipo_mov == "INGRESO":
        if obra:
            return Resultado(CLASIFICACION_POR_TIPO_OBRA.get(obra.tipo), f"R4: tipo de la obra ({obra.tipo})")
        return Resultado(None, "R5: ingreso sin obra", preguntar="obra")

    # 2. Contratista dual (obra y personal): siempre se pregunta.
    if contratista and contratista.dual:
        return Resultado(None, f"R2: «{contratista.nombre}» es dual", preguntar="clasificacion")

    # 3. El rubro resuelto afecta lo personal.
    if rubro and rubro.afecta == "personal":
        return Resultado("personal", f"R3: rubro «{rubro.rubro_2}» afecta personal")

    # La obra identificada define la clasificación por su tipo.
    if obra:
        return Resultado(CLASIFICACION_POR_TIPO_OBRA.get(obra.tipo), f"R4: tipo de la obra ({obra.tipo})")

    # 4. Contratista con rubro de obra y sin obra → es de obra, falta saber cuál.
    if contratista and rubro and rubro.afecta == "obra":
        return Resultado("obra", "R4: contratista de obra sin obra identificada", preguntar="obra")
    if rubro and rubro.afecta == "estructura":
        return Resultado("estructura", f"R4: rubro «{rubro.rubro_2}» afecta estructura")

    # «Retiro» sin nada más fuerte: personal, y se pregunta el rubro.
    if marcador_personal_debil:
        return Resultado("personal", "R1b: «Retiro» sin otra señal → personal")

    # 5. Nada de lo anterior.
    return Resultado(None, "R5: sin señales suficientes", preguntar="obra")
