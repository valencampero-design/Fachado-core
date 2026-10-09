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

---

# Resultado — motor (sesión del 9/10)

Hecho en `fachado-core`, **commiteado sin pushear** (4 commits sobre `70df209`): D, E, F, G,
H en simulacro y la ñ. Nada aplicado en el Sheet. El gateway no se tocó. M (el cruce
completo) no estaba en el pedido de esta sesión: queda pendiente.

| Commit | Qué |
|---|---|
| `ebc1570` | D · pocas preguntas, E · métrica por movimiento, F · efectivo = caja de obra |
| `5da8952` | G · cajas de obra en dólares + migración de la caja de Lennon (simulacro) |
| `37ae3f5` | La ñ: razones sociales completas |
| `03ff490` | H · script de correcciones por contraasiento (simulacro) |

## Los tests de §5 que son del motor

| | Resultado |
|---|---|
| 1 · «Retiro/Sofi» + comprobante | Personal, sin obra, rubro Familia (`supuesto`), **cero preguntas** |
| 2 · «Lennon/Miguel» + recibo legible | Miguel Soto, importe y fecha del recibo, rubro del último uso, cuenta **Caja obra Lennon**, **cero preguntas**. También «Lennon/Miguel efectivo» sin comprobante |
| 3 · El texto de la captura 4 | INGRESO, Lennon, USD 20.000, 28/09, Caja obra Lennon; con la caja en dólares, **cero preguntas** (sin tc) |
| 4 a 6 | Son del gateway |

Están en `tests/test_casos.py` (secciones «Conversación · D / F / G» y «La ñ») y en
`tests/test_confirmar.py` («G · Caja obra Lennon en dólares»). Los tres archivos de tests:
TODO OK.

**Por qué la captura 2 preguntó el importe**: el texto llegó 8 s antes que la foto. Leído
junto, el recibo da todo (7.084.000, Miguel Soto, efectivo, 03/10). Es de agrupamiento en el
gateway: la foto que llega con una ficha pendiente sin comprobante tendría que sumarse a esa
ficha, y eso choca con la regla A («llega un comprobante → movimiento nuevo»). Pregunta
abierta abajo.

## E · La métrica: preguntas por movimiento, antes y después

`python -m tests.test_corpus --adjuntos --historia historia.json`: lee los comprobantes reales
y siembra los libros en memoria con MOVIMIENTOS de los dos libros al 9/10 (11 del estudio, 5
personales). El mismo archivo para el antes (código de `70df209`) y el después (código final).
Es el número que vería Gabriel si mandara hoy los 54 movimientos del corpus.

| Preguntas por movimiento | Antes | Después |
|---|---|---|
| **Todos** | 1,22 | **0,98** |
| Todos, con cero preguntas | 18/54 (33 %) | **20/54 (37 %)** |
| **Con obra + contratista + comprobante** | 0,63 | **0,45** |
| Con obra + contratista + comprobante, cero preguntas | 11/19 (58 %) | **13/20 (65 %)** |
| Qué se pregunta | rubro 17, importe 16, etapa 13, contratista 9, obra 6, clasificación 4, tc 1 | importe 16, etapa 13, contratista 9, obra 6, clasificación 4, **rubro 4**, tc 1 |
| Obra/contratista con las preguntas de diseño | 45/50 (90 %) | 45/50 (90 %) |
| Invariante (faltante sin pregunta) | 0 de 59 | 0 de 59 |

El subconjunto completo pasa de 19 a 20 movimientos porque la ñ resolvió el contratista de
«Pago Moreno» (Maragaño): ahora entra en el subconjunto, y pregunta la etapa de Moreno.

Las otras mediciones (código de D/E/F, antes de G y la ñ):

| | Antes | Después |
|---|---|---|
| Con adjuntos, libros vacíos · todos | 1,24 · 18/54 (33 %) | 1,02 · 18/53 (34 %) |
| Con adjuntos, libros vacíos · completos | 0,63 · 11/19 (58 %) | 0,47 · 11/19 (58 %) |
| Sin adjuntos, libros vacíos · todos | 1,85 · 1/54 (2 %) | 1,65 · 1/54 (2 %) |
| Sin adjuntos, con historia · todos | 1,85 | 1,61 |

