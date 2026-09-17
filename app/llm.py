"""Cliente de Anthropic y prompts.

El LLM entra SOLO para lo que el diccionario no resolvió. Nunca decide la clasificación
obra / estructura / personal: eso es código (clasificador.py).

Las listas canónicas van en el system prompt, que es estable → prompt caching. El mensaje
del usuario, que cambia, va después del breakpoint.
"""
import base64
import json
import logging
import threading

import anthropic

from app.config import settings
from app.maestros import Maestros

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cliente: anthropic.Anthropic | None = None


def _anthropic() -> anthropic.Anthropic:
    global _cliente
    with _lock:
        if _cliente is None:
            _cliente = anthropic.Anthropic()
    return _cliente


def disponible() -> bool:
    return settings().llm_habilitado


def _llamar(system: list[dict], content: list[dict] | str, schema: dict, max_tokens: int = 4000) -> tuple[dict | None, dict]:
    """Una llamada con salida JSON estructurada. Devuelve (datos, uso)."""
    s = settings()
    try:
        resp = _anthropic().beta.messages.create(
            model=s.llm_modelo,
            max_tokens=max_tokens,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": s.llm_effort, "format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.RateLimitError:
        logger.warning("LLM: rate limit")
        return None, {"error": "rate_limit"}
    except anthropic.APIStatusError as e:
        logger.error("LLM: error %s: %s", e.status_code, e.message)
        return None, {"error": f"http_{e.status_code}"}
    except anthropic.APIConnectionError:
        logger.error("LLM: error de conexión")
        return None, {"error": "conexion"}

    uso = {
        "modelo": resp.model,
        "input": resp.usage.input_tokens,
        "output": resp.usage.output_tokens,
        "cache_read": resp.usage.cache_read_input_tokens or 0,
        "cache_write": resp.usage.cache_creation_input_tokens or 0,
    }
    if resp.stop_reason in ("refusal", "max_tokens"):
        logger.warning("LLM: stop_reason=%s", resp.stop_reason)
        return None, {**uso, "error": resp.stop_reason}
    texto = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        return json.loads(texto), uso
    except json.JSONDecodeError:
        logger.error("LLM: JSON inválido: %r", texto[:200])
        return None, {**uso, "error": "json"}


# ─── Resolución de tokens ──────────────────────────────────────────────────────

def _system_maestros(m: Maestros) -> list[dict]:
    obras = "\n".join(f"- {o.nombre} (código: {o.codigo}; tipo: {o.tipo})"
                      for o in m.obras if o.estado != "cerrada")
    contratistas = "\n".join(
        f"- {c.nombre}" + (f" (rubro habitual: {c.rubro_1} / {c.rubro_2})" if c.rubro_1 else "")
        for c in m.contratistas)
    rubros = "\n".join(f"- {r.rubro_1} / {r.rubro_2}" for r in m.rubros)
    cuentas = "\n".join(f"- {c.nombre}" for c in m.cuentas)
    alias = "\n".join(f"- «{a.como_lo_dice}» → {a.valor_canonico} ({a.tipo})" for a in m.alias)
    texto = f"""Sos el intérprete de mensajes de WhatsApp de un estudio de arquitectura de Villa La Angostura (Argentina) que administra obras. El arquitecto anota pagos y cobros con mensajes cortos del estilo «contratista/obra», «obra/concepto» o «Retiro/club/cuota», en cualquier orden, con apodos, abreviaturas y errores de tipeo.

Tu trabajo es acotado: te paso los fragmentos del mensaje que un diccionario no pudo reconocer, y para cada uno decís qué es y a qué valor canónico corresponde. Un sistema aparte, con reglas propias, decide si el gasto es de obra, de estructura o personal: vos no lo decidas.

Reglas:
- `valor` tiene que ser EXACTAMENTE uno de los nombres de las listas de abajo (para rubros, «rubro_1 / rubro_2»). Si no estás seguro de a cuál corresponde, devolvé `valor: null` y una confianza baja: preguntarle al arquitecto es barato, imputar mal es caro.
- Un nombre de pila que coincide con varios contratistas es ambiguo: null.
- Un texto libre que describe el gasto (por ejemplo «cuota 3 esquí» o «adelanto») es `descripcion`, con `valor: null`.
- `confianza` va de 0 a 1.

OBRAS
{obras}

CONTRATISTAS
{contratistas}

RUBROS (rubro_1 / rubro_2; el nivel 2 dice qué se compró, nunca dónde)
{rubros}

CUENTAS
{cuentas}

ALIAS YA CONOCIDOS
{alias}"""
    return [{"type": "text", "text": texto, "cache_control": {"type": "ephemeral"}}]


ESQUEMA_TOKENS = {
    "type": "object",
    "properties": {
        "tokens": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "token": {"type": "string"},
                    "categoria": {"type": "string", "enum": ["obra", "contratista", "rubro", "cuenta", "descripcion", "desconocido"]},
                    "valor": {"type": ["string", "null"]},
                    "confianza": {"type": "number"},
                },
                "required": ["token", "categoria", "valor", "confianza"],
                "additionalProperties": False,
            },
        },
        "rubro_sugerido": {
            "type": ["object", "null"],
            "properties": {
                "valor": {"type": ["string", "null"]},
                "confianza": {"type": "number"},
            },
            "required": ["valor", "confianza"],
            "additionalProperties": False,
        },
    },
    "required": ["tokens", "rubro_sugerido"],
    "additionalProperties": False,
}


