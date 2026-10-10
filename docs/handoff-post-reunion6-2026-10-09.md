# Handoff — después de la reunión 6 (9/10): Petrus adentro, cinco fallas nuevas

> 9/10/2026 · A&C. Mismo archivo en `fachado-core/docs/` y en
> `chatbot-contable/docs/clientes/fachado/`. Leé primero **`CONTEXTO-FACHADO.md` v1.9**:
> cambiaron §5.6 (contratista nuevo), §5.8 (pago en dólares desde la caja, la palabra «caja»,
> US$ siempre visible), §5.12 (una pregunta una vez, consultas que no se consumen, «eliminar»
> = anular, rubro por último uso) y §8 (Petrus ya carga).
>
> **Capturas:** `chatbot-contable/docs/clientes/fachado/capturas/2026-10-09-post-reunion/`
> (4 imágenes, numeradas). Miralas antes de empezar.
>
> **Prioridad del proyecto (§8):** hacia adelante. No se invierte tiempo en el histórico. La
> meta es noviembre con todo operativo: Gabriel y Petrus cargando sin fricción.

## Reglas de siempre

- Ningún test escribe en el Sheet real. Commits armados, **sin pushear**.
- Gateway: los otros cuatro clientes no cambian.
- Decisión de negocio que no esté en v1.9: no se inventa, se anota al final.
- Cada falla de abajo termina en **un test de conversación** que la reproduce.

---

## Las cinco fallas

| # | Captura | Qué pasó | Qué tiene que pasar | Lado |
|---|---|---|---|---|
| 1 | `01-elias-contratista-nuevo-y-pregunta-doble` | PDF de Galicia + «Lennon/elias/zingueria» → «¿Quién es «elias»?» con Ibañez, Mathias Flores, Mariela Escribana. **La pregunta llegó dos veces** | Elías no está en el maestro: **es nuevo** (§5.6 v1.9). Ficha: «Elías es nuevo: lo agrego como contratista · Zinguería», nombre completo y CUIT del destinatario del comprobante, alias «elias». Al confirmar, alta en CONTRATISTAS. Cero preguntas | motor (alta) + gateway (doble) |
| 2 | `02-sofi-pregunta-importe-y-despues-lo-lee` | Comprobante + «Retiro/sofi» → «¿Cuál es el importe?» y **enseguida** la ficha con $ 80.000 del comprobante | No preguntar nada hasta tener el comprobante leído. Una sola respuesta: la ficha | gateway |
| 3 | `03-eliminar-y-consultas-comidas-por-pregunta` | «el M 0014 ESTA MAL HAY QUE ELIMINARLO» → «¿A quién se le pagó?». Después de Descartar, «¿En cuánto está el saldo de la caja chica de Lennon?» y «Quiero saber el saldo actual de la caja chica» → **otra vez** «¿A quién se le pagó?» | «eliminar/borrar/anular M 0014» = anulación (§5.19): mostrar M-000014 y botón «Anular M-000014». Una consulta se contesta aunque haya una pregunta pendiente. **Saldo de la caja de obra** como consulta nueva | gateway + motor |
| 4 | `04-ingreso-usd-sin-us` | «15000 dólares» → ficha «Ingreso **$ 15.000**… Cuenta: Caja obra Lennon» | «Ingreso **US$ 15.000**». Toda ficha y acuse en dólares muestra US$ | gateway (y verificar que el motor devolvió `moneda = USD`) |
| 5 | (nota de la reunión) | Pagos en dólares desde la caja de Lennon | Se descuentan **directo en dólares, sin tipo de cambio**. «caja» en el mensaje = caja de la obra | motor |

---

## Gateway (`chatbot-contable`)

