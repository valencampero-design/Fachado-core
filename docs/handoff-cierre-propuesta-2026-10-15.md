# Handoff — cerrar la propuesta: conciliación, tablero y los ajustes del 15/10

> 15/10/2026 · A&C. Mismo archivo en `fachado-core/docs/` y en
> `chatbot-contable/docs/clientes/fachado/`. **Corren dos sesiones en paralelo, toda la
> mañana, sin supervisión.** Leé primero **`CONTEXTO-FACHADO.md` v1.10**: cambiaron §5.6
> («Es nuevo», personal desconocido), §5.8 (tc del recibo), §5.15 (Moreno sigue preguntando),
> §7 (las dos Sofía) y hay dos secciones nuevas, **§5.20 Conciliación** y **§5.21 Tablero**.
>
> Este documento define **los contratos entre los dos lados** (§3) para que ninguna sesión
> espere a la otra. Si un contrato tiene que cambiar, se anota al final de este archivo y se
> sigue; no se para.

## 0 · Reglas para trabajar solo toda la mañana

- **Orden fijo**: hacé las partes en el orden de tu sección. Terminá y commiteá cada parte
  antes de empezar la siguiente. Si una parte se traba más de 30 minutos, anotá por qué al
  final de este archivo y pasá a la siguiente.
- **Commits por parte, sin pushear.** Valen revisa y despliega al mediodía.
- **Ningún test ni script escribe en los Sheets reales.** Migraciones con simulacro por
  defecto; Valen las aplica con `--aplicar`. Las pruebas de conciliación usan los extractos
  de muestra (abajo) y libros en memoria.
- **Decisión de negocio que no esté en v1.10: no se inventa.** Se elige la opción más
  conservadora, se marca en el código como supuesto y se anota al final de este archivo.
- Gateway: los otros cuatro clientes no cambian. Todo en `handlers/obras.py` y servicios
  propios de Fachado.
- Archivos modificados solo por CRLF: fuera de los commits.

**Extractos de muestra (reales, de agosto):**
`OneDrive/Documentos/A&C/Fachado/Archivos Muestra/Muestra 2/CompartirDetalleMovimiento-2026082009*.xlsx`
(4 archivos, Banco Patagonia, cuentas `CA $ 273-125852351-000` y `CA $ 48-69556582-001`).
Formato: 4 filas de encabezado (`Cuenta:`, `Saldos al:`, `Ultimos Movimientos`), después
`Fecha | Descripción | Débito | Crédito | Saldo`, importes como `$ 14.000,00`, fechas
`dd/mm/aaaa`. Las transferencias traen CUIT y nombre en la descripción
(`TRANSFERENCIA ENTRE CUENTAS VAR 20929415044  MARAGAÑO GUERRERO MARCELO`). Copialos a
`tests/fixtures/` del motor.

---

## 1 · Motor (`fachado-core`)

### M1 · Ajustes del 15/10 (≈1 h)

1. **Las dos Sofía** (§7 v1.10). Maestro, por migración en simulacro: **Sofía Fachado**
   (CUIT 27-47181632-4, personal, `Personal › Familia`) y **Sofía Cervera** pasa a
   estructura (Austral). Rubro de Sofía Cervera: el que el maestro ya use para personal del
   estudio; si no hay ninguno, `Honorarios › Personal del estudio`, anotado como supuesto.
   Resolver «sofi»: CUIT/nombre del comprobante → «Retiro» → Austral/estudio → si nada,
   pregunta `apodo_ambiguo` con las dos.
2. **«Es nuevo»** (§5.6 v1.10): cuando la pregunta `contratista` trae opciones cercanas, el
   motor agrega la opción `"__nuevo__"` (rótulo «Es nuevo»). Respondida con ese valor, la
   ficha pasa a `extras.contratista_nuevo` con el nombre como lo escribió el usuario.
3. **Personal con destinatario desconocido**: no hay alta; el nombre va a la descripción.
   Test con «Retiro/Fulano».
4. **TC del recibo** (§5.8 v1.10): si el lector encuentra «US$ X × TC» (o equivalente), ese
   es el `tc` (origen `comprobante`) y no se pregunta. Tests con los recibos de Miguel.
5. **Chicos**: `ConfirmarOut.obra` suma `moneda` para cada total (`pagado_por_el_comitente`
   incluido); `/consultar` con `consulta = "obra"`: el saldo de una obra (lo mismo que
   `ConfirmarOut.obra`, en texto para WhatsApp).

