# El tablero en Looker Studio — guía paso a paso

> Para Valen. CONTEXTO-FACHADO.md §5.21. El motor deja los datos en hojas `VISTA_*` del Master
> (y `VISTA_PERSONAL` en «FACHADO — Personal»), que se recalculan solas cada noche. El tablero
> **solo lee esas hojas**: nunca MOVIMIENTOS. **Sin presupuestos** (etapa posterior).

## 0 · Antes de empezar

1. El motor desplegado con M3 y la primera corrida de `POST /vistas/recalcular` hecha (o
   `python scripts/recalcular_vistas.py` con `MOTOR_URL` y `MOTOR_API_KEY`). Tienen que
   existir en el Master: `VISTA_SALDOS`, `VISTA_OBRAS`, `VISTA_RUBROS`, `VISTA_PROVEEDORES`,
   `VISTA_DETALLE`; y en el libro personal, `VISTA_PERSONAL`.
2. El cron nocturno creado en Railway (ver el handoff técnico, «Cron de vistas»).
3. Entrar a <https://lookerstudio.google.com> con la cuenta que tiene acceso al Master.

## 1 · Las fuentes de datos (una por hoja)

Para cada hoja: **Crear → Fuente de datos → Hojas de cálculo de Google → Master → la hoja →**
«Usar la primera fila como encabezados» tildado → **Conectar**. Revisar los tipos y dejarlos
así (en la pantalla de campos, columna «Tipo»):

| Fuente | Campo | Tipo | Agregación |
|---|---|---|---|
| **VISTA_SALDOS** | `fecha` | Fecha (AAAAMMDD) | — |
| | `cuenta`, `tipo_cuenta`, `moneda`, `es_caja_de_obra` | Texto | — |
| | `movido_en_el_dia`, `saldo` | Número | Suma para `movido_en_el_dia`; **Promedio** para `saldo` (ver nota) |
| **VISTA_OBRAS** | `obra`, `tipo`, `servicio`, `comitente`, `caja_moneda`, `semaforo`, `lleva_cc` | Texto | — |
| | `aportes_comitente`, `pagado_con_plata_del_estudio`, `pagado_por_el_comitente`, `saldo`, `caja_ingresado`, `caja_pagado`, `caja_por_rendir`, `ejecutado_total_ars`, `ejecutado_usd_sin_convertir`, `ventas`, `capital_propio_inmovilizado` | Moneda (ARS) — **`caja_*` y `ejecutado_usd_sin_convertir` como Número** (pueden estar en dólares) | Suma |
| | `ultimo_movimiento` | Fecha | — |
| **VISTA_RUBROS** | `mes` | Fecha (AAAAMM) | — |
| | `obra`, `rubro_1`, `rubro_2`, `tipo_gasto` | Texto | — |
| | `importe_ars` | Moneda (ARS) | Suma |
| | `importe_usd_sin_convertir`, `cantidad` | Número | Suma |
| **VISTA_PROVEEDORES** | `mes` | Fecha (AAAAMM) | — |
| | `contratista`, `obra` | Texto | — |
| | `importe_ars` | Moneda (ARS) | Suma |
| | `importe_usd_sin_convertir`, `cantidad_pagos` | Número | Suma |
| **VISTA_DETALLE** | `fecha` | Fecha | — |
| | `mes` | Fecha (AAAAMM) | — |
| | `comprobante_url` | **URL** | — |
| | `importe`, `importe_ars`, `tc` | Número / Moneda (ARS) para `importe_ars` | Suma |
| | el resto (`id_mov`, `tipo`, `obra`, `etapa`, `contratista`, `rubro_*`, `cuenta`, `quien_pago`, `moneda`, `descripcion`, `cargado_por`, `estado_conc`) | Texto | — |

**Nota sobre los saldos**: `VISTA_SALDOS` trae una fila por cuenta y por día con un
movimiento, con el saldo acumulado a ese día. Como hay una sola fila por cuenta y día, usá
`saldo` con agregación **Promedio** (nunca Suma: sumaría saldos de días distintos). Para la
evolución, una serie temporal (dimensión `fecha`, desglose `cuenta`). Para «el saldo de hoy»,
una tabla con dimensión `cuenta` y `fecha`, ordenada por `fecha` descendente: la primera fila
de cada cuenta es la última conocida. Las cajas de obra en dólares tienen `moneda = USD`:
van en un gráfico aparte (filtro `es_caja_de_obra = sí`), nunca sumadas con los pesos.

**El link al comprobante**: en `VISTA_DETALLE`, `comprobante_url` como tipo **URL**; en la
tabla, el campo se ve como link. Si querés un texto fijo: campo calculado
`HYPERLINK(comprobante_url, "ver")`.

