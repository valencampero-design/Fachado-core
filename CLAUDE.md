# CLAUDE.md — `fachado-core`

## Antes de tocar nada

Leé **`CONTEXTO-FACHADO.md`** en la raíz de este repo. Es la memoria compartida del proyecto:
el glosario, las reglas de negocio decididas y cómo escribe realmente el arquitecto. Se edita
en el proyecto de Claude de A&C y baja acá.

**Si aparece una decisión de negocio que no está en ese archivo, no la implementes.** Avisá que
falta y pedí que se actualice el contexto primero. Una regla implementada y no escrita es una
regla que nadie va a poder explicar en dos meses.

Esto vale también para la documentación: **`docs/handoff-fachado-core.md` es el estado técnico
del repo** —qué está hecho, qué falta, cómo se corre, qué variables hacen falta— y **no repite
las reglas de negocio**, solo dice en qué módulo vive cada una. Duplicarlas es lo que hizo que
el handoff terminara afirmando cosas falsas: cada sesión aprendía algo que las otras no veían.

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

**Que ese porcentaje suba es el trabajo de las próximas semanas.** Al 25/09: 84 % de obras,
84 % de contratistas, **92 % contando las preguntas de diseño** —un apodo ambiguo o un
contratista dual preguntan porque el maestro dice que hay que preguntar—, con 9 de 55 mensajes
usando LLM.

La métrica sale también **por usuario**: el corpus es 100 % del titular y cómo escribe Petrus
no se sabe todavía. No mezclar los números de los dos.

`python -m tests.test_reglas` es el otro test: no mide, verifica que lo que el motor resuelve
sea lo que el negocio decidió. `python -m tests.test_casos` corre los ejemplos con los que el
proyecto definió cada regla. Y `python -m tests.test_confirmar` prueba la escritura, el cierre
semanal y `/consultar`. Correr los cuatro.

Corre contra `tests/maestros_snapshot.json` para que sea reproducible. Si cambia la métrica es
por código, o porque se regeneró el snapshot a propósito.

**Antes de dar por terminado cualquier cambio en el resolver o el clasificador, correr el
test.** Si el número baja, el cambio está mal aunque el caso puntual funcione.

## Reglas de este repo

- **Sin base de datos.** La fuente de verdad es el Google Sheet.
- **Sin estado entre requests.** Ni sesiones ni caché de conversación. Los maestros sí se
  cachean con TTL.
- **`/interpretar` nunca escribe nada.** Lee los libros solo para avisar de un posible
  duplicado, y si no puede leerlos la ficha sale igual. Solo `/confirmar` escribe, con la
  confirmación de un usuario, y `/cierre-semanal`, que resume lo ya confirmado.
- **Lo personal nunca se escribe en el libro del estudio.** Va a «FACHADO — Personal», y si
  ese libro no está configurado, se rechaza (503). Quién ve lo personal es por persona
  (`USUARIOS.ve_personal`), no por rol.
- **Los tests nunca escriben en el libro real.** MOVIMIENTOS es append-only: una fila de
  prueba no se borra. `test_confirmar` usa un libro en memoria; para eso existen los puertos
  `Libro` y `Archivador`.
- **Una fila se escribe entera o no se escribe.** Se arma y valida en memoria antes de tocar el
  Sheet. Idempotencia por `msg_id`, cálculo del `id_mov` y escritura van bajo el mismo lock: no
  separarlos. Las dos filas de un traspaso, y los dos contraasientos que lo anulan, van en
  **una sola escritura**.
- **El libro no se edita nunca.** Una corrección es un contraasiento (`/anular`, §5.19) y
  después la fila correcta. Todo lo derivado —saldos, consultas, duplicados, conciliación—
  saca el par anulado con `filtros.sin_anulados`: un cálculo nuevo también tiene que hacerlo.
- **Un teléfono que no está en USUARIOS no escribe.** Ningún teléfono va escrito en el código:
  salen de USUARIOS.
- **Cualquier saldo del estudio sale de `Maestros.cuentas_del_estudio()`**, que es una lista
  blanca: las cajas de obra y lo que paga el comitente son plata de terceros.
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
movimientos. Por eso la clave de idempotencia de `/confirmar` es `msg_id` **más**
`ficha_indice`, y el `msg_id` es el del mensaje original, no el del botón que lo confirma.

## Hallazgos sobre el Sheet

El maestro lo mantiene una persona a mano, así que llega sucio. El motor **no lo corrige
solo**: lo resuelve lo mejor que puede y **deja una advertencia** en `/maestros/recargar`.
Alias que apuntan a nombres inexistentes, filas duplicadas y rubros habituales que no están en
RUBROS son casos esperados, no excepciones.

**Si el maestro contradice a `CONTEXTO-FACHADO.md`, se corrige el maestro** (decisión de
Valentín, 24/09). Cómo: con un script que primero muestra el simulacro, citando en la nota de
cada fila el punto del contexto que la justifica. **Nada se borra**: lo que deja de
corresponder pasa a `inactivo`. Si la contradicción necesita un dato que el contexto no da
—por ejemplo, qué obras tienen caja de obra—, no se inventa: se pregunta.

## Los secretos

Solo en variables de entorno de Railway. Cada API va con la credencial que le corresponde:
**Sheets con la service account** del gateway (el Sheet está compartido con ella como
**Editor**, y el scope es de escritura) y **Drive con OAuth de usuario**, porque `drive.file`
solo alcanza a los archivos y carpetas que creó esa misma app. El detalle de por qué, en
`docs/handoff-fachado-core.md` §5.
