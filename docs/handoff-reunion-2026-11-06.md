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

## Resultado