### M2 · Conciliación (§5.20) — la parte grande (≈3 h)

1. **Parser** (`app/extracto.py`): el Excel de Banco Patagonia → líneas
   `{cuenta_banco, fecha, descripcion, debito, credito, saldo, cuit, nombre, ref}`.
   `hash_id` = sha256 de `cuenta_banco|fecha|descripcion|importe|saldo`. Tolerante a las
   variantes de los 4 archivos de muestra. Tests con los 4.
2. **BANCO_RAW** (ya existe, ampliala con `preparar_sheet.py` si hace falta:
   `cuenta_banco`, `cuit`, `nombre`, `ref`, `estado`, `id_mov`, `importado_ts`). Append
   idempotente por `hash_id`: un extracto que se superpone con el anterior no duplica.
3. **Desde el 1/11** (§5.20): las líneas anteriores a `CONCILIACION_DESDE` (variable,
   default `2026-11-01`) se importan con `estado = ANTERIOR` y no se concilian ni preguntan.
4. **Matcheo** contra `filtros.para_conciliacion` de los **dos** libros (lo personal fila
   por fila; nunca la línea semanal; sin pares anulados; solo cuentas que concilian):
   - fuerte: mismo importe y ref de operación o CUIT → `CONCILIADO`;
   - probable: mismo importe, fecha ±3 días, uno solo → `CONCILIADO`;
   - ambiguo (varios candidatos) → `A_REVISAR`, con los candidatos;
   - sin candidato → `SIN_CARGAR`.
   Escribe `id_banco` y `estado_conc` en el movimiento **por la columna, sin editar nada
   más** (es la única escritura sobre una fila existente que se permite; anotala en el
   handoff técnico).
5. **Clasificación de lo que falta**: gastos bancarios (comisión, impuesto, intereses, cruce
   de fondos, IVA percepción…) → lote `gastos_bancarios`; Mercado Libre / Mercado Pago sin
   comprobante → lote `meli_personal`; el resto → una **ficha** por línea, armada como si
   la línea fuera un comprobante (importe, fecha, cuenta Banco, contratista por CUIT o
   nombre con el resolver), con sus preguntas normales («¿A qué obra?»).
6. **Endpoints** (contrato en §3):
   - `POST /conciliar/extracto` — importa, concilia y devuelve el resumen y lo pendiente.
   - `GET /conciliar/pendientes?telefono=` — lo pendiente, para retomarlo.
   - `POST /conciliar/lote` — confirma un lote (gastos bancarios o MeLi personal).
   Las fichas de líneas sin cargar se confirman con el `/confirmar` de siempre, con
   `msg_id = "banco:<hash_id>"` (idempotente) y `extras.id_banco = <hash_id>`: al escribir,
   `/confirmar` marca la línea `CONCILIADO`.
7. **Saldos de apertura**: `CUENTAS.saldo_apertura` + `fecha_apertura` (nueva). El saldo
   según el libro de una cuenta = apertura + movimientos desde esa fecha. Migración en
   simulacro que solo agrega la columna; los valores los carga Valen el 1/11.
8. **Resumen**: saldo según libro vs saldo según banco (último `saldo` del extracto, por
   cuenta y total), diferencia, conteos por estado. Lo usa `/conciliar/extracto` y lo suma
   `/cierre-semanal` a su respuesta (`resumen_banco`).
9. **Tests**: los 4 extractos contra un libro en memoria sembrado con movimientos que
   coinciden, ambiguos y faltantes; reimportar el mismo extracto no cambia nada; una línea
   anterior a `CONCILIACION_DESDE` no genera preguntas.

### M3 · Vistas para el tablero (§5.21) (≈2 h)

1. `POST /vistas/recalcular` reescribe hojas `VISTA_*` en el maestro (son derivadas: se
   pueden reescribir enteras; nunca toca MOVIMIENTOS):
   - `VISTA_SALDOS`: por cuenta y por día, saldo según libro (cajas de obra aparte, en su
     moneda).
   - `VISTA_OBRAS`: por obra — aportes del comitente, pagado con plata del estudio, pagado
     por el comitente, caja de obra (en su moneda), ejecutado total, **capital propio
     inmovilizado** (definición de §5.21) y semáforo (§5.21: caja de obra en negativo o
     estudio financiando = rojo; sin movimientos en 30 días = gris; el resto, verde).
     **Sin presupuesto**: es una etapa posterior, no va ahora.
   - `VISTA_RUBROS`: mes × obra × rubro_1 × rubro_2 × tipo_gasto, importe en pesos.
   - `VISTA_PROVEEDORES`: mes × contratista × obra, importe y cantidad de pagos.
   - `VISTA_DETALLE`: movimientos vigentes (sin anulados) con link al comprobante, para el
     detalle por obra.
   - En el libro personal, `VISTA_PERSONAL` (mes × rubro × destino).
   Todo sin pares anulados, sin informales donde corresponda, y lo personal **nunca** en
   las vistas del maestro (solo la línea semanal).
