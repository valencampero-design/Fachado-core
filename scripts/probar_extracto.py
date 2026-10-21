"""Prueba un extracto sin importarlo: cómo lo lee el motor y cómo lo clasificaría.

Para la primera muestra de un formato nuevo (el reporte de Mercado Pago, 21/10) o cuando un
extracto da 422. No lee ni escribe ningún Sheet: usa el maestro del snapshot.

    python scripts/probar_extracto.py "Archivos Muestra/Muestra 3/reporte.pdf"
    python scripts/probar_extracto.py archivo.pdf --texto      (además, el texto crudo del PDF)

Muestra, por línea: fecha, importe, saldo, a qué cuenta del libro iría y si va a un lote. Y un
**control de saldos**: el saldo de cada línea tiene que ser el de la anterior más su importe.
Si no encadena, el parser se salteó una línea o leyó mal un signo.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, ".")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archivos", nargs="+")
    ap.add_argument("--texto", action="store_true", help="mostrar el texto crudo del PDF (las primeras 80 líneas)")
    args = ap.parse_args()
    os.environ.setdefault("MAESTROS_SNAPSHOT", str(Path("tests") / "maestros_snapshot.json"))

    from app import maestros
    from app.conciliar import cuenta_de_linea, lote_de
    from app.extracto import ExtractoNoReconocido, leer_extracto

    m = maestros.cargar()
    codigo = 0
    for archivo in args.archivos:
        contenido = Path(archivo).read_bytes()
        print(f"\n=== {archivo} ({len(contenido):,} bytes)")
        if args.texto and contenido.startswith(b"%PDF-"):
            from app.comprobante import texto_pdf
            texto = texto_pdf(contenido) or ""
            print(f"--- texto del PDF ({len(texto.splitlines())} líneas; las primeras 80)")
            for renglon in texto.splitlines()[:80]:
                print(f"  | {renglon}")
            print("---")
        try:
            lineas = leer_extracto(contenido)
        except ExtractoNoReconocido as e:
            print(f"NO RECONOCIDO (el motor contestaría 422): {e}")
            codigo = 1
            continue
        print(f"{len(lineas)} líneas · origen {lineas[0].origen} · cuenta_banco «{lineas[0].cuenta_banco}» · "
              f"{lineas[-1].fecha} a {lineas[0].fecha}")
        print(f"{'fecha':10} {'importe':>14} {'saldo':>14}  {'cuenta':12} {'lote':16} descripción")
        for x in lineas:
            d = x.dict()
            cuenta = cuenta_de_linea(d, m)
            importe = (x.credito or 0) - (x.debito or 0)
            print(f"{x.fecha:10} {importe:>14,.2f} {x.saldo if x.saldo is not None else '':>14}  "
                  f"{(cuenta.nombre if cuenta else '¿?')[:12]:12} {lote_de(d) or '-':16} {x.descripcion[:60]}"
                  + (f"  [ref {x.ref}]" if x.ref else ""))
        # control: en orden cronológico (orden alto = más vieja), saldo_n = saldo_n-1 + importe_n
        cronologico = sorted(lineas, key=lambda x: (x.fecha, -x.orden))
        rotos = []
        for antes, x in zip(cronologico, cronologico[1:]):
            if antes.saldo is None or x.saldo is None:
                continue
            esperado = round(antes.saldo + (x.credito or 0) - (x.debito or 0), 2)
            if abs(esperado - x.saldo) > 0.01:
                rotos.append((x, esperado))
        if rotos:
            codigo = 1
            print(f"\nCONTROL DE SALDOS: {len(rotos)} línea(s) no encadenan (se saltea una línea o un signo está mal):")
            for x, esperado in rotos[:10]:
                print(f"  {x.fecha} {x.descripcion[:50]}: saldo {x.saldo:,.2f}, esperado {esperado:,.2f}")
        else:
            print("\nControl de saldos: OK, cada saldo es el anterior más el importe.")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
