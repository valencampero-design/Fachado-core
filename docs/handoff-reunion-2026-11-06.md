# Handoff — lo que salió de la reunión del 6/11

> 7/11/2026 · A&C. Mismo archivo en `fachado-core/docs/` y en
> `chatbot-contable/docs/clientes/fachado/`.
>
> **Leé primero `CONTEXTO-FACHADO.md` v1.14** (viene con este handoff). Cambiaron:
> - §5.4, R1: una obra propia le gana a «Retiro»;
> - §5.7: la caja de ahorro 48 pasa a ser la cuenta personal de Gabriel;
> - §5.14: el cierre semanal no suma lo pagado desde la 48;
> - el final de §5.14: un gasto de obra cargado como personal se pasa al estudio;
> - §5.20: son tres extractos, no cuatro;
> - §6: Gessel y Belelli pasan a ser obras propias.
>
> **Valen no va a estar mirando ni contestando.** Trabajás de punta a punta, con Chrome para
> Data Studio y Drive. Lo que necesite su decisión va a «## Para Valen» al final, con la opción
> más conservadora tomada.

## 0 · Autorizado esta vez (y qué no)

**Autorizado, solo para esta tarea:**
- **Escribir en el Master y en el libro personal reales**, con un respaldo previo de cada hoja
  que toques (`scripts/respaldar_hojas.py`). Puede ser:
  - `OBRAS`, `CUENTAS` y `ALIAS`;
  - **filas nuevas** en `MOVIMIENTOS` de los dos libros: contraasientos y cargas.
- Mover y renombrar comprobantes en Drive, solo los de los movimientos que se pasan de libro.
- Pushear los dos repos y desplegar en Railway.
- Usar el Chrome de Valen para Data Studio y Drive.

**Sigue prohibido:**
- **editar o borrar una fila existente de `MOVIMIENTOS`**: se corrige siempre con
  contraasiento (§5.19). Conciliar no aplica acá;
- tocar `CONCILIACION_DESDE`;
- escribir contraseñas;
- compartir informes o archivos con alguien nuevo. El tablero del estudio ya está compartido
  con Gabriel y Petrus: no cambies los permisos;
- mostrar secretos.

**Simulacro primero, siempre.** Cada script corre en seco, revisás los conteos, y recién
después `--aplicar`.

---

## 1 · Motor (`fachado-core`)

### M1 · Gessel y Belelli, obras propias (§6 v1.14)

1. **Maestro.** Migración `2026_11_07_gessel_belelli.py`:
   - `OBRAS`: Gessel y Belelli pasan de `tipo = personal` a `obra_propia`, servicio `todo`,
     comitente «El arquitecto», con una nota del cambio del 6/11;
   - alias `gesell` → Gessel; verificá que exista `belleli` → Belelli.
2. **Lo ya cargado.** Las filas del libro personal con obra Gessel o Belelli: hoy son
   **P-000004, P-000005 (Belelli) y P-000010 (Gessel)**, pero buscá todas.
   - En el personal, un **contraasiento** de cada una (§5.19, `anula` = id original).
   - En el estudio, una **fila nueva** con los mismos datos: fecha, importe, cuenta, medio,
     contratista y comprobante. Agregá:
     - `tipo_gasto` de obra;
     - el rubro traducido a la lista vigente: si el rubro está entre los «a confirmar», dejalo
       como está y anotalo;
     - en la descripción, «pasado del libro personal (P-0000xx) el 7/11».
   - Vinculá las dos filas (`vinculo`), como en una corrección.
3. **El cierre semanal.** Esas filas ya están sumadas en las líneas «Gastos personales ·
   semana N» del Master. Por ejemplo, M-000026 es la semana con P-000010. Verificá que, con
   los contraasientos del personal, la próxima corrida de `cierre_semanal` escriba el
   **ajuste a la baja** de cada semana afectada, y que no lo duplique. Si hoy solo revisa la
   semana en curso, que revise las semanas con anulaciones nuevas (§5.19). Corrélo en
   simulacro y dejá los ajustes que escribiría en el resultado; aplicalo.
4. **El motor.**
   - R1 v1.14: un mensaje que nombra una obra propia va a esa obra aunque diga «Retiro», con
     la advertencia «Gessel es una obra propia: lo cargo en el estudio».
   - Test: «Retiro/Gessel 50000», «Gesell/Granjeri» + comprobante y «Belleli/Metrogas».
