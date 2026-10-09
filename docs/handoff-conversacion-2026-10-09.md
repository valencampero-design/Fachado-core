# Handoff — la conversación del bot (primera semana de uso real)

> 9/10/2026 · A&C. Mismo archivo en `fachado-core/docs/` y en
> `chatbot-contable/docs/clientes/fachado/`. Antes de tocar código leé **`CONTEXTO-FACHADO.md`
> v1.8**: cambiaron §5.7 (paso 1), §5.8 (efectivo en una obra con caja y cajas en dólares),
> §5.12 («Pocas preguntas» y «La conversación tiene que seguir el hilo») y §8.
>
> **Capturas:** `chatbot-contable/docs/clientes/fachado/capturas/2026-10-09/` (8 imágenes,
> numeradas en orden cronológico). Miralas todas antes de empezar.

## El problema, en una frase

El bot carga, pero **usarlo es tedioso**: hace 4 o 5 preguntas por movimiento, pregunta
cosas que el mensaje ya dice o que no aplican, toma un mensaje nuevo como respuesta a una
pregunta vieja y entra en bucles de error. Gabriel (el arquitecto) dice que «Lennon/Miguel»
más el comprobante **tendría que alcanzar**. Ese es el criterio de aceptación de esta tanda.

## Reglas de siempre

- Ningún test escribe en el Sheet real (append-only). Commits armados, **sin pushear**.
- Gateway: los otros cuatro clientes no cambian.
- Decisión de negocio que no esté en el contexto v1.8: no se inventa, se anota al final.
- Archivos que figuran modificados solo por finales de línea (CRLF): no van en los commits.

---

## 1 · Qué muestran las capturas

| # | Archivo | Qué pasó | Qué debería pasar |
|---|---|---|---|
| 1 | `01-retiro-sofi-pide-obra-a-un-personal` | «Retiro/Sofi» + comprobante. Pregunta el rubro personal (7 opciones) y después **«¿A qué obra?»** | Retiro = personal (§5.4): **nunca se pregunta obra**. Sofi es hija → rubro `Familia` como supuesto. Cero preguntas |
| 2 | `02-lennon-miguel-pide-rubro-e-importe` | «Lennon/Miguel» + foto de un recibo. Pregunta **rubro** (10 opciones al azar: Contratistas, Áridos, Hormigón…) y **importe** | Miguel = Miguel Soto/Matamala (§7): rubro habitual o el último usado con él. Importe del comprobante. Cero preguntas; si el recibo no se lee, solo el importe |
| 3 | `03-pide-obra-y-rubro-otra-vez` | Pregunta obra (10 opciones) y después rubro de nuevo, con la misma lista de materiales | Ver si el texto nombraba la obra (cruzar con CAPTURA). Si hay que preguntar el rubro, las opciones son las que se usaron con ese contratista, no los primeros 10 de RUBROS |
| 4 | `04-ingreso-usd-lennon-pide-obra` | «INGRRSO/28 de septiembre, Lennon me pasó us$20.000 para ingresar a caja chica, efectivo» → **«¿A qué obra?»** | Obra = Lennon (está en el texto). Tipo = INGRESO (el typo «INGRRSO» tiene que reconocerse). Es un adelanto del comitente a la **caja de obra de Lennon**, en dólares (§5.8 v1.8). Cero preguntas |
| 5 | `05-ingreso-pregunta-a-quien-se-pago-y-honorarios` | Sigue: «¿A quién se le pagó?» (a un ingreso). «Es un ingreso» → «¿certificación o honorarios?» (no es ninguna). «Efectivo» (texto, no botón) → «¿De qué cuenta entra?» | A un ingreso no se le pregunta a quién se pagó. Una respuesta escrita que no es una opción se lee como texto: «Efectivo» y «caja chica» son datos |
| 6 | `06-tipo-de-cambio-lo-dejamos-en-dolares` | «¿A qué tipo de cambio?» → «Lo dejamos en dólares» → «No entendí el tipo de cambio» | Con la caja en dólares no hace falta tipo de cambio para un ingreso en dólares. «Lo dejamos en dólares» es una respuesta válida |
| 7 | `07-falta-un-dato-en-bucle` | Da 1500 → «No lo pude cargar: falta un dato». «¿Cuál?» → «No entendí el tipo de cambio». 1500 → falta un dato. 1450 → falta un dato | El error dice **qué** falta. «¿Cuál?» se contesta. Nunca un bucle: al segundo intento, ofrecer «Descartar» o «Dejarlo para revisar» |
| 8 | `08-pregunta-vieja-se-come-un-pago-nuevo` | Horas después, comprobante + «Sofia cervera/Austral» → «No entendí el tipo de cambio». «¡Es un pago nuevo! No hay tipo de cambio» → otra vez lo mismo | **Un comprobante nuevo nunca es la respuesta a una pregunta pendiente**: arranca un movimiento nuevo y el anterior queda en pendientes |

