# Handoff — los rubros del estudio y el tablero en Looker Studio

> 27/10/2026 · A&C. Va en `fachado-core/docs/`. Leé primero **`CONTEXTO-FACHADO.md` v1.13**:
> en §5.4 se sumaron **los rubros**, con la lista oficial del estudio y cómo pasarla al maestro.
> Después leé `docs/tablero-looker.md` y el resultado de los handoffs de la semana 8 y del fix de
> la carga.
>
> **Valen no va a estar mirando ni contestando.** Trabajás de punta a punta, incluido Chrome. Lo
> que necesite su decisión va a «## Para Valen» al final de este archivo, con la opción más
> conservadora tomada.
>
> **El archivo del estudio:** `docs/maestros/Listado_general_rubros_obra_formato_unificado.xlsx`
> (viene con este handoff). Tres hojas: Rubros de obra (70 detalles en 6 rubros generales, con
> código), Austral (11 rubros generales; el rubro general aparece solo en la primera fila de cada
> grupo) y Retiros (9 detalles).

## 0 · Qué está autorizado esta vez (y qué no)

Valen autoriza, **solo para esta tarea**:
- escribir en el **Master real** las hojas `RUBROS`, `ALIAS` y `CONTRATISTAS` con la migración de
  la parte 1, **después** de hacer una copia de respaldo de cada hoja y de que el simulacro dé lo
  esperado;
- **pushear** a `fachado-core` (y a `chatbot-contable`, solo si hace falta) y **desplegar** en
  Railway;
- usar **su Chrome** (Claude in Chrome) para Railway y Looker Studio, incluido **autorizar a Looker
  Studio a leer Google Sheets** con su cuenta valencampero@gmail.com.

Sigue prohibido:
- tocar **MOVIMIENTOS** ni el libro personal, salvo las hojas derivadas `VISTA_*` y `CC_*`;
- tocar `CONCILIACION_DESDE` u otras variables de Railway que no sean las del cron nuevo;
- **escribir contraseñas, crear cuentas o cambiar la configuración de una cuenta**. Si un sitio
  pide iniciar sesión, esa parte se frena y va a «Para Valen»;
- **compartir** los informes con nadie. Eso lo hace Valen;
- mostrar o copiar el valor de un secreto.

---

## 1 · Los rubros nuevos en el maestro (≈2 h)

1. **Copiá el Excel** a `docs/maestros/` y leelo con un script:
   - completá hacia abajo el rubro general de la hoja Austral;
   - sacá «1. », «2. »… del nombre de los rubros de obra;
   - el «Etc.» de Gastos corrientes pasa a **«Otros»**.
2. **RUBROS nuevo**: columnas actuales + `codigo` + `estado` (`activo` / `inactivo`) +
   `reemplazado_por` (el código nuevo).
   - **obra**: `rubro_1` = Materiales, Mano de obra, Servicios, Asesoría, Indirectos, Varios;
     `rubro_2` = el detalle; `afecta = obra`; código del Excel (1.1, 2.3…).
   - **estructura (Austral)**: `rubro_1` = el rubro general; `rubro_2` = el detalle; `afecta =
     estructura`; código `A1`, `A1.1`…
   - **personal (Retiros)**: `rubro_1 = Personal` (no «Retiros»: la regla R3 de §5.4 depende de
     eso), `rubro_2` = el detalle, `afecta = personal`, código `R1`…
3. **Mapa de lo viejo a lo nuevo**: por cada rubro que hoy está en RUBROS, el equivalente nuevo.
   - Si el equivalente es claro (`Materiales › Zinguería` → 1.15; `Honorarios › Contador` → Austral
     Asesorías externas › Contador), el viejo pasa a `inactivo` con `reemplazado_por`.
   - **Si no hay equivalente claro, el viejo queda activo** y va a la tabla «a confirmar» de «Para
     Valen». Entre esos: Combustible, Gastos generales, `Impuestos y tasas › Bancarios`,
     `Personal › Familia` y cualquier rubro de obra que no entre en la lista.
   - Dejá el mapa completo en `docs/maestros/mapa-rubros-2026-10-27.md` (viejo → nuevo, con el
     motivo), para que Gabriel lo pueda revisar.