Sin leer los comprobantes casi todo mensaje con adjunto pregunta el importe: ese modo no
mide el criterio de D. Lo que más queda: **el importe** (comprobantes que no se pueden leer,
o mensajes sin adjunto) y **la etapa de Moreno** (dos etapas en curso: pregunta abierta 4).

## H · El simulacro del script de correcciones

Antes de correrlo, lo que dicen los comprobantes (bajados y mirados uno por uno):

- **M-000001**: «Sábado 7/02 de 2026 · Recibí de Lucas Lennon · US$ 400 × 1425 · $ 570.000 de
  2.000.000 · Pintura de madera». El 7/2/2026 fue sábado: **la fecha está bien leída**.
- **M-000008**: «Miércoles 05 de agosto de 2026 · Recibí de Lucas Lennon · US$ 6.600 × 1515
  ≈ 10.000.000 · Cert. 17 e obra». El 5/8/2026 fue miércoles: **la fecha está bien leída**.
- **M-000010**: «Miércoles 07 de octubre de 2026 · US$ 2.000 × $ 1535 = 3.070.000 ·
  Certificado de obra».
- **P-000001**: transferencia del Banco Patagonia de Gabriel a **«FACHADO, SOFIA»** (CUIT
  27-47181632-4), $ 184.000, 30/09 16:05. No es Tucu.

Así que el punto 3 (fechas) no cambia nada, y cada recibo trae su tipo de cambio: con la caja
en dólares, es el tc de cada pago. Salida de
`python scripts/migraciones/2026_10_09_correcciones.py --con-ingreso-usd` (simulacro: los dos
libros reales leídos, todo corrido con `/anular` y `/confirmar` sobre una copia en memoria):

```
SIMULACRO · correcciones del 9/10 (handoff H)
  («Caja obra Lennon» todavía está en ARS en el Sheet: el simulacro la toma en USD, como queda después de la migración)

Lennon antes:   pagado con plata del estudio $ 13,640,000 · pagado por el comitente $ 0

1 · Ingreso de USD 20.000 a la caja de Lennon (28/09)
    cargado como M-000012: tipo=INGRESO, fecha=2026-09-28, importe=20000, moneda=USD, obra=Lennon, etapa=1, cuenta=Caja obra Lennon, medio_pago=Efectivo, tipo_gasto=obra, tipo_comprobante=Sin comprobante, descripcion=Adelanto de Lucas Lennon para la caja de obra (capturas 4 a 7 del 9/10), origen=WHATSAPP
      por qué: adelanto del comitente a la caja (§5.8)

2 a 4 · Contraasientos y recargas
  · M-000001 anulado por M-000013
    recargado como M-000014: cuenta: «Efectivo» → «Caja obra Lennon», tc: «1» → «1425», etapa: «» → «1»
      por qué: §5.8 v1.8: el efectivo de Lennon sale de su caja. Recibo: US$ 400 × 1425 = $ 570.000
      la caja descuenta US$ 400.00
  · M-000008 anulado por M-000015
    recargado como M-000016: cuenta: «Efectivo» → «Caja obra Lennon», tc: «1» → «1515»
      por qué: §5.8 v1.8: el efectivo de Lennon sale de su caja. Recibo: US$ 6.600 × 1515 ≈ $ 10.000.000
      la caja descuenta US$ 6,600.66
  · M-000010 anulado por M-000017
    recargado como M-000018: cuenta: «Efectivo» → «Caja obra Lennon», tc: «1» → «1535»
      por qué: §5.8 v1.8: el efectivo de Lennon sale de su caja. Recibo: US$ 2.000 × 1535 = $ 3.070.000
      la caja descuenta US$ 2,000.00
  · P-000001 anulado por P-000006
    recargado como P-000007: obra: «Moreno» → «», etapa: «1» → «», comitente: «Gonzalo Fernández Moreno» → «», contratista: «Tucu» → «Sofia Cervera», item: «Tucu» → «FACHADO, SOFIA»
      por qué: Retiro/Sofi: un personal no lleva obra; la transferencia es a «FACHADO, SOFIA», no a Tucu
  · P-000004 anulado por P-000008
    recargado como P-000009: medio_pago: «Otro» → «Mercado Pago»
      por qué: pagado desde Mercado Pago, no «Otro»
  · P-000005 anulado por P-000010
    recargado como P-000011: medio_pago: «Otro» → «Mercado Pago»
      por qué: pagado desde Mercado Pago, no «Otro» (el rubro Agua, abierto)

Lennon después: pagado con plata del estudio $ 0 · pagado por el comitente $ 0 · caja (USD): ingresado 20,000.00, pagado 9,000.66, por rendir 10,999.34

5 · M-000005 (Austral · Valentín Campero · $ 400): no se toca

(simulacro: no se escribió nada en los libros ni se movió nada en Drive. Correr con --aplicar)
```

