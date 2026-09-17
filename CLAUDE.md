# CLAUDE.md — `fachado-core`

## Antes de tocar nada

Leé **`CONTEXTO-FACHADO.md`** en la raíz de este repo. Es la memoria compartida del proyecto:
el glosario, las reglas de negocio decididas y cómo escribe realmente el arquitecto. Se edita
en el proyecto de Claude de A&C y baja acá.

**Si aparece una decisión de negocio que no está en ese archivo, no la implementes.** Avisá que
falta y pedí que se actualice el contexto primero. Una regla implementada y no escrita es una
regla que nadie va a poder explicar en dos meses.

## Qué es este repo

El **motor de imputación de Fachado**. Sabe de obras, contratistas, rubros y conciliación, y
**no sabe nada de WhatsApp**. Es una API HTTP **sin estado**.

Repo hermano: `chatbot-contable`, el gateway, que tiene la sesión y los botones.

## Por qué no tiene estado

- Se prueba con `curl` y con el corpus de 101 mensajes reales, **sin mandar un WhatsApp**. Eso
  es lo que hace viable iterar el parser todos los días.
- Si el motor está caído, el gateway sigue archivando el mensaje crudo y responde ✅.

## La métrica

```bash
python -m tests.test_corpus            # diccionario + LLM
python -m tests.test_corpus --sin-llm  # solo diccionario
```

**Que ese porcentaje suba es el trabajo de las próximas semanas.** Al 17/09: 82 % de obras,
98 % de contratistas, 80 % las dos cosas, con solo 10 de 55 mensajes usando LLM.

Corre contra `tests/maestros_snapshot.json` para que sea reproducible. Si cambia la métrica es
por código, o porque se regeneró el snapshot a propósito.

**Antes de dar por terminado cualquier cambio en el resolver o el clasificador, correr el
test.** Si el número baja, el cambio está mal aunque el caso puntual funcione.

## Reglas de este repo

- **Sin base de datos.** La fuente de verdad es el Google Sheet.
- **Sin estado entre requests.** Ni sesiones ni caché de conversación. Los maestros sí se
  cachean con TTL.
- **`/interpretar` nunca escribe nada.** Es una función pura sobre los maestros.
- **Primero el diccionario, después el LLM.** Exacto → CUIT → palabra única → difuso (≥ 88) →
  LLM solo para lo que quedó.
- **El LLM solo puede devolver valores que existen en los maestros.** Lo que inventa se descarta.
- **La clasificación obra / estructura / personal va en código, no en el prompt.** Es una
  decisión contable y tiene que ser auditable y determinista.
- **No hardcodear obras ni contratistas.** Todo sale de los maestros.
- Del más barato al más caro para leer un comprobante: **nombre de archivo → texto del PDF →
  modelo.** Los PDF del homebanking son texto, no imagen.

## El contrato con el gateway

`origen_campo` dice de dónde salió cada valor: `texto`, `comprobante`, `maestro`, `inferido`,
`llm`, `fecha_mensaje`, `contexto_previo`. El gateway lo usa para mostrar «del comprobante» al
lado de cada dato en la ficha de confirmación. **No lo saques**: es lo que hace que el usuario
confíe en lo que ve.

`fichas` es una lista. Casi siempre trae un elemento, pero un mensaje puede traer dos
movimientos.

## Hallazgos sobre el Sheet

El maestro lo mantiene una persona a mano, así que llega sucio. El motor **no lo corrige
solo**: lo resuelve lo mejor que puede y **deja una advertencia** en `/maestros/recargar`.
Alias que apuntan a nombres inexistentes, filas duplicadas y rubros habituales que no están en
RUBROS son casos esperados, no excepciones.

## Los secretos

Solo en variables de entorno de Railway. El refresh token del gateway **no sirve acá**: tiene
scope `drive.file` y este repo necesita además `spreadsheets.readonly`.