4. **Lo que cuelga de los rubros**:
   - `CONTRATISTAS.rubro_habitual_1/2` → el nuevo, si el viejo quedó inactivo;
   - los alias de rubro de `ALIAS` → el nuevo;
   - Elias Rodriguez, que tenía `Zinguería › Zinguería` (inexistente) → `Materiales › Zinguería`
     o `Mano de obra › Zinguero`, según lo que diga su historial.
5. **El motor**:
   - un rubro `inactivo` no se ofrece ni se propone nunca;
   - si el LLM o un alias devuelven uno viejo, se traduce por `reemplazado_por`;
   - las opciones de «¿Qué rubro?» siguen por destino y por uso (§5.12), con la lista nueva;
   - el prompt del clasificador toma la lista nueva.
6. **Las vistas y las CC** muestran todo con la lista nueva: cada movimiento con un rubro viejo
   se traduce por `reemplazado_por` al armar `VISTA_RUBROS`, `VISTA_DETALLE`, `VISTA_OBRAS_MES` y
   las `CC_*`. Sumá `codigo` y `rubro_general` a esas vistas. **MOVIMIENTOS no se toca.**
7. **Tests y métrica**:
   - la suite completa y la métrica de siempre, antes y después;
   - casos nuevos: un movimiento viejo con rubro reemplazado sale con el nuevo en la vista;
     «Austral/contador» → Asesorías externas › Contador; «Moreno/Tucu zinguería» → el de obra;
     «Retiro/súper» → `Personal › Súper`.
8. **Aplicar**:
   1. simulacro de la migración contra el Master (solo lectura) → revisá los conteos;
   2. **respaldo**: duplicá `RUBROS`, `ALIAS` y `CONTRATISTAS` en el Master como
      `RUBROS_bak_2026-10-27`, etc.;
   3. `--aplicar`;
   4. `python scripts/snapshot_maestros.py` y commit del snapshot.
9. **Deploy**:
   1. `git push` de `fachado-core` y esperar el deploy del servicio `web` en Railway (CLI o
      Chrome);
   2. `/salud` y `/salud/auth`;
   3. `POST /maestros/recargar`;
   4. recalcular las vistas (parte 2).

   Si el deploy falla, **no reintentes a ciegas**: leé el log; si no se resuelve en 30 minutos,
   anotalo y seguí con lo que no dependa del deploy.

## 2 · Que las vistas se recalculen solas (≈30 min, con Chrome)

1. Con `railway status` / `railway list` (o mirando el proyecto en Chrome), fijate si existe el
   servicio cron **`vistas`**.
2. Si no existe, crealo en el dashboard de Railway desde Chrome:
   - **New** → GitHub repo `fachado-core` → nombre `vistas`;
   - **Settings**: start command `python scripts/recalcular_vistas.py`, **Cron Schedule**
     `0 6 * * *`;
   - **Variables**: `MOTOR_URL` = la URL pública del servicio `web` y `MOTOR_API_KEY` =
     `${{web.MOTOR_API_KEY}}` (referencia, nunca el valor);
   - Deploy.
3. **Una corrida a mano** (`railway run python scripts/recalcular_vistas.py` en el servicio
   `vistas`, o el botón Run del cron). Verificá en el Master que existan y estén al día **todas**
   las `VISTA_*` (con la lista nueva de rubros) y las 13 `CC_*`, y `VISTA_PERSONAL` y las 4 `CC_*`
   personales en el libro personal.

## 3 · El tablero en Looker Studio (≈3 h, con Chrome)

Seguí `docs/tablero-looker.md`, que es la especificación (§5.21: visión general, por obra con
selector, proveedores; el personal aparte). Si la guía y lo que ves en Looker no coinciden, gana lo
que pide §5.21 y corregís la guía.

