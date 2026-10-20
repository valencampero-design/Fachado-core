# Handoff — semana 8: dejar noviembre listo (extractos, Mercado Pago, saldos y tablero)

> 20/10/2026 · A&C. Mismo archivo en `fachado-core/docs/` y en
> `chatbot-contable/docs/clientes/fachado/`. Leé primero **`CONTEXTO-FACHADO.md` v1.11**:
> cambiaron §5.20 (Petrus manda los extractos, el bot se los pide por semana, cuatro cuentas
> del estudio + el PDF de Mercado Pago) y §5.21 (lo que pidió Gabriel para el tablero). Y el
> resultado de la tirada anterior, al final de `handoff-cierre-propuesta-2026-10-15.md`.
>
> **Corren dos sesiones en paralelo, sin supervisión, hasta el miércoles a la tarde.** Este
> documento fija los contratos (§3) para que ninguna espere a la otra. Si un contrato tiene
> que cambiar, se anota al final de este archivo y se sigue.
>
> **Meta:** el 1/11 Petrus manda los cuatro extractos y el reporte de Mercado Pago de
> octubre, Valen carga los saldos al 31/10, y noviembre es el primer mes que se cierra contra
> el banco. Todo lo de abajo sirve a eso.

## 0 · Reglas

- **Orden fijo**: las partes en el orden de tu sección; commit por parte, **sin pushear**. Si
  una parte se traba más de 30 minutos, anotá por qué al final y pasá a la siguiente.
- **Ningún test ni script escribe en los Sheets reales.** Scripts con simulacro por defecto;
  Valen corre `--aplicar`. Las pruebas de conciliación, con los extractos de muestra y libros
  en memoria.
- **`CONCILIACION_DESDE` no se baja nunca contra el Master real** (no es reversible). Para
  ver el circuito, motor local contra una **copia**.
- **Decisión de negocio que no esté en v1.11: no se inventa.** La opción más conservadora,
  marcada como supuesto en el código y anotada al final. Los supuestos de esta tirada ya
  están listados en §4: se confirman con Gabriel y Petrus el jueves 22.
- Gateway: los otros cuatro clientes no cambian. Todo en `handlers/obras.py`,
  `services/fachado_*.py` y `services/motor_client.py`.
- Archivos modificados solo por CRLF: fuera de los commits.

**Muestras:**
- Extractos de banco: los cuatro formatos ya están en `tests/fixtures/` del motor (CA $,
  CC $, CA U$S y la CA $ 48-69556582-001).
- **Reporte de Mercado Pago en PDF**: Valen se lo pide hoy a Petrus y lo deja en
  `OneDrive/Documentos/A&C/Fachado/Archivos Muestra/Muestra 3/`. Si cuando llegues a esa
  parte no está, seguí las instrucciones de M2.

---

## 1 · Motor (`fachado-core`)

### M1 · Cuentas corrientes de todas las obras (≈30 min) — lo primero

El 15/10 se pidió **una `CC_<obra>` por cada obra** y `obras_con_cc()` quedó con el criterio
viejo: deja afuera proyecto y dirección, Austral, Jardín Maternal y los personales. Contra el
Master real hoy hay 7 hojas.

1. `obras_con_cc()` → **todas las obras de OBRAS**:
   - todas las de terceros, cualquiera sea el servicio (las de proyecto y dirección muestran
     sobre todo los honorarios cobrados);
   - las propias y Austral;
   - Jardín Maternal, aunque esté cerrada (es la obra de referencia).
   Una obra sin movimientos tiene igual su hoja, con los totales en cero.
2. **Los inmuebles personales** (Sur, Abucoque, Belelli, Gessel): su `CC_<inmueble>` va en el
   **libro personal**, nunca en el Master. Se arma desde `VISTA_PERSONAL` y el detalle
   personal, con el mismo formato. Es la única forma de que un colaborador futuro sin
   `ve_personal` no las vea (§5.13).
3. Test: con el maestro del snapshot salen **13 hojas en el Master** (las 11 obras de §6,
   Austral y Jardín Maternal) y **4 en el personal**; ninguna personal en el Master.
4. Corregí el docstring y `docs/tablero-looker.md` donde diga lo contrario.

### M2 · Mercado Pago y las cuatro cuentas juntas (≈3 h)

1. **Las cuatro cuentas son del estudio** (§5.20 v1.11). Esto cierra la pregunta abierta 1 de
   la tirada anterior: la CA $ 48-69556582-001 se queda en el BANCO_RAW del Master. Lo
   personal se sigue cruzando contra el libro personal, fila por fila.