## 2 · El informe: tres páginas (§5.21) + el personal aparte

**Crear → Informe** y agregar las fuentes de arriba. Tema claro, una columna en el celular
(Archivo → Configuración del informe → «Diseño adaptable»).

### Página 1 · Consolidado

1. **Saldo de caja por cuenta**: serie temporal de `VISTA_SALDOS` (dimensión `fecha`,
   desglose `cuenta`, métrica `saldo` Promedio), filtro `es_caja_de_obra = no`. Al lado, la
   tabla «saldo de hoy» de la nota de arriba.
2. **Resultado del mes por rubro**: barras de `VISTA_RUBROS`, dimensión `rubro_1`, métrica
   `importe_ars`, control de período sobre `mes` (por defecto, mes actual). Filtro
   `tipo_gasto ≠ personal` (lo personal del Master es solo la línea semanal).
3. **Semáforo de obras**: tabla de `VISTA_OBRAS` con `obra`, `semaforo`,
   `capital_propio_inmovilizado`, `caja_por_rendir`, `caja_moneda`, `ultimo_movimiento`.
   Formato condicional sobre `semaforo`: `rojo` fondo rojo, `gris` gris, `verde` verde.
   Leyenda: rojo = caja de obra en negativo o el estudio financiando la obra; gris = sin
   movimientos en 30 días.

### Página 2 · Por obra

Un **control de lista desplegable** sobre `obra` (fuente `VISTA_DETALLE`, que filtra todas las
fuentes con campo `obra`: en Looker, «Filtros entre fuentes»/campo común `obra`).

1. **Ejecución por rubro**: barras apiladas de `VISTA_RUBROS` (dimensión `mes`, desglose
   `rubro_1`, métrica `importe_ars`).
2. **Aportes del comitente contra egresos**: cuadros de resultados de `VISTA_OBRAS`:
   `aportes_comitente`, `pagado_con_plata_del_estudio`, `pagado_por_el_comitente`,
   `ejecutado_total_ars`, `caja_por_rendir` (+ `caja_moneda` al lado: la caja de Lennon está
   en dólares).
3. **Top de proveedores**: tabla de `VISTA_PROVEEDORES`, dimensión `contratista`, métricas
   `importe_ars` y `cantidad_pagos`, orden descendente, 10 filas.
4. **Detalle con link al comprobante**: tabla de `VISTA_DETALLE` con `fecha`, `id_mov`,
   `etapa`, `contratista`, `rubro_2`, `quien_pago`, `importe`, `moneda`, `comprobante_url`,
   orden por `fecha` descendente, 50 filas por página.

### Página 3 · Proveedores

1. **Ranking por volumen**: tabla de `VISTA_PROVEEDORES` (dimensión `contratista`, métricas
   `importe_ars`, `cantidad_pagos`), con control de período sobre `mes` y control de `obra`.
2. **Evolución de lo pagado**: serie temporal (dimensión `mes`, métrica `importe_ars`), con
   control de `contratista`. La propuesta habla de «evolución de precios»: sin cantidades en
   los comprobantes, se muestra **lo pagado**, no precios unitarios (§5.21).

### El personal, en un informe aparte

Fuente nueva desde **«FACHADO — Personal» → `VISTA_PERSONAL`** (`mes` Fecha AAAAMM; `rubro_1`,
`rubro_2`, `destino` Texto; `importe_ars` Moneda; `cantidad` Número). Un informe propio con:
barras por `rubro_2` del mes, serie temporal por `mes`, tabla por `destino` (los inmuebles:
Belelli, Sur, Abucoque, Gessel). **Compartirlo solo con quien tiene `ve_personal`** (§5.13,
§5.14). Nunca agregar esta fuente al informe del estudio.

## 3 · Compartir

- Informe del estudio: Compartir → con Gabriel y Petrus, «Puede ver». Las fuentes de datos con
  **credenciales del propietario** (Valen), para que el que mira no necesite acceso al Sheet.
- Informe personal: solo con Gabriel.
- Desde el celular: abrir el link en la app de Looker Studio o en el navegador; con «Diseño
  adaptable» se ve en una columna.

## 4 · Si algo no aparece

- **Una hoja `VISTA_*` vacía o vieja**: correr `python scripts/recalcular_vistas.py`; si
  falla, mirar los logs del servicio del cron en Railway.
- **Un campo nuevo en la hoja**: en la fuente de datos, «Actualizar campos».
- **Números que no cierran con la planilla vieja**: las vistas ya no cuentan los pares
  anulados (§5.19), separan lo que pagó el comitente (§5.9) y llevan la caja de Lennon en
  dólares (§5.8). Las CC_<OBRA> nuevas usan la misma lógica.