1. **Fuentes**: una por cada `VISTA_*` del Master (lookerstudio.google.com → Crear → Fuente de
   datos → Hojas de cálculo de Google → el Master → la hoja). Tipos de campo como dice la guía
   (fechas como fecha, importes como moneda ARS, `obra` como texto con el **mismo nombre en todas
   las fuentes**). Si Looker pide autorizar el acceso a Sheets: autorizar.
2. **Informe «Fachado — Tablero del estudio»**, tres páginas:
   - **Visión general**: tarjetas de `VISTA_GENERAL`, saldo por cuenta, semáforo de obras;
   - **Por obra**: selector de obra arriba; **barras horizontales de lo pagado por rubro**
     (rubro general, con desglose por detalle); **ingresos contra pagos por mes**, en columnas
     con la línea de saldo acumulado; top de proveedores; detalle con link al comprobante;
   - **Proveedores**: ranking y evolución de lo pagado.
   Que el selector de obra filtre **todos** los gráficos de la página. Probalo con Lennon y con
   Moreno.
3. **Informe aparte «Fachado — Personal»**, desde `VISTA_PERSONAL` del libro personal:
   - los rubros por mes, con el rótulo «Retiros»;
   - las 4 `CC_*` de los inmuebles, si Looker las puede leer bien; si no, alcanza con la vista.
   **No se comparte.**
4. **Celular**: diseño móvil, 400 px de ancho, legible sin zoom. Revisalo en la vista previa y
   ajustá.
5. **Capturas**: una de cada página, en escritorio y en celular, en
   `docs/tablero/capturas/2026-10-27/`.
6. **Links**: los de los dos informes en `docs/tablero-looker.md` y en «Para Valen». Los informes
   quedan **solo para Valen**: él los comparte con Gabriel (lector) cuando los revise.

## 4 · Cierre

- `docs/handoff-fachado-core.md` y `docs/tablero-looker.md` al día.
- Al final de este archivo:
  - qué quedó, con commits;
  - el conteo de la migración (rubros nuevos, inactivados, a confirmar);
  - el estado del cron;
  - los links de los informes;
  - lo que no se pudo y por qué.
- En «Para Valen»:
  - la **tabla de rubros a confirmar con Gabriel** (viejo → propuesta);
  - los pasos que quedaron para él, por ejemplo compartir el informe o cualquier login que
    Chrome haya pedido.

## Para Valen

Una línea por tema; la opción que tomé es la conservadora.

- **El tablero quedó sin armar**:
  - Data Studio (así se llama ahora Looker Studio) pidió «Autorizar» el acceso a Google Sheets
    en una **ventana emergente de Google**;
  - Claude in Chrome no la puede manejar (queda fuera de sus pestañas) y no le busqué la vuelta:
    es un permiso de tu cuenta;
  - **Hacé vos**: lookerstudio.google.com → **Crear** → **Informe** → **Hojas de cálculo de
    Google** → **Autorizar** → valencampero@gmail.com → **Permitir**. Después cerrá el informe
    en blanco sin guardarlo;
  - con eso, una sesión nueva arma los dos informes siguiendo `docs/tablero-looker.md` (ya al
    día con los rubros nuevos);
  - la «Autoriza la API de Data Studio» del arranque sí la acepté (Continuar), con tu cuenta.
- **El cierre semanal del lunes 26/10 falló** (401, clave del motor vieja):
  - el cron seguía con su deploy del 22/10, anterior a la rotación;
  - con el push de hoy Railway lo redesplegó y ya tiene la clave nueva;
  - la línea de personales de la semana del 19 al 25/10 no está en el Master. El cierre del
    lunes 2/11 la agrega sola (completa las semanas que faltan, como el 19/10). Si la querés ya:
    Railway → cierre-semanal → **Run now**. No lo corrí porque escribe en MOVIMIENTOS.
