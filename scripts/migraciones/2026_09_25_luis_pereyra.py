"""«Luis Pereyra» es la misma persona que «Luis Pereira»: la fila repetida pasa a inactiva.

Confirmado por Valentín el 25/09. El alias `luis pereyra` ya apuntaba a «Luis Pereira», así que
el bot nunca proponía la fila con y; lo único que hacía era dejar la advertencia de un rubro
habitual inexistente («Pintura»). Nada se borra (CONTEXTO-FACHADO.md §5.1 y §9): la fila queda
`inactivo`, con una nota que dice por qué. Idempotente.

    python scripts/migraciones/2026_09_25_luis_pereyra.py
    python scripts/migraciones/2026_09_25_luis_pereyra.py --aplicar
"""
import argparse
import sys

sys.path.insert(0, ".")
from app import sheets  # noqa: E402
from app.config import settings  # noqa: E402
from app.maestros import normalizar  # noqa: E402
from app.sheets import columna_a_letra as letra  # noqa: E402

REPETIDA = "Luis Pereyra"
CANONICA = "Luis Pereira"
NOTA = f"Misma persona que «{CANONICA}» (confirmado por Valentín, 25/09). Inactivo: no se borra."


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    sid = settings().sheet_id
    filas = sheets.leer_rango(sid, "CONTRATISTAS!A:Z", formato="FORMATTED_VALUE")
    encabezado = [normalizar(x) for x in filas[0]]
    c_nombre, c_estado, c_notas = (encabezado.index(x) for x in ("contratista", "estado", "notas"))

    if not any(len(f) > c_nombre and normalizar(f[c_nombre]) == normalizar(CANONICA) for f in filas[1:]):
        sys.exit(f"No está «{CANONICA}» en CONTRATISTAS: no se inactiva la otra fila sin la canónica")

    cambios: list[tuple[str, str, str]] = []
    for n, f in enumerate(filas[1:], start=2):
        if len(f) <= c_nombre or normalizar(f[c_nombre]) != normalizar(REPETIDA):
            continue
        for col, nuevo in ((c_estado, "inactivo"), (c_notas, NOTA)):
            actual = f[col] if col < len(f) else ""
            if actual != nuevo:
                cambios.append((f"CONTRATISTAS!{letra(col + 1)}{n}", actual, nuevo))

    if not cambios:
        print("Nada que hacer: ya está inactivo.")
        return
    for rango, antes, despues in cambios:
        print(f"  · {rango}: «{antes}» → «{despues}»")
    if not args.aplicar:
        print("\n(simulacro: no se escribió nada. Correr con --aplicar)")
        return
    for rango, _, despues in cambios:
        sheets.escribir_rango(sid, rango, [[despues]])
    print(f"\nAplicado: {len(cambios)} cambio(s)")


if __name__ == "__main__":
    main()