Sin `--con-ingreso-usd`, lo mismo sin el punto 1: la caja queda con US$ 9.000,66 pagados y
−9.000,66 por rendir (§5.8: el arquitecto puso plata propia) hasta que se cargue el adelanto.

Orden para aplicarlo (lo corre Valen, después del deploy):

```bash
python scripts/migraciones/2026_10_09_caja_lennon_usd.py --aplicar
```
```bash
python scripts/migraciones/2026_10_09_correcciones.py --aplicar
```

El segundo se niega a correr si la caja sigue en pesos. Es idempotente: cada corrección tiene
su `msg_id` fijo (`correccion-2026-10-09-<id_mov>`), y volver a correrlo no duplica nada.

## Decisiones que tomé (técnicas; ninguna regla de negocio nueva)

1. **Rubro**: el último usado con ese contratista **del mismo lado** (obra o personal),
   ordenado por fecha y `ts`; origen `supuesto`. Las opciones de la pregunta, por uso en los
   libros (×2) y en los habituales del maestro (×1), con la categoría del contratista primero.
2. **El rubro no se pregunta junto con el contratista ni con obra/personal**: sale de esa
   respuesta. `obligatorios.PREGUNTAS_QUE_DEFINEN_EL_RUBRO`; el invariante lo cubre.
3. **Frases libres**: de tres palabras o más se sacan obra, contratista y cuenta firmes (alias,
   exacto, palabra única); de dos palabras, solo si las dos resuelven firme. Nada difuso.
4. **Un personal con obra de terceros**: la obra se descarta con advertencia («Un gasto
   personal no lleva la obra «Moreno»: no se escribe»). Un inmueble personal (Belelli) sí
   queda.
5. **La C y «efectivo del estudio» viajan en `extras`** (`caja_de`, `efectivo_estudio`). Sin
   eso, cualquier respuesta posterior (el tc, el rubro) perdía la caja. La C solo vale para la
   misma obra.
6. **Sin tc solo en cajas de obra en dólares.** Un ingreso en dólares al `Banco USD` sigue
   llevando tc: el saldo del estudio se suma en pesos (§5.7). Dólares a una caja en dólares
   van con `tc` e `importe_ars` vacíos; un pago en pesos desde una cuenta en dólares exige un
   tc mayor que 1.
7. **El tc del día** es el del último movimiento de esa cuenta con esa fecha (por `ts`); con
   la fecha del mensaje si el texto no trae otra.
8. **Caja obra Lennon no tiene movimientos** en el Sheet: la migración le cambia la moneda (no
   hace falta «Caja obra Lennon USD»). No la apliqué. El snapshot de los tests sigue igual al
   Sheet; los tests la pasan a dólares mientras dura el caso.
9. **H**: M-000001 recarga con etapa 1 (la única en curso de Lennon; `/confirmar` la exige).
   P-000001 recarga con contratista **Sofia Cervera** (lo que Gabriel escribió, «Sofi», por
   alias) e ítem «FACHADO, SOFIA» (el comprobante). Cada recarga se atribuye a quien cargó la
   original (Gabriel), con su teléfono de USUARIOS.
10. **La métrica con historia**: `test_corpus --historia ARCHIVO.json` siembra los libros en
    memoria con MOVIMIENTOS reales (11 del estudio y 5 personales al 9/10). El mismo archivo
    para el antes y el después. Sin historia, el rubro del último uso no puede verse.