2. **Parser del reporte de Mercado Pago** (`app/extracto.py`, `origen = "mercado_pago"`):
   - PDF con texto (no escaneado): `pdfplumber` o lo que ya use `comprobante.py`, sin LLM.
   - Formato esperado del resumen de cuenta de Mercado Pago: `Fecha | Descripción | ID de la
     operación | Valor | Saldo`, importes `$ 1.234,56` con signo. **Verificalo contra la
     muestra**: si es distinto, gana la muestra.
   - El ID de la operación va a `ref` (es el match fuerte contra el comprobante de Mercado
     Pago). El nombre del destinatario, a `nombre`.
   - Cuenta del libro: `Mercado Pago` (§5.7). Si no existe en CUENTAS, migración en
     simulacro que la agrega (ARS, concilia = sí).
   - **Sin muestra todavía:** escribí el parser contra el formato esperado, tests con un PDF
     armado en `tests/fixtures/`, y un test con la muestra real marcado `skip` hasta que esté.
     Anotalo al final.
3. **Clasificación de Mercado Pago:**
   - compras de Mercado Libre sin comprobante → lote `meli_personal` (como en el banco);
   - rendimientos, comisiones y retenciones de Mercado Pago → lote `gastos_bancarios`;
   - transferencias recibidas y enviadas → matcheo y fichas como cualquier línea.
4. **Traspasos entre cuentas propias.** Hoy, con cinco fuentes, la misma plata aparece dos
   veces:
   - **Entre las cuentas en pesos del banco** (CA → CC): las dos van a `Banco`, así que el
     par (mismo importe, signo opuesto, misma fecha, dos `cuenta_banco` del estudio) se marca
     `INTERNA`. Concilia solo, sin pregunta, sin movimiento.
   - **Banco ↔ Mercado Pago**: el par es un TRASPASO de `Banco` a `Mercado Pago` (o al
     revés). Si el libro ya lo tiene, concilian las dos líneas contra sus dos filas. Si no,
     **una sola ficha de traspaso** con las dos líneas (no dos egresos sueltos).
   - **Pesos ↔ dólares** (CA $ → CA U$S): traspaso entre monedas (§5.7), dos filas. El tipo
     de cambio sale del par: importe en pesos / importe en dólares, origen `comprobante`.
     No se pregunta.
   - El emparejamiento se hace **al armar lo pendiente**, no al importar: los extractos
     llegan de a uno y el par puede completarse con el archivo siguiente. Ventana ±1 día
     hábil.
5. **Gastos bancarios en dólares** (pregunta abierta 4 del 15/10). Supuesto conservador:
   - **un lote aparte por moneda**: `gastos_bancarios` en US$, con `requiere_tc = true`;
   - si ya hay un tipo de cambio usado ese día en el libro, viene como `tc_sugerido`;
   - el gateway lo pregunta **una vez para todo el lote**. Así se respeta §5.7 («cada
     movimiento en dólares lleva su tipo de cambio») sin una pregunta por línea de
     centavos.
6. **`GET /conciliar/estado`** (nuevo, solo lectura): qué llegó y qué falta, por cuenta. Lo
   usa el gateway para el pedido semanal (G1). Contrato en §3.
7. Tests:
   - los cuatro extractos + el PDF de Mercado Pago contra un libro en memoria;
   - un traspaso CA→CC que queda `INTERNA`;
   - un Banco→Mercado Pago que da una sola ficha de traspaso, también si los dos archivos
     llegan en orden inverso;
   - un pesos→dólares con el tc calculado;
   - el lote en US$ con tc;
   - reimportar todo no cambia nada.

### M3 · Saldos de apertura al 31/10 (≈45 min)

Gabriel y Petrus arman los saldos; Valen los carga el 1/11. Dejale eso en un paso.

1. `docs/saldos-apertura-31-10.csv`: plantilla con una fila por cuenta que concilia o lleva
   saldo:
   - Banco, Banco USD, Mercado Pago, Efectivo y cada caja de obra (en su moneda);
   - columnas `cuenta, moneda, saldo, fecha` (fecha 2026-10-31, saldo vacío).
   Leé las cuentas de CUENTAS, no las inventes.
2. `scripts/cargar_saldos_apertura.py --csv <archivo>`, simulacro por defecto:
   - valida que cada cuenta exista y que el saldo sea un número (acepta `1.234.567,89`);
   - escribe `saldo_apertura` y `fecha_apertura` en CUENTAS con `--aplicar`;
   - **control**: para Banco, Banco USD y Mercado Pago muestra el saldo del banco al 31/10
     (la última línea `ANTERIOR` de BANCO_RAW con fecha ≤ 31/10, si ya está importada) contra
     el saldo cargado, y la diferencia. Si la diferencia no es cero, lo avisa pero no frena.
   Las tres cuentas del banco en pesos suman en `Banco`: el control compara la suma de sus
   tres saldos.
3. Test con un CSV de ejemplo y un libro en memoria.

### M4 · Tablero: lo que pidió Gabriel (§5.21 v1.11) (≈1,5 h)

1. **Ingresos contra pagos de cada obra.** Nueva `VISTA_OBRAS_MES`: obra × mes con
   `ingresos` (aportes del comitente + honorarios cobrados), `pagos` (todo lo ejecutado, con
   plata del estudio, del comitente o de la caja), `saldo_mes` y `saldo_acumulado`, en pesos.
   Lo que está en dólares sin convertir va en columnas US$ aparte, como en VISTA_OBRAS.
