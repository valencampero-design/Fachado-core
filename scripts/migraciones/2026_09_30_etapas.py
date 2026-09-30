"""ETAPAS: las etapas relevadas el 29/09 (CONTEXTO-FACHADO.md §5.15, v1.7).

| Obra   | Etapas |
|--------|--------|
| Lennon | 1 en curso; 2 y 3 futuras |
| Moreno | 1 en curso y extras en curso; 2 futura |

El resto de las obras no tiene etapas: no se cargan filas. Si una fila ya existe, solo se
corrige su estado; nada se borra.

    python scripts/migraciones/2026_09_30_etapas.py                  (simulacro)
    python scripts/migraciones/2026_09_30_etapas.py --aplicar
    python scripts/migraciones/2026_09_30_etapas.py --snapshot tests/maestros_snapshot.json

**Correrla después de desplegar el motor del 30/09**: la versión anterior no entiende una
etapa con nombre («extras») ni el estado «futura», y preguntaría etapas que no corresponden.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _comun import Migracion  # noqa: E402

ETAPAS = [
    ("Lennon", "1", "Etapa 1", "en curso"),
    ("Lennon", "2", "Etapa 2", "futura"),
    ("Lennon", "3", "Etapa 3", "futura"),
    ("Moreno", "1", "Etapa 1", "en curso"),
    ("Moreno", "extras", "Extras", "en curso"),
    ("Moreno", "2", "Etapa 2", "futura"),
]
POR_QUE = "§5.15 v1.7: relevadas el 29/09"


def main() -> None:
    mig = Migracion(["ETAPAS", "OBRAS"], __doc__)
    for columna in ("obra", "etapa", "descripcion", "estado"):
        mig.asegurar_columna("ETAPAS", columna)
    for obra, etapa, descripcion, estado in ETAPAS:
        if not mig.buscar("OBRAS", obra=obra):
            sys.exit(f"No está la obra «{obra}» en OBRAS")
        existentes = mig.buscar("ETAPAS", obra=obra, etapa=etapa)
        if existentes:
            for n, _ in existentes:
                mig.poner("ETAPAS", n, "estado", estado, POR_QUE)
        else:
            mig.agregar("ETAPAS", {"obra": obra, "etapa": etapa, "descripcion": descripcion, "estado": estado}, POR_QUE)
    mig.terminar()


if __name__ == "__main__":
    main()