11. **La ñ** ya la plegaba `normalizar` (NFKD: «Maragaño» → «maragano»). Lo que fallaba era
    el nombre legal completo: ahora empareja si todas las palabras del contratista están en la
    razón social, en cualquier orden, y solo si hay uno.

## Preguntas abiertas (decisiones de negocio que no están en v1.8)

1. **Los pagos de Lennon de febrero y agosto** (M-000001, M-000008) son anteriores al adelanto
   del 28/09, y los tres recibos dicen «Recibí de **Lucas Lennon**». ¿Salieron de una caja
   que ya tenía dólares (hubo adelantos antes, sin cargar), o los pagó el comitente directo
   («Pagado por el comitente», §5.9)? El script sigue el handoff (caja de obra); si fueron del
   comitente, cambia la cuenta de esos dos.
2. **Sofía**: la transferencia de P-000001 es a «FACHADO, SOFIA» (CUIT 27-47181632-4) y
   «Sofi» es alias de **Sofia Cervera**. ¿Son la misma persona? Si sí, cargarle ese CUIT a
   Sofia Cervera; si no, dar de alta a Sofía Fachado y cambiar la línea de P-000001 del script.
3. **El rubro de Edesur** (P-000005 dice Agua; no hay rubro de electricidad). El script no lo
   toca.
4. **La etapa de Moreno**: tiene dos en curso (1 y extras), y es **la pregunta que más queda
   en el corpus** después del importe (13). ¿Se usa la etapa del último pago a ese contratista
   en esa obra como `supuesto`, igual que el rubro?
5. **El tc del recibo**: los recibos de Miguel dicen «US$ 2.000 × 1535». Si el lector sacara
   ese tc, el primer pago del día de la caja en dólares tampoco preguntaría. ¿Vale el tc del
   recibo como el del día?
6. **El ingreso de USD 20.000** del 28/09: falta que Gabriel lo confirme (`--con-ingreso-usd`).
7. **M-000005** (Austral · Valentín Campero · $ 400): ¿es una prueba? No se tocó.
8. **M-000010** está con rubro Materiales › Albañilería y el recibo dice «Certificado de obra»
   de Miguel Soto (contratista). No estaba en la lista de H: no se tocó.
9. **Captura 2** (el texto 8 s antes que la foto): ¿la foto que llega con una ficha pendiente
   sin comprobante se suma a esa ficha, aunque la regla A diga «movimiento nuevo»? Es del
   gateway.
10. **El pago Tucu/Moreno** (la imagen de la fila 172 de CAPTURA) puede haberse perdido:
    P-000001 se lo llevó como respuesta. Entra en el cruce (M).

## Deploy (9/10, después de la sesión)

- Pusheado y desplegado en Railway (`web`); `/salud` responde.
- **`Caja obra Lennon` pasó a USD en el Sheet** (`2026_10_09_caja_lennon_usd.py --aplicar`:
  CUENTAS fila 9; no tenía movimientos). `/maestros/recargar` y snapshot regenerado (`cdedbc8`):
  el único cambio es esa moneda. Los tres archivos de tests, TODO OK.
- **Verificado en producción con `/interpretar`** (no escribe):
  - «Lennon/Miguel efectivo $1.450.000» → Miguel Soto, **Caja obra Lennon**, rubro Albañilería
    (el último pago a Miguel, M-000010) y una sola pregunta: el tipo de cambio, porque es el
    primer pago en pesos del día desde la caja en dólares.
  - El texto de la captura 4 → INGRESO, Lennon, USD 20.000, 28/09, Caja obra Lennon, **cero
    preguntas**.
- **No aplicado**: el script de correcciones (preguntas abiertas 1 y 2 primero) y el ingreso
  de USD 20.000 (falta la confirmación de Gabriel). Hasta que se cargue, la caja de Lennon
  no tiene movimientos.
- **Del gateway** (otra sesión): mostrar el saldo de la caja con `caja_obra.moneda` (US$) y
  mandar «en dólares» / «no hay tipo de cambio» como respuesta a `tipo_cambio` sin validarla
  como número.
