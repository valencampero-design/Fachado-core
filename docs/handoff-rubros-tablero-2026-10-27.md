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

## Resultado
