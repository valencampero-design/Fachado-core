# Revisión de los datos cargados — 28/10/2026

> Foto del Master «FACHADO — Gestión de Obras» al **28/10/2026**, leída en solo lectura con
> `app/sheets.py`. No se escribió nada en ninguna hoja.
>
> **El libro personal no se leyó**: `FACHADO_PERSONAL_SHEET_ID` está vacío en el `.env` local.
> Todo lo que diga «personal» sale de las líneas del cierre semanal que hay en el Master, de
> los handoffs y de BANCO_RAW. Los P-0000xx se citan de los handoffs, no se verificaron.
>
> Fuentes: MOVIMIENTOS, OBRAS, ETAPAS, CERTIFICADOS, CUENTAS, CONTRATISTAS, RUBROS, USUARIOS,
> BANCO_RAW, «Revisión GABI» y las VISTA_* (las recalculó el cron del 28/10); CONTEXTO v1.13,
> `handoff-fachado-core.md`, los handoffs del 9/10, 20/10, 21/10 y 27/10, `estado-2026-10-21.md`,
> `saldos-apertura-31-10.csv`, `maestros/mapa-rubros-2026-10-27.md` y `tests/corpus.csv`.

---

## Resumen

- **El Master tiene 32 movimientos**: 22 cargados por WhatsApp (Gabriel 15, Petrus 7) y 10 del
  cierre semanal. No hay ninguna anulación ni ningún movimiento conciliado.
- **Hace 7 días que no entra nada.** La última carga es M-000033 (21/10, 22:22). Desde el deploy
  del 22/10, que arreglaba las trabas del 20/10, no hay ni una carga por WhatsApp. Petrus no
  carga desde el 17/10.
- **Solo 5 de las 13 obras del Master tienen movimientos**: Lennon, Gonzalo, Moreno, Austral y
  Hua Huan. **8 están en 0**: Cerro Bayo, Lumaia, Muelle de piedra, Tonga, Moquehue, Grigera
  Galpón, Tres Cerros y Jardín Maternal (cerrada). Tampoco hay ningún ingreso de honorarios ni
  ningún certificado.
- **Faltan movimientos que el banco sí muestra.** Por ejemplo, Sofía Cervera ($ 657.685, 5/10),
  el cobro de Bosque de Lumas (US$ 5.772,39, 30/9: Lumaia), un crédito de $ 2.214.743,40 sin
  identificar (14/10) y una decena de transferencias a terceros. Tampoco entraron los cuatro
  movimientos de las capturas del 20/10.
- **Lennon y Moreno salen en rojo por cómo se cargaron, no porque el estudio esté
  financiándolas**:
  - Lennon: las correcciones del 9/10 siguen sin aplicar (pagos contra Efectivo/Banco en vez de
    «Pagado por el comitente» o la caja de obra);
  - Moreno: no tiene cargado ningún cobro de certificado.
- **Rubros**: de los 20 movimientos con rubro, 14 tienen un rubro viejo, ya inactivo (las vistas
  lo traducen), y 6 tienen uno de los 35 «a confirmar con Gabriel».
- **Para el 1/11** falta todo lo que tienen que hacer otros:
  - los saldos de apertura (el CSV tiene las 12 cuentas vacías);
  - los extractos del 17/10 en adelante (BANCO_RAW termina el 16/10);
  - el reporte real de Mercado Pago;
  - la semana 19–25/10 del cierre semanal: la agrega el cierre del 2/11.

---

## 1 · Panorama de MOVIMIENTOS

**32 filas, de M-000001 a M-000033.** Falta M-000014, un número reservado por un `/confirmar`
que falló el 9/10; es el mismo «M 0014» que Gabriel pidió eliminar ese día.

- **Fechas de los movimientos**: del 07/02/2026 al 21/10/2026.
- **Fechas de carga**: del 29/09 al 21/10.

| Mes (fecha del movimiento) | Movimientos |
|---|---|
| 2026-02 | 1 (M-000001, Luis Pereira · Lennon) |
| 2026-07 | 1 (M-000012, Elias Rodriguez · Lennon) |
| 2026-08 | 2 (M-000008 Miguel Soto · Lennon, M-000009 Maragaño · Moreno) |
| 2026-09 | 7 |
| 2026-10 | 21 |