2. **Visión general.** Nueva `VISTA_GENERAL`, una fila por día de cálculo:
   - saldo por cuenta (Banco, Banco USD, Mercado Pago, Efectivo, total cajas de obra);
   - ingresos y pagos del mes;
   - capital propio inmovilizado total;
   - obras en rojo y en gris;
   - diferencia libro contra banco del último extracto (si hay).
3. **Selector de obra**: el campo se llama `obra`, con el mismo nombre y tipo en **todas** las
   vistas que lo tienen, para que un control de Looker filtre varias fuentes a la vez.
   Verificá que sea así y anotá en la guía si Looker necesita algo más.
4. **Barras horizontales por rubro**: `VISTA_RUBROS` alcanza. Que `rubro_1` y `rubro_2` vengan
   sin vacíos («Sin rubro» en vez de vacío) para que la barra no salga en blanco.
5. **`docs/tablero-looker.md`**, reescribir las páginas:
   - **Visión general** (lo primero que ve Gabriel en el celular): tarjetas de VISTA_GENERAL,
     saldo por cuenta, semáforo de obras;
   - **Por obra**: selector de obra arriba; barras horizontales de lo pagado por rubro;
     ingresos contra pagos por mes (columnas + línea de saldo acumulado); top de
     proveedores; detalle con link;
   - **Proveedores**, igual que hoy;
   - el personal, aparte.
   Paso a paso con clics, como para alguien que nunca usó Looker. Diseño pensado para el
   celular (vista de móvil, ancho 400 px).
6. **El cron de vistas**: el 15/10 aparecieron las `CC_` pero ninguna `VISTA_*`. Las CC las
   escribió `crear_cc_obras.py`; las vistas solo las escribe el cron, que no corrió.
   - Revisá que `scripts/recalcular_vistas.py` termine con código distinto de 0 y un mensaje
     claro si el motor contesta error o tarda.
   - Agregá `--simulacro`: lo que escribiría (hojas y filas) sin escribir.
   - Dejá en `docs/handoff-fachado-core.md` los pasos exactos para crear el servicio en
     Railway: nombre, start command, cron en UTC, variables, y cómo ver el log de la
     primera corrida.

### M5 · Cierre

- **Métrica de siempre** antes y después.
- **Valen autoriza una corrida con `--adjuntos`** (unos USD 0,20) **al final**: es la que
  dice cuántas preguntas hace el bot de verdad con comprobante.
- Actualizá `docs/handoff-fachado-core.md` (contratos y scripts nuevos).
- Al final de este archivo, con el formato de siempre:
  - qué quedó y qué no;
  - los supuestos;
  - el orden de deploy y de scripts para Valen.

---

## 2 · Gateway (`chatbot-contable`)

### G1 · El pedido semanal de extractos a Petrus (≈1,5 h)

§5.20 v1.11: el bot le pide los extractos a Petrus una vez por semana. Es un mensaje
proactivo, así que fuera de la ventana de 24 h va como **plantilla de Meta**. Mismo patrón
que el resumen del lunes (`services/fachado_lunes.py`): ventana desconocida = cerrada;
plantilla; si falla, texto libre.

1. **Job semanal**, apagado por defecto:
   - `FACHADO_PEDIDO_EXTRACTOS=1` lo prende;
   - día y hora configurables: `FACHADO_PEDIDO_EXTRACTOS_CRON`, default **viernes 16:00
     AR** (supuesto, §4);
   - destinatario: el usuario con `rol` de conciliación en el tenant. Sumá
     `"conciliacion": true` a Petrus en `config/tenants/5492944574499.json`, no un teléfono
     escrito en el código.
2. **Antes de mandar, preguntá al motor qué falta** (`GET /conciliar/estado`):
   - si de las cinco fuentes ya llegó todo lo de la semana, no manda nada;
   - si falta algo, lo nombra: «Me faltan: CA U$S y Mercado Pago».
3. **Plantilla** `fachado_pedido_extractos` (Utilidad, español). Valen la pide hoy en Meta
   con este texto; dejalo igual en `docs/clientes/fachado/plantilla-pedido-extractos.md`,
   con el formato de `plantilla-resumen-lunes.md`:
   ```
   Hola {{1}}. Para cerrar la semana del estudio necesito los extractos del banco y el reporte de Mercado Pago. Me faltan: {{2}}. Mandámelos por acá cuando puedas.
   ```
   Ejemplos: `{{1}}` = `Petrus`, `{{2}}` = `CA U$S y Mercado Pago`.
4. **Recordatorio**: si el próximo día hábil a las 10:00 sigue faltando algo, un solo
   recordatorio. Después, nada más hasta la semana siguiente.
5. Tests: ventana abierta y cerrada; nada que pedir; el recordatorio una sola vez.

### G2 · Varios extractos juntos (≈1,5 h)

