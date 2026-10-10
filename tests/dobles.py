"""Dobles de prueba compartidos: un libro en memoria y un Drive falso.

Los tests NUNCA escriben en el Sheet real: MOVIMIENTOS es append-only y una fila de prueba no
se puede borrar. El libro en memoria imita al Sheet en lo que importa: escribir la fila N pisa
lo que había en la fila N. Así, si el lock del id_mov fallara, se vería igual que en
producción: dos confirmaciones sacan el mismo número y la segunda borra a la primera.
"""
import contextlib
import time

# El encabezado de CERTIFICADOS (tanda 5). Vive acá para no depender del snapshot, que solo
# guarda maestros.
ENCABEZADO_CERTIFICADOS = ["obra", "etapa", "numero", "fecha", "saldo_a_cobrar", "fuente", "msg_id",
                           "cargado_por", "comprobante_url"]


class LibroMemoria:
    def __init__(self, encabezado: list[str], alias: list[list] = (), demora: float = 0.0):
        self.encabezado = list(encabezado)
        self.filas: list[list] = [list(encabezado)]
        self.alias = [list(a) for a in alias]
        self.contratistas_nuevos: list[dict] = []  # altas de §5.6 v1.9
        self.certificados: list[list] = [list(ENCABEZADO_CERTIFICADOS)]
        self.demora = demora
        self.escrituras = 0  # llamadas de escritura a MOVIMIENTOS: un traspaso tiene que ser una
        self.reactivados: list[str] = []  # contratistas que /confirmar reactivó en el maestro
        self.etapas_activadas: list[tuple[str, str]] = []  # etapas que /confirmar pasó a en curso

    def sembrar(self, **campos) -> None:
        """Una fila ya existente en el libro, cargada antes de la prueba."""
        self.filas.append([campos.get(c, "") for c in self.encabezado])

    def leer_movimientos(self):
        time.sleep(self.demora)
        return [list(f) for f in self.filas]

    def escribir_fila(self, numero, valores):
        self.escribir_filas(numero, [valores])

    def escribir_filas(self, numero, filas):
        time.sleep(self.demora)
        self.escrituras += 1
        for i, valores in enumerate(filas):
            _escribir(self.filas, numero + i, valores)

    def leer_alias(self):
        return [list(a) for a in self.alias]

    def agregar_alias(self, fila):
        self.alias.append(list(fila))

    def agregar_contratista(self, valores):
        from app.maestros import normalizar
        if any(normalizar(c.get("contratista")) == normalizar(valores.get("contratista")) for c in self.contratistas_nuevos):
            return False
        self.contratistas_nuevos.append(dict(valores))
        return True

    def reactivar_contratista(self, nombre):
        self.reactivados.append(nombre)
        return True

    def activar_etapa(self, obra, etapa):
        self.etapas_activadas.append((obra, etapa))
        return True

    def leer_certificados(self):
        return [list(f) for f in self.certificados]

    def escribir_certificado(self, numero, valores):
        _escribir(self.certificados, numero, valores)

    def movimientos(self) -> list[dict]:
        return [dict(zip(self.encabezado, f)) for f in self.filas[1:]]


def _escribir(tabla: list[list], numero: int, valores: list) -> None:
    while len(tabla) < numero - 1:
        tabla.append([])
    if len(tabla) >= numero:
        tabla[numero - 1] = list(valores)  # igual que el Sheet: pisa
    else:
        tabla.append(list(valores))


class ArchivadorFalso:
    def __init__(self, fallar: bool = False):
        self.fallar = fallar
        self.movidos: list[tuple] = []
        self.avisos: list[str] = []

    def archivar(self, file_id, carpetas, nombre_base):
        if self.fallar:
            raise ConnectionError("Drive caído (simulado)")
        self.movidos.append((file_id, list(carpetas), nombre_base))
        return f"https://drive.google.com/file/d/{file_id}/view"


@contextlib.contextmanager
def cuenta_en_moneda(nombre: str, moneda: str):
    """Mientras dura el caso, la cuenta está en esa moneda (§5.8 v1.8: Caja obra Lennon en
    dólares). Se cambia en lo que lee el maestro, no en el objeto: /confirmar recarga los
    maestros. Al salir se recargan como estaban. Devuelve los maestros cambiados."""
    from app import maestros
    original = maestros._leer_crudo

    def crudo():
        d = original()
        for fila in d["CUENTAS"][1:]:
            if fila and fila[0] == nombre:
                fila[2] = moneda
        return d
    maestros._leer_crudo = crudo
    try:
        yield maestros.cargar(forzar=True)
    finally:
        maestros._leer_crudo = original
        maestros.cargar(forzar=True)
