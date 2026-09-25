"""Migración de datos de la tanda 1 del handoff del 25/09 (CONTEXTO-FACHADO.md v1.5).

Queda versionada para que se sepa qué se tocó a mano en el maestro y en el libro, y por qué.
Idempotente: si algo ya está como corresponde, no lo vuelve a escribir.

    python scripts/migraciones/2026_09_25_tanda1.py --petrus-telefono <tel>
    python scripts/migraciones/2026_09_25_tanda1.py --petrus-telefono <tel> --aplicar

Antes: `python scripts/preparar_sheet.py --aplicar` (crea las columnas que esto completa).

Lo que hace, con el punto del contexto que lo justifica:

- USUARIOS: `ve_personal` y `auto_confirmar` para los dos, y el teléfono de Petrus (§5.13).
- TERCEROS: Petrus vuelve a `activo`: maneja efectivo del estudio (§5.13).
- CONTRATISTAS: «Pint Andina» se llama «Pinturería Andina» (§7). Ningún movimiento la
  referenciaba, así que se renombra. Alias `pint andina` y `ferr andina` (§7).
- CUENTAS: una «Caja obra <obra>» por cada obra de terceros activa (§5.8); la fila mal
  cargada «caja_obra» pasa a `inactiva`. Las obras propias no llevan caja.
- MOVIMIENTOS: M-000007 a M-000009 (certificaciones de Moreno) pasan de Efectivo a
  «Caja obra Moreno» (§5.8). **Única edición del libro**, autorizada por el handoff y por
  Valentín el 25/09: son filas semilla, cargadas a mano antes de que existiera /confirmar.
  Ninguna fila confirmada se edita.
"""
import argparse
import sys

sys.path.insert(0, ".")
from app import sheets  # noqa: E402
from app.config import settings  # noqa: E402
from app.maestros import normalizar, solo_digitos  # noqa: E402
from app.sheets import columna_a_letra as letra  # noqa: E402