Petrus va a mandar **cinco archivos seguidos** (cuatro `.xlsx` y un PDF). Hoy cada extracto
dispara su propio resumen y su propia cola: serían cinco resúmenes y lo pendiente mezclado.

1. **Ráfaga de extractos**: los archivos de extracto de un mismo teléfono dentro de la
   ventana de agrupamiento (90 s desde el último) se juntan.
   - Se importan **de a uno, en orden**, con `POST /conciliar/extracto`.
   - Mientras tanto, un solo acuse: «Recibí 5 archivos, los reviso contra los libros».
   - Al terminar, **un solo resumen**: el `resumen` del último (que ya es global), más las
     líneas importadas sumadas.
2. **Lo pendiente se arma una vez, al final**, con `GET /conciliar/pendientes`, y se recorre
   como hoy (lotes, ambiguas, fichas). Así los traspasos que emparejó el motor (M2.4) llegan
   como una sola ficha.
3. **El PDF de Mercado Pago**:
   - va a `/conciliar/extracto` (no a `/interpretar`) cuando el nombre o el texto lo
     marcan: «mercado pago», «resumen de cuenta», «extracto», «reporte»;
   - también cuando llega dentro de una ráfaga de extractos;
   - si el motor contesta **422** («no es un extracto»), el PDF vuelve al circuito normal de
     comprobantes, sin error para el usuario. Un comprobante de Mercado Pago nunca se pierde
     por parecer un reporte.
4. **Lote en dólares** (M2.5): «3 gastos bancarios en US$ por US$ 4,12. ¿A qué tipo de
   cambio?».
   - Si viene `tc_sugerido`: «¿Uso 1.450, el del día?» con «Sí» y la opción de escribir otro.
   - El tc va a `/conciliar/lote` **como string**: es el mismo error del 9/10 con
     `Respuesta.valor`.
5. **Fichas de traspaso** de la conciliación: «Vi que pasaste $ 300.000 del banco a Mercado
   Pago el 28/10. ¿Lo cargo como traspaso?» → Confirmar con `msg_id = "banco:<hash_a>"` y
   `extras.ids_banco = [hash_a, hash_b]` (contrato en §3).
6. **Las preguntas van a quien mandó el extracto** (§5.20: Petrus). Dejalo explícito en el
   código y con un test: si los manda Petrus, Gabriel no recibe ninguna pregunta de la
   conciliación.
7. Tests:
   - ráfaga de 5 archivos → un acuse, un resumen, una cola;
   - el PDF de Mercado Pago dentro y fuera de la ráfaga;
   - un PDF de comprobante que no es reporte (422 → comprobante);
   - el lote en US$, con y sin `tc_sugerido`;
   - una ficha de traspaso;
   - una interrupción en el medio y retomar con «banco».

### G3 · Cierre

- Actualizá `docs/handoff-fachado.md`.
- Al final de este archivo, con el formato de siempre:
  - qué quedó y qué no;
  - los cambios de contrato;
  - cómo probarlo en ensayo **sin bajar `CONCILIACION_DESDE`**.

---

## 3 · Contratos (fijos para esta tirada)

```jsonc
// POST /conciliar/extracto — ahora acepta también el PDF de Mercado Pago
{ "telefono": "549...", "adjunto": { "url": "...", "mime": "application/pdf", "nombre": "...", "sha256": "..." } }
→ { /* lo mismo que hoy */,
    "origen": "banco_patagonia" | "mercado_pago",
    "cuenta_banco": "CA $ 273-125852351-000" | "Mercado Pago" | …,
    "internas": 2 }                         // pares entre cuentas propias, conciliados solos
// 422 {campo: "adjunto"} si no es un extracto: el gateway lo trata como comprobante si es PDF.

// lotes[] suma: "moneda": "ARS" | "USD", "requiere_tc": bool, "tc_sugerido": "1450" | null

// POST /conciliar/lote suma: "tipo_cambio": "1450"   (string; obligatorio si el lote requiere_tc)
// 422 {campo: "tipo_cambio"} si falta o no es número.

// pendientes[] suma: "tipo": "linea" | "traspaso"
//   traspaso: "hash_ids": [a, b], "interpretacion" con una ficha TRASPASO (dos cuentas, tc si cambia la moneda)
// /confirmar de un traspaso de conciliación: msg_id = "banco:<a>" (el primero de hash_ids),
//   ficha.extras.ids_banco = [a, b] → escribe las dos filas y marca CONCILIADO las dos líneas.
//   Con una sola línea sigue siendo extras.id_banco, como hoy.

// GET /conciliar/estado?telefono=549…   (nuevo, solo lectura)
→ { "semana_desde": "2026-10-26",
    "fuentes": [ { "cuenta_banco": "CA $ 273-125852351-000", "cuenta": "Banco", "origen": "banco_patagonia",
                   "ultima_importacion": "2026-10-23T16:10:00-03:00", "ultima_fecha_linea": "2026-10-23",
                   "al_dia": true } ],
    "faltan": ["CA U$S", "Mercado Pago"],      // rótulos cortos para la plantilla
    "texto": "Me faltan: CA U$S y Mercado Pago" }
// al_dia = hay líneas importadas con fecha dentro de la semana pedida. Las cinco fuentes salen de CUENTAS
// (las cuatro del banco por número + Mercado Pago), no fijas en el código.
```