**G1 · Preguntas y fichas duplicadas (capturas 1 y 2) — la más urgente.** Desde `8430254`
(«un adjunto dentro de los 90 s se suma a la ficha en curso») el mismo grupo parece
procesarse **dos veces**: una al cerrar el grupo con el texto, y otra al sumar el adjunto o
al vencer el timer. Resultado: la misma pregunta dos veces (captura 1) o una pregunta de un
`/interpretar` sin comprobante seguida de la ficha de otro con comprobante (captura 2).
- Reproducilo con el orden real de las capturas: adjunto → texto a los pocos segundos.
- Regla: **un grupo se interpreta una sola vez**, cuando el texto lo cierra y **todas sus
  subidas terminaron** (el future de cada adjunto). La suma de un adjunto tardío a una ficha
  sin comprobante reemplaza la ficha; nunca manda una segunda pregunta para lo mismo.
- Antes de mandar una pregunta, si es idéntica a la última enviada a ese teléfono para la
  misma ficha, no se manda.
- Tests: adjunto→texto, texto→adjunto (8 s), adjunto→texto→segundo adjunto. En los tres,
  **un solo mensaje del bot** por pregunta y por ficha.

**G2 · Consultas y pedidos con una pregunta pendiente (captura 3).** Con una pregunta
abierta, un texto que no es una respuesta se manda a `/interpretar` **sin**
`contexto_previo` (regla A): si vuelve `intencion = consulta`, se contesta con `/consultar` y
la pregunta sigue pendiente (se recuerda en una línea). Hoy «saldo de la caja chica de
Lennon» terminó como respuesta a «¿A quién se le pagó?»: revisá por qué no entró por la
regla A (¿lo tomó como «texto corto = dato de la ficha»?). Una frase con «?» , «saldo»,
«cuánto», «quiero saber» no es un dato.

**G3 · «Eliminar» = anular (captura 3).** «eliminar», «borrar», «anular», «está mal… M
0014» con un id de movimiento (aceptá `M 0014`, `M-0014`, `M14`, `M-000014`, y `P-` igual)
→ `GET /movimientos/M-000014` → «M-000014 · Lennon · Miguel Soto $ … ¿Lo anulo?» con
«🗑 Anular» / «No». «Anular» → `/anular` sin recarga. Es el mismo circuito de «corregir»,
sin la ficha nueva.

**G4 · Después de «Descartar», nada vuelve a preguntar** sobre esa ficha. En la captura 3,
tras «Listo, lo dejo…» el siguiente mensaje recibió otra vez «¿A quién se le pagó?»: o
quedó la pregunta viva, o subió otra ficha de la cola sin avisar. Si sube una de la cola,
se avisa cuál es antes de preguntar.

**G5 · US$ (captura 4).** En la ficha y en el acuse, el importe usa `moneda`: `US$ 15.000`
si es USD. Si el motor devolvió `moneda = ARS` para «15000 dólares», es del motor (M5):
anotalo.

## Motor (`fachado-core`)

**M1 · Contratista nuevo (§5.6 v1.9, captura 1).**
- Un token que no resuelve por exacto, alias, CUIT ni difuso ≥ 88 (§5.5) **no** genera
  `apodo_ambiguo` con candidatos lejanos: es **contratista nuevo**.
- Datos: nombre y CUIT del destinatario del comprobante si lo hay (razón social completa);
  si no, el nombre como lo escribió, capitalizado. Rubro: del texto si resuelve a RUBROS
  («zingueria» → Zinguería); si no, una sola pregunta de rubro.
- La ficha lleva `extras.contratista_nuevo = {nombre, cuit, rubro_habitual_1/2, alias}` y
  una advertencia «Elías es nuevo: lo agrego como contratista». No es un faltante.
- `/confirmar`, después de escribir el movimiento, da de alta en CONTRATISTAS (activo, con
  rubro habitual) y escribe el alias (igual que hoy con `alias_propuesto`). Si falla el
  alta, advertencia, no error.
- Ojo con el difuso: «elias» no puede proponer «Ibañez». Revisá por qué esos tres
  candidatos salieron (¿LLM? ¿difuso bajo?) y que no vuelva a pasar.

