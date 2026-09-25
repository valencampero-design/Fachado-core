# Handoff proyecto → código · `fachado-core` · 25 de septiembre de 2026

**Semana 4 de 8.** Sale de la reunión con el arquitecto del 24/09. Antes de tocar nada,
**leé `CONTEXTO-FACHADO.md` v1.5 entero**: todo lo que pide este documento ya está escrito
ahí como decisión de negocio. Si algo de acá contradice al contexto, gana el contexto y
avisame.

---

## Qué cambió en el contexto

| § | Qué | En una línea |
|---|---|---|
| 5.1 · 5.14 | **Libro personal aparte** | Lo personal va a un segundo archivo; el del estudio recibe una línea semanal que lo resume |
| 5.8 | **Caja chica en cualquier obra** | Se marca con una `C` pegada a la obra. Los certificados de Moreno son plata de la obra |
| 5.11 | **Certificados = cuentas por cobrar** | El cruce entra ahora. Del certificado solo interesa el saldo a cobrar y la fecha |
| 5.12 | **Período de prueba** | Por ahora se confirma todo; después, lo completamente claro se escribe solo |
| 5.13 | **Petrus = mismas atribuciones** | Confirma solo, maneja efectivo, ve lo personal. Su reemplazo futuro no |
| 5.15 | **Etapas** | `Lennon1` es la etapa 1. Si la obra tiene etapas y no se indica, se repregunta |
| 5.16 | **Duplicados entre usuarios** | Si Gabriel y Petrus cargan lo mismo, se detecta y se pregunta |
| 5.17 | **Depósitos en negro** | Pasante informal: fuera del IVA y de la conciliación |

Hay **cuatro supuestos a confirmar** con el arquitecto (contexto §8). Construí el mecanismo
de forma que cambiar cualquiera sea tocar una regla, no rehacer el modelo.

---

## El orden

Cinco tandas. **Cada una deja el motor en producción funcionando**, así que se pueden
cortar en commits separados. Después de cada tanda, correr el corpus: **el 92 % no puede
bajar**.

---

## Tanda 1 · Datos del maestro

Rápida, y desbloquea lo demás.

**`USUARIOS`**
- Agregar columnas `ve_personal` y `auto_confirmar`, al final.
- Gabriel: `ve_personal = sí`, `auto_confirmar = no`.
- **Petrus: `5492944574499`**, rol `colaborador`, activo, `ve_personal = sí`,
  `auto_confirmar = no`.

**`TERCEROS`** — Petrus pasa a `activo`: vuelve a manejar efectivo del estudio.

**Pinturería Andina** — el comercio se llama así. Si ningún movimiento referencia a
«Pint Andina», renombrá la fila; si alguno la referencia, pasala a `inactivo`, creá
«Pinturería Andina» y dejá `pint andina` como alias. Nunca borrar.

**Cajas de obra en `CUENTAS`**
- Una fila **`Caja obra <obra>`** por cada obra con `tipo = obra_terceros` (hoy son siete),
  con `tipo = caja_obra`, `concilia_contra_banco = no`.
- La fila mal cargada llamada «caja_obra» pasa a `inactivo`.
- Las obras propias **no** llevan caja: el comitente es él mismo.

**Los tres cobros de Moreno** (`M-000007` a `M-000009`: certificado 4, 4 extras y pintura)
son certificaciones, o sea plata de la obra: su `cuenta` pasa de `Efectivo` a
**`Caja obra Moreno`**. Son filas semilla cargadas a mano antes de que existiera
`/confirmar`, así que se corrigen directo. **De acá en adelante ninguna fila confirmada se
edita**: cómo se corrige un movimiento confirmado es una decisión de diseño todavía abierta.

Efecto esperado: el saldo del estudio **baja $5.245.596** y aparece esa plata en la caja de
Moreno. Verificalo.

**`MOVIMIENTOS`** — agregar al final, en este orden: `etapa`, `informal`, `ref_comprobante`.
La última guarda número de operación, número de cheque o el hash del archivo: es lo que
usa la detección de duplicados (tanda 3).

---

## Tanda 2 · El token de obra: etapa y caja chica

La sintaxis nueva es **`<obra>[<etapa>][C]`**:

| Escribe | Obra | Etapa | Cuenta |
|---|---|---|---|
| `Barba/Lennon` | Lennon | — | la que corresponda |
| `Barba/Lennon1` | Lennon | 1 | la que corresponda |
| `Barba/LennonC` | Lennon | — | `Caja obra Lennon` |
| `Barba/Lennon1C` | Lennon | 1 | `Caja obra Lennon` |