Todo lo demás de los contratos del 15/10 sigue igual. **Sin presupuestos**: ninguna vista ni
contrato los incluye.

---

## 4 · Supuestos de esta tirada (se confirman el jueves 22 con Gabriel y Petrus)

| # | Supuesto | Dónde |
|---|---|---|
| S1 | El pedido de extractos sale el **viernes a las 16:00**, con un recordatorio el próximo día hábil a las 10:00 | G1 |
| S2 | Los gastos bancarios en dólares van en un lote aparte con **un tipo de cambio para todo el lote** | M2.5, G2.4 |
| S3 | Rendimientos y comisiones de Mercado Pago van con los gastos bancarios (Austral, `Impuestos y tasas › Bancarios`) | M2.3 |
| S4 | Una transferencia entre dos cuentas del estudio en pesos no es un movimiento: concilia sola | M2.4 |
| S5 | En «ingresos» de una obra entran los aportes del comitente y los honorarios cobrados | M4.1 |

Siguen abiertos del 15/10 y **no se tocan en código**: rubro de Sofía Cervera, MeLi como
`Personal › Consumos`, capital propio inmovilizado.

---

## Orden de deploy (Valen, miércoles 21)

1. **Motor**:
   - las migraciones en simulacro y después con `--aplicar`;
   - push → `/salud`;
   - `crear_cc_obras.py`, simulacro y `--aplicar` (las CC de todas las obras y las
     personales);
   - el cron de vistas según la guía.
2. **Gateway**:
   - push;
   - en Meta, las dos plantillas aprobadas → `FACHADO_RESUMEN_LUNES=1` y
     `FACHADO_PEDIDO_EXTRACTOS=1`;
   - `"conciliacion": true` en el tenant de Petrus.
3. **Prueba en producción**: Petrus manda los cinco archivos de la semana. Como son de
   octubre, todo entra `ANTERIOR`: un acuse, un resumen, «todo anterior al 1/11». Ese es el
   resultado correcto.
4. **Viernes 23**: ensayo completo con el motor local contra una **copia** del Master y
   `CONCILIACION_DESDE=2026-10-01`.

## Al terminar (las dos sesiones)

Debajo de esta línea, cada sesión deja su resultado: qué quedó (con commits), qué no y por
qué, supuestos, cambios de contrato y los pasos de deploy en orden.

---

## Resultado — Motor (sesión del 20/10)

Las cuatro partes de código commiteadas, una por parte, en `main`, **sin pushear**. El único
push fue el autorizado: `89efc4a` (el snapshot de las dos Sofía), primero de todo. Ningún
test ni script escribió en los Sheets reales: todo lo que tocó el Master o el libro personal
fue lectura o simulacro. No se corrió ningún `--aplicar`, no se tocó `CONCILIACION_DESDE` ni
las variables de Railway.

Seis suites en verde al cierre: `test_casos`, `test_confirmar`, `test_reglas`,
`test_conciliar` (55 checks, +19), `test_vistas` (48, +23) y `test_apertura` (17, nueva).

### Qué quedó

| Parte | Commits | Qué |
|---|---|---|
| — | `64313c8` | Este handoff, commiteado sin cambios (autorizado) |
| **M1** | `5897289`, `63fddb2` | Una `CC_` por cada obra: **13 en el Master** y las 4 de los inmuebles (Sur, Abucoque, Belelli, Gessel) **en el libro personal**, con el mismo formato (`cuenta_corriente_personal`). `crear_cc_obras.py` escribe las dos; su simulacro contra los libros reales da 13 + 4. `63fddb2`: cinco tests de `test_casos` usaban «elias» como contratista inexistente y el snapshot del 15/10 trae a Elias Rodriguez; ahora usan «teodoro» |
| **M2** | `b4e0c8e`, `491e041` | **Mercado Pago y las cuatro cuentas juntas.** Ver abajo. `491e041`: `.gitattributes` con `*.pdf` y `*.xlsx` binarios (el PDF armado es todo ASCII y un checkout con `autocrlf` le rompería el xref) |
| **M3** | `05b230b` | `docs/saldos-apertura-31-10.csv` (12 cuentas leídas de CUENTAS: Banco, Banco USD, Efectivo, Mercado Pago y las 8 cajas de obra, cada una en su moneda) y `scripts/cargar_saldos_apertura.py --csv` con el control contra el banco. Simulacro contra el Master real: lee bien, «sin saldo, no se carga» en las 12 |
| **M4** | `3f03a0e` | `VISTA_OBRAS_MES`, `VISTA_GENERAL`, `obra` igual en todas las vistas, «Sin rubro» / «Sin obra», `recalcular_vistas.py` con códigos de salida y `--simulacro`, la guía de Looker reescrita y los pasos del cron en Railway |
| **M5** | (este commit) | `docs/handoff-fachado-core.md` al día (archivos, endpoints, contratos, deploy) y este resultado |