2. **Cuentas corrientes por obra en el Sheet maestro** (entregable de la propuesta):
   una hoja `CC_<obra>` por cada obra que lleva cuenta corriente (§6: administración, «todo»
   y obras propias — hoy Lennon, Moreno, Moquehue, Gonzalo, Hua Huan, Grigera Galpón, Tres
   Cerros; no las de «proyecto y dirección» ni los inmuebles personales). Misma lógica que
   la planilla actual de Gabriel, **leyendo de las `VISTA_*`** (no de MOVIMIENTOS crudo, para
   no repetir la lógica de anulados, cajas y monedas):
   - encabezado: aportes del comitente, pagado con plata del estudio, pagado por el
     comitente, caja de obra (en su moneda), saldo;
   - bloques: aportes del comitente · por contratista · por rubro · detalle cronológico con
     link al comprobante (y la etapa, en Lennon y Moreno).
   Script `scripts/crear_cc_obras.py`, idempotente, simulacro por defecto: crea las que
   faltan y **reescribe** las existentes (son derivadas). `CC_LENNON` y `CC_GONZALO` ya
   existen con las fórmulas viejas (no conocen cajas de obra, dólares ni anulados): se
   reemplazan. Una obra nueva en OBRAS → la próxima corrida le crea su hoja. Valen lo corre
   con `--aplicar`. Si las fórmulas sobre las vistas no alcanzan, que el recálculo nocturno
   las escriba como valores; anotá cuál elegiste.
3. Un servicio cron más en Railway (como `cierre-semanal`) que llame a `/vistas/recalcular`
   cada noche: dejá el script y las instrucciones; lo crea Valen.
4. **`docs/tablero-looker.md`**: guía paso a paso para que Valen arme el Looker Studio
   (fuentes = cada `VISTA_*`, campos, filtros, las tres páginas de §5.21 y la del personal
   aparte). Sin presupuesto. Valen lo arma a mano; vos dejás los datos y la guía.

### M4 · Cierre

Actualizá `docs/handoff-fachado-core.md` (contratos nuevos, variables nuevas:
`CONCILIACION_DESDE`, el cron de vistas) y al final de este archivo: qué quedó, qué no, las
decisiones tomadas, la métrica de siempre (antes/después) y el orden de deploy y
migraciones.

---

## 2 · Gateway (`chatbot-contable`)

### G1 · Ajustes del 15/10 (≈30 min)

1. **«Es nuevo»**: la opción `"__nuevo__"` se muestra como botón «Es nuevo» y vuelve como
   `respuestas` con ese valor. Si hay más de 2 opciones cercanas + «Es nuevo», lista
   numerada como hoy.
2. **`consulta = "obra"`**: se pasa tal cual (el motor arma el texto). Frases: «¿cómo está
   Lennon?», «saldo de la obra X».
3. **Moneda en el acuse**: usar la moneda que trae cada total de `ConfirmarOut.obra`.

### G2 · El extracto por WhatsApp (§5.20) (≈2 h)

1. **Detectar el extracto**: un documento `.xlsx`/`.xls` (o mime de hoja de cálculo) cuyo
   nombre empiece con `CompartirDetalleMovimiento`, o cualquier hoja de cálculo cuando el
   texto diga «extracto» / «resumen del banco». **No** pasa por el agrupamiento de
   comprobantes ni por `/interpretar`.
2. Capturar como siempre (CAPTURA + Drive) y llamar a `POST /conciliar/extracto` con el
   link y el teléfono.
3. **Contestar el resumen** (el `texto` que arma el motor) y después **recorrer lo
   pendiente de a uno**, con el mismo circuito de fichas y preguntas de siempre:
   - primero los **lotes** (gastos bancarios, MeLi personal): un mensaje con el total y
     botones «✅ Cargar todo» / «Ver detalle» / «Después»;
   - después cada **línea sin cargar** como una ficha: «Vi un pago de $ 165.700 a Grimau el
     25/10 que no tengo cargado.» + las preguntas del motor + Confirmar. `msg_id =
     "banco:<hash_id>"`;
   - las **ambiguas**: «Este pago de $ X puede ser M-000031 o M-000034. ¿Cuál es?» con
     botones, y la respuesta va a `/conciliar/lote` con `{tipo: "asignar", hash_id, id_mov}`.
