"""Genera las muestras ARMADAS de octubre para tests/test_conciliar.py (handoff del 20/10, M2).

No son archivos reales: son el formato esperado, mientras no llegue la muestra de Mercado Pago
(`Archivos Muestra/Muestra 3/`). Cuando llegue, gana la muestra: se ajusta el parser y estos
archivos quedan como casos chicos y legibles.

- `armado-octubre-mercado-pago.pdf`: el «resumen de cuenta» de Mercado Pago, con texto (no
  escaneado), `Fecha | Descripción | ID de la operación | Valor | Saldo`.
- `armado-octubre-CA.xlsx`, `armado-octubre-CC.xlsx`, `armado-octubre-USD.xlsx`: extractos de
  Banco Patagonia con el formato de `CompartirDetalleMovimiento-*.xlsx`, armados para que haya un
  pase CA → CC, un pase Banco → Mercado Pago, una compra de dólares (CA $ → CA U$S) y gastos
  bancarios en las dos monedas.

    python tests/fixtures/generar_muestras_armadas.py
"""
from pathlib import Path

AQUI = Path(__file__).resolve().parent

MERCADO_PAGO = [
    "Mercado Pago",
    "RESUMEN DE CUENTA",
    "Periodo: 01-10-2026 al 31-10-2026",
    "Fecha Descripción ID de la operación Valor Saldo",
    "28-10-2026 Transferencia recibida de Gabriel Federico Fachado 81234567890 $ 300.000,00 $ 312.345,67",
    "29-10-2026 Compra Mercado Libre 81234567891 $ -23.587,34 $ 288.758,33",
    "30-10-2026 Rendimientos 81234567892 $ 1.234,56 $ 289.992,89",
    "30-10-2026 Transferencia enviada a Grimau 81234567893 $ -165.700,00 $ 124.292,89",
    "31-10-2026 Retención de IIBB 81234567894 $ -120,00 $ 124.172,89",
    "Saldo final $ 124.172,89",
]

PESOS = "$\xa0"
DOLARES = "US$\xa0"
BANCO = {
    "armado-octubre-CA.xlsx": ("CA $ 273-125852351-000", PESOS, [
        ("31/10/2026", "COMISION MANTENIMIENTO CUENTA ", "1.500,00", "", "1.000.000,00"),
        ("28/10/2026", "TRANSFERENCIA ENTRE CUENTAS PROPIAS ", "50.000,00", "", "1.001.500,00"),
        ("28/10/2026", "TRANSFERENCIA E-BANK A CVU MERCADO PAGO ", "300.000,00", "", "1.051.500,00"),
        ("27/10/2026", "COMPRA-VENTA DOLARES POR EBANK ", "145.000,00", "", "1.351.500,00"),
        ("26/10/2026", "TRANSFERENCIA ENTRE CUENTAS VAR 20929415044  MARAGAÑO GUERRERO MARCELO", "30.000,00", "",
         "1.496.500,00"),
    ]),
    "armado-octubre-CC.xlsx": ("CC $ 273-125852351-000", PESOS, [
        ("28/10/2026", "TRANSFERENCIA ENTRE CUENTAS PROPIAS ", "", "50.000,00", "50.000,00"),
    ]),
    "armado-octubre-USD.xlsx": ("CA U$S 273-125852351-000", DOLARES, [
        ("31/10/2026", "ACREDITACION DE INTERESES ", "", "0,05", "98,05"),
        ("30/10/2026", "COMISION PAQUETE ", "2,00", "", "98,00"),
        ("27/10/2026", "COMPRA-VENTA DOLARES POR EBANK ", "", "100,00", "100,00"),
    ]),
}


def pdf_con_texto(lineas: list[str]) -> bytes:
    """Un PDF mínimo con una línea de texto por renglón (Helvetica, WinAnsi)."""
    def literal(t: str) -> bytes:
        crudo = t.encode("cp1252")
        return b"(" + crudo.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"
    texto = b"BT /F1 9 Tf 12 TL 30 560 Td " + b" ".join(literal(t) + b" Tj T*" for t in lineas) + b" ET"
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(texto)).encode() + b" >>\nstream\n" + texto + b"\nendstream",
    ]
    salida = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objetos, start=1):
        offsets.append(len(salida))
        salida += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    salida += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    salida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(salida)


def extracto_banco(cuenta: str, signo: str, filas: list[tuple]) -> bytes:
    import io

    import openpyxl
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "Movimientos"
    hoja.append(["Información de sus cuentas"])
    hoja.append(["Cuenta:", cuenta])
    hoja.append(["Saldos al:", "31/10/2026 10:00"])
    hoja.append([])
    hoja.append(["Ultimos Movimientos"])
    hoja.append(["Fecha", "Descripción", "Débito", "Crédito", "Saldo"])
    for fecha, desc, debito, credito, saldo in filas:
        hoja.append([fecha, desc, signo + debito if debito else "", signo + credito if credito else "", signo + saldo])
    buf = io.BytesIO()
    libro.save(buf)
    return buf.getvalue()


def main() -> None:
    (AQUI / "armado-octubre-mercado-pago.pdf").write_bytes(pdf_con_texto(MERCADO_PAGO))
    for nombre, (cuenta, signo, filas) in BANCO.items():
        (AQUI / nombre).write_bytes(extracto_banco(cuenta, signo, filas))
    print("Listo:", ", ".join(["armado-octubre-mercado-pago.pdf", *BANCO]))


if __name__ == "__main__":
    main()