**M2 en detalle:**
- **El PDF de Mercado Pago** (`extracto.leer_mercado_pago`): pypdf, sin LLM; `origen =
  mercado_pago`, `cuenta_banco = "Mercado Pago"`; el ID de la operación queda en `ref`, y es
  el match fuerte contra un comprobante de Mercado Pago (`ref_comprobante = op:<ID>`).
- **Clasificación**: la compra de Mercado Libre va al lote `meli_personal`; rendimientos,
  comisiones y retenciones van a `gastos_bancarios` (S3); las transferencias, con match o
  ficha.
- **Las cinco fuentes salen de CUENTAS**, no del código. Columna nueva `cuentas_banco`:
  - `Banco` ← CA $ 273, CC $ 273 y CA $ 48;
  - `Banco USD` ← CA U$S;
  - `Mercado Pago` ← el reporte.

  Migración `2026_10_20_cuentas_conciliacion.py`, aplicada **solo al snapshot**. Cada línea
  busca candidatos solo en su cuenta del libro (`cuenta_de_linea`).
- **Traspasos entre cuentas propias** (`emparejar`, ±1 día hábil, el par más cercano):
  - CA → CC = las dos líneas `INTERNA`, sin movimiento ni pregunta (S4), contadas en
    `internas`;
  - Banco ↔ Mercado Pago = **una** ficha TRASPASO, llegue primero el que llegue;
  - pesos ↔ dólares (las dos líneas «COMPRA-VENTA DOLARES») = traspaso con el tc del par
    (145.000 / 100 = 1.450).

  `/confirmar` con `extras.ids_banco` escribe las dos filas, cada una con su `id_banco`, y
  marca las dos líneas.
- **Lote en dólares** (S2): `moneda`, `requiere_tc` y `tc_sugerido` (el tc que el libro usó el
  último día del lote). `/conciliar/lote` sin `tipo_cambio` da 422 `{campo: tipo_cambio}`; con
  «1.450» escribe en Banco USD con ese tc.
- **`GET /conciliar/estado`** según §3.
- **Tests**:
  - los cuatro archivos contra un libro en memoria, también con Mercado Pago primero y en orden
    inverso;
  - CA→CC INTERNA, Banco→MP con una sola ficha, pesos→USD con tc, el lote en US$ con tc,
    `estado` con «Me faltan: CA $ 48»;
  - reimportar todo no cambia nada.

**M4 en detalle:**
- **`VISTA_OBRAS_MES`**, obra × mes. Columnas:
  - `aportes_comitente`, `honorarios_cobrados` y `pagado_directo_por_el_comitente`, que suman
    `ingresos`;
  - `pagos`, `saldo_mes` y `saldo_acumulado`;
  - las de US$ sin convertir, aparte;
  - `mes_fecha`.

  Los meses vacíos van en cero hasta el actual.
- **`VISTA_GENERAL`**: una fila por día (los últimos 90), con `es_hoy`. Trae:
  - el saldo de Banco, Banco USD, Mercado Pago y Efectivo;
  - las cajas de obra en $ y en US$;
  - ingresos y pagos del mes;
  - capital propio;
  - obras en rojo y en gris, con la cuenta y la lista;
  - la diferencia libro − banco y el último extracto.

  Contra los libros reales (solo lectura) se calcula en 4 s.
- **`obra`**: el mismo nombre y tipo (texto, nunca vacío) en VISTA_OBRAS, VISTA_OBRAS_MES,
  VISTA_RUBROS, VISTA_PROVEEDORES y VISTA_DETALLE. Hay un test que lo verifica. En Looker no
  hace falta nada más que no renombrar el campo (anotado en la guía).
- **`mes_fecha`** en VISTA_RUBROS y VISTA_PROVEEDORES: una fecha real para los controles de
  período, en vez de depender de cómo Looker lea «2026-10».

### Qué no y por qué

- **La muestra real del PDF de Mercado Pago no estaba** (`Archivos Muestra/Muestra 3/` no
  existe). El parser está escrito contra un formato **armado**
  (`tests/fixtures/generar_muestras_armadas.py`). `test_conciliar` lee la muestra real sola
  cuando aparezca; hoy dice SKIP. Hasta probarla, un PDF real puede no reconocerse: en ese
  caso devuelve 422 y el gateway lo manda al circuito de comprobantes, que es lo seguro.
- **Nada aplicado en los Sheets** (prohibido en esta tirada). Quedan para Valen:
  `preparar_sheet` (la columna `cuentas_banco` y `BANCO_RAW.origen`), la migración del 20/10,
  `crear_cc_obras` y, el 1/11, los saldos. El orden está abajo.
- **CONTEXTO v1.11 incompleto en el repo**: `44b37fb` solo trae las CC de §5.21 y el
  encabezado dice 1.10. Trabajé con este handoff como especificación. La sesión del gateway
  encontró lo mismo.