**Por tipo y moneda**

| | Cantidad | Importe |
|---|---|---|
| EGRESO por WhatsApp (obra y estructura) | 20 | $ 19.017.760,59 |
| EGRESO del cierre semanal (lo personal pagado con cuentas del estudio) | 10 | $ 5.212.058,67 |
| INGRESO | 2 | $ 2.076.360 (M-000025, Lennon) y US$ 20.000 (M-000015, caja de Lennon) |
| En USD | 1 | M-000015 (sin tipo de cambio, como corresponde a la caja en dólares) |

No hay TRASPASO, PASANTE, contraasientos (`anula`/`vinculo` vacíos en las 32), certificados ni
movimientos `informal`.

**Por obra**

| Obra | Movs | Egresos | Ingresos | Último |
|---|---|---|---|---|
| (sin obra: cierre semanal personal) | 10 | $ 5.212.058,67 | — | 18/10 |
| Gonzalo | 8 | $ 807.454,52 | — | 21/10 |
| Lennon | 7 | $ 17.193.000 | $ 2.076.360 + US$ 20.000 | 13/10 |
| Moreno | 4 | $ 450.000 | — | 13/10 |
| Austral | 2 | $ 324.922 | — | 14/10 |
| Hua Huan | 1 | $ 242.384,07 | — | 15/10 |

**Por cuenta**

| Cuenta | Movs | Comentario |
|---|---|---|
| Banco | 22 | 15 de WhatsApp + 7 del cierre |
| Efectivo | 5 | 4 pagos de Lennon/Moreno con recibo + 1 cierre. Según el 9/10, los de Lennon no son del estudio |
| Mercado Pago | 4 | M-000022/23 (EPEN, pagados en realidad con débito del banco) + 2 cierres |
| Caja obra Lennon | 1 | El ingreso de US$ 20.000 |
| Banco USD, Chequera, Pagado por el comitente y 7 cajas de obra | **0** | Ver §3.6 |

**Otros cortes**

- **Por `cargado_por`**: Gabriel Fachado 15, Cierre semanal 10, Petrus 7. Nada cargado como
  `bot`.
- **Por `origen`**: WHATSAPP 22, CIERRE 10. Ninguna fila viene de un extracto: la conciliación
  arranca el 1/11 (`CONCILIACION_DESDE`).
- **Por `estado_conc`**: PENDIENTE 15 (todas en Banco), SOLO_CAJA 17. **CONCILIADO: 0.**
- **Por `tipo_gasto`**: obra 20, personal 10, estructura 2.
- **Por `medio_pago`** (las de WhatsApp): Transferencia 13, Efectivo 5, Tarjeta 3, Otro 1
  (M-000011, MODO).
- **Etapa**: los 10 movimientos de Lennon y Moreno llevan etapa 1. Ninguno va a «extras» ni a
  la 2.

---

## 2 · Obras: cuáles tienen movimientos y cuáles no

Se cruzó OBRAS (17 filas) con MOVIMIENTOS y VISTA_OBRAS. Las 4 obras personales viven en el
libro personal, que no se leyó.

