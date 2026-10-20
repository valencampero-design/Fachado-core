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