5. **Las cuentas corrientes y vistas.** `CC_GESSEL` y `CC_BELELLI` pasan al Master; las del
   libro personal se borran porque son derivadas y quedarían viejas. `VISTA_PERSONAL` ya no
   las tiene. Recalculá las vistas.

### M2 · Lo de obra cargado como personal: Moreno (fin de §5.14 v1.14)

1. En el tablero personal hay una línea de Moreno: es **P-000001** (30/09, $ 184.000, Tucu,
   obra Moreno, rubro «Personal › Familia»). **Buscá todas las filas del libro personal con
   una obra del estudio** (cualquier obra que no sea de tipo `personal`). Con cada una, lo
   mismo que en M1.2:
   - contraasiento en el personal y fila nueva en el estudio;
   - el rubro, el habitual del contratista: Tucu = Marcelo Orellana;
   - el cierre semanal, como en M1.3.
2. **Lo dudoso no se mueve.** Si encontrás filas personales **sin obra** con un rubro que
   parece de obra (por ejemplo P-000018, Nacho Sanitarista, «Mano de obra › Especialistas»),
   no las muevas: van a «Para Valen» con tu propuesta. Lo mismo si ves un contratista mal
   resuelto (P-000006: el comprobante dice «FACHADO, SOFIA» y el contratista es Sofía
   Cervera).
3. **Que no vuelva a pasar.** Reproducí cómo P-000001 quedó personal teniendo obra Moreno,
   a partir del mensaje del 30/09 en CAPTURA o del `msg_id`. Corregí la causa con un test:
   una ficha con obra del estudio nunca va al libro personal salvo que la obra sea de tipo
   `personal`.

### M3 · La caja de ahorro 48 pasa a ser personal (§5.7 v1.14)

1. **`CUENTAS`:**
   - cuenta nueva **`Banco personal (CA 48)`**: ARS, `concilia = no`, `cuentas_banco` = la CA
     $ 48-69556582-001, solo libro personal;
   - en `Banco`, sacá la 48 de `cuentas_banco`.
   - **Fecha de corte**: 1/11/2026, en una variable o en la nota de la cuenta, no fija en el
     código.
2. **Los gastos personales desde la 48.** Un «Retiro» con comprobante bancario cuya cuenta de
   origen es la 48 → cuenta `Banco personal (CA 48)`.
   - Si el lector no saca la cuenta de origen, sumá ese campo: número de cuenta o CBU de
     origen, si el comprobante lo trae.
   - Si no se puede saber de qué cuenta salió, `Banco personal (CA 48)` marcado como
     **(supuesto)**, solo cuando lo carga Gabriel: desde el 1/11 usa la 48 para lo personal.
   - Si lo carga Petrus, como hoy (Banco). Anotalo como supuesto en «Para Valen».
3. **El cierre semanal** no suma lo pagado desde `Banco personal (CA 48)` (§5.14 v1.14).
4. **El pase del estudio a la 48 = retiro** (§5.7 v1.14):
   - en la conciliación, una línea del extracto de la 273 que va a la 48 ya **no es `INTERNA`**;
   - es un **retiro de Gabriel**, sin pregunta de obra: «Vi que le pasaste $ X a tu cuenta
     personal (CA 48) el dd/mm. Lo cargo como retiro» → Confirmar;
   - la forma recomendada:
     - en el libro personal, un TRASPASO de `Banco` a `Banco personal (CA 48)`, que el cierre
       semanal cuenta como salida del estudio;
     - `VISTA_PERSONAL` no lo cuenta como gasto, porque el gasto es el detalle cargado desde
       la 48 y no se cuenta dos veces.

     Si encontrás algo más simple que cumpla las tres cosas (sale del estudio, no se cuenta
     dos veces, no se pregunta la obra), usalo y anotalo.
5. **Extractos:**
   - `GET /conciliar/estado` y el pedido semanal piden **tres** fuentes del banco más Mercado
     Pago, sin la 48;
   - si llega un extracto de la 48, el bot contesta «Ese extracto es de tu cuenta personal:
     no hace falta mandarlo» y no importa nada;
   - lo de la 48 que ya esté en BANCO_RAW queda como está.
6. **Saldos de apertura**: `docs/saldos-apertura-31-10.csv` y `cargar_saldos_apertura.py`
   tienen que dejar de sumar la 48 en `Banco`.

### M4 · Cierre del motor