**M2 · Consulta «saldo de caja» (captura 3).** Nueva consulta en `/consultar`
(`consulta = "caja"`): saldo de la caja de obra de esa obra, en su moneda (ingresado,
pagado, por rendir), y los últimos movimientos. `inferir_consulta` la reconoce por «saldo»,
«caja», «caja chica», «cuánto hay/queda». `_intencion` tiene que devolver `consulta` para
esas frases aunque nombren una obra. Si la pidieran, el saldo de una obra (lo mismo que
`ConfirmarOut.obra`) es la variante natural: dejala anotada, no hace falta hoy.

**M3 · Pagos en dólares desde la caja en dólares (§5.8 v1.9, nota 5).** Un EGRESO con
`moneda = USD` y cuenta = caja de obra en USD: **sin tc ni pregunta**, descuenta US$ directo.
«caja», «caja chica», «de la caja» en el texto = la caja de la obra del mensaje (como la
`C`). Tests: «Lennon/Miguel caja USD 2.000», «Lennon/Miguel 2000 dólares de la caja».

**M4 · «Eliminar M 0014» no es un movimiento.** `_intencion` no tiene que devolver
`movimiento` (con «¿A quién se le pagó?») para un texto que nombra un `id_mov` y un verbo de
borrar/corregir. Devolvé `intencion = "otro"` o, mejor, una intención nueva `"anular"` con
`extras.id_mov`, si el gateway prefiere apoyarse en eso (acordalo con el gateway y anotalo).

**M5 · Verificar la moneda en una corrección (captura 4).** «15000 dólares» como respuesta a
«¿Qué cambio?» (con `contexto_previo`) tiene que dejar `moneda = USD`. Test.

---

## Tests mínimos al terminar

1. Captura 1 completa (PDF → «Lennon/elias/zingueria») → **una** ficha, contratista nuevo
   con nombre y CUIT del comprobante, rubro Zinguería, cero preguntas, un solo mensaje.
2. Captura 2 (comprobante → «Retiro/sofi») → la ficha con $ 80.000, sin preguntar el importe.
3. Pregunta pendiente + «¿cuánto hay en la caja chica de Lennon?» → contesta el saldo en US$
   y recuerda la pendiente.
4. «el M 0014 está mal, hay que eliminarlo» → propone anular M-000014; con «Anular», anula.
5. «15000 dólares» como corrección → US$ 15.000 en la ficha y en el acuse.
6. «Lennon/Miguel caja USD 2.000» → egreso US$ 2.000 de Caja obra Lennon, sin tc, sin
   preguntas.

## Al terminar

- Actualizá `docs/handoff-fachado-core.md` y `docs/handoff-fachado.md`.
- Al final de este archivo: qué hiciste, la causa de G1, y los contratos nuevos
  (`extras.contratista_nuevo`, `consulta = "caja"`, intención de anular si la hacés).
- Cruzá contratos entre los dos lados antes de desplegar, como el 30/09 y el 9/10.

---

# Resultado — motor (fachado-core), 9/10

M1 a M5 hechos, con sus tests. **Commiteado sin pushear.** El gateway no se tocó (G1 a G5 son
de su sesión; `docs/handoff-fachado.md` es del gateway y no lo edité).

