# fachado-core

Motor de imputación de Estudio Fachado. API HTTP **sin estado**: interpreta mensajes de
obra y devuelve fichas de `MOVIMIENTOS`. No sabe nada de WhatsApp; eso es el gateway
(`chatbot-contable`). La fuente de verdad es el Sheet «FACHADO — Gestión de Obras».

## Correr local

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
cp .env.example .env    # completar
.venv/Scripts/python -m uvicorn app.main:app --reload
```

## Endpoints

| | |
|---|---|
| `GET /salud` | sin auth |
| `POST /interpretar` | texto + adjuntos → `{fichas, preguntas, diagnostico}`. Nunca escribe nada |
| `POST /maestros/recargar` | fuerza la relectura del Sheet |
| `POST /confirmar`, `/consultar` | 501, fase 2 |

Todos menos `/salud` piden `X-API-Key: $MOTOR_API_KEY`.

## Cómo interpreta

1. `resolver.py` parte el texto por `/` y resuelve cada token contra los maestros, sin
   importar el orden: ALIAS → exacto → palabra única → difuso (≥ 88).
2. `llm.py` solo para los tokens que quedaron sin resolver, o para sugerir rubro cuando el
   contratista no tiene rubro habitual. Solo puede devolver valores de los maestros.
3. `comprobante.py`: nombre de archivo → texto del PDF → visión. El comprobante manda en
   importe, fecha y destinatario; el texto en obra, ítem y rubro. Si chocan, se pregunta.
4. `clasificador.py`: la cascada obra / estructura / personal, en código. Cada ficha dice
   qué regla la decidió (`regla`).

## Métrica

```bash
python -m tests.test_corpus            # diccionario + LLM (necesita ANTHROPIC_API_KEY)
python -m tests.test_corpus --sin-llm  # solo diccionario
```

Corre los mensajes reales de `tests/corpus.csv` contra `tests/maestros_snapshot.json` y
reporta cuántos resuelven obra y contratista sin preguntar. Para refrescar el snapshot:
`python scripts/snapshot_maestros.py`.