| Obra | Tipo | Servicio | Comitente | Etapas | Movs | Último | Semáforo | Nota |
|---|---|---|---|---|---|---|---|---|
| Lennon | obra_terceros | administración | Lennon · paga directo | 3 (1 en curso) | 7 | 13/10 | 🔴 rojo | −$ 15,1 M de «capital propio»: la corrección del 9/10, sin aplicar |
| Moreno | obra_terceros | administración | Fernández Moreno · certificados | 3 (1 y extras en curso) | 4 | 13/10 | 🔴 rojo | Solo pagos; **ningún cobro de certificado**, y la caja de obra en 0 |
| Gonzalo | obra_propia | todo | El arquitecto | — | 8 | 21/10 | 🟢 verde | La más cargada |
| Hua Huan | obra_propia | todo | El arquitecto | — | 1 | 15/10 | 🟢 verde | Solo una factura de EPEN |
| Austral | estructura | — | — | — | 2 | 14/10 | 🟢 verde | M-000005 ($ 400 que eran US$ 400) y Pellegrini. Falta Sofía Cervera |
| **Cerro Bayo** | obra_terceros | proyecto y dirección | Cerro Bayo S.A. | — | **0** | — | ⚪ gris | Ningún honorario |
| **Lumaia** | obra_terceros | proyecto y dirección | Bosque de Lumas S.A. | — | **0** | — | ⚪ gris | **El banco muestra un cobro de US$ 5.772,39 el 30/9 que no está cargado** |
| **Muelle de piedra** | obra_terceros | proyecto y dirección | Consorcio | — | **0** | — | ⚪ gris | Ningún honorario |
| **Tonga** | obra_terceros | proyecto y dirección | Gastón Maggi | — | **0** | — | ⚪ gris | Ningún honorario |
| **Moquehue** | obra_terceros | todo | Alicia Marson | — | **0** | — | ⚪ gris | Ni costos ni ingresos |
| **Grigera Galpón** | obra_propia | todo | El arquitecto | — | **0** | — | ⚪ gris | — |
| **Tres Cerros** | obra_propia | todo | El arquitecto | — | **0** | — | ⚪ gris | — |
| **Jardín Maternal** | obra_terceros | administración | — | — | **0** | — | ⚪ gris | **Cerrada**: es esperable |
| Sur | personal | — | — | — | 0 en el Master | ? | — | Libro personal (no leído) |
| Abucoque | personal | — | — | — | 0 en el Master | ? | — | El 20/10 Gabriel mandó $ 50.000 (Natalia Livio): verificar si entró en el personal |
| Belelli | personal | todo | El arquitecto | — | 0 en el Master | ? | — | Edesur y Metrogas (P-000005, según el 9/10) |
| Gessel | personal | todo | El arquitecto | — | 0 en el Master | ? | — | Libro personal (no leído) |
| **Minas** | — | — | — | — | — | — | — | **No existe en OBRAS.** Es la obra nueva del 20/10 ($ 1.000.000): no se dio de alta |

**Sin ningún movimiento (8 en el Master):** Cerro Bayo, Lumaia, Muelle de piedra, Tonga,
Moquehue, Grigera Galpón, Tres Cerros y Jardín Maternal. VISTA_GENERAL las cuenta como «8 obras
en gris». Jardín Maternal está cerrada; si se saca del conteo, quedan 7.

**Con muy poco:**
- Hua Huan: 1 movimiento, una factura de servicio;
- Austral: 2, uno de ellos mal cargado;
- Moreno: 4 pagos y ningún ingreso.

**Lo que no hay en ninguna obra:** honorarios cobrados y certificados (CERTIFICADOS está vacía).
Por eso, en VISTA_OBRAS_MES, `honorarios_cobrados` da 0 en todas y Moreno no tiene
`aportes_comitente`.

---

## 3 · Calidad de lo cargado

### 3.1 Lo que está bien

- **20 de las 22 cargas por WhatsApp tienen comprobante** en Drive y `ref_comprobante`. Las
  dos que no:
  - M-000005: Valen, sin comprobante;
  - M-000015: el ingreso en dólares de Lennon, en efectivo.
- **Ningún egreso de obra sin contratista.** Los dos sin contratista son ingresos (M-000015,
  M-000025), como corresponde.
- **Sin rubro solo los dos ingresos**, que no lo necesitan.
- **Los 10 movimientos de Lennon y Moreno llevan etapa.**
- **No hay valores «null» ni filas corridas.** Las 33 columnas están alineadas.

### 3.2 Rubros

RUBROS tiene 170 filas: 144 activas (109 de la lista del estudio y 35 a confirmar) y 26
inactivas. En MOVIMIENTOS:

| Situación | Movs | Ejemplos |
|---|---|---|
| Rubro viejo, **inactivo** (las vistas lo traducen por `reemplazado_por`) | 14 | Mano de obra › Carpintero (M-000004, 09, 16, 19, 21) → 2.10; Mano de obra › Contratistas (M-000001, 08, 24, 32) → 2.1; Materiales › Albañilería (M-000010, 13) → 1.2; Mano de obra › Albañil (M-000020, 33) → 2.9; Jornales (M-000002); Zinguería (M-000012) |
| Rubro **a confirmar con Gabriel** | 6 | Servicios públicos › EPEN (M-000022, 23), › Camuzzi (M-000003); Impuestos y tasas › Municipales (M-000011); Honorarios › Asesores (M-000005) |
| Rubro de la lista nueva | 0 | Todo se cargó antes del 27/10 |

