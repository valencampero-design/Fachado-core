# Inventario de secretos — motor `fachado-core` y sus crons

> Hecho el 22/10/2026 por el incidente de Railway del 21/10. **Supuesto de trabajo: toda variable
> que esté o haya estado en Railway está comprometida.** No contiene ningún valor.
>
> El inventario completo, con las credenciales que el motor comparte con el gateway, está en
> `chatbot-contable/docs/seguridad/inventario-secretos.md`. El paso a paso para rotar, en
> `chatbot-contable/docs/seguridad/rotacion-2026-10-22.md`.

## Servicios (proyecto Railway `bountiful-trust`)

| Servicio | Qué corre | Variables que lee |
|---|---|---|
| `web` | `uvicorn app.main:app` | Todas las de abajo |
| `cierre-semanal` | `python scripts/cierre_semanal.py`, `0 11 * * 1` | `MOTOR_URL`, `MOTOR_API_KEY` |
| `vistas` | `python scripts/recalcular_vistas.py`, `0 6 * * *` | `MOTOR_URL`, `MOTOR_API_KEY` |

En tu PC, `fachado-core/.env` tiene secretos reales (nunca estuvo en git).

## Secretos, de mayor a menor riesgo

| # | Variable | Servicios | Si alguien la tiene | Dónde se rota | ¿Cambia algo en el gateway a la vez? |
|---|---|---|---|---|---|
| 1 | `GOOGLE_CREDENTIALS_JSON` | `web` | Lee y escribe el Master, «FACHADO — Personal» y **todos los Sheets compartidos con la service account, incluidos los de los otros clientes del gateway** | Google Cloud → IAM → Cuentas de servicio → Claves (ver el gateway, §2) | **Sí: es la misma service account que el gateway** |
| 2 | `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN` (+ `GOOGLE_OAUTH_CLIENT_ID`) | `web` | Lee, mueve o borra los adjuntos de Fachado en Drive (`drive.file`) | Google Cloud → Credenciales (secret) y myaccount.google.com (refresh token); regenerar con `python scripts/get_google_token.py <client_secret.json>` | **Sí: mismo cliente OAuth y mismo refresh token que el gateway** |
| 3 | `MOTOR_API_KEY` | `web` (la exige), `cierre-semanal` y `vistas` (la mandan) | `/confirmar` y `/anular` escriben en el Master real; `/conciliar/*`, `/vistas/recalcular`; `/consultar` lee saldos. Basta conocer un teléfono de USUARIOS | La generamos nosotros. **Sin corte** con `MOTOR_API_KEY_ANTERIOR` | **Sí**: el gateway la manda como `FACHADO_MOTOR_API_KEY` |
| 4 | `MOTOR_API_KEY_ANTERIOR` | `web` | Lo mismo que la 3, mientras exista | Nueva (22/10): existe solo durante una rotación. Borrarla al terminar | — |
| 5 | `ANTHROPIC_API_KEY` | `web` | Gasta a nuestro nombre. No da acceso a datos (el motor no usa Files API ni batches) | console.anthropic.com → API keys. **Key propia del motor**, distinta de la del gateway | No |

## Configuración (no son secretos)

| Variable | Para qué |
|---|---|
| `FACHADO_SHEET_ID`, `FACHADO_PERSONAL_SHEET_ID` | Master y Personal |
| `DRIVE_CARPETA_COMPROBANTES_ID` | Carpeta «comprobantes» en Drive (la creó la app OAuth) |
| `MOTOR_URL` | Solo crons: la URL pública del motor |
| `MAESTROS_SNAPSHOT`, `MAESTROS_TTL_SEGUNDOS`, `CACHE_COMPROBANTES` | Maestros offline / caché (vacías en Railway, salvo el TTL) |
| `LLM_HABILITADO`, `LLM_MODELO`, `LLM_EFFORT`, `LLM_MODELO_COMPROBANTE`, `LEER_ADJUNTOS` | LLM y adjuntos |
| `UTC_OFFSET_HORAS`, `CONCILIACION_DESDE` | Zona horaria, inicio de la conciliación |
| `GOOGLE_CREDENTIALS_PATH` | Solo local |

## Qué cambió en el código el 22/10

- `MOTOR_API_KEY_ANTERIOR`: el motor acepta las dos durante la rotación; `GET /salud/auth` dice
  cuál entró.
- Arranque: el servicio `web` no arranca si falta `MOTOR_API_KEY`, `FACHADO_SHEET_ID`, la service
  account, el OAuth de Drive o (con LLM) `ANTHROPIC_API_KEY`, y dice cuál.
- Logs y respuestas sin secretos (`app/seguridad.py`).
- `scripts/verificar_credenciales.py` y `scripts/movimientos_desde.py` (solo lectura).