- Tests de todo lo anterior y la suite completa.
- La métrica de siempre, antes y después.
- `docs/handoff-fachado-core.md` al día.
- `docs/manual-usuarios.md`:
  - Gessel y Belelli como obras;
  - la 48 como cuenta personal;
  - tres extractos en vez de cuatro;
  - y además: «Depósito» = pago del comitente sin factura, y `pagado por el comitente` como
    tramo para un pago directo con factura (ver la nota al final).

---

## 2 · Gateway (`chatbot-contable`)

1. **El retiro a la 48** en la conciliación: el gateway muestra el texto que arma el motor,
   con Confirmar. Sin preguntas.
2. **Un extracto de la 48** (el motor contesta que no hace falta): el gateway lo dice así y no
   lo trata como error.
3. **El pedido semanal**: el texto de faltantes sale de `/conciliar/estado`. Verificá que con
   tres fuentes no quede nada fijo en el código.
4. Suite completa, HENSEL incluido. `docs/handoff-fachado.md` al día.

---

## 3 · El tablero, más interactivo (con Chrome)

Lo que pidió Gabriel: **hacer clic en los gráficos y filtrar**. En los dos informes
(los links están en `docs/tablero-looker.md`):

1. **Filtro cruzado** en todos los gráficos y tablas (en Data Studio: el gráfico →
   Configuración → Interacciones → «Filtro cruzado»). Hacer clic en un rubro de las barras o la
   torta, en una obra del semáforo o en un proveedor filtra el resto de la página. Probalo en
   cada página.
2. **Controles arriba de cada página:**
   - período (rango de fechas, por defecto «Todo»);
   - obra;
   - rubro general;
   - contratista;
   - en la visión general, además, cuenta;
   - en el personal: período, rubro y destino.

   Que filtren las fuentes de la página: el campo `obra` ya se llama igual en todas.
3. **Desglose (drill down) en rubros**: en las barras y la torta, de rubro general al detalle
   (`rubro_general` → `rubro_2`), con la opción de volver.
4. **Botón «Restablecer»** (o el control equivalente) para limpiar los filtros, visible en el
   celular.
5. **Gessel y Belelli** aparecen ahora en el selector de obra y en el semáforo del informe del
   estudio, y ya no en el personal. Después de recalcular las vistas, «Actualizar campos» en
   las fuentes que lo necesiten.
6. Revisalo en el **celular** (diseño adaptable), con capturas en
   `docs/tablero/capturas/2026-11-07/`.
7. `docs/tablero-looker.md`: qué se cambió y cómo se usa el filtro cruzado. Agregá también un
   párrafo para el manual: «Tocá una barra para filtrar».

---

## 4 · Orden y cierre

1. Respaldos.
2. M3.1 (`CUENTAS`) y M1.1 (`OBRAS`), en simulacro y después `--aplicar`.
3. El código: motor y gateway, con tests.
4. Push y deploy, con `/salud` y `/maestros/recargar`.
5. M1.2 y M2: los pases de libro, en simulacro y después `--aplicar`.
6. M1.3: el cierre semanal en simulacro; aplicar los ajustes.
7. M1.5: recalcular vistas y CC.
8. La parte 3, el tablero.
9. Al final de este archivo:
   - **la tabla de filas movidas**: P-… → M-…, con el contraasiento y el ajuste del cierre;
   - lo que no se pudo hacer;
   - los supuestos;
   - los links.

**Nota para el manual (decidido en el chat del 6/11):**
- El comitente que **le paga directo al proveedor** se carga así:
  - **sin factura** (en negro): `Deposito Proveedor/Obra $importe`;
  - **con factura**: `Obra/Proveedor/pagado por el comitente`, con ese tramo entre barras.
- En Lennon no hace falta ninguno, salvo que el comprobante no muestre el CUIT del comitente.

## Para Valen

Lo que necesita tu decisión. En cada caso quedó tomada la opción más conservadora; nada de esto
bloqueó el resto.

1. **P-000001 no se movió a Moreno** (contradice M2.1, a propósito). El comprobante (en Drive,
   `P-000001 Tucu $184.000…`) es una transferencia de **$ 184.000 a «FACHADO, SOFIA»** (CUIT
   27-47181632-4) **desde la CA 48**, concepto «Varios», y el extracto de la 48 tiene esa misma línea
   el 30/09. En CAPTURA, el mensaje original es «Sofi/Varios»; el «Tucu/Moreno» que llegó después
   era el texto de **otra** imagen, la transferencia de **$ 200.000 a Orellana del 28/09**, que ya
   está cargada como **M-000020** (Moreno · Marcelo Orellana). Pasarla al estudio cargaría a Moreno
   (obra de terceros) un pago a la hija. **Quedó como está.** Propuesta: corregirla dentro del
   libro personal (contraasiento y una fila nueva con Sofía Fachado, Personal › Familia, sin obra),
   con un script de una corrida; la dejo lista si la aprobás. Mientras tanto, «Moreno» sigue
   apareciendo como destino en el tablero personal.