### Supuestos y decisiones (conservadores; ninguno cambia un contrato de §3)

- **S2–S5 implementados** como dice §4 (S1 es del gateway). Los abiertos del 15/10 —rubro de
  Sofía Cervera, MeLi como `Personal › Consumos`, capital propio— **no se tocaron**.
- **«Ingresos» de una obra incluye lo que el comitente pagó directo** (además de los aportes y
  los honorarios de S5), y esos mismos pagos están en `pagos`. Si no, Lennon aparecería con
  −$22 millones de saldo acumulado, como si el estudio financiara la obra: §5.9 lo prohíbe.
  Va en su propia columna, para que se vea.
- **Honorarios** = un ingreso con «honorario» en `rubro_1`, `rubro_2` o `item`; el resto de los
  ingresos de la obra (también los que entran a la caja de obra) son aportes.
- **`VISTA_GENERAL` se recalcula entera** (90 días hacia atrás) en vez de agregar una fila por
  noche. No depende de que el cron haya corrido los días anteriores, que fue el problema del
  15/10.
- **La diferencia libro − banco va vacía** mientras la cuenta no tenga `fecha_apertura`: antes
  del saldo de apertura no dice nada.
- **Plantilla de saldos**: sin Chequera ni «Pagado por el comitente», porque no son plata en
  una cuenta. Una fila con el saldo vacío se saltea con un aviso; cualquier error (cuenta que
  no existe, moneda equivocada, número o fecha inválidos, cuenta repetida) hace que no se
  escriba nada. Acepta coma o punto y coma (el Excel en castellano guarda con «;»).
- **El control de saldos sin la columna `cuentas_banco`** (si Valen carga los saldos antes de
  la migración) deduce las cuentas del banco de las líneas importadas. Así no puede decir cuál
  falta, pero compara igual.
- **Una línea del banco que dice «mercado pago» ya no va al lote MeLi**: es un pase a la
  billetera y se empareja como traspaso. Las compras de Mercado Libre se siguen reconociendo
  por «mercado libre», «mercadolibre» o «merpago».
- **Las líneas «COMPRA-VENTA DOLARES» nunca van a un lote**: o son el par de un traspaso o una
  ficha. Para emparejarlas, el tc tiene que ser plausible (entre 50 y 100.000).
- **`importado_ts` en hora argentina** (antes, la del servidor, UTC). Lo necesitaba
  `estado.ultima_importacion`, que se publica con `-03:00`.
- **Los totales de arriba de `resumen`** son ahora Banco + Mercado Pago (todo lo que está en
  pesos y concilia). Por cuenta siguen apareciendo por separado.

### Cambios de contrato (aditivos, cruzados con la sesión del gateway)

- `GET /conciliar/estado`: cada fuente suma `rotulo`. Los rótulos de las dos CA $ llevan el
  número («CA $ 273», «CA $ 48») para distinguirlas. El gateway alineó sus ejemplos, que
  usaban «CA $», en su commit `6f30fda`.
- `tipo_cambio` llega tal cual lo escribió el usuario y se lee con `numero()`: «1.450,50» →
  1450,5. Si vale ≤ 1 o no es un número, devuelve 422.
- `POST /vistas/recalcular` acepta `{"simulacro": true}` → `{"simulacro": true, "escribiria":
  {hoja: filas}}`. Lo usa solo el cron; el gateway no lo llama.

### La métrica de siempre

Gratis (`test_corpus --sin-llm --historia`), con la historia bajada hoy de los dos libros (la
del 9/10 ya no estaba): **antes (`64313c8`) y después, idénticas**, también en el JSON
completo. Nada de esta tirada toca `/interpretar`.

| | Antes = después |
|---|---|
| Obra/destino sin preguntar | 38/50 (76 %) |
| Con las preguntas de diseño | 45/50 (90 %) · 1 dual + 6 apodos |
| Preguntas por movimiento | 1,54 (cero preguntas: 1/54) |
| Con obra + contratista + comprobante | 1,11 (cero preguntas: 0/19) |
| Invariante | 0 de 59 |

El caso obligatorio «Austral/Sofi» falla **antes y después**: espera una pregunta de
clasificación que se sacó a propósito el 15/10 (las dos Sofía). El caso quedó viejo y no lo
toqué porque el rubro de Sofía Cervera sigue abierto.

**Con los comprobantes** (`--adjuntos --historia`, una sola corrida, la autorizada): **USD
0,225**. Fueron 24 lecturas de comprobantes y 6 llamadas de tokens; la caché local no tenía
ninguno de estos archivos. Es el número real de preguntas del bot con comprobante:

| | 9/10 (última con adjuntos) | Hoy |
|---|---|---|
| Preguntas por movimiento | 0,98 | **0,87** · cero preguntas 24/54 (44 %) |
| Con obra + contratista + comprobante | 0,45 · 65 % sin preguntas | **0,30** · **15/20 (75 %)** sin preguntas |
| Obra/destino sin preguntar | — | 45/50 (90 %) |
| Obra y contratista sin preguntar | — | 39/50 (78 %); con las de diseño, 45/50 (90 %) |
| Qué se pregunta | — | importe 16, etapa 13, contratista 6, obra 6, rubro 4, tc 1, clasificación 1 |
| Invariante | 0 | 0 de 59 |

La mejora contra el 9/10 viene de lo del 15/10 (las Sofía, «Es nuevo», el tc del recibo) y de
una historia más larga (30 movimientos del estudio), no de esta tirada, que no toca
`/interpretar`. La corrida termina con código 1 solo por el caso «Austral/Sofi» de arriba.

### Deploy, en orden (Valen; motor)

1. **Push** de `fachado-core` (los commits de M1 a M5) → Railway despliega `web` →
   `curl.exe <URL>/salud`.
2. **Las columnas**: primero `python scripts/preparar_sheet.py` (simulacro). Tiene que dar
   `CUENTAS!I1 cuentas_banco` y `BANCO_RAW!R1 origen`, más lo del 15/10 si todavía no se
   aplicó. Después, con `--aplicar`.
3. **Las cuentas de la conciliación**: primero
   `python scripts/migraciones/2026_10_20_cuentas_conciliacion.py` (simulacro). Pone las cuentas
   del banco de Banco, Banco USD y Mercado Pago, y Mercado Pago pasa a concilia = SÍ. Después,
   con `--aplicar`; después, `POST /maestros/recargar`.
4. **Las CC_**: primero `python scripts/crear_cc_obras.py` (simulacro: 13 en el Master y 4 en el
   personal), después con `--aplicar`. Necesita `FACHADO_PERSONAL_SHEET_ID` en el entorno.
5. **El cron de vistas**: los pasos en `docs/handoff-fachado-core.md` §5. Primero
   `python scripts/recalcular_vistas.py --simulacro` desde la PC y después la corrida de
   verdad; tienen que aparecer `VISTA_GENERAL` y `VISTA_OBRAS_MES`.
6. **Looker Studio** con `docs/tablero-looker.md`.
7. **El 1/11**:
   - Gabriel y Petrus completan `docs/saldos-apertura-31-10.csv`;
   - Valen corre `python scripts/cargar_saldos_apertura.py --csv docs/saldos-apertura-31-10.csv`,
     mira el control contra el banco y después corre con `--aplicar`;
   - Petrus manda los extractos de octubre (entran `ANTERIOR`, que es lo que da el saldo del
     banco al 31/10 para el control) y después los de noviembre.

**No** bajar `CONCILIACION_DESDE` en Railway para probar (ver el 15/10).

## Para Valen

- **CONTEXTO v1.11**: el del repo está incompleto (el encabezado dice 1.10 y §5.20 no tiene lo
  de esta semana). Subí la versión completa; las dos sesiones trabajaron con el handoff.
- **Muestra de Mercado Pago**: dejala en `Archivos Muestra/Muestra 3/`. Hay que correr
  `test_conciliar` y, si no la lee, ajustar `leer_mercado_pago`: el formato es armado.
- **Orden de los scripts**: `preparar_sheet` → migración del 20/10 → `/maestros/recargar` →
  `crear_cc_obras`. Al revés, la migración frena con «correr antes preparar_sheet».
- **`al_dia` de `/conciliar/estado`**: cuenta las líneas con fecha en la semana (§3). Una
  cuenta sin movimientos en la semana (la CA $ 48 se usa poco) va a figurar como faltante
  aunque Petrus mande el extracto. Hay que confirmar con Petrus si es así o si alcanza con que
  lo haya mandado.
- **Ingresos de una obra**: incluyen lo que pagó directo el comitente (además de S5), por
  §5.9. Confirmalo con Gabriel el jueves junto con S5.
- **Plantilla de saldos**: Chequera quedó afuera. Si tiene cheques emitidos sin debitar al
  31/10, ¿lleva saldo de apertura?
- **Elias Rodriguez** tiene rubro habitual `Zinguería › Zinguería`, que no está en RUBROS
  (¿`Materiales › Zinguería`?). El motor lo avisa y no lo usa: corregirlo en CONTRATISTAS.
- **El caso «Austral/Sofi» de la métrica** espera una pregunta que ya no se hace (desde el
  15/10). Actualizarlo cuando se decida el rubro de Sofía Cervera.
- **Semáforo gris**: Jardín Maternal (cerrada) sale siempre gris, igual que en VISTA_OBRAS.
  Decidí si una obra cerrada tiene que quedar fuera del conteo de la visión general.
- **MeLi y Mercado Pago**: las líneas del banco que dicen «mercado pago» ahora son pases a la
  billetera y no compras de MeLi. Con el primer extracto real, revisá que ninguna compra de
  MeLi caiga ahí.
- **El push**: M1 a M5 están commiteados en `main` sin pushear (6 commits después de
  `64313c8`, más el de este resultado).