Hallazgos puntuales:

- **M-000024** (Pellegrini, Austral, `estructura`) tiene un rubro de obra (Mano de obra ›
  Contratistas, que pasa a «Contratista principal» en una obra de estructura). Es la falla 2 del
  20/10, de antes del fix. Hay que saber qué le hizo Pellegrini al estudio para elegir el rubro
  de Austral.
- **M-000010 y M-000013** (Miguel Soto, Lennon, $ 3.070.000 y $ 3.000.000) están como
  Materiales › Albañilería. El recibo de M-000010 dice «Certificado de obra» de un contratista:
  sería Mano de obra (pregunta 8 del 9/10, abierta).

### 3.3 Cuentas y monedas mal puestas (ya conocidas, sin corregir)

| id_mov | Qué tiene | Qué debería tener | Estado |
|---|---|---|---|
| M-000001, M-000008, M-000010 | Lennon, cuenta **Efectivo** ($ 13.640.000) | Caja obra Lennon o «Pagado por el comitente» (pregunta 1 del 9/10) | Script `2026_10_09_correcciones.py` sin aplicar |
| **M-000012, M-000013** | Lennon, cuenta **Banco**, PENDIENTE | Probablemente «Pagado por el comitente»: las operaciones `LR…` parecen del banco de Lennon (como su ingreso M-000025), y **M-000013 ($ 3.000.000, 9/10) no aparece en el extracto del estudio**, que llega hasta el 16/10 | **Nuevo**: confirmarlo con Gabriel |
| M-000005 | **$ 400** en Banco | **US$ 400** desde Banco USD (el extracto lo muestra el 5/10) | Pendiente del 9/10 (tc a confirmar) |
| M-000022, M-000023 | EPEN en **Mercado Pago**, SOLO_CAJA | Banco: son «COMPRAS PATAGONIA 24» del 13/10 en la CA $ 48 | Decidido en v1.12 para adelante; estos dos quedan así |
| M-000015 | US$ 20.000, descripción «Lennon me dio Para a , efectivo» | El adelanto a la caja de Lennon | Falta que Gabriel confirme el ingreso (`--con-ingreso-usd`) |

### 3.4 Contratistas

CONTRATISTAS tiene 85 filas: 78 activas, 4 inactivas y **3 sin estado** (Juanma, Volquete,
Sanos Sanitarios). **Se usan 12** en MOVIMIENTOS:

| Contratista | Movs |
|---|---|
| Marcelo Maragaño | 5 |
| Miguel Soto | 3 |
| Marcelo Orellana | 2 |
| Epen | 2 |
| Luis Pereira, Tucu, Camuzzi, Valentin Campero, Municipalidad, Elias Rodriguez, Maximiliano pelegrini, Sergio Coria | 1 cada uno |

**Duplicados o nombres parecidos:**

- **Exactos**:
  - «Maderera Misiones», 2 filas;
  - «Marcelo Maragaño», 2 filas (el motor las fusiona y lo avisa).
- **Misma persona con otro nombre**:
  - «Fabrica de calcos» y «Sergio González», que es «Fábrica de Calcos»: los dos activos;
  - «Silla Cuadruple» y «Silla Cuádruple»: los dos inactivos;
  - «Luis Pereyra» (inactivo) y «Luis Pereira».
- **Ortografía**: «Maximiliano pelegrini» en el maestro, «PELLEGRINI MAXIMILIANO» en el banco.
- **Para mirar**:
  - «Guillermo pintor» y «Guillermo Vazquez»;
  - «Ricardo Ramos» y «Roberto Ramos»;
  - «Albañiles», genérico;
  - «Estudio» y «Honorarios Arquitectura» cargados como contratistas.
- **«Tucu» (M-000002, $ 125.000, 30/9)**: en el extracto, esa transferencia del 30/9 va a
  **Orellana Marcelo**. ¿Tucu es Orellana, o se cargó mal el contratista?

