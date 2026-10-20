# El tablero en Looker Studio — guía paso a paso

> Para Valen. CONTEXTO-FACHADO.md §5.21 (v1.11, lo que pidió Gabriel). Reescrita el 20/10.
> El motor deja los datos en hojas `VISTA_*` del Master (y `VISTA_PERSONAL` en «FACHADO —
> Personal»), que se recalculan solas cada noche. El tablero **solo lee esas hojas**: nunca
> MOVIMIENTOS. **Sin presupuestos** (etapa posterior). Pensado para el **celular de Gabriel**:
> lo primero que ve es la visión general, en una columna de 400 px de ancho.

El informe del estudio tiene tres páginas: **Visión general**, **Por obra** y **Proveedores**.
El personal va en un informe aparte.

---

## 0 · Antes de empezar

1. Que existan las hojas. En el Master: `VISTA_GENERAL`, `VISTA_SALDOS`, `VISTA_OBRAS`,
   `VISTA_OBRAS_MES`, `VISTA_RUBROS`, `VISTA_PROVEEDORES` y `VISTA_DETALLE`. En el libro
   personal: `VISTA_PERSONAL`.
   - Si no están, las escribe una corrida de `python scripts/recalcular_vistas.py`, con
     `MOTOR_URL` y `MOTOR_API_KEY` en el entorno.
   - Para ver antes qué escribiría, sin escribir nada, agregá `--simulacro`.
2. El cron nocturno creado en Railway. Los pasos están en `docs/handoff-fachado-core.md`, en
   «El cron de las vistas». Sin el cron, las hojas quedan como estaban el día que las
   escribiste.
3. Entrá a <https://lookerstudio.google.com> con la cuenta que tiene acceso al Master.

## 1 · Las fuentes de datos (una por hoja)

Una «fuente de datos» es la conexión de Looker con **una** hoja. Se crea una por cada hoja de
la lista. Para cada una:

1. Arriba a la izquierda, clic en **Crear** y después en **Fuente de datos**.
2. En la lista de conectores, clic en **Hojas de cálculo de Google**.
3. En la columna del medio, elegí el **Master**. A la derecha, elegí **la hoja**
   (`VISTA_GENERAL`, por ejemplo).
4. Dejá tildado **«Usar la primera fila como encabezados»**.
5. Arriba a la derecha, clic en **Conectar**.
6. Aparece la lista de campos. En la columna **Tipo**, revisá que cada campo quede como dice la
   tabla de abajo (clic en el tipo para cambiarlo).
7. Arriba a la izquierda, cambiá el nombre de la fuente por el de la hoja.
8. Cerrá la pestaña de la fuente.

Repetí los ocho pasos con cada hoja.

| Fuente | Campo | Tipo | Agregación |
|---|---|---|---|
| **VISTA_GENERAL** | `fecha` | Fecha | — |
| | `es_hoy`, `obras_en_rojo_lista`, `obras_en_gris_lista`, `ultimo_extracto` | Texto | — |
| | `saldo_banco`, `saldo_mercado_pago`, `saldo_efectivo`, `cajas_obra_ars`, `ingresos_mes`, `pagos_mes`, `capital_propio_inmovilizado`, `diferencia_libro_banco_ars` | Moneda (ARS) | Suma |
| | `saldo_banco_usd`, `cajas_obra_usd`, `diferencia_libro_banco_usd` | Moneda (USD) | Suma |
| | `obras_en_rojo`, `obras_en_gris` | Número | Suma |
| **VISTA_OBRAS_MES** | `obra`, `mes` | Texto | — |
| | `mes_fecha` | Fecha | — |
| | `aportes_comitente`, `honorarios_cobrados`, `pagado_directo_por_el_comitente`, `ingresos`, `pagos`, `saldo_mes`, `saldo_acumulado` | Moneda (ARS) | Suma |
| | `ingresos_usd_sin_convertir`, `pagos_usd_sin_convertir`, `saldo_acumulado_usd_sin_convertir` | Moneda (USD) | Suma |
| **VISTA_SALDOS** | `fecha` | Fecha | — |
| | `cuenta`, `tipo_cuenta`, `moneda`, `es_caja_de_obra` | Texto | — |
| | `movido_en_el_dia` | Número | Suma |
| | `saldo` | Número | **Promedio** (nunca Suma: sumaría saldos de días distintos) |
| **VISTA_OBRAS** | `obra`, `tipo`, `servicio`, `comitente`, `caja_moneda`, `semaforo`, `lleva_cc` | Texto | — |
| | `aportes_comitente`, `pagado_con_plata_del_estudio`, `pagado_por_el_comitente`, `saldo`, `ejecutado_total_ars`, `ventas`, `capital_propio_inmovilizado` | Moneda (ARS) | Suma |
| | `caja_ingresado`, `caja_pagado`, `caja_por_rendir`, `ejecutado_usd_sin_convertir` | Número (pueden estar en dólares: la caja de Lennon) | Suma |
| | `ultimo_movimiento` | Fecha | — |
| **VISTA_RUBROS** | `mes`, `obra`, `rubro_1`, `rubro_2`, `tipo_gasto` | Texto | — |
| | `mes_fecha` | Fecha | — |
| | `importe_ars` | Moneda (ARS) | Suma |
| | `importe_usd_sin_convertir`, `cantidad` | Número | Suma |
| **VISTA_PROVEEDORES** | `mes`, `contratista`, `obra` | Texto | — |
| | `mes_fecha` | Fecha | — |
| | `importe_ars` | Moneda (ARS) | Suma |
| | `importe_usd_sin_convertir`, `cantidad_pagos` | Número | Suma |
| **VISTA_DETALLE** | `fecha` | Fecha | — |
| | `comprobante_url` | **URL** | — |
| | `importe_ars` | Moneda (ARS) | Suma |
| | `importe`, `tc` | Número | Suma |
| | el resto (`id_mov`, `mes`, `tipo`, `obra`, `etapa`, `contratista`, `item`, `rubro_*`, `tipo_gasto`, `cuenta`, `quien_pago`, `moneda`, `descripcion`, `cargado_por`, `estado_conc`) | Texto | — |