Reglas del parser:

- **Primero intentá el token entero** contra obras, códigos y alias. Recién si no matchea,
  probá sacarle una `C` final y un número final. **Solo aceptás el recorte si lo que queda
  matchea una obra.** Así una obra cuyo nombre termine en número o en «c» nunca se rompe.
- Mayúsculas y minúsculas dan igual. `lennon1c` vale.
- La palabra suelta **`caja`** en el mensaje equivale a la `C`.
- Si viene la `C` y la obra **no tiene fila de caja** en `CUENTAS`: no inventes la cuenta.
  Pregunta en la ficha y advertencia.

**Hoja nueva `ETAPAS`** en el maestro: `obra · etapa · descripcion · estado`. Arranca vacía;
las etapas las carga el arquitecto.

- **Obra sin filas en `ETAPAS`**: no tiene etapas y el bot nunca las pregunta.
- **Obra con etapas y el mensaje no dice cuál**: pregunta con botones, una opción por etapa
  activa.
- **Viene un número pero la obra no tiene etapas**: advertencia y `etapa` vacía. El motor no
  escribe maestros desde `/interpretar`.

**Ingresos de obras administradas.** Un `INGRESO` que dice certificado (`cert`,
`certificado`) en una obra con servicio `administración` o `todo` va a la **caja de esa
obra**, no a la caja del estudio. Un ingreso que dice honorarios (`hon`, `honorarios`) va al
estudio. Si no dice ninguna de las dos en una obra administrada, pregunta.

**Depósitos.** La palabra **`depósito`** (con o sin tilde) marca un **`PASANTE`** con
`informal = sí`: una sola fila, obra y contratista del mensaje, suma a lo adelantado y a lo
pagado de la obra y no toca la caja del estudio. Los informales quedan **excluidos de todo
cálculo de IVA y de la conciliación**: dejá ese filtro hecho aunque esos módulos no existan
todavía.

---

## Tanda 3 · Duplicados entre usuarios y período de prueba

### El mismo hecho cargado dos veces

Esto es distinto de la idempotencia por `msg_id`, que ya funciona: acá son **dos mensajes
distintos**, de Gabriel y de Petrus, que describen el mismo pago.

En `/interpretar`, antes de devolver la ficha, buscá en el libro del estudio **y en el
personal**:

| Fuerza | Criterio |
|---|---|
| **Fuerte** | Misma `ref_comprobante`: número de operación, número de cheque o hash del archivo. WhatsApp manda el `sha256` del adjunto en el payload: pedile al gateway que lo pase |
| **Probable** | Mismo importe, fecha ±3 días, y mismo contratista **o** misma obra |

Si hay coincidencia, la ficha trae `posible_duplicado` con `id_mov`, `cargado_por`, `fecha`
y `fuerza`, y **una pregunta**: *«Petrus ya cargó un pago igual el 23/9. ¿Es el mismo?»* con
dos botones. **Nunca descartes solo**, ni siquiera con coincidencia fuerte.

Dos casos reales que tienen que preguntar y **no** fusionarse, porque el arquitecto confirmó
que son pagos distintos:

- los dos `AUSTRAL/IVA` del 4/9, mandados con un segundo de diferencia;
- el cheque 510 y la transferencia a Eco Aislación: $4.032.391,70, mismo día y mismo
  contratista, pero con distinta referencia.

### Período de prueba

`/interpretar` devuelve un campo nuevo, **`requiere_confirmacion`**:

- `auto_confirmar = no` para el usuario → **siempre `true`**. Es el estado actual de los dos.
- `auto_confirmar = sí` → `false` solo si se cumple **todo**: importe, fecha y destinatario
  del comprobante; obra y contratista del maestro; sin preguntas; sin conflictos; sin
  `posible_duplicado`. Si falla cualquiera, `true`.

El gateway obedece ese campo. `/confirmar` no cambia. El paso de `no` a `sí` lo hace A&C a
mano, por usuario, cuando la métrica de ese usuario lo justifique.

---

## Tanda 4 · El libro personal

Es la tanda más grande. Leé §5.14 antes.

**El archivo.** A&C crea «FACHADO — Personal» con la misma estructura que `MOVIMIENTOS` y lo
comparte con la service account. Variable nueva: `FACHADO_PERSONAL_SHEET_ID`. Sin maestros
propios: los maestros siguen siendo los del archivo del estudio.

**`/confirmar` rutea por `tipo_gasto`.** `personal` → libro personal; el resto → libro del
estudio.
- Secuencia de ids propia en el personal: `P-000001`.
- La idempotencia por `msg_id` tiene que mirar **los dos libros**.
- El comprobante va a `personal/<AAAA-MM>/`, como ya está.