FILAS_SEMILLA_MORENO = ["M-000007", "M-000008", "M-000009"]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--petrus-telefono", required=True)
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    sid = settings().sheet_id
    leido = sheets.leer_hojas(sid, ["USUARIOS!A:Z", "TERCEROS!A:Z", "CONTRATISTAS!A:Z", "ALIAS!A:C",
                                    "CUENTAS!A:Z", "OBRAS!A:Z", "MOVIMIENTOS!A:AZ"])
    cambios: list[tuple[str, list[list], str]] = []

    def col(hoja: str, nombre: str) -> int:
        return leido[hoja][0].index(nombre) + 1

    def celda(hoja: str, fila: int, nombre: str) -> str:
        return f"{hoja}!{letra(col(hoja, nombre))}{fila}"

    def valor(hoja: str, fila: int, nombre: str) -> str:
        f = leido[hoja][fila - 1]
        i = col(hoja, nombre) - 1
        return str(f[i]) if i < len(f) else ""

    def poner(hoja: str, fila: int, nombre: str, nuevo: str, por: str) -> None:
        if valor(hoja, fila, nombre) != nuevo:
            cambios.append((celda(hoja, fila, nombre), [[nuevo]], f"{por}: {nombre} «{valor(hoja, fila, nombre)}» → «{nuevo}»"))

    def filas_de(hoja: str, columna: str, buscado: str) -> list[int]:
        i = col(hoja, columna) - 1
        return [n for n, f in enumerate(leido[hoja], start=1)
                if n > 1 and len(f) > i and normalizar(str(f[i])) == normalizar(buscado)]

    # ── USUARIOS (§5.13) ──────────────────────────────────────────────────────
    for n, f in enumerate(leido["USUARIOS"][1:], start=2):
        nombre = f[1] if len(f) > 1 else ""
        if not nombre:
            continue
        poner("USUARIOS", n, "ve_personal", "sí", nombre)
        poner("USUARIOS", n, "auto_confirmar", "no", nombre)
        if normalizar(nombre) == "petrus":
            poner("USUARIOS", n, "telefono", solo_digitos(args.petrus_telefono), nombre)
            poner("USUARIOS", n, "activo", "sí", nombre)

    # ── TERCEROS (§5.13) ──────────────────────────────────────────────────────
    for n in filas_de("TERCEROS", "tercero", "Petrus"):
        poner("TERCEROS", n, "estado", "activo", "Petrus")
        poner("TERCEROS", n, "notas", "Reincorporado el 24/09 (contexto §5.13): maneja efectivo del estudio. "
                                      "NO borrar: 106 pagos del histórico lo referencian.", "Petrus")

    # ── Pinturería Andina (§7) ────────────────────────────────────────────────
    for n in filas_de("CONTRATISTAS", "contratista", "Pint Andina"):
        poner("CONTRATISTAS", n, "contratista", "Pinturería Andina", f"CONTRATISTAS fila {n}")
    alias_existentes = {(normalizar(f[0]), normalizar(f[1])) for f in leido["ALIAS"][1:] if len(f) > 1}
    alias_nuevos = [[como, destino, "contratista"] for como, destino in
                    (("pint andina", "Pinturería Andina"), ("ferr andina", "Ferretería Andina"))
                    if (normalizar(como), normalizar(destino)) not in alias_existentes]
    if alias_nuevos:
        n = len(leido["ALIAS"]) + 1
        cambios.append((f"ALIAS!A{n}:C{n + len(alias_nuevos) - 1}", alias_nuevos,
                        f"ALIAS: {[a[0] for a in alias_nuevos]}"))

    # ── CUENTAS: estado y cajas de obra (§5.8) ────────────────────────────────
    for n, f in enumerate(leido["CUENTAS"][1:], start=2):
        if not f or not f[0]:
            continue
        mal_cargada = normalizar(f[0]).replace(" ", "_") == "caja_obra"
        poner("CUENTAS", n, "estado", "inactiva" if mal_cargada else (valor("CUENTAS", n, "estado") or "activa"), f"CUENTAS «{f[0]}»")
        if mal_cargada:
            poner("CUENTAS", n, "notas", "Mal cargada: una caja de obra va una fila por obra. Inactiva desde 25/09", f"CUENTAS «{f[0]}»")

    enc_obras = leido["OBRAS"][0]
    i_tipo, i_estado = enc_obras.index("tipo"), enc_obras.index("estado")
    obras_terceros = [f[0] for f in leido["OBRAS"][1:]
                      if len(f) > i_estado and normalizar(f[i_tipo]) == "obra terceros" and normalizar(f[i_estado]) == "activa"]
    existentes = {normalizar(f[0]) for f in leido["CUENTAS"][1:] if f}
    cajas = [[f"Caja obra {obra}", "caja_obra", "ARS", "no", "0,00",
              "Plata del comitente en poder del arquitecto (contexto §5.8). No suma al saldo del estudio", "activa"]
             for obra in obras_terceros if normalizar(f"Caja obra {obra}") not in existentes]
    if cajas:
        n = len(leido["CUENTAS"]) + 1
        enc = leido["CUENTAS"][0]
        orden = ["cuenta", "tipo", "moneda", "concilia_contra_banco", "saldo_apertura", "notas", "estado"]
        filas = [[c[orden.index(h)] if h in orden else "" for h in enc] for c in cajas]
        cambios.append((f"CUENTAS!A{n}:{letra(len(enc))}{n + len(filas) - 1}", filas,
                        f"CUENTAS: {len(filas)} cajas de obra ({', '.join(obras_terceros)})"))

    # ── MOVIMIENTOS: las tres certificaciones de Moreno (§5.8) ─────────────────
    for id_mov in FILAS_SEMILLA_MORENO:
        for n in filas_de("MOVIMIENTOS", "id_mov", id_mov):
            if normalizar(valor("MOVIMIENTOS", n, "obra")) == "moreno":
                poner("MOVIMIENTOS", n, "cuenta", "Caja obra Moreno", id_mov)

    for rango, valores, que in cambios:
        print(f"  {rango:<24} {que}")
        if len(valores) > 1 or len(valores[0]) > 1:
            for v in valores:
                print(f"  {'':<24}   {v}")
    if not cambios:
        print("Nada que hacer: ya está todo migrado.")
        return
    if not args.aplicar:
        print(f"\n{len(cambios)} cambio(s). Simulacro: no se escribió nada. Correr con --aplicar")
        return
    for rango, valores, _ in cambios:
        sheets.escribir_rango(sid, rango, valores)
    print(f"\nAplicado: {len(cambios)} cambio(s)")


if __name__ == "__main__":
    main()