## 2 · Lo que se ve al cruzar con los libros (leído por A&C el 9/10)

Del Sheet maestro (MOVIMIENTOS, CC_LENNON, CC_GONZALO) y del libro personal. **Hay que
completar el cruce** (§4.M): A&C no pudo leer CAPTURA completa.

- **Lennon quedó con −$ 13.640.000 «pagado por el estudio»** en CC_LENNON: los pagos a
  Miguel Soto (3.070.000 del 07/10 y 10.000.000 con fecha 05/08) y a Luis Pereira (M-000001,
  570.000) están en la cuenta `Efectivo` del estudio. Según §5.8 v1.8 son de la **caja de
  obra de Lennon**.
- **Fechas raras:** M-000001 (Luis Pereira, cargado el 29/09) tiene fecha **2026-02-07**; el
  pago de 10.000.000 a Miguel, **2026-08-05**. Verificar contra los comprobantes: si es una
  lectura mal hecha (día/mes invertidos u otra fecha del papel), es un bug del lector.
- **P-000001** (libro personal, 30/09 16:20): contratista **Tucu**, **obra Moreno, etapa 1**,
  rubro Personal › Familia. Coincide con la captura 1 («Retiro/Sofi»): un gasto personal no
  lleva obra, y el contratista tendría que ser Sofía. Verificar con el comprobante.
- **P-000005** Edesur con rubro_2 `Agua` (Edesur es electricidad). **P-000004/5** con
  `medio_pago = Otro` siendo Mercado Pago.
- **M-000005**: Austral · Valentín Campero · $ 400 · honorarios. Parece una prueba: Valen
  confirma si se anula.
- **No aparecen en los libros** (verificar en el cruce): el ingreso de USD 20.000 de Lennon
  (28/09, capturas 4 a 7), el pago a Sofía Cervera / Austral por $ 657.685 (captura 8) y el
  pago a Miguel de $ 708.400 (captura 2). Probablemente quedaron trabados en las preguntas.
- El **cierre semanal funciona**: M-000006/07 (W40) suman lo personal de Banco
  (184.000 + 237.101,98) y de Efectivo (99.999,87).

## 3 · Las causas, como las leemos

1. **El motor pregunta en vez de deducir.** Rubro sin mirar el historial del contratista;
   importe aunque haya comprobante; obra aunque el texto la nombre; obra a un personal;
   contratista a un ingreso.
2. **El gateway no distingue una respuesta de un mensaje nuevo.** Con una pregunta pendiente,
   todo lo que llega se trata como su respuesta: un comprobante nuevo, un «¿cuál?», un
   «es un ingreso».
3. **Las respuestas escritas que no son una opción se pierden** en vez de volver al motor como
   texto con la ficha como contexto.
4. **Los errores no dicen qué falta** y no tienen salida.
5. **El modelo de caja de obra no contempla dólares ni el «efectivo» sin la `C`.**

---

## 4 · Qué hay que hacer

### P0 · La conversación (gateway, con ayuda del motor)

**A · Un mensaje nuevo no es la respuesta a una pregunta vieja.** Con una pregunta
pendiente, antes de tomar lo que llega como respuesta:

- un **adjunto** → movimiento nuevo; el anterior va a la cola de pendientes, con aviso.
- un **texto** que no encaja con la pregunta (no es una opción, no es un número cuando se
  pide un número, no es corto) → se manda a `/interpretar` **sin** `contexto_previo`; si
  vuelve un movimiento con obra o contratista propios, es nuevo. Si no, se trata como dato
  de la ficha pendiente (B).