**Acceso.** Un usuario con `ve_personal = no` no puede confirmar movimientos personales ni
recibir datos del libro personal en ninguna respuesta: 403. Hoy los dos usuarios tienen
`sí`, así que probalo con un usuario de test.

**La línea semanal.** Endpoint nuevo **`POST /cierre-semanal`**, con `X-API-Key`:

- Para una semana ISO —la anterior, por defecto— suma los egresos personales **por cuenta**
  y escribe en el libro del estudio **una fila por cuenta**: `EGRESO`,
  `tipo_gasto = personal`, descripción `Gastos personales · semana 2026-W39`,
  `concilia = FALSO`, `origen = CIERRE`.
- **Idempotente** por semana y cuenta: correrlo dos veces no duplica.
- **Cargas atrasadas.** Si después del cierre entra un personal con fecha de una semana ya
  cerrada, la próxima corrida escribe **una fila de ajuste por la diferencia**. Nunca se
  edita la línea anterior: el libro es append-only.
- Se dispara con un cron de Railway **los lunes a las 8 hora argentina**, y también se
  puede llamar a mano.

**Saldo del estudio.** Suma las líneas semanales, no las filas personales. Queda hasta una
semana atrasado en lo personal: es lo esperado, y está escrito en el contexto.

---

## Tanda 5 · Certificados y `/consultar`

### Certificados

Hoja nueva **`CERTIFICADOS`**: `obra · etapa · numero · fecha · saldo_a_cobrar · fuente ·
msg_id · cargado_por · comprobante_url`.

- `/interpretar` reconoce un certificado **como documento, no como gasto**: devuelve una ficha
  de tipo `CERTIFICADO`, y `/confirmar` lo escribe en `CERTIFICADOS`, no en `MOVIMIENTOS`.
- Un cobro (`INGRESO` con certificado) **cancela** al certificado de misma obra, etapa y
  número. Pendiente de cobro = certificado − cobros.

**Llega por las dos vías, y las dos valen lo mismo.** No hay un formato de texto obligatorio:
el arquitecto puede escribir el certificado como le salga —`Certificado 5 Moreno1
$3.200.000`, `cert 2 etapa 1 Lennon 1.500.000 del 20/9`, lo que sea— y se resuelve con el
mismo resolver de siempre: diccionario primero, LLM para lo que falte. **No acotes la
sintaxis.** Si falta un dato, se pregunta.

#### El PDF: hay un ejemplo real

Está en **`tests/fixtures/cert_loguercio_etapa3.pdf`**. Es un certificado de una obra ya
cerrada, de febrero de 2024, pero el formato es el que usa hoy. Lo genera él desde Excel, así
que **el texto se extrae limpio con pypdf: no hace falta visión**.

**El único monto que importa es el punto 7 de la primera tabla:**

```
7    Saldo a cancelar en la presente certificación (5+6):     3.402.032,64
```

Número de certificado, fecha y obra se toman **solo para identificarlo**. Ningún otro número
del documento se guarda: ni el monto del contrato, ni el anticipo, ni el fondo de reparo, ni
el ajuste por CAC.

Lo que sale de ese PDF, y de dónde:

| Campo | Valor | De dónde |
|---|---|---|
| `saldo_a_cobrar` | 3.402.032,64 | Punto 7. **Anclá la búsqueda en el texto** «Saldo a cancelar en la presente certificación», no en el número 7 ni en la posición |
| `numero` | 1 | `CERTIFICADO AUSTRAL Nº: 1` |
| `fecha` | 2024-02-19 | `FECHA: 19/2/2024` — día y mes **sin cero adelante** |
| `obra` | — | Ver abajo |
| `etapa` | — | Ver abajo |

**Tres trampas de este formato:**

1. **«Austral» es el nombre de su constructora**, no la obra. El documento dice
   `CERTIFICADO AUSTRAL` y `www.Caustral.com.ar`. En el maestro, Austral es la obra de
   indirectos del estudio. **La palabra Austral dentro de un certificado nunca resuelve a esa
   obra.**
2. **La obra no viene con el nombre del maestro.** El PDF dice `OBRA: Vivienda Multifamiliar
   Etapa 2` y `UBICACIÓN: tres cerros`. Lo que sí identifica la obra es el destinatario,
   `Sr. Roberto Lo Guercio`: buscalo contra `OBRAS.comitente`. Si no aparece, pregunta. Y como
   siempre, **si el texto del mensaje dice la obra, manda el texto**: el comprobante manda en
   montos, fecha y número; el texto, en obra y etapa (contexto §5.2).