**Rubro habitual:**

- 36 activos **sin rubro habitual**. Son casi los mismos 41 de «Revisión GABI», que sigue con
  las columnas «Rubro que corresponde» y «Sigue trabajando?» vacías.
- 22 tienen un habitual **a confirmar**. Dos están mal de origen:
  - **Edesur → Servicios públicos › Agua** (Edesur es luz);
  - **Rentas → Impuestos y tasas › Municipales** (Rentas es provincial).

### 3.5 Formato

- **`importe_ars`**: 29 con formato de moneda y 3 sin formato (M-000016 `100000`, M-000018
  `38667,3`, M-000015 vacío).
- **`tc`**: aparece como `1` o `1,00`.

No rompe las vistas, pero en el Sheet se ve desparejo.

### 3.6 Cuentas

- **Sin movimientos**:
  - Banco USD, aunque el extracto tiene 14 líneas y M-000005 debería estar ahí;
  - Chequera;
  - **Pagado por el comitente**, aunque Lennon «paga directo»;
  - las cajas de obra de Moreno, Cerro Bayo, Lumaia, Muelle de piedra, Tonga, Moquehue y
    Gonzalo.
- **«Caja obra Gonzalo» existe y está en el CSV de saldos**, pero Gonzalo es obra propia, y el
  contexto dice que las propias no tienen caja (§6 y handoff del 25/09). ¿Se borra del CSV o
  Gabriel la usa?
- **Ninguna cuenta tiene todavía `saldo_apertura` ni `fecha_apertura`**: todas en 0,00 y sin
  fecha. Es lo esperado hasta el 1/11.

### 3.7 Conciliación

- **BANCO_RAW** tiene 100 filas:
  - **99 líneas reales**, importadas el 17/10, todas `ANTERIOR`;
  - por cuenta: CA $ 48 71, CA $ 273 14, CA U$S 14;
  - **cubren del 21/09 al 16/10**;
  - más **la fila 2, de ejemplo** («(se calcula al importar)», PENDIENTE, sin cuenta), que
    conviene borrar a mano.
- **Ninguna línea tiene `id_mov`**: no hay nada conciliado, porque se concilia desde el 1/11.
- **Los 15 PENDIENTE contra el extracto** (cruce a mano, por importe, fecha y nombre):

| | Movs | Cuáles |
|---|---|---|
| Tienen su línea en el extracto | 10 | M-000002, 03, 04, 11, 16, 19, 20, 21, 24, 25 |
| La tienen, en otra moneda | 1 | M-000005 (es US$ 400) |
| Fuera del rango del extracto | 3 | M-000012 (13/7), M-000032 (20/10), M-000033 (21/10) |
| **Sin línea en el extracto** | 1 | **M-000013**: Lennon, $ 3.000.000 |

**Líneas del extracto, desde el 28/09 (el arranque del bot), que no están en el Master.** Algunas
pueden estar en el libro personal: hay que cruzarlas con él.

| Fecha | Importe | Contraparte | Lectura probable |
|---|---|---|---|
| 05/10 | $ 657.685 | Cervera de los Santos, Sofía | **Sueldo: estructura (Austral).** Ya figuraba como perdido el 9/10 (captura 8) |
| 30/09 | US$ 5.772,39 (crédito) | Bosque de Lumas S.A. | **Honorario de Lumaia** |
| 14/10 | $ 2.214.743,40 (crédito) | «Crédito por transferencia», sin nombre | ¿Un aporte o un honorario? A identificar |
| 28/09 | $ 314.768,98 | Claudio Casasola y Hno. | ¿Un proveedor de obra? |
| 29/09 | $ 500.000 | Cuevas Bustamante, Nelson | ? |
| 28/09 y 05/10 | $ 50.000 y $ 100.000 | Durando, Guillermo | ? |
| 02/10 | $ 119.000 | Belizan, Erika | ? |
| 16/10 | $ 120.000 | Breit, José Agustín | ? |
| 28/09 | $ 178.650 | Real, Mariana Valeria | ? |
| 01/10 | $ 29.040 | A Su Servicio SRL | ? |
| 05/10 | $ 10.000 | Cipreses del Sur SRL | ? |
| varias | — | En todo el extracto: First Data (7 líneas), Visa, MercadoLibre (14), compraventa de dólares (10 en pesos y 9 en dólares), Netflix, Claro, DPR Sellos, intereses | Lotes de la conciliación: tarjetas (P-34), MeLi, traspasos y gastos bancarios |
| varias | — | Familia: Sofía, Juan Manuel y Marcela | Personal: debería estar en el libro personal |