def resolver_tokens(m: Maestros, texto: str, tokens: list[str], contexto: dict, pedir_rubro: bool) -> tuple[dict | None, dict]:
    lineas = [f"Mensaje completo: «{texto}»"]
    if contexto:
        lineas.append("Ya resuelto por diccionario: " + "; ".join(f"{k}: {v}" for k, v in contexto.items()))
    if tokens:
        lineas.append("Fragmentos sin reconocer: " + " | ".join(f"«{t}»" for t in tokens))
    else:
        lineas.append("Fragmentos sin reconocer: ninguno (devolvé `tokens` vacío).")
    if pedir_rubro:
        lineas.append("Además, sugerí el rubro (rubro_1 / rubro_2) más probable para este pago en `rubro_sugerido`.")
    else:
        lineas.append("`rubro_sugerido`: null.")
    return _llamar(_system_maestros(m), "\n".join(lineas), ESQUEMA_TOKENS)


# ─── Lectura de comprobantes ───────────────────────────────────────────────────

ESQUEMA_COMPROBANTE = {
    "type": "object",
    "properties": {
        "es_comprobante": {"type": "boolean"},
        "tipo_comprobante": {"type": ["string", "null"]},
        "medio_pago": {"type": ["string", "null"], "description": "Transferencia, Cheque, Efectivo, Tarjeta, Débito automático u Otro"},
        "fecha": {"type": ["string", "null"], "description": "Fecha de emisión/operación, AAAA-MM-DD"},
        "fecha_pago": {"type": ["string", "null"], "description": "Fecha de pago si es un cheque diferido, AAAA-MM-DD"},
        "importe": {"type": ["number", "null"]},
        "moneda": {"type": ["string", "null"], "description": "ARS o USD"},
        "razon_social_destinatario": {"type": ["string", "null"]},
        "cuit_destinatario": {"type": ["string", "null"]},
        "cuenta_destino": {"type": ["string", "null"], "description": "CBU, CVU, alias o número de cuenta de destino"},
        "razon_social_originante": {"type": ["string", "null"]},
        "cuit_originante": {"type": ["string", "null"]},
        "id_operacion": {"type": ["string", "null"]},
        "numero_cheque": {"type": ["string", "null"]},
    },
    "required": ["es_comprobante", "tipo_comprobante", "medio_pago", "fecha", "fecha_pago", "importe", "moneda",
                 "razon_social_destinatario", "cuit_destinatario", "cuenta_destino", "razon_social_originante",
                 "cuit_originante", "id_operacion", "numero_cheque"],
    "additionalProperties": False,
}

_SYSTEM_COMPROBANTE = [{
    "type": "text",
    "text": "Extraés datos de comprobantes de pago argentinos (transferencias de homebanking, cheques, "
            "Mercado Pago, facturas, tickets). Los importes argentinos usan punto de miles y coma decimal: "
            "«$ 4.032.391,70» es 4032391.70. Las fechas vienen como DD/MM/AAAA: devolvelas como AAAA-MM-DD. "
            "Si un dato no figura, null: no lo inventes. En un cheque diferido, `fecha` es la de emisión y "
            "`fecha_pago` la de pago.",
}]


def extraer_comprobante(contenido: bytes | None, mime: str, texto_pdf: str | None) -> tuple[dict | None, dict]:
    if texto_pdf:
        content: list[dict] = [{"type": "text", "text": f"Texto extraído del PDF:\n\n{texto_pdf[:20000]}"}]
    elif contenido and mime.startswith("image/"):
        content = [{"type": "image", "source": {"type": "base64", "media_type": mime,
                                                 "data": base64.standard_b64encode(contenido).decode()}}]
    elif contenido and mime == "application/pdf":
        content = [{"type": "document", "source": {"type": "base64", "media_type": mime,
                                                    "data": base64.standard_b64encode(contenido).decode()}}]
    else:
        return None, {"error": "formato_no_soportado"}
    content.append({"type": "text", "text": "Extraé los datos de este comprobante."})
    return _llamar(_SYSTEM_COMPROBANTE, content, ESQUEMA_COMPROBANTE)
