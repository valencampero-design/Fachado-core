"""Settings del motor, leídos de variables de entorno.

Sin estado: todo lo que el motor necesita saber viene de acá o del Sheet maestro.
"""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _bool(nombre: str, default: bool) -> bool:
    valor = os.getenv(nombre)
    if valor is None or valor == "":
        return default
    return valor.strip().lower() in ("1", "true", "si", "sí", "yes")


@dataclass(frozen=True)
class Settings:
    # Autenticación gateway → motor
    motor_api_key: str = field(default_factory=lambda: os.getenv("MOTOR_API_KEY", ""))

    # Sheet maestro «FACHADO — Gestión de Obras»
    sheet_id: str = field(default_factory=lambda: os.getenv("FACHADO_SHEET_ID", ""))
    # Si está seteado, los maestros se leen de este JSON en vez del Sheet
    # (tests offline). Mismo formato que Sheets values.get.
    maestros_snapshot: str = field(default_factory=lambda: os.getenv("MAESTROS_SNAPSHOT", ""))
    maestros_ttl_segundos: int = field(default_factory=lambda: int(os.getenv("MAESTROS_TTL_SEGUNDOS", "300")))

    # Service account (la misma del gateway): lee el Sheet, que está compartido con ella.
    google_credentials_json: str = field(default_factory=lambda: os.getenv("GOOGLE_CREDENTIALS_JSON", ""))
    google_credentials_path: str = field(default_factory=lambda: os.getenv("GOOGLE_CREDENTIALS_PATH", ""))

    # Google OAuth de usuario: para Drive (una service account no tiene cuota en un Drive personal)
    google_client_id: str = field(default_factory=lambda: os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""))
    google_client_secret: str = field(default_factory=lambda: os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""))
    google_refresh_token: str = field(default_factory=lambda: os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN", ""))

    # LLM
    llm_habilitado: bool = field(default_factory=lambda: _bool("LLM_HABILITADO", True))
    llm_modelo: str = field(default_factory=lambda: os.getenv("LLM_MODELO", "claude-opus-5"))
    llm_effort: str = field(default_factory=lambda: os.getenv("LLM_EFFORT", "low"))

    # Lectura de adjuntos (descarga de Drive + PDF + visión)
    leer_adjuntos: bool = field(default_factory=lambda: _bool("LEER_ADJUNTOS", True))

    # Carpeta raíz «comprobantes» en Drive, adonde /confirmar mueve cada adjunto. Tiene que
    # haberla creado esta app OAuth: `drive.file` no ve carpetas creadas a mano. Si está
    # vacía, el motor la crea en la raíz del Drive la primera vez y avisa el id.
    drive_carpeta_comprobantes_id: str = field(default_factory=lambda: os.getenv("DRIVE_CARPETA_COMPROBANTES_ID", ""))

    # Zona horaria del cliente para fechar mensajes (Argentina no tiene horario de verano)
    utc_offset_horas: int = field(default_factory=lambda: int(os.getenv("UTC_OFFSET_HORAS", "-3")))

    @property
    def tiene_oauth_google(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret and self.google_refresh_token)


def settings() -> Settings:
    # Se reconstruye en cada llamada: barato, y permite que los tests cambien env.
    return Settings()