Las dos de $ 200.000 (14/10, a Marcela, y 16/10, a Alvarez) son P-000007 y P-000017, según el ensayo
del 21/10.

El ensayo de octubre del 21/10, con los dos libros, dio sobre 50 líneas:
- 13 conciliadas solas;
- 1 interna;
- 5 compraventas de dólares;
- 2 lotes;
- 2 con dos candidatos;
- 21 preguntas sueltas.

Es un buen termómetro de lo que el bot le va a preguntar a Petrus en noviembre si no se carga
antes.

---

## 4 · Lo que falta

| # | Qué | Evidencia en los datos | Responsable | Cuándo |
|---|---|---|---|---|
| 1 | **Completar los saldos al 31/10** en `docs/saldos-apertura-31-10.csv` | Las 12 cuentas con `saldo` vacío | Gabriel + Petrus | Antes del 1/11 |
| 2 | Decidir **Chequera** (¿cheques emitidos sin debitar?) y **Caja obra Gonzalo** (¿sobra?) | Chequera no está en el CSV; Gonzalo es obra propia | Gabriel | Antes del 1/11 |
| 3 | Correr `cargar_saldos_apertura.py`: simulacro y después `--aplicar` | `fecha_apertura` vacía en CUENTAS | Valen | 1/11 |
| 4 | **Extractos del 17/10 al 31/10** de las 3 cuentas del banco y, después, el primero de noviembre | BANCO_RAW termina el 16/10 | Petrus | Ya |
| 5 | **El reporte o PDF real de Mercado Pago** (`Archivos Muestra/Muestra 3/`, la carpeta todavía no existe) | El parser está hecho con un formato armado | Petrus → Valen | Antes del primer extracto de noviembre |
| 6 | **La semana 19–25/10 del cierre semanal** | No hay línea «2026-W43»: el cron del 26/10 dio 401 | Automático el 2/11 (o Valen: Railway → Run now) | 2/11 |
| 7 | **Las correcciones del 9/10**: Lennon (cuentas), M-000005 en US$, P-000001 y el ingreso de US$ 20.000 | `anula`/`vinculo` vacíos; Lennon en rojo con $ 15,1 M | Gabriel contesta, Valen aplica | Antes de compartir el tablero |
| 8 | **Cargar lo que no entró** (ver §3.7): Sofía Cervera, el honorario de Lumaia, el crédito del 14/10, el pago a Miguel de $ 708.400 (captura 2 del 9/10) y los cuatro del 20/10 (YPF $ 77.000 · Austral, Mathias Flores · Austral, Natalia Livio · Abucoque, Minas $ 1.000.000) | No están en el Master | Gabriel / Petrus (por el bot) | Antes del 1/11, o dejarlo al histórico (decisión del 9/10) |
| 9 | **Dar de alta la obra Minas** (por el bot, ya funciona) | No está en OBRAS | Gabriel | Con su próximo movimiento |
| 10 | **Los 35 rubros a confirmar** (tabla en `handoff-rubros-tablero-2026-10-27.md` y mapa en `docs/maestros/`) y las 2 equivalencias dudosas (Hormigón, Alquiler de equipos) | 6 movimientos y 22 contratistas los usan | Gabriel | Esta semana |
| 11 | **«Revisión GABI»**: rubro y si sigue trabajando, para 41 contratistas | Columnas vacías | Gabriel | Sin apuro |
| 12 | **Limpiar CONTRATISTAS**: duplicados, los 3 sin estado, Edesur y Rentas | §3.4 | Valen (en el maestro, nada se borra) | Después de 10 y 11 |
| 13 | **Certificados de Moreno** (4, 4 extras, pintura, 18 y 22 en el corpus de septiembre) y sus cobros a la caja de obra | CERTIFICADOS vacía; Moreno sin ingresos | Petrus / Gabriel | Cuando se cobre el próximo, o al ordenar el histórico |
| 14 | **Honorarios** de Cerro Bayo, Lumaia, Muelle de piedra y Tonga | 0 movimientos en las cuatro | Gabriel | Con cada cobro |
| 15 | **Cajas de obra**: ¿hay plata de comitentes en poder del estudio (Moreno, Moquehue…)? | 7 cajas en 0 | Gabriel | Con los saldos (punto 1) |
| 16 | Borrar a mano la **fila 2 de ejemplo de BANCO_RAW** | Fila PENDIENTE sin cuenta | Valen | Antes del 1/11 |
| 17 | **Compartir el tablero** (estudio con Gabriel y Petrus, personal solo con Gabriel) y sumar la tarjeta de diferencia contra el banco | Informes sin compartir; columnas `diferencia_*` vacías | Valen | Después de 7 y del 1/11 |
| 18 | **Decisiones abiertas**: S1–S5; ingresos con lo que paga directo el comitente; `al_dia` del pedido semanal; tarjetas de crédito (P-34: First Data y Visa); transferencias a MercadoLibre (¿carga de saldo de MP?); DPR Sellos; rubro de Sofía Cervera; «Servicios» personal; combustible de obra; obras cerradas en el conteo de «gris» | Handoffs del 20/10, 21/10 y 27/10 | Gabriel + Petrus (reunión) | Antes del 1/11 |
| 19 | El hueco de **M-000014** | No existe en MOVIMIENTOS | Valen (log del gateway del 9/10) | Sin apuro |
| 20 | **Presupuesto de obra contra ejecutado y cuentas por pagar** | Fuera del alcance: etapa futura, a presupuestar aparte (§8) | Valen (propuesta) | Después de noviembre |
| 21 | **IVA** (§5.10) | No empezado | — | Se planifica aparte |