2. **Filas personales dudosas, sin mover** (M2.2):
   - **P-000018** · 16/10 · $ 350.000 · Nacho Sanitarista · «Mano de obra › Especialistas» · sin
     obra (cargó Petrus). Propuesta: preguntarle a Gabriel la obra; si es de una obra, mismo pase
     que Gessel/Belelli.
   - **P-000006** · 09/10 · $ 80.000 · el comprobante dice «FACHADO, SOFIA» y el contratista quedó
     **Sofía Cervera** (es de la hija; Familia está bien). Propuesta: contraasiento y recarga con
     Sofía Fachado en el personal.
   - **P-000003** (01/10, Camuzzi, $ 237.101,98) y **P-000013** (15/10, EPEN, $ 411.022,46):
     personales sin obra con rubro de obra («Servicios públicos»). Gonzalo y Hua Huan pagan Camuzzi
     y EPEN desde el estudio; estos pueden ser de una casa o de una obra. Preguntar.
   - **El script del 9/10 (`2026_10_09_correcciones.py`) no debe correrse para los P-**: P-000004 y
     P-000005 ya están anulados por el pase, y su corrección de P-000001 ponía «Sofia Cervera»,
     que según §7 v1.10 es incorrecto.
3. **Supuestos de la CA 48** (§5.7 v1.14, anotados como pidió M3.2):
   - un retiro **de Petrus** sin cuenta de origen va a **Banco (supuesto)**, como hasta ahora; uno
     **de Gabriel**, desde el 1/11, a **Banco personal (CA 48) (supuesto)**;
   - en el extracto de la 273, una **«TRANSFERENCIA ELECTRONICA» sin destinatario** desde el 1/11 se
     toma como el pase a la 48 (es como aparecían los pases entre la 273 y la 48 en octubre). Si
     Gabriel tuviera otra cuenta propia en el mismo banco, habría que distinguirla;
   - la fecha de corte vive en `fecha_apertura` de la cuenta (2026-11-01): cambiarla ahí, sin deploy.
4. **P-000010 (ahora M-000050) no tiene contratista**: el original tampoco (el ítem es «GRANJERI
   ROBERTO OSCAR»). Lo dejé igual. Propuesta: dar de alta a Granjeri en CONTRATISTAS (Materiales ›
   pisos); no lo hice porque CONTRATISTAS no estaba entre las hojas autorizadas.
5. **Rubros «a confirmar» que quedaron como estaban** en las filas nuevas (sin código en la lista
   del estudio): «Servicios públicos › Metrogas» (M-000048), «Servicios públicos › Agua» de Edesur
   (M-000049, pregunta abierta desde el 9/10) y «Materiales › pisos» (M-000050). El medio de pago de
   M-000048/49 quedó «Otro», igual que el original (la corrección a «Mercado Pago» del 9/10 nunca se
   aplicó).
6. **Tablero: el semáforo de la Visión general no filtra el resto de la página al tocarlo.** El
   filtro cruzado de Data Studio entre fuentes distintas solo funciona si la otra fuente tiene todos
   los campos del gráfico, y la tabla del semáforo tiene obra + semáforo + último movimiento. El
   resto anda (barras ↔ torta ↔ detalle en «Por obra», proveedores ↔ evolución, todo el personal) y
   el control de obra filtra la página entera. Opciones: dejarlo así (tomada), o sacar «Semáforo» y
   «Último movimiento» de las dimensiones de esa tabla (perdería el color por fila). También: en
   «Proveedores» no agregué el control de rubro general (VISTA_PROVEEDORES no tiene rubro: no
   filtraría nada), y el control de rubro de «Por obra» se lee `rubro_general`.
7. **Drive**: el token OAuth local sigue vencido (`invalid_grant`), así que los tres comprobantes
   los moví y renombré con el conector de Drive de tu cuenta. Las carpetas nuevas
   `comprobantes/Gessel/2026-08` y `comprobantes/Belelli/2026-10` las creó esa otra app: el motor
   (con `drive.file`) puede no verlas y crear otra «Gessel»/«Belelli» la próxima vez que archive ahí.
   Propuesta: regenerar el token (`scripts/get_google_token.py`) y, si aparece una carpeta doble,
   juntarlas.