- **palabras de salida**: «cancelar», «descartar», «olvidalo», «es otro», «nuevo» →
  descarta la pendiente (o la deja en la cola) y lo dice.
- una **pregunta del usuario** («¿cuál?», «¿qué falta?», «?») → contestar qué campo falta y
  por qué, sin consumirla como respuesta.

**B · Una respuesta escrita que no es una opción vuelve al motor como texto.** `/interpretar`
con `contexto_previo` = la ficha y el `texto` tal cual (no como `respuestas`). El motor la
fusiona: «efectivo» → cuenta, «caja chica» → caja de la obra, «es un ingreso» → tipo
INGRESO, «lo dejamos en dólares» → moneda USD. Después se recalculan las preguntas.

**C · Nunca un error sin el campo, nunca un bucle.**
- El 422 tiene que decir **qué** falta («No lo pude cargar: falta la cuenta»). Hoy dice
  «falta un dato»: revisá el mapeo de `campo`/`detalle` en `_mensaje_rechazo`.
- **Reproducí el 422 de la captura 7** (el ingreso de USD con tipo de cambio 1500): ¿qué
  campo faltaba? Anotalo.
- Al segundo fallo seguido sobre la misma ficha: botones «❌ Descartar» y «🕓 Dejar para
  revisar». «Dejar para revisar» guarda la ficha en pendientes, manda la alerta a
  `CAPTURA_ALERT_PHONE` con el msg_id y le dice a Gabriel «Lo reviso yo y te aviso».
- Nunca repetir «No entendí…» dos veces seguidas: la segunda vez, explicar con un ejemplo y
  ofrecer las mismas dos salidas.

### P0 · Pocas preguntas (motor) — §5.12 v1.8

**D · «Lennon/Miguel» + comprobante = cero preguntas.** Criterio de aceptación, con tests
sobre los casos de las capturas.

- **Rubro**, en orden: rubro habitual del contratista → **el último rubro usado con ese
  contratista en MOVIMIENTOS** (los dos libros) → origen `supuesto`. Solo si el contratista
  es nuevo y no hay nada, se pregunta, y las opciones son las de su categoría más usadas,
  no los primeros 10 de RUBROS.
- **Importe** del comprobante. Si el comprobante no se pudo leer, se pregunta **solo** el
  importe. Revisá por qué la captura 2 lo preguntó (¿recibo manuscrito? ¿`LEER_ADJUNTOS`?
  ¿falló la visión?) y dejalo en el log.
- **Obra en texto libre**: «Lennon me pasó us$20.000» → Lennon (el nombre de la obra
  aparece aunque sea también el apellido del comitente). Test con el texto exacto de la
  captura 4.
- **Tipo con typos**: «INGRRSO», «ingrso», «egreso» → tipo correcto por parecido.
- **A un personal no se le pregunta obra** (captura 1), y si viene obra en un personal no se
  escribe (P-000001). **A un ingreso no se le pregunta contratista** (captura 5).
- **Ingreso en una obra de administración con «caja chica» / «para la caja»** → adelanto
  del comitente a la caja de obra (§5.8). La pregunta «¿certificación u honorarios?» solo
  aplica a Moreno-cobros; si hay que hacerla en otra obra, tiene que incluir la opción
  «Adelanto para la caja de obra».
- **Duales** (Sofi, Juanma) con «Retiro» → personal sin preguntar (Retiro manda, R-23);
  Sofi/Juanma → rubro `Familia` como supuesto.

**E · Métrica nueva: preguntas por movimiento.** Sumá al `test_corpus` el promedio de
preguntas por movimiento y el % de movimientos con **cero** preguntas, total y para los que
traen obra + contratista + comprobante. Medí antes y después.

### P1 · Caja de obra (motor) — §5.8 v1.8

**F · «Efectivo» en una obra con caja de obra = esa caja**, con o sin `C`. «Efectivo del
estudio» fuerza la cuenta `Efectivo`.