---

## 5 · Patrones de uso

**Quién carga y cuándo** (por fecha de carga, semanas ISO):

| Semana | Gabriel | Petrus | Cierre semanal |
|---|---|---|---|
| 29/09–04/10 (W40) | 5 | — | — |
| 05/10–11/10 (W41) | 7 | 1 | 2 |
| 12/10–18/10 (W42) | 1 | 6 | 2 |
| 19/10–25/10 (W43) | 2 | — | 6 (puesta al día de W36–W42) |
| 26/10–28/10 (W44) | **0** | **0** | 0 (falló el 26/10) |

- **Promedio**: unas 7 cargas por WhatsApp por semana, en 10 días distintos. **Cayó a 2 la
  semana del 20/10 y a 0 desde el 22/10.** La caída coincide con las trabas del 20/10 y con la
  caída de Railway del 21/10. Después del deploy del 22/10 nadie volvió a probar.
- **Reparto**:
  - Gabriel carga sobre todo **Gonzalo** (7 de sus 15) y pagos viejos de Lennon;
  - Petrus carga **Lennon, Moreno, EPEN y Austral**, todos del 9/10 al 17/10.
- **Carga atrasada**: más de la mitad entra en el día (12 de 22), pero 7 se cargaron **más de 10 días
  después**:
  - M-000001, a 234 días;
  - M-000012, a 88;
  - M-000008, a 63;
  - M-000009, a 47;
  - M-000020, M-000019 y M-000015, entre 11 y 17.

  Gabriel usa el bot también para ir subiendo recibos viejos de Lennon.
- **Cómo escriben**: el patrón es **«Destino/Contratista» o «Contratista/Destino» más el
  comprobante**. En el corpus de septiembre son 47 de 58 textos («Miguel/Lennon»,
  «Retiro/club/cuota 4 esquí», «Ingreso Moreno/cert. 22»). La `descripcion` de MOVIMIENTOS casi
  siempre es el número de operación del comprobante («Op. …»). La única con texto libre es
  M-000015.
- **Comprobantes**:
  - mayoría de transferencias (13), recibos manuscritos en efectivo (4) y pagos de servicios
    por tarjeta, MP o MODO (4);
  - el 91 % de las cargas trae comprobante.

**Fallas típicas del bot** registradas en los handoffs:

| Falla | Cuándo | Estado |
|---|---|---|
| Demasiadas preguntas: 4–5 por movimiento, importe aunque hubiera comprobante, obra aunque el texto la nombrara | Semana 1 (29/09–8/10) | Corregido el 9/10: 1,22 → 0,98 preguntas por movimiento. Con la historia del 20/10 da **1,56** |
| «¿A qué obra?» en un gasto personal («Retiro/Sofi», «Retiro/Abucoque») | 29/09 y 20/10 | Corregido (v1.8 y v1.12) |
| Rubros de obra ofrecidos en Austral; sin Combustible ni Gastos generales | 20/10 | Corregido el 22/10 y con la lista del estudio el 27/10 |
| Un comprobante nuevo tomado como respuesta a la pregunta anterior, con importes pisados (Minas → Abucoque) | 9/10 y 20/10 | Corregido en el gateway (G1, 21/10) |
| Un «4» suelto mandado como mensaje nuevo | 20/10 | Corregido |
| Bucles de tipo de cambio («Lo dejamos en dólares» → «No entendí») | 9/10 | Corregido |
| Pregunta duplicada; US$ mostrado como $ | 9/10 | Corregido |
| Rubro mal inferido: Edesur como Agua; Miguel Soto como Materiales; Pellegrini con rubro de obra en Austral | 9/10–17/10 | Los datos siguen así (§3) |
| **Movimientos perdidos en las trabas**: US$ 20.000 de Lennon (después entró), Sofía Cervera, Miguel $ 708.400 y los cuatro del 20/10 | 29/09–20/10 | **Siguen faltando** |

Lo que no se pudo probar en producción (27/10) se va a ver la primera vez que carguen:
- el ticket de YPF como foto;
- la mezcla de comprobantes en el gateway.

---

## 6 · Preguntas abiertas para Gabriel

1. **¿Por qué no se cargó nada desde el 21/10?** ¿Volvieron a trabarse, esperaban el aviso de
   que estaba arreglado, o pagaron poco? Si hubo pagos, conviene cargarlos antes del 1/11.
2. **Lennon**: ¿los pagos a Miguel Soto, Luis Pereira y Elías (M-000001, 08, 10, 12, 13) los
   pagaste vos, de la caja de Lennon, o los pagó Lennon directo? M-000013 ($ 3.000.000) no está
   en el extracto del estudio. ¿Confirmás el ingreso de US$ 20.000 del 28/09?
3. **Moreno**: ¿qué certificados se cobraron desde septiembre (4, 4 extras, pintura, 18, 22…),
   cuándo y a qué caja?
4. **Lumaia**: los US$ 5.772,39 de Bosque de Lumas del 30/9, ¿son honorarios? ¿Y los
   $ 2.214.743,40 del 14/10, de quién son?
5. **Cerro Bayo, Muelle de piedra, Tonga y Moquehue**: ¿cobraste honorarios este año? ¿Moquehue
   («todo») tiene costos que el estudio pague?
6. **Grigera Galpón y Tres Cerros**: ¿están paradas o hubo gastos que no se cargaron?
7. **Sofía Cervera**: ¿el pago de $ 657.685 del 5/10 es su sueldo de octubre? ¿Va como Sueldos
   fijos de Austral?
8. **Las transferencias sin identificar**: Casasola, Cuevas Bustamante, Durando, Belizan,
   Breit, Real y A Su Servicio. ¿Qué son y de qué obra?
9. **Pellegrini** (M-000024, Austral): ¿qué trabajo hizo para el estudio?
10. **Tucu** (M-000002): el banco dice que la transferencia fue a Orellana. ¿Tucu es Marcelo
    Orellana?
11. **Caja obra Gonzalo**: ¿la usás? Si no, sale del CSV de saldos. ¿Y Chequera: tenés cheques
    sin debitar al 31/10?
12. **Los 35 rubros a confirmar**, empezando por los que ya se usan: EPEN, Camuzzi y Municipales
    en una obra, y Honorarios › Asesores (Valen).
13. **Minas**: ¿es una obra nueva? Tipo, servicio y comitente.
14. **Jardín Maternal**: ¿la dejamos fuera del conteo de obras «en gris» del tablero?