Tres reglas que valen para todas las fuentes:

- **`obra` es Texto en todas.** Así un solo selector de obra filtra todos los gráficos de la
  página, aunque vengan de fuentes distintas. Un selector filtra otra fuente cuando esa fuente
  tiene un campo con el **mismo nombre y el mismo tipo**. El motor ya los escribe iguales:
  nunca le cambies el nombre a `obra` en una fuente. Lo que no tiene obra dice «Sin obra».
- **Para los gráficos por mes, usá `mes_fecha`** (es una fecha: el primer día del mes). `mes`
  («2026-10») queda como texto, para las tablas.
- **Pesos y dólares nunca se suman.** Lo que está en dólares sin convertir va en columnas
  aparte (`*_usd_*`), en sus propias tarjetas.

## 2 · El informe del estudio

1. Clic en **Crear** y después en **Informe**.
2. Te pide una fuente: elegí **VISTA_GENERAL** (pestaña «Mis fuentes de datos») y clic en
   **Agregar**. Si pregunta, clic en **Agregar al informe**.
3. Agregá las demás fuentes del estudio: menú **Recurso**, después **Administrar las fuentes
   de datos agregadas**, **Agregar una fuente de datos**, pestaña «Mis fuentes de datos», una
   por una. **Nunca agregues `VISTA_PERSONAL`** a este informe.
4. **El tamaño de la página, para el celular**:
   - menú **Tema y diseño** (arriba, en la barra);
   - pestaña **Diseño**;
   - en **Tamaño del lienzo**, elegí **Personalizado**, con **ancho 400** y alto 2000;
   - el alto se ajusta después, cuando la página esté completa.

   Todo va en una sola columna, un elemento debajo del otro. Si al crear el informe Looker
   ofrece un **«Diseño adaptable»**, elegilo: hace lo mismo solo.
5. Arriba a la izquierda, poné el nombre: «Fachado — Tablero».
6. Abajo de todo, agregá páginas con el menú **Página** y **Página nueva**, hasta tener tres.
   Para cambiarles el nombre: menú **Página**, **Administrar páginas**, los tres puntos al lado
   de cada una, **Cambiar nombre**. Los nombres: «Visión general», «Por obra» y «Proveedores».

Para agregar un gráfico: en la barra, clic en **Agregar un gráfico**, elegí el tipo y dibujalo
en la página. A la derecha aparece el panel con dos pestañas: **Configuración** (qué datos
muestra) y **Estilo** (cómo se ve). La fuente del gráfico se elige arriba de todo en
Configuración, en **Fuente de datos**.

### Página 1 · Visión general (lo primero que ve Gabriel)

Todo sale de **VISTA_GENERAL**. Hay una fila por día (los últimos 90). Las tarjetas muestran
**la de hoy**: cada tarjeta lleva el filtro `es_hoy = sí`. Ese filtro se crea **una vez**:

1. Seleccioná la primera tarjeta. En Configuración, abajo de todo, clic en **Agregar un
   filtro** y después en **Crear un filtro**.
2. Nombre: «Hoy». Elegí **Incluir**, el campo `es_hoy`, la condición **Es igual a (=)** y el
   valor `sí`.
3. Clic en **Guardar**.

En las tarjetas siguientes, el mismo botón **Agregar un filtro** ya muestra «Hoy»: un clic.