4. **No secuestra la conversación**: si el usuario manda un comprobante o un movimiento en
   medio, se atiende (regla A) y la conciliación queda en «pendientes»; «pendientes» y
   «banco» la retoman (`GET /conciliar/pendientes`).
5. **Tests**: el extracto de muestra con el motor mockeado según §3: resumen, lote,
   una línea sin cargar confirmada, una ambigua, interrupción con un comprobante y
   retomar.

### G3 · El lunes (≈1 h)

El cierre semanal del lunes suma el resumen del banco (§5.20). Mandárselo a Gabriel y a
Petrus requiere escribirles **fuera de la ventana de 24 h** de WhatsApp: hace falta una
**plantilla aprobada por Meta**. Dejá:
- el envío implementado con `send_template`, detrás de una variable
  `FACHADO_RESUMEN_LUNES` (apagada por defecto), con el nombre de plantilla configurable;
- el texto propuesto de la plantilla en `docs/clientes/fachado/plantilla-resumen-lunes.md`
  para que Valen la pida en Meta;
- si la ventana está abierta (el usuario escribió en las últimas 24 h), mensaje normal.

### G4 · Cierre

Actualizá `docs/handoff-fachado.md` y al final de este archivo: qué quedó, qué no, los
cambios de contrato si los hubo, y cómo probarlo en ensayo.

---

## 3 · Contratos entre los dos lados (fijos para esta mañana)

```jsonc
// POST /conciliar/extracto
{ "telefono": "549...", "adjunto": { "url": "...", "mime": "...", "nombre": "CompartirDetalleMovimiento-....xlsx", "sha256": "..." } }
→ {
  "importadas": 120, "repetidas": 7, "anteriores": 0,
  "conciliadas": 80, "a_revisar": 3, "sin_cargar": 15, "sin_banco": 4,
  "lotes": [ { "tipo": "gastos_bancarios" | "meli_personal", "cantidad": 12, "total": 45210.5,
               "hash_ids": ["…"], "texto": "12 gastos bancarios por $ 45.210,50" } ],
  "ambiguas": [ { "hash_id": "…", "texto": "Este pago de $ X …", "candidatos": ["M-000031","M-000034"] } ],
  "pendientes": [ { "hash_id": "…", "texto": "Vi un pago de $ 165.700 a Grimau el 25/10 que no tengo cargado.",
                    "interpretacion": { /* la misma forma que InterpretarOut, con fichas y preguntas */ } } ],
  "resumen": { "saldo_libro": 0, "saldo_banco": 0, "diferencia": 0, "por_cuenta": [ … ] },
  "texto": "Extracto importado: 120 líneas, 80 conciliadas… Diferencia: $ …"
}

// GET /conciliar/pendientes?telefono=549…   → la misma forma, solo lo que sigue abierto.

// POST /conciliar/lote
{ "telefono": "549...", "tipo": "gastos_bancarios" | "meli_personal" | "asignar" | "ignorar",
  "hash_ids": ["…"], "id_mov": null }      // id_mov solo con "asignar"
→ { "escritos": ["M-000040", …], "conciliadas": ["…"], "texto": "Cargué 12 gastos bancarios." }

// /confirmar de una línea sin cargar: msg_id = "banco:<hash_id>", ficha.extras.id_banco = "<hash_id>"
// → además de escribir, marca la línea CONCILIADO.

// Pregunta contratista con «Es nuevo»: opciones [..., "__nuevo__"]; respuesta {campo: "contratista", valor: "__nuevo__"}.
// /consultar: consulta = "obra" (nuevo).
// Sin presupuestos en esta etapa: ninguna vista ni contrato los incluye.
// ConfirmarOut.obra: cada total con su moneda.
```

Errores: 422 si el archivo no es un extracto reconocible (`{campo: "adjunto", detalle}`);
el gateway contesta «No reconocí ese archivo como un extracto del banco».

---

## Al terminar (las dos sesiones)

Debajo de esta línea, cada sesión deja su resultado con el formato de siempre: qué quedó
(con commits), qué no y por qué, decisiones tomadas, cambios de contrato, y los pasos de
deploy para Valen en orden.
