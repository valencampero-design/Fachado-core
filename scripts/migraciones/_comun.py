"""Lo común a las migraciones de datos del maestro, desde el 30/09.

Cada migración declara qué celdas pone y qué filas agrega; esto se encarga de leer, mostrar
el simulacro y aplicar. Dos destinos:

- **El Sheet** (por defecto): sin `--aplicar` es un simulacro. Las columnas tienen que existir
  antes: las agrega `scripts/preparar_sheet.py --aplicar`.
- **`--snapshot tests/maestros_snapshot.json`**: aplica lo mismo sobre la copia de los maestros
  que usan los tests, sin tocar el Sheet. Agrega las columnas que falten. Así la métrica se
  mide con el maestro como va a quedar.

Idempotente siempre: lo que ya está como corresponde no se vuelve a escribir.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from app.maestros import normalizar  # noqa: E402


class Migracion:
    def __init__(self, hojas: list[str], descripcion: str):
        ap = argparse.ArgumentParser(description=descripcion)
        ap.add_argument("--aplicar", action="store_true", help="escribir en el Sheet (sin esto, simulacro)")
        ap.add_argument("--snapshot", metavar="JSON", help="aplicar sobre la copia de los tests en vez del Sheet")
        self.args = ap.parse_args()
        sys.stdout.reconfigure(encoding="utf-8")
        self.hojas = hojas
        self.cambios: list[tuple[str, str, int, str, str, str]] = []  # (tipo, hoja, fila, columna, valor, por qué)
        self.nuevas: list[tuple[str, list, str]] = []  # (hoja, fila, por qué)
        if self.args.snapshot:
            self.snapshot = json.loads(Path(self.args.snapshot).read_text(encoding="utf-8"))
            self.tablas = {h: [list(f) for f in self.snapshot.get(h, [])] for h in hojas}
        else:
            from app import sheets
            from app.config import settings
            self.sid = settings().sheet_id
            self.tablas = sheets.leer_hojas(self.sid, [f"{h}!A:Z" for h in hojas])

    # ── Lectura ────────────────────────────────────────────────────────────────
    def encabezado(self, hoja: str) -> list[str]:
        return [str(x) for x in (self.tablas.get(hoja) or [[]])[0]]

    def asegurar_columna(self, hoja: str, columna: str) -> None:
        if columna in self.encabezado(hoja):
            return
        if not self.args.snapshot:
            sys.exit(f"{hoja} no tiene la columna «{columna}»: correr antes scripts/preparar_sheet.py --aplicar")
        self.tablas[hoja][0].append(columna)
        self.cambios.append(("columna", hoja, 1, columna, columna, "columna nueva"))

    def registros(self, hoja: str) -> list[tuple[int, dict]]:
        """(número de fila en el Sheet, {columna: valor}) de cada fila con datos."""
        enc = self.encabezado(hoja)
        return [(n, {c: (str(f[i]) if i < len(f) else "") for i, c in enumerate(enc)})
                for n, f in enumerate(self.tablas.get(hoja, [])[1:], start=2) if any(str(x).strip() for x in f)]

    def buscar(self, hoja: str, **igual) -> list[tuple[int, dict]]:
        return [(n, r) for n, r in self.registros(hoja)
                if all(normalizar(r.get(c)) == normalizar(v) for c, v in igual.items())]

    # ── Cambios ────────────────────────────────────────────────────────────────
    def poner(self, hoja: str, fila: int, columna: str, valor: str, por: str) -> None:
        enc = self.encabezado(hoja)
        actual = self.tablas[hoja][fila - 1]
        i = enc.index(columna)
        if (str(actual[i]) if i < len(actual) else "") == valor:
            return
        self.cambios.append(("celda", hoja, fila, columna, valor, por))
        while len(actual) <= i:
            actual.append("")
        actual[i] = valor

    def agregar(self, hoja: str, valores: dict, por: str) -> None:
        fila = [valores.get(c, "") for c in self.encabezado(hoja)]
        self.nuevas.append((hoja, fila, por))
        self.tablas[hoja].append(fila)

    # ── Salida ─────────────────────────────────────────────────────────────────
    def terminar(self) -> None:
        if not (self.cambios or self.nuevas):
            print("Nada que hacer: el maestro ya está como corresponde.")
            return
        for tipo, hoja, fila, columna, valor, por in self.cambios:
            print(f"  · {hoja} fila {fila}, {columna} = «{valor}»  ({por})" if tipo == "celda"
                  else f"  · {hoja}: columna nueva «{columna}»")
        for hoja, fila, por in self.nuevas:
            print(f"  + {hoja}: {fila}  ({por})")
        if self.args.snapshot:
            for h in self.hojas:
                self.snapshot[h] = self.tablas[h]
            Path(self.args.snapshot).write_text(json.dumps(self.snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\nAplicado sobre {self.args.snapshot} (el Sheet no se tocó)")
            return
        if not self.args.aplicar:
            print("\n(simulacro: no se escribió nada. Correr con --aplicar)")
            return
        from app import sheets
        from app.sheets import columna_a_letra as letra
        for tipo, hoja, fila, columna, valor, _ in self.cambios:
            if tipo == "celda":
                col = self.encabezado(hoja).index(columna) + 1
                sheets.escribir_rango(self.sid, f"{hoja}!{letra(col)}{fila}", [[valor]])
        for hoja, fila, _ in self.nuevas:
            sheets.agregar_filas(self.sid, f"{hoja}!A:{letra(len(fila))}", [fila])
        print(f"\nAplicado: {len(self.cambios)} celda(s) y {len(self.nuevas)} fila(s) nueva(s)")