1. **Saldo por cuenta.** Una **Tarjeta de resultados** (en Agregar un gráfico, «Tarjeta de
   resultados») por cada una, con su métrica y el filtro «Hoy», de arriba hacia abajo:
   - `saldo_banco` («Banco»);
   - `saldo_mercado_pago` («Mercado Pago»);
   - `saldo_efectivo` («Efectivo»);
   - `saldo_banco_usd` («Banco US$»).

   De a dos por fila entran en 400 px (cada tarjeta de unos 190 px de ancho). Para cambiar el
   título: pestaña Estilo, o doble clic en el nombre de la métrica en Configuración.
2. **Cajas de obra**, debajo y con otro color para que no se confundan con la plata del
   estudio, que no es: `cajas_obra_ars` y `cajas_obra_usd`.
3. **El mes**: tres tarjetas, `ingresos_mes`, `pagos_mes` y `capital_propio_inmovilizado`
   («Capital propio en obras»).
4. **Semáforo**: dos tarjetas, `obras_en_rojo` y `obras_en_gris`. Debajo, una **Tabla** con
   las dimensiones `obras_en_rojo_lista` y `obras_en_gris_lista`, sin métricas y con el filtro
   «Hoy». Para ver cuáles son, la tabla del semáforo (punto 6) lo muestra por obra.
5. **Diferencia contra el banco**: una tarjeta con `diferencia_libro_banco_ars`, filtro «Hoy».
   En Estilo, poné el **formato condicional** en rojo si es distinto de 0. Al lado, una tabla
   chica con `ultimo_extracto`: hasta qué día llegó el último extracto. Vacía quiere decir
   que todavía no se cargó el saldo de apertura de esa cuenta (eso se hace el 1/11 con
   `scripts/cargar_saldos_apertura.py`) o que no hay extracto.
6. **El semáforo por obra**: una **Tabla**, fuente **VISTA_OBRAS**, con:
   - dimensiones `obra` y `semaforo`;
   - métricas `capital_propio_inmovilizado` y `caja_por_rendir`;
   - dimensión `ultimo_movimiento`.

   Pestaña Estilo, **Formato condicional**, **Agregar**: si `semaforo` es igual a `rojo`,
   fondo rojo. Repetí con `gris` (fondo gris) y con `verde` (fondo verde).
   - Rojo: la caja de obra en negativo, o el estudio financiando una obra de terceros.
   - Gris: sin movimientos en 30 días.
7. **La evolución** (opcional, al final de la página): un **Gráfico de series temporales** de
   VISTA_GENERAL, con dimensión `fecha` y métricas `saldo_banco` y `saldo_mercado_pago`.
   Este **no** lleva el filtro «Hoy»: muestra los 90 días.

### Página 2 · Por obra

1. **El selector de obra**, arriba de todo:
   - **Agregar un control** y después **Lista desplegable**;
   - fuente **VISTA_OBRAS**, campo de control `obra`;
   - en Estilo, destildá «Selección múltiple», así se elige una obra por vez;
   - en Configuración, **Selección predeterminada**: `Lennon` (o la que Gabriel mire más).

   Como `obra` se llama igual en todas las fuentes, el selector filtra todos los gráficos de la
   página. Si alguno no se filtra, revisá en esa fuente que `obra` sea Texto y se llame igual.
2. **Lo pagado por rubro, en barras horizontales**: **Gráfico de barras** (el de barras
   acostadas; el de barras paradas se llama «Gráfico de columnas»):
   - fuente **VISTA_RUBROS**;
   - dimensión `rubro_2` (o `rubro_1` para ver más agrupado);
   - métrica `importe_ars`;
   - en Configuración, **Ordenar** por `importe_ars` descendente;
   - en Estilo, **10 barras**.

   Lo que no tiene rubro sale como «Sin rubro», nunca como una barra en blanco.
3. **Ingresos contra pagos, por mes**: **Gráfico combinado** (en Agregar un gráfico, dentro de
   «Gráfico de columnas»):
   - fuente **VISTA_OBRAS_MES**, dimensión `mes_fecha`;
   - métricas `ingresos`, `pagos` y `saldo_acumulado`, en ese orden;
   - **Ordenar** por `mes_fecha` ascendente.

   En la pestaña Estilo:
   - **Serie 1** (ingresos) y **Serie 2** (pagos): **Barras**;
   - **Serie 3** (saldo acumulado): **Línea**, eje **derecho**.

   Debajo, dos tarjetas con `ingresos_usd_sin_convertir` y `pagos_usd_sin_convertir` (lo que
   está en dólares sin convertir, aparte).
   - Los ingresos son los aportes del comitente, los honorarios cobrados y lo que el comitente
     pagó directo. Esto último cuenta de los dos lados: si no, Lennon aparecería con −$22
     millones, como si el estudio financiara la obra.