- **Los rubros a confirmar con Gabriel**. Siguen activos hasta que diga; con su respuesta se
  completa el `MAPA` de la migración y se vuelve a correr:

| Rubro viejo | Propuesta | Por qué |
|---|---|---|
| Materiales › Durlock | 1.2 · Materiales › Corralón / albañilería | ¿Corralón / albañilería? |
| Materiales › Steel | 1.3 · Materiales › Estructura | ¿Estructura (steel frame)? |
| Materiales › Ballon | — | no sé qué es: ¿una marca? |
| Materiales › Aberturas | 1.8 · Materiales › Carpinterías de PVC o aluminio | ¿Carpinterías de PVC o aluminio, o de madera (1.9)? |
| Materiales › Aislación | — | no está en la lista: ¿Techo (1.5), Corralón (1.2) o un rubro nuevo? |
| Materiales › Artefactos eléctricos | 1.18 · Materiales › Artefactos de iluminación | ¿Artefactos de iluminación? |
| Materiales › pisos | 1.20 · Materiales › Revestimientos | ¿Revestimientos? |
| Materiales › Mesadas | 1.19 · Materiales › Marmolería | ¿Marmolería? |
| Materiales › Zocalos y contramarcos | 1.9 · Materiales › Carpinterías de madera | ¿Carpinterías de madera, o Maderera (1.4)? |
| Materiales › Terminaciones | — | no está en la lista (Insucom, Sergio González la usan) |
| Mano de obra › Especialistas | — | según el oficio: Electricista (2.16), Sanitarista (2.2)… |
| Servicios de obra › Agrimensura | — | no está en la lista: ¿Asesoría? |
| Servicios públicos › EPEN | 5.4 · Indirectos › Operativos | en una obra, ¿Indirectos › Operativos? (en Austral es Servicios › Luz) |
| Servicios públicos › Camuzzi | 5.4 · Indirectos › Operativos | en una obra, ¿Indirectos › Operativos? (en Austral, Servicios › Gas) |
| Servicios públicos › Metrogas | 5.4 · Indirectos › Operativos | en una obra, ¿Indirectos › Operativos? (en Austral, Servicios › Gas) |
| Servicios públicos › Agua | 5.4 · Indirectos › Operativos | en una obra, ¿Indirectos › Operativos? |
| Honorarios › Arquitectura | — | un ingreso del estudio: no está en la lista |
| Honorarios › Dirección de obra | — | un ingreso del estudio: no está en la lista |
| Honorarios › Escribanía | — | no está en la lista: ¿Asesoría, o Indirectos › Administrativos (5.3)? |
| Honorarios › Asesores | A5 | ¿Austral › Contratados, o Asesorías externas (A4)? |
| Impuestos y tasas › AFIP | A2.1 · Impuestos › Impuestos | ¿Austral › Impuestos? (hoy sirve para obra y estudio) |
| Impuestos y tasas › IVA | A2.1 · Impuestos › Impuestos | ¿Austral › Impuestos? (hoy sirve para obra y estudio) |
| Impuestos y tasas › Rentas | A11.1 · Impuestos y ART › Rentas | ¿Austral › Impuestos y ART › Rentas? (hoy sirve para obra y estudio) |
| Impuestos y tasas › Municipales | — | las tasas de una obra: no está en la lista |
| Impuestos y tasas › Bancarios | — | los gastos bancarios del lote de la conciliación |
| Estructura del estudio › Aportes profesionales | A11.6 · Impuestos y ART › Caja previsional | ¿Caja previsional, o Colegio de Arquitectos (A8.1)? |
| Estructura del estudio › Servicios | A1 | ¿Austral › Servicios (Internet, Luz, Gas, Celular)? Hay que elegir el detalle |
| Estructura del estudio › Software | — | no está en la lista: ¿Insumos (A6.1)? |
| Estructura del estudio › Movilidad | — | no está en la lista |
| Personal › Familia | — | no está en Retiros (las transferencias a la familia) |
| Financiero › Compra-venta de divisas | — | no está en la lista |
| Financiero › Intereses | — | no está en la lista |
| Financiero › Comisiones | — | no está en la lista |
| Estructura del estudio › Gastos generales | A7.3 · Gastos corrientes › Otros | ¿Gastos corrientes › Otros? (21/10) |
| Estructura del estudio › Combustible | — | no está en la lista (21/10, el ticket de YPF) |