3. **La etapa se contradice dentro del mismo caso**: el cuerpo dice «Etapa 2» y el nombre del
   archivo dice «Etapa 3». Orden de prioridad: el texto del mensaje; si no dice, el nombre
   del archivo y el cuerpo; **si esos dos no coinciden, no elijas: `conflictos` y pregunta.**

Dos detalles de parseo:

- Los montos vienen en formato argentino, `3.402.032,64`, pero **no siempre con separador de
  miles**: en el mismo documento aparece `348143,38`. El parser tiene que aceptar los dos.
- Hay un control gratis: el punto 7 es la suma de los puntos 5 y 6. Si los podés leer y la
  diferencia supera $1, advertencia. En el ejemplo da $0,01 de redondeo: tiene que pasar.

Este ejemplo, de paso, confirma el supuesto 1 del contexto (§5.15): es el certificado
**Nº 1 de la etapa 2**, o sea que la numeración de certificados es por etapa. Etapa y
certificado son dos cosas distintas.

### `/consultar`

Las tres preguntas que hizo el arquitecto. Cada respuesta devuelve los números **y** un
campo `texto` listo para mandar por WhatsApp.

| Pregunta | Qué devuelve |
|---|---|
| «¿Cuántos pagos se le hicieron a X por la obra Y?» | Cantidad, total y detalle: fecha, importe, medio, quién cargó |
| «¿Cuánto va gastado en cada obra, de mano de obra y de materiales?» | Total por obra abierto por `rubro_1`. **Incluye lo que pagó el comitente**: es costo de la obra, aunque no sea plata del estudio. Mostralo separado |
| «¿El comitente pagó todas las certificaciones?» | Por obra y etapa: certificado, cobrado, pendiente |

Todo filtrado por `ve_personal` del que pregunta.

---

## Lo que NO va en esta tanda

- **IVA y facturas emitidas.** Incluye el control de los cobros del banco contra las
  facturas emitidas. Se planifica aparte.
- **Conciliación bancaria.**
- **Cuentas por pagar a proveedores** y el reporte de pendientes para el comitente: idea
  para una etapa futura, a presupuestar.
- **Cómo se corrige un movimiento ya confirmado**: decisión de diseño abierta.
- **Conectar el gateway**: es otro repo y otra sesión. Anotá en el handoff lo que el gateway
  va a necesitar de lo que construiste acá.

Siguen abiertas, no las implementes: qué es «Estudio» en `Estudio/Austral`, y a qué
certificado corresponden las cuatro fotos del 11/9 que dicen solo «ingreso».

---

## Casos nuevos para el corpus

Agregalos a `tests/` con el resultado esperado:

| Mensaje | Esperado |
|---|---|
| `Barba/Lennon1C` | Lennon, etapa 1, `Caja obra Lennon` |
| `Barba/LennonC` | Lennon, sin etapa, `Caja obra Lennon` |
| `Barba/Lennon1` con Lennon sin etapas cargadas | Lennon, etapa vacía, advertencia |
| `Ingreso Moreno/cert. 4/efectivo $2.600.000` | `INGRESO`, `Caja obra Moreno`, certificado 4 |
| `Ingreso Moreno/honorarios $500.000` | `INGRESO`, caja del estudio |
| `Deposito Marcelo/Moreno $300.000` | `PASANTE`, `informal = sí`, Moreno |
| `Certificado 5 Moreno1 $3.200.000` | Ficha `CERTIFICADO`, Moreno, etapa 1, número 5 |
| `cert 2 etapa 1 Lennon 1.500.000 del 20/9` | Ficha `CERTIFICADO`, Lennon, etapa 1, número 2, fecha 20/9 |
| `cert_loguercio_etapa3.pdf` sin texto | `saldo_a_cobrar` 3.402.032,64, número 1, fecha 2024-02-19; **obra y etapa preguntan** (Lo Guercio no está en OBRAS; etapa 2 contra 3) |
| El segundo `AUSTRAL/IVA` del 4/9 | `posible_duplicado` probable, pregunta |

---

## Al terminar

Decime:

- el número del corpus antes y después, **por usuario**;
- cuánto bajó el saldo del estudio después de mover los cobros de Moreno;
- qué necesita el gateway de todo esto: campos nuevos en la ficha, `requiere_confirmacion`,
  la pregunta de duplicado, el `sha256` del adjunto, el cron;
- qué decisiones tomaste que no estaban escritas en el contexto, para subirlas.

Commit por tanda, **sin pushear**.