4. **Top de proveedores**: **Tabla**, fuente **VISTA_PROVEEDORES**:
   - dimensión `contratista`;
   - métricas `importe_ars` y `cantidad_pagos`;
   - Ordenar por `importe_ars` descendente;
   - en Estilo, **Filas por página: 10**.
5. **Detalle con el link al comprobante**: **Tabla**, fuente **VISTA_DETALLE**:
   - dimensiones `fecha`, `contratista`, `rubro_2`, `quien_pago`, `moneda` y `comprobante_url`;
   - métrica `importe`;
   - Ordenar por `fecha` descendente;
   - **Filas por página: 20**.

   En 400 px no entran más columnas. `comprobante_url` como tipo URL se ve como link. Para que
   diga «ver» en vez de la dirección:
   - **Agregar un campo** y **Agregar campo calculado**;
   - nombre «comprobante»;
   - fórmula `HYPERLINK(comprobante_url, "ver")`;
   - usá ese campo en la tabla.

### Página 3 · Proveedores

1. Un **Control de período** (Agregar un control, **Control de período**), con **Período
   predeterminado: Este año**. Filtra todo lo que tiene una fecha (`mes_fecha`).
2. Un **Lista desplegable** de `obra` (fuente VISTA_PROVEEDORES), con selección múltiple.
3. **Ranking**: **Tabla** de **VISTA_PROVEEDORES**:
   - dimensión `contratista`;
   - métricas `importe_ars` y `cantidad_pagos`;
   - Ordenar por `importe_ars` descendente.
4. **Evolución de lo pagado**: **Gráfico de series temporales**:
   - dimensión `mes_fecha`, métrica `importe_ars`;
   - arriba, un **Lista desplegable** de `contratista`.

   Muestra **lo pagado**, no precios unitarios: los comprobantes no traen cantidades (§5.21).

### Ver cómo queda en el celular

1. Arriba a la derecha, clic en **Ver**.
2. Abrí el link del informe en el celular, en el navegador o en la app de Looker Studio.

Si algo queda cortado, volvé a **Editar** y achicá el elemento, porque el lienzo mide 400 de
ancho. Para el alto, en **Tema y diseño**, pestaña **Diseño**, en **Tamaño del lienzo**,
ajustá el alto hasta que no quede espacio en blanco abajo.

## 3 · El personal, en un informe aparte

1. Una fuente nueva, igual que en el punto 1, desde **«FACHADO — Personal»**, hoja
   **`VISTA_PERSONAL`**:
   - `mes`, `rubro_1`, `rubro_2` y `destino`: Texto;
   - `importe_ars`: Moneda (ARS);
   - `cantidad`: Número.
2. **Crear** e **Informe**, con esa fuente. Mismo lienzo de 400 px. Nombre: «Fachado —
   Personal».
3. Tres gráficos:
   - un **Gráfico de barras** por `rubro_2`, métrica `importe_ars`;
   - una **Tabla** por `mes`;
   - una **Tabla** por `destino` (los inmuebles: Sur, Abucoque, Belelli, Gessel).
4. **Compartirlo solo con quien tiene `ve_personal`** (§5.13, §5.14). Nunca agregar esta
   fuente al informe del estudio.

Las cuentas corrientes de los inmuebles (`CC_SUR`, `CC_BELELLI`…) están en el libro personal,
como hojas: no hace falta ponerlas en el tablero.

## 4 · Compartir

- **Informe del estudio**: botón **Compartir** (arriba a la derecha) → agregar a Gabriel y a
  Petrus con «Lector».
- **Las fuentes de datos con las credenciales del propietario**: en cada fuente,
  **Credenciales de datos** → **Propietario**. Así el que mira no necesita acceso al Sheet.
- **Informe personal**: solo con Gabriel.

## 5 · Si algo no aparece

- **Una hoja `VISTA_*` vacía, vieja o que no existe.** Corré
  `python scripts/recalcular_vistas.py`. Si termina con «ERROR…», el mensaje dice por qué: el
  motor no contesta, tarda, la clave no coincide o el motor devolvió un error. Si el cron no
  corrió, mirá el log del servicio `vistas` en Railway.
- **Un campo nuevo en la hoja** (por ejemplo `mes_fecha`). Abrí la fuente de datos y hacé clic
  en **Actualizar campos**, abajo a la izquierda.
- **El selector de obra no filtra un gráfico.** En la fuente de ese gráfico, `obra` tiene que
  ser Texto y llamarse exactamente `obra`.
- **Las tarjetas de la visión general dan números enormes.** Les falta el filtro «Hoy»: sin el
  filtro suman los 90 días.
- **Números que no cierran con la planilla vieja.** Hay tres diferencias a propósito:
  - las vistas no cuentan los pares anulados (§5.19);
  - separan lo que pagó el comitente (§5.9);
  - llevan la caja de Lennon en dólares (§5.8).

  Las CC_<OBRA> usan la misma lógica.