8. **Push del gateway**: en `chatbot-contable` había un commit tuyo local sin pushear de hoy
   (`dc8565a`, docs de Belakay, solo documentación). Salió junto con el mío.
9. **Revisión en el celular**: la ventana de Chrome está maximizada y no se pudo achicar; las
   capturas son del informe con la página limitada a 420 px de ancho (el diseño adaptable responde
   igual), no de un teléfono. Conviene mirarlo una vez en el celular de Gabriel.

## Resultado

*7/11/2026, en el orden de la parte 4.* Todo aplicado y desplegado, salvo lo de «Para Valen».

### Filas movidas (M1.2 y M2)

| Original (personal) | Fecha | Importe | Obra | Fila nueva (estudio) | Contraasiento (personal) | Ajuste del cierre semanal |
|---|---|---|---|---|---|---|
| **P-000004** · Metro Gas | 08/10 | $ 6.692,55 | Belelli | **M-000048** (vínculo P-000024) | **P-000024** (anula P-000004) | **M-000052** · 2026-W41 · Mercado Pago · INGRESO **$ 38.667,30** (P-000004 + P-000005; baja M-000018) |
| **P-000005** · Edesur | 08/10 | $ 31.974,75 | Belelli | **M-000049** (vínculo P-000025) | **P-000025** (anula P-000005) | **M-000052** (el mismo) |
| **P-000010** · Granjeri | 31/08 | $ 1.440.740,00 | Gessel | **M-000050** (vínculo P-000026) | **P-000026** (anula P-000010) | **M-000051** · 2026-W36 · Banco · INGRESO **$ 1.440.740** (baja M-000026) |
| P-000001 · «Tucu» | 30/09 | $ 184.000,00 | Moreno | — no se movió (Para Valen 1) | — | — |

- Simulacro antes de cada `--aplicar`, con el mismo resultado; la segunda corrida no escribe nada.
- El cierre semanal se corrió en simulacro sobre copias de los dos libros (2 filas, las de la
  tabla; una segunda corrida, 0) y después en producción (`POST /cierre-semanal` 2026-W44): escribió
  exactamente M-000051 y M-000052, sin avisos. Una nueva llamada no escribe nada.
- Comprobantes movidos y renombrados (el link no cambia): `comprobantes/Belelli/2026-10/M-000048
  Metro Gas $6.692,55.jpg`, `…/M-000049 Edesur $31.974,75.jpg` y `comprobantes/Gessel/2026-08/
  M-000050 GRANJERI ROBERTO OSCAR $1.440.740.jpg`.
- Saldo del estudio: sin cambio neto (cada fila nueva del estudio se compensa con su ajuste).

### Maestros (M3.1, M1.1)

- **Respaldos** (antes de tocar nada): `OBRAS_bak_2026-11-07`, `CUENTAS_bak_2026-11-07` y
  `ALIAS_bak_2026-11-07` en el Master; `CC_GESSEL_bak_2026-11-07` y `CC_BELELLI_bak_2026-11-07` en el
  personal; MOVIMIENTOS y BANCO_RAW del Master y MOVIMIENTOS y VISTA_PERSONAL del personal, a
  archivo en `A&C/Fachado/respaldos/2026-11-07/` (fuera de los repos), verificados contra el Sheet.
- `2026_11_07_cuenta_48.py --aplicar`: **CUENTAS** +1 fila («Banco personal (CA 48)»: personal, ARS,
  no concilia, `fecha_apertura` 2026-11-01, `cuentas_banco` CA $ 48-69556582-001) y 1 celda (la 48
  sale de `Banco.cuentas_banco`).
- `2026_11_07_gessel_belelli.py --aplicar`: **OBRAS** 4 celdas (Gessel y Belelli → `obra_propia`,
  con la nota del 6/11; servicio y comitente ya estaban) y **ALIAS** +1 (`gesell` → Gessel;
  `belleli` y `gessel` ya estaban).
- `/maestros/recargar` en producción: 17 obras, 16 cuentas, 54 alias; solo las advertencias de
  siempre.

### Código

- **Motor** (`fachado-core`, `d9a8040` y `a81d79c`): R1 v1.14; ninguna ficha con obra del estudio
  en el libro personal (cascada y 422 en `/confirmar`; P-000001 reproducido en `test_casos`); la CA
  48 (cuenta de origen del comprobante, supuesto para Gabriel, cierre semanal, extracto ignorado,
  retiro en la conciliación, resumen contra el banco sin la 48); CC_ viejas del personal borradas
  por `recalcular`; migraciones, script del pase y respaldo a archivo. Detalle en
  `docs/handoff-fachado-core.md` («Lo del 7/11»).