| | Qué quedó | Tests |
|---|---|---|
| **M1** contratista nuevo | Un token que no resuelve ya no trae «parecidos» lejanos: los candidatos se filtran con el umbral de §5.5 (`resolver.cercanos`, WRatio ≥ 88; «elias» contra Ibañez da 72). Sin candidatos cercanos, es **nuevo**: nombre y CUIT del destinatario del comprobante (razón social «PEREZ, ELIAS DANIEL» → «Elias Daniel Perez»), o el nombre como lo escribió, capitalizado; rubro del texto o una sola pregunta; lo escrito queda como alias. `/confirmar` lo da de alta en CONTRATISTAS (activo, CUIT, rubro habitual) y escribe el alias; si falla, advertencia | `test_casos` «M1» (7), `test_confirmar` «M1» (5) |
| **M2** saldo de caja | `/consultar` con `consulta = "caja"`: ingresado, pagado, por rendir **en la moneda de la caja** y los últimos 5. `inferir_consulta` la reconoce por «saldo», «caja», «caja chica», «cuánto hay/queda»; `_intencion` devuelve `consulta` para esas frases **aunque haya `contexto_previo`** | `test_casos` «M2» (7), `test_confirmar` «M3 y M2» (3) |
| **M3** USD desde caja USD | Ya funcionaba desde el 9/10 (G): sin tc, descuenta US$ directo. «caja», «caja chica», «de la caja» = la caja de la obra | `test_casos` «M3» (2), `test_confirmar` (1) |
| **M4** «eliminar M 0014» | Intenciones nuevas `anular` y `corregir`, con `id_mov` normalizado; nunca `movimiento`, aunque venga con `contexto_previo` | `test_casos` «M4» (10) |
| **M5** moneda en una corrección | Ya funcionaba desde `8fad1ea` (la moneda que dice el texto manda): «15000 dólares» con `contexto_previo` → USD 15.000, sin tc en la caja en dólares. **El «$ 15.000» de la captura 4 es del gateway (G5)**: el motor devuelve `moneda = USD` | `test_casos` «M5» (2) |

Los tests mínimos 1 (lado motor), 3 (lado motor: consulta + saldo en US$), 4 (lado motor:
la intención), 5 (lado motor) y 6 están cubiertos. Los tres archivos de tests: TODO OK.

**Por qué salieron Ibañez, Mathias Flores y Mariela Escribana (captura 1)**: no fue el LLM ni
el difuso del resolver. La pregunta «¿Quién es «elias»?» completaba las opciones con
`resolver.candidatos`, que devolvía **los tres más parecidos sin ningún umbral**. Ahora pasan
por `resolver.cercanos`.

**G1** (la pregunta doble) es del gateway: el motor no tiene estado y contesta lo mismo a dos
llamadas iguales. Lo que se ve en la captura 1 (dos «¿Quién es «elias»?» idénticas) son dos
`/interpretar` del mismo grupo.

**La métrica** (`test_corpus --adjuntos --historia`, la misma historia del 9/10): **sin
cambios**. 0,98 preguntas por movimiento (37 % con cero); con obra + contratista +
comprobante, 0,45 (65 % con cero); invariante 0 de 59. El corpus no tiene contratistas
nuevos: de las 9 preguntas de contratista que quedan, 8 son los apodos ambiguos «Marce» /
«Marcelo», que preguntan a propósito (§7), y una es «Pago Moreno».

## Contratos nuevos (para cotejar con el gateway antes de desplegar)

**1 · Contratista nuevo (`/interpretar` → `/confirmar`)**
- La ficha trae `campos.contratista` = el nombre nuevo (origen `comprobante` si salió del
  comprobante, `texto` si no) y
  `extras.contratista_nuevo = {nombre, cuit, rubro_habitual_1, rubro_habitual_2, alias}`
  (`cuit` y `alias` pueden venir vacíos; `alias` vacío si es igual al nombre).
- `extras.advertencias` incluye «Elias Daniel Perez es nuevo: lo agrego como contratista ·
  Zinguería» (sin « · rubro» si todavía no lo hay). **No es un faltante ni una pregunta.**
- Si falta el rubro, una sola pregunta `rubro`; contestada, el motor actualiza
  `extras.contratista_nuevo.rubro_habitual_*`. Si el usuario contesta otro contratista, el
  motor saca `extras.contratista_nuevo`.