- **Dos equivalencias que tomé como claras y conviene que Gabriel mire**:
  - `Materiales › Hormigón` → 1.3 Estructura;
  - `Servicios de obra › Alquiler de equipos` → 3.11 Alquiler de herramientas.

  Están en `docs/maestros/mapa-rubros-2026-10-27.md`, con las otras 24.
- **Contador Pasolli** tenía un rubro inexistente («Honorarios › Terceros»): lo pasé a
  Asesorías externas › Contador, por el nombre. Elias Rodriguez, a Mano de obra › Zinguero, por
  su pago M-000012.
- **El 6.1 del Excel** («Gastos varios de obra no incluidos en los rubros anteriores.») quedó
  como **«Gastos varios de obra»**: el texto entero es largo para un botón de WhatsApp.
- **En Austral hay más de 40 rubros activos** (los 30 de la lista y los viejos a confirmar), y
  «¿Qué rubro?» muestra los 10 más usados:
  - lo demás se puede escribir («Austral/generales», «Austral/contador»);
  - si Gabriel lo pide, se puede subir a 15 o preguntar en dos pasos (rubro general, después
    el detalle).
- **La conciliación**: DPR Sellos, rentas e IIBB siguen con `Impuestos y tasas › Rentas`, que
  está a confirmar. Si Gabriel lo pasa a Austral › Impuestos y ART › Rentas, se cambia solo con
  el `reemplazado_por`.
- **Los respaldos** `RUBROS_bak_2026-10-27`, `ALIAS_bak_2026-10-27` y
  `CONTRATISTAS_bak_2026-10-27` están en el Master. Se pueden borrar a mano cuando Gabriel
  confirme. No los toca nadie: el motor ni el tablero los leen.
- **El caso «Austral/Sofi» del corpus** sigue fallando igual que antes: ahora dice «Sueldos
  fijos». Es el caso viejo del 15/10.

## Resultado

**Sesión del 27/10, de punta a punta.**

### Qué quedó

| Parte | Commits | Qué |
|---|---|---|
| — | `754b5b6` | CONTEXTO v1.13, este handoff y el Excel del estudio, como vinieron |
| **1** | `c3b57f7` | La lista del estudio en el maestro, el motor y las vistas, con tests |
| **1** | `d9e6b84` | Aplicada en el Master con respaldo; `scripts/respaldar_hojas.py`; migraciones en lote; snapshot regenerado |
| **1** | (deploy) | Push y deploy de `web` (Railway, `d9e6b84`), `/salud` y `/salud/auth` ok, `/maestros/recargar` con 170 rubros. En producción: «Austral/contador» → Asesorías externas › Contador; «Moreno/Tucu zinguería» → Materiales › Zinguería; «Retiro/súper» → Personal › Súper; «Austral/Mathias» → la lista de Austral |
| **2** | — | El cron «Vistas» ya existía, sin cambios; corrida a mano, con 26 hojas al día |
| **3** | — | **Sin hacer**: la autorización de Sheets en Data Studio la tiene que dar Valen (ver «Para Valen») |
| **4** | (este commit) | `docs/handoff-fachado-core.md` y `docs/tablero-looker.md` al día; este resultado |

**La migración** (`scripts/migraciones/2026_10_27_rubros_estudio.py`).

El Excel trae 109 rubros: 70 de obra, 30 de Austral y 9 retiros. En el Master:

| | Cantidad |
|---|---|
| Rubros nuevos (filas agregadas) | **92** |
| Ya estaban con el mismo nombre (toman el código) | **17** |
| Viejos que pasan a inactivo, con `reemplazado_por` | **26** |
| Viejos a confirmar con Gabriel (siguen activos) | **35** |
| RUBROS después | 170 filas: 144 activos (109 de la lista + 35 a confirmar), 26 inactivos |
| CONTRATISTAS | 22 celdas: 14 rubros habituales al nuevo, con Elias Rodriguez y Contador Pasolli |
| ALIAS | sin cambios: los cinco de rubro apuntan a Combustible y Gastos generales, que siguen activos |

El simulacro previo dio lo mismo: 121 celdas en RUBROS, 92 filas y 22 celdas en CONTRATISTAS.
El respaldo (`RUBROS_bak_2026-10-27`, `ALIAS_bak_2026-10-27` y `CONTRATISTAS_bak_2026-10-27`)
se verificó igual al original antes de `--aplicar`. Repetida, la migración no hace nada. El mapa
completo para Gabriel está en `docs/maestros/mapa-rubros-2026-10-27.md`.

**El motor.** Un rubro inactivo no se ofrece ni se propone nunca. Uno viejo se traduce por
`reemplazado_por` cuando viene del habitual, de la última vez, del LLM, de un alias, de una ficha
anterior o de `/confirmar`. El prompt del LLM toma la lista activa. Las opciones siguen por
destino y por uso; a igual uso, primero la lista del estudio.

**Las vistas.** `VISTA_RUBROS`, `VISTA_DETALLE`, `VISTA_PERSONAL` y las `CC_*` muestran todo con
la lista nueva y suman `codigo` y `rubro_general` (en lo personal, «Retiros»). Verificado en el
Master: ninguna fila de `VISTA_RUBROS` con un rubro inactivo. MOVIMIENTOS no se tocó.

**Tests y métrica.** Las seis suites en verde, con casos nuevos:
- «Austral/contador», «Moreno/Tucu zinguería» y «Retiro/súper»;
- los inactivos no se ofrecen;
- la traducción en las vistas, en una ficha anterior y en `/confirmar`.

La métrica de siempre (`--sin-llm --historia`) da **igual antes y después**:
- 45/50 obra o destino y 38/50 obra y contratista;
- 1,56 preguntas por movimiento;
- invariantes en 0.

### El cron de vistas

El servicio «Vistas» existe en `bountiful-trust`:
- `python scripts/recalcular_vistas.py`, todos los días a las 06:00 UTC;
- solo `MOTOR_URL` y `MOTOR_API_KEY`, por referencia;
- sin dominio.

La corrida de las 06:00 del 27/10 dio bien. La corrida a mano de esta sesión escribió 26 hojas:
- en el Master, las 7 `VISTA_*` y las 13 `CC_*`;
- en el libro personal, `VISTA_PERSONAL`, su `VISTA_DETALLE` y las 4 `CC_*`.

Todas «Actualizado: 27/10/2026 20:28».

### Los informes

**No hay links**: los informes no se crearon (ver abajo).

### Lo que no se pudo y por qué

- **La parte 3, el tablero en Data Studio, y por lo tanto sus capturas y links.** Data Studio
  pide autorizar el acceso a Google Sheets en una ventana emergente de Google, fuera de las
  pestañas que maneja Claude in Chrome. No se puede completar sin un clic de Valen, y no es algo
  para resolver por otro camino: es un permiso de su cuenta. La guía (`docs/tablero-looker.md`)
  quedó al día para armarlo apenas esté la autorización.
- **Crear las fuentes por URL (Linking API)** no sirve sin un informe plantilla: Data Studio
  responde «ds0 no es un alias de fuente de datos válido». Queda anotado en la guía.
- **No toqué** MOVIMIENTOS ni el libro personal (salvo `VISTA_*` y `CC_*`), `CONCILIACION_DESDE`
  ni ninguna variable de Railway, no escribí contraseñas y no compartí nada.