- **Gateway** (`chatbot-contable`, `a785895`): el extracto de la 48 se avisa y no cuenta como
  importado; tests del retiro a la 48 con Confirmar y del pedido con tres extractos + Mercado Pago
  (sin rótulos fijos). `docs/handoff-fachado.md` §14.
- **Tests**: motor — reglas 25, casos 265, confirmar 182, conciliar 75, vistas 56, apertura 17,
  seguridad 21: todo OK. Gateway — obras, pedido de extractos, HENSEL, alertas, caché, canonize,
  respuesta, lunes y seguridad: todo OK.
- **La métrica** (corpus de siempre, contra el snapshot):

  | | Antes | Después |
  |---|---|---|
  | Obra / contratista / las dos sin preguntar | 90 % · 86 % · 76 % | 90 % · 86 % · 76 % |
  | Con las preguntas de diseño | 90 % | 90 % |
  | Necesitaron LLM | 6/55 | 6/55 |
  | Preguntas por movimiento (todos · con obra + contratista + comprobante) | 1,57 · 1,26 | 1,56 · 1,21 |
  | Casos obligatorios | 5/6 («Austral/Sofi» esperaba la pregunta de dual de antes del 15/10) | 6/6 (expectativa al día con §7 v1.10) |
  | Invariantes | 0 · 0 | 0 · 0 |

### Deploy

- Push de los dos repos a `main`; Railway desplegó `web`, `Vistas` y `cierre-semanal` del motor
  (15:01 y, con el arreglo del resumen, 15:07) y el gateway (15:01). `/salud` del motor y del
  gateway: ok.
- En producción, con `/interpretar` (no escribe): «Retiro/Gessel 50000» → Gessel, obra, con «Gessel
  es una obra propia: lo cargo en el estudio»; «Belleli/Metrogas» y «Gesell/Granjeri» → obra;
  «Retiro/Sofi» de Gabriel → Banco personal (CA 48) (supuesto), de Petrus → Banco;
  `/conciliar/estado` → «Me faltan: CA $, CC $, CA U$S y Mercado Pago».

### Vistas y cuentas corrientes (M1.5)

- `POST /vistas/recalcular` en simulacro y después aplicado: **CC_GESSEL** ($ 1.440.740) y
  **CC_BELELLI** ($ 38.667,30) en el Master, con el semáforo; **borradas del personal** las dos
  viejas (quedan sus `_bak_`). VISTA_PERSONAL sin Gessel ni Belelli (destinos: sin destino,
  Abucoque y Moreno por P-000001). El cron de la noche las vuelve a escribir igual.

### El tablero (parte 3)

- Multifiltro en todos los gráficos y tablas de los dos informes; controles arriba de cada página;
  desglose Rubro general → Rubro en barras y tortas; botón «Restablecer filtros» en cada página;
  tabla «Movimientos» nueva en la Visión general. Probado en modo lectura (controles entre fuentes,
  clic en barras, desglose, restablecer). Detalle y límites en `docs/tablero-looker.md` («Lo del
  7/11»); capturas en `docs/tablero/capturas/2026-11-07/`. Los permisos de los informes no se
  tocaron.

### Lo que no se pudo hacer

- Mover P-000001 (no correspondía: Para Valen 1).
- Que el semáforo de la Visión general filtre la página al tocarlo (Para Valen 6).
- Mirarlo en un teléfono de verdad (Para Valen 9).
- Mover los comprobantes con el motor (token local vencido: Para Valen 7).

### Links

- Tablero del estudio: <https://datastudio.google.com/reporting/2c7984bd-2bae-4e34-a492-b48a9bf2fd73>
- Tablero personal: <https://datastudio.google.com/reporting/d9779551-7295-4456-9f76-589fc0777da9>
- Master: <https://docs.google.com/spreadsheets/d/1yoakmhO1--WXCtWWStNrmczgYkaT1g0H54fTK2QCc9A>
- Libro personal: <https://docs.google.com/spreadsheets/d/1O4bMJXi4kooBvZZ6Wn-SlGhn2g2QjlANrmw3L7rCcZY>
- Repos: <https://github.com/valencampero-design/Fachado-core> ·
  <https://github.com/valencampero-design/chatbot-contable>