- `/confirmar` lo usa **si `campos.contratista` es ese nombre y no existe en CONTRATISTAS**:
  alta + alias, después de escribir el movimiento. `ConfirmarOut.contratista_creado` = el
  nombre dado de alta (o `null`). Si falla, el movimiento queda y vuelve una advertencia.
  **El gateway tiene que devolver `extras` sin tocar en `/confirmar`** (ya lo hace con
  `reactivar` y `activar_etapa`).
- La pregunta `contratista` («¿Quién es «X»?») puede venir **sin opciones** si no hay
  parecidos cercanos y el token no puede ser un nombre (números, cuatro palabras o más) o la
  obra también se está preguntando.

**2 · Consulta `caja` (`/consultar`)**
- `ConsultarIn.consulta` y `ConsultarOut.consulta` aceptan `"caja"`. Se infiere del texto
  («¿cuánto hay en la caja chica de Lennon?»).
- `datos = {obra, caja, moneda, ingresado, pagado, por_rendir, ultimos: [{id_mov, fecha,
  tipo, importe, moneda, entra, importe_original, moneda_original, contratista,
  cargado_por}]}`. Los importes, en la moneda de la caja; `importe_original` y
  `moneda_original`, como se cargó el movimiento. `texto` ya viene con «US$».
- Sin obra: si una sola caja tiene movimientos, contesta esa; si no, vuelve una pregunta
  `campo = "obra"`, «¿La caja de qué obra?», con las obras: repreguntar con
  `consulta = "caja"` y `obra`.
- Una obra sin caja: «X no tiene caja de obra», `datos.caja = null`.

**3 · Intenciones `anular` y `corregir` (`/interpretar`)**
- `InterpretarOut.intencion` puede ser `"anular"` (eliminar, borrar, anular, sacar, quitar,
  dar de baja + un id) o `"corregir"` (corregir, está mal, cambiar + un id, sin verbo de
  borrar), con **`InterpretarOut.id_mov`** normalizado («M 0014», «M-0014», «M14» →
  `M-000014`; `P-` igual). `fichas` y `preguntas` vienen vacías.
- Se detectan **aunque venga `contexto_previo`** (no con `respuestas`).
- `anular` → `GET /movimientos/{id_mov}` → «¿Lo anulo?» → `/anular` sin recarga (G3).
  `corregir` → el circuito de corrección de siempre.

**4 · Consultas con una pregunta pendiente**: `_intencion` devuelve `consulta` para una
consulta clara («saldo», «cuánto hay/queda», «quiero saber», o con «?») aunque venga
`contexto_previo`. El gateway igual la tiene que mandar sin `contexto_previo` (G2).

**5 · US$**: la ficha trae `campos.moneda`; con `"USD"`, el gateway muestra «US$» (G5).

## Decisiones que tomé (técnicas)

1. «Parecido de verdad cercano» = WRatio ≥ 88, el mismo número de §5.5.
2. Un contratista nuevo solo cuando el token puede ser un nombre (una a tres palabras, sin
   números) **y no se está preguntando la obra** (si no, «Gesell» mal escrito se daba de alta
   como contratista).
3. La razón social «APELLIDO, NOMBRE» se da vuelta y se capitaliza («ORELLANA, MARCELO DE»
   → «Marcelo de Orellana»).
4. La consulta de caja sin obra contesta sola si hay una única caja con movimientos.
5. Además de `anular`, una intención `corregir` para «el M 0014 está mal» sin verbo de
   borrar: antes daba `otro` y, con una pregunta pendiente, «¿A quién se le pagó?».

## Preguntas abiertas

1. **«Es nuevo» como opción**: cuando sí hay parecidos cercanos, ¿la pregunta suma un botón
   «Es nuevo»? Hoy no: el usuario contesta el nombre y, si no existe, vuelve como texto.
2. **Lo personal**: «Retiro/Fulano» con Fulano desconocido sigue yendo a la descripción, sin
   alta. ¿También se da de alta?
3. **El saldo de una obra** (lo mismo que `ConfirmarOut.obra`) como consulta: anotado, no
   hecho.