**G · Cajas de obra en dólares.**
- `Caja obra Lennon` pasa a **moneda USD** (si no tiene movimientos, cambiá la moneda;
  si tiene, creá `Caja obra Lennon USD` y dejá la otra inactiva; anotá cuál hiciste).
- Un **ingreso en dólares** a una caja en dólares: sin tipo de cambio.
- Un **pago en pesos** desde una caja en dólares: `importe` en pesos, y la caja descuenta
  `importe / tc` dólares. El `tc` **se pide en el primer pago del día de esa caja y se
  reutiliza el resto del día** (el motor lo lee del último movimiento de esa caja en esa
  fecha; sigue sin estado), mostrado en la ficha como «TC 1.450 (de hoy)».
- El saldo de la caja se informa en dólares.
- «Lo dejamos en dólares», «no hay tipo de cambio», «en dólares» → respuestas válidas
  cuando la cuenta de destino está en dólares.

### P1 · Corregir lo que ya está en los libros

**H ·** Un script en `scripts/migraciones/` (simulacro por defecto; Valen lo corre con
`--aplicar`) que, **por contraasiento** (§5.19, nunca editando):
1. Cargue primero el **ingreso de USD 20.000 a la caja de Lennon** del 28/09, si Gabriel lo
   confirma (si no, queda en la lista de reenvíos).
2. Pase a `Caja obra Lennon` los pagos de Lennon cargados contra `Efectivo` (Miguel Soto ×2,
   Luis Pereira M-000001), anulando y recargando.
3. Corrija las fechas de M-000001 y del pago de 10.000.000 si el comprobante lo confirma.
4. Corrija P-000001 (sin obra; contratista según el comprobante), el rubro de Edesur y el
   `medio_pago` de los de Mercado Pago.
5. **No toque M-000005** hasta que Valen diga si es una prueba.

Dejá el simulacro impreso al final de este archivo antes de aplicar nada.

### P1 · El cruce completo

**M ·** Leé CAPTURA desde el 29/09 y cruzala contra MOVIMIENTOS de los dos libros. Una tabla
al final de este archivo con **cada mensaje**: hora · texto · adjunto sí/no · resultado
(`M-…`/`P-…` escrito · descartado por Gabriel · trabado en una pregunta · error) · cuántas
preguntas hizo el bot. Al pie: cuántos movimientos se perdieron y cuáles hay que pedirle a
Gabriel que reenvíe. Los mensajes del bot no están en CAPTURA: si hace falta reconstruirlos,
usá los logs del gateway o deducilos por las respuestas de Gabriel.

### P2 · Lo que quedó abierto del 30/09

- **La ñ:** plegar ñ→n al comparar razones sociales («Maragano» = «Maragaño»). Es técnico, no
  cambia reglas.

---

## 5 · Tests que tienen que existir al terminar

Un **test de conversación por cada captura**, con el gateway real y el motor real en memoria
(libro en memoria, WhatsApp mockeado): se mandan los mismos mensajes que mandó Gabriel y se
verifica qué contesta el bot. Mínimos:

1. «Retiro/Sofi» + comprobante → ficha personal, sin obra, sin preguntas.
2. «Lennon/Miguel» + comprobante legible → ficha completa, **cero preguntas**, cuenta =
   caja de obra si dice efectivo.
3. El texto de la captura 4 → INGRESO, Lennon, caja de obra en USD, USD 20.000, sin preguntas.
4. Pregunta pendiente + llega un comprobante → movimiento nuevo, el anterior en pendientes.
5. Pregunta de tipo de cambio + «¿cuál?» → explica, no consume.
6. Dos 422 seguidos → ofrece Descartar / Dejar para revisar, y el mensaje nombra el campo.

## 6 · Orden sugerido (hoy Valen tiene reunión con el arquitecto)

1. **A, B, C** (gateway) y **D** (motor): son los que más se notan.
2. Deploy de los dos, probar las 8 capturas en ensayo.
3. **F, G, H, M** después.

## Al terminar

- Actualizá `docs/handoff-fachado-core.md` y `docs/handoff-fachado.md`.
- Al final de este archivo: la métrica (preguntas por movimiento, antes y después), el
  simulacro del script de correcciones, la tabla del cruce y las decisiones que tomaste.
