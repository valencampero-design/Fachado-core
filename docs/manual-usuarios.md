# Manual del bot de Fachado

*Para Gabriel, Petrus y quien se sume al estudio. Versión del 28/10/2026.*

Este manual cuenta cómo usar el bot de WhatsApp del estudio: qué mandarle, cómo lo entiende,
qué te va a preguntar y dónde queda todo después. Está armado a partir de cómo funciona hoy el
sistema. Lo que todavía no está definido está marcado **«a confirmar»**.

---

## 1 · Qué es y para qué sirve

- Es un contacto de WhatsApp al que le mandás los pagos, los cobros y los comprobantes del estudio.
- El bot los lee, arma una **ficha** y te pide que la confirmes.
- Cuando confirmás, queda escrito en la **planilla** del estudio (o en la planilla personal, si es personal).
- De esa planilla salen solas las cuentas corrientes de cada obra y el tablero.
- La idea es que cargues **una sola vez**, desde el celular, y que nadie tenga que copiar números a mano.

---

## 2 · Cómo cargar un pago o un cobro

### La forma corta

Escribí la obra y a quién le pagaste, separados por una barra:

```
Lennon/Miguel
```

Si mandás el comprobante (foto o PDF) junto, **con eso alcanza**. El importe, la fecha y la
cuenta salen del comprobante. El rubro sale del que se usa siempre con ese contratista.

- **El orden no importa.** `Lennon/Miguel` y `Miguel/Lennon` son lo mismo.
- **Mayúsculas y tildes dan igual.** `barba/lennon1c` se entiende.
- Podés usar los apodos de siempre: `Barba`, `Felipe J`, `Ecoaislaciones`, `Lalo`.

### Si no hay comprobante, poné el importe

```
Metro Gas/Grigera Galpón 11.750
Barba/Hua Huan/efectivo $20.000
Austral/combustible 77000
```

El importe se puede escribir con o sin `$`, con puntos de miles o sin ellos.

### Lo que podés agregar

| Para decir… | Escribí | Ejemplo |
|---|---|---|
| Que es un **cobro** | `Ingreso` o `cobro` al principio | `Ingreso Moreno/honorarios $500.000` |
| Que es un **pago** | Nada (es lo normal), o `Pago` | `Pago Moreno` + comprobante |
| La **fecha** | `20/9`, `del 20/9`, `04/09/26` o `28 de septiembre` | `cert 2 etapa 1 Lennon 1.500.000 del 20/9` |
| Que fue en **dólares** | `US$`, `u$s`, `usd` o `dólares` | `Austral/Valentín 400 dólares` |
| Que salió del **efectivo** | `efectivo` | `Barba/Hua Huan/efectivo $20.000` |
| Que salió de la **caja de la obra** | `caja`, `caja chica` o una `C` pegada a la obra | `Barba/LennonC` |
| Que salió del **efectivo del estudio** (en una obra con caja) | `efectivo del estudio` | `Lennon/Miguel/efectivo del estudio $500.000` |
| La **etapa** | El número pegado a la obra, o el nombre | `Barba/Lennon1`, `Marcelo Maragaño/Moreno extras` |
| El **rubro** | La palabra del rubro | `Moreno/Tucu zinguería`, `Austral/contador` |
| Que es **personal** | `Retiro`, `casa` o `particular` | `Retiro/súper $45.000` |

Si no ponés la fecha, se usa la del comprobante; si no hay comprobante, la del día del mensaje.

### De qué cuenta salió la plata

El bot decide la cuenta en este orden:

1. **Lo que vos escribiste**: `efectivo`, `caja`, `banco`, `mercado pago`.
2. **Lo que dice el comprobante**:
   - una transferencia o un débito → **Banco**;
   - un cheque → **Chequera**;
   - un comprobante de Mercado Pago pagado con plata de la cuenta → **Mercado Pago**;
   - un comprobante de Mercado Pago pagado **con tarjeta de débito** → **Banco** (la plata salió del banco).
3. **Lo que dice la obra**: en Lennon, el comitente paga directo, así que va como **«Pagado por el comitente»**.
4. Si nada lo dice, el bot pone **Banco / transferencia** y en la ficha aparece marcado **(supuesto)**. Si no fue así, corregilo.

### Dólares

- Escribí siempre la moneda: `US$ 400`, `400 dólares`, `u$d 400`. **Un importe sin moneda se toma en pesos.**
- Cuando cargás algo en dólares, el bot te pregunta **a qué tipo de cambio fue**. Contestá solo el número: `1450` o `1.450,50`.
- No pregunta el tipo de cambio cuando:
  - el comprobante ya lo trae (por ejemplo, un recibo que dice `US$ 2.000 x 1535`);
  - pagás en dólares desde una caja de obra que está en dólares (se descuenta directo en dólares);
  - es el segundo pago del día desde la misma caja en dólares: reusa el tipo de cambio del primero y lo muestra en la ficha («TC 1.450 (de hoy)»).
- «Banco USD» es el nombre de la cuenta en dólares. `pasé $1.450.000 del banco al banco usd` sigue siendo un importe en pesos.

---

## 3 · Comprobantes

### Qué podés mandar

- **Fotos** (tickets, recibos, capturas de transferencias).
- **PDF** (los comprobantes del homebanking, de Mercado Pago, cheques, certificados).

### Qué lee el bot de un comprobante

- **Importe y fecha.**
- **A quién se le pagó**: nombre o razón social, y CUIT.
- **Número de operación o de cheque.**
- **Cómo se pagó**: transferencia, cheque, efectivo, Mercado Pago (y si fue con débito o crédito).
- **Tipo de cambio**, si el recibo lo dice.

Si reconoce el CUIT o el nombre del destinatario, ya sabe qué contratista es, aunque no lo
escribas.

### Qué conviene mandar junto

Mandá **el comprobante y un texto corto** con la obra y el contratista:

```
[foto del comprobante]
Lennon/Miguel
```

- El texto puede ir como epígrafe de la foto o en un mensaje aparte.
- **El texto puede ir antes o después** del comprobante. El bot espera hasta **90 segundos** para juntarlos.
- Si mandás **varios comprobantes seguidos y después un texto**, el texto vale para todos: el bot arma una ficha por comprobante y las confirmás **todas juntas** con un solo botón.
- Si mandás un comprobante **sin texto**, a los 90 segundos el bot lo lee solo y te pregunta lo que falte (casi siempre, la obra).

### Quién manda en cada dato

- **El comprobante manda** en importe, fecha, destinatario y número de operación.
- **Tu texto manda** en obra, contratista, rubro y descripción.
- Si el texto y el comprobante **no coinciden en el importe o la fecha**, el bot no elige: te muestra los dos y te pregunta cuál vale.

### Lo que no es un movimiento

Una foto de obra, un «gracias», un «después te paso el ticket»: el bot lo guarda igual y te
contesta:

```
Recibido ✅ No encontré un movimiento.
```

### Audios

El bot pasa los audios a texto y los trata como un mensaje escrito. Igual conviene escribir: es
más preciso con nombres e importes. *(Cómo se comporta con audios en la carga real: a confirmar.)*

---

## 4 · Las preguntas del bot, y cómo confirmar, corregir o anular

### La ficha

Antes de escribir nada, el bot te muestra una ficha. Al lado de cada dato dice de dónde lo sacó:

```
📋 · Egreso
$ 7.084.000 · 03/10   (del comprobante)
Obra: Lennon, etapa 1 (en curso)   (del texto)
Contratista: Miguel Soto · Mano de obra   (del texto)
Cuenta: Caja obra Lennon · Efectivo   (inferido)
Para: obra
```

Debajo vienen tres botones:

- **✅ Confirmar**: lo escribe en la planilla.
- **✏️ Corregir**: te pregunta «¿Qué cambio?» y le escribís el cambio (`efectivo`, `Moreno`, `$ 150.000`, `es un ingreso`).
- **❌ Descartar**: no lo carga. Igual queda guardado en la copia de respaldo.

Las marcas que podés ver:

| Marca | Qué quiere decir |
|---|---|
| (del comprobante) | Lo leyó del comprobante |
| (del texto) | Lo escribiste vos |
| (del maestro) | Sale de la planilla de obras y contratistas |
| (inferido) | Lo dedujo por una regla (por ejemplo, «efectivo» en Lennon es la caja) |
| (supuesto) | No había ningún dato y puso lo más probable. **Mirala** |
| (de la ficha anterior) | Lo trajo de la ficha que estabas corrigiendo |
| 📕 Libro personal | Va a la planilla personal |
| ℹ️ … | Un aviso: contratista u obra nueva, tipo de cambio reusado, etc. |

**Mientras dure el período de prueba, el bot pide confirmación siempre**, aunque esté todo claro.

### Las preguntas

El bot pregunta **solo lo que no puede deducir**. Las más comunes:

- «¿A qué obra?»
- «¿Qué rubro?»
- «¿A quién se le pagó?»
- «¿Cuál es el importe?»
- «¿Qué etapa de Moreno?»
- «¿A qué tipo de cambio?»
- «Este ingreso de Moreno, ¿qué es?» (Certificación, Honorarios o Adelanto para la caja de obra)
- «¿Quién es «Marce»?» (cuando un apodo puede ser más de una persona)

Cómo contestarlas:

- **Con 3 opciones o menos**: vienen como **botones**. Tocá uno.
- **Con más de 3**: vienen como **lista numerada**. Contestá con **el número** (`4`) o **escribiendo el nombre** (`Club y deporte`).
- **Sin opciones** (importe, tipo de cambio): escribí el dato.
- Si no sabés qué te pide, escribí `¿cuál?` o `qué falta` y te lo explica.
- Podés contestar con otro dato en vez de la opción: `efectivo`, `caja chica`, `es un ingreso`, `lo dejamos en dólares`. El bot lo suma a la ficha.

### Si cambiás de tema en el medio

- **Si mandás otro movimiento** mientras el bot espera una respuesta, arranca una ficha nueva y la anterior queda **pendiente**. Te avisa:

  ```
  Dejo pendiente el movimiento anterior (1 sin confirmar). Escribí "pendientes" cuando quieras retomarlo.
  ```

- **Si le hacés una consulta** («¿cuánto hay en la caja de Lennon?»), te contesta y vuelve a la pregunta que tenía abierta.
- **Si mandás un comprobante mientras una ficha espera Confirmar**, te pregunta: «¿Este comprobante es del movimiento que estás confirmando?» → **Sí, es de ese** / **No, es otro**.

### Comandos que entiende

| Escribí | Qué hace |
|---|---|
| `pendientes` | Retoma la primera ficha que quedó sin confirmar, de a una |
| `cancelar`, `descartar`, `dejalo`, `olvidalo` | Deja de lado la ficha que tiene una pregunta abierta (queda en «pendientes») |
| `corregir M-000012` | Corrige un movimiento ya cargado |
| `anular M-000014` | Anula un movimiento ya cargado |
| `banco` o `extracto` | Retoma lo pendiente de la conciliación con el banco |

### El acuse

Cuando confirmás, el bot te contesta con el **número del movimiento**:

```
✅ M-000123 · Lennon. Pagado en la obra: $ 18.500.000. Caja Lennon: US$ 4.200
```

- **M-** son los movimientos del estudio; **P-** los personales.
- Guardá ese número: es el que se usa para corregir o anular.
- Si diste de alta algo nuevo, lo dice: «Di de alta a … como contratista» o «Di de alta la obra Minas».

### Corregir algo ya cargado

La planilla **no se edita nunca**. Para corregir:

1. **Respondé al acuse** de ese movimiento (mantené apretado el mensaje → Responder), o escribí `corregir M-000012`.
2. El bot te muestra el movimiento y pregunta «¿Qué cambio?».
3. Escribí el cambio: `Moreno`, `efectivo`, `$ 150.000`, `es de Marcelo Orellana`.
4. Te muestra la ficha corregida con dos botones: **✅ Anular y cargar** / **❌ Dejar como está**.

Al confirmar, el bot anula el original (deja una fila que lo compensa) y carga el correcto.
Queda el rastro de qué se cargó, quién lo corrigió y cuándo.

### Anular algo ya cargado

Escribí el pedido **con el número**:

```
anular M-000014
borrá el M 14
el M 0014 está mal, hay que eliminarlo
```

El bot te muestra el movimiento y pregunta «¿Lo anulo?» → **🗑 Anular M-000014** / **No**.
La fila no se borra: queda con su anulación al lado.

> **Sin el número no puede.** «Borrá el pago de Miguel de ayer» no alcanza: el bot no adivina
> cuál es. Buscá el número en el acuse o en la planilla.

### Si algo no sale

- Si el bot no puede cargar algo, **te dice qué falta** («No lo pude cargar: falta cuenta») y te deja corregir o descartar.
- Si falla dos veces seguidas, te ofrece **🕓 Dejar para revisar**: queda guardado y lo mira Valen.
- Si el sistema está caído, igual te contesta «Recibido ✅ Quedó guardado, lo reviso y te aviso». **Nunca se pierde un mensaje**: todo lo que mandás queda en una copia de respaldo antes de procesarse.

---

## 5 · Casos especiales

### Lo personal (retiros)

Cualquier mensaje con **`Retiro`**, **`casa`** o **`particular`** es personal. «Retiro» manda
siempre, aunque el proveedor sea uno de obra:

```
Retiro/súper $45.000
Electricidad Angostura/Retiro $9.000
Retiro/Abucoque + comprobante
```

- Va a la **planilla personal**, no a la del estudio. Los números empiezan con **P-**.
- A un gasto personal **no se le pregunta la obra**. Si nombrás un inmueble personal (Sur, Abucoque, Belelli, Gessel), queda imputado a ese inmueble.
- Los rubros que ofrece son los personales (Súper, Casa, Club y deporte…).
- Si el destinatario no está en la planilla, **no se da de alta**: queda en la descripción.
- Lo personal solo lo ven las personas habilitadas para verlo. Si Petrus escribe «Retiro», es lo personal de Gabriel.

### Austral (gastos del estudio)

`Austral` es la obra de los gastos del estudio:

```
Austral/contador $150.000
Austral/nafta $45.000
Austral/generales $12.000
Sofia/Austral $100.000
```

- Los rubros que ofrece son los del estudio (Contador, Internet, Sueldos…), nunca los de obra.
- Un **ticket de estación de servicio** (YPF, Shell, Axion, Puma, Gulf) va solo a **Combustible**. Si no decís a qué es, la única pregunta es «¿A qué obra?», con Austral primero.
- Si un apodo puede ser dos personas (por ejemplo «Sofi»), el bot usa el comprobante o el destino para saber cuál es; si no puede, pregunta con dos botones.

### Contratista nuevo

Si nombrás a alguien que no está en la planilla y **la obra está en el mensaje**, el bot lo da de
alta al confirmar:

```
Lennon/Juan Perez $1.000
```

- La ficha avisa: «Juan Perez es nuevo: lo agrego como contratista».
- Si hay comprobante, el nombre completo y el CUIT salen de ahí; lo que escribiste queda como apodo.
- El rubro sale de tu texto (`Lennon/Juan Perez/zinguería`). Si no lo decís, te pregunta una sola vez.
- Si el nombre se parece a alguien que ya existe, pregunta «¿Quién es «Rodri»?» con los parecidos **y un botón «Es nuevo»**.

### Obra nueva

Si nombrás algo que no conoce y **no hay ninguna obra en el mensaje**:

```
No conozco «Minas». ¿Es una obra nueva o un contratista nuevo?
[Obra nueva] [Contratista nuevo]
```

Con **Obra nueva**, al confirmar la da de alta. Tipo de obra, servicio y comitente los completa
Valen después. Su cuenta corriente aparece sola a la noche siguiente.

### Contratista inactivo

Si escribís el nombre exacto de alguien que figura como inactivo, pregunta «X está inactivo,
¿lo reactivo?» → **Reactivar** / **Es otro**.

### Pagos que hace el comitente

- **Lennon**: el comitente paga directo. Mandá el comprobante con `Lennon/Contratista` y el bot lo carga como **«Pagado por el comitente»**. Sirve para seguir lo que se pagó en la obra; no mueve la caja del estudio.
- **Depósito** («en negro»): escribí `Depósito` y queda como pago informal del comitente, fuera del banco y del IVA:

  ```
  Deposito Marcelo/Moreno $300.000
  ```

### Cajas de obra (plata del comitente en efectivo)

La caja de una obra es la plata que el comitente te dio para pagar esa obra. **No es del
estudio**: es plata a rendir.

- Tienen caja las obras de terceros: Lennon, Moreno, Cerro Bayo, Lumaia, Muelle de piedra, Tonga y Moquehue. **La caja de Lennon está en dólares.**
- Para pagar desde la caja, cualquiera de estas sirve:

  ```
  Lennon/Miguel efectivo $500.000
  Barba/LennonC
  Lennon/Miguel 2000 dólares de la caja
  ```

- **En una obra con caja, «efectivo» es la caja de la obra.** Si pagaste con el efectivo del estudio, decilo: `efectivo del estudio`.
- Para cargar lo que entra a la caja:

  ```
  Ingreso Lennon caja US$ 20.000
  ```

  Si escribís solo `Ingreso Lennon $100.000`, te pregunta qué es y una opción es «Adelanto para la caja de obra».

### Cobros de certificados y honorarios

```
Ingreso Moreno/cert. 4/efectivo $2.600.000
Ingreso Moreno/cert 4 extras $500.000
Ingreso Moreno/honorarios $500.000
```

- Un cobro de **certificado** en una obra administrada entra a la **caja de esa obra** (no es del estudio).
- Un cobro de **honorarios** entra al estudio.
- Si no decís cuál es, pregunta: Certificación, Honorarios o Adelanto para la caja de obra.
- En Moreno hay dos etapas en curso (1 y extras): si no decís cuál, pregunta.

### Cargar un certificado emitido

Lo que falta cobrar de cada certificado se lleva aparte. Mandalo como texto o como PDF:

```
Certificado 5 Moreno1 $3.200.000
cert 2 etapa 1 Lennon 1.500.000 del 20/9
```

- Del PDF solo toma **obra, etapa, número, fecha y el punto 7** («Saldo a cancelar en la presente certificación»).
- Si el texto y el PDF dicen cosas distintas (número, etapa), pregunta.
- «Austral» dentro de un certificado es la constructora que lo firma, nunca la obra: si no nombrás la obra, la pregunta.
- Si cargás el mismo certificado dos veces, te avisa.

### Etapas

- Lennon tiene la **etapa 1 en curso**: si no decís la etapa, usa esa.
- Moreno tiene **1 y extras en curso**: si no decís cuál, pregunta.
- Si nombrás una etapa que figura como futura (`Barba/Lennon2`), pregunta si la pasa a «en curso».
- Las obras sin etapas nunca preguntan la etapa.

### Varios pagos en un mensaje

- **Varios comprobantes y un texto**: una ficha por comprobante, con la obra y el contratista del texto. Se confirman juntas con un solo botón.
- **Dos movimientos en un mismo texto**: el bot los separa cuando están unidos con «e imputar», «e ingresar», «e registrar» o «e cargar»:

  ```
  Ingreso Moreno/cert. 22 e imputar pago aparte Marcelo/Moreno
  ```

  Fuera de esa forma, conviene **un mensaje por movimiento** *(otras formas de juntar dos movimientos: a confirmar)*.

### Transferencias entre cuentas (traspasos)

Sacar del cajero, reponer una caja o pasar plata entre cuentas no es un gasto: es un **traspaso**.

```
saqué efectivo $50.000
Extracción 100.000
repuse la caja de LennonC con efectivo 80.000
pasé de la caja de obra Moreno al banco 1.000.000
pasé 1.000 dólares del banco usd al banco
```

- Decí **de dónde sale y a dónde entra**. Si falta uno, pregunta.
- Entre pesos y dólares pregunta el tipo de cambio.
- Un pago desde la caja chica (`Barba/LennonC`) sigue siendo un pago, no un traspaso.

### Extractos del banco y conciliación

*Esto lo hace Petrus. Arranca el 1/11: noviembre es el primer mes que se cierra contra el banco.
Lo de octubre se importa pero no se pregunta.*

**Qué mandar, una vez por semana:**

- Los **cuatro extractos del banco** en Excel (las tres cuentas en pesos y la de dólares), tal como los baja el homebanking.
- El **reporte de Mercado Pago** en PDF.

**Cómo mandarlos:**

- Los Excel del banco los reconoce solos por el nombre del archivo. Si les cambiaste el nombre, escribí `extracto` en el mensaje.
- El PDF de Mercado Pago mandalo con un texto que diga **`Mercado Pago`** o **`reporte`**. Si no, el bot lo toma como un comprobante más.
- Mandalos **todos seguidos**. El bot contesta «Dale, lo reviso contra los libros. Un minuto.» y espera 90 segundos desde el último antes de procesarlos todos juntos.

**Qué pasa después:**

1. Un **resumen**: saldo según la planilla, saldo según el banco, la diferencia y cuántas líneas quedan.
2. Lo que coincide se marca solo.
3. Lo que queda, **de a una**:
   - **Gastos bancarios** en un lote: «12 gastos bancarios por $ X. ¿Los cargo?» → **Cargar todo** / **Ver detalle** / **Después**. Si están en dólares, pregunta un tipo de cambio para todo el lote.
   - **Compras de Mercado Libre sin comprobante**, en otro lote, como gasto personal sin clasificar.
   - **Un pago que puede ser de dos movimientos**: botones con los dos y **Ninguno**.
   - **Un pago que no está cargado**: «Vi un pago de $ 165.700 a Grimau el 25/10 que no tengo cargado.» y pregunta lo que falte, como una ficha más, con **Confirmar**.
   - **Un pase entre cuentas**: «Vi que pasaste $ 300.000 del banco a Mercado Pago el 28/10. ¿Lo cargo como traspaso?».
4. Las preguntas le llegan **a quien mandó el extracto**.
5. Si tocás **Después** o te vas a otra cosa, retomás escribiendo `banco`.

Los **pagos de tarjeta de crédito** (First Data, Visa) por ahora son una pregunta por línea:
cómo se cargan está *a confirmar con Gabriel*.

---

## 6 · Consultas

Preguntale en castellano, nombrando la obra o el contratista. No hace falta la barra.

| Querés saber | Escribí |
|---|---|
| Cómo está una obra | `¿cómo está Lennon?` · `saldo de la obra Moreno` |
| Cuánto hay en una caja de obra | `¿cuánto hay en la caja chica de Lennon?` |
| Cuánto se le pagó a alguien | `¿Cuánto le pagué a Felipe J?` · `¿Cuántos pagos se le hicieron a Marcelo por la obra Moreno?` |
| Cuánto va gastado | `¿Cuánto va gastado en Lennon?` · `gasto de mano de obra y materiales en Moreno` |
| Qué certificados faltan cobrar | `¿El comitente pagó todas las certificaciones?` |

Qué contesta:

- **Una obra**: aportes del comitente, lo pagado con plata del estudio, lo pagado por el comitente, el saldo, y la caja de obra si tiene.
- **Una caja**: lo que queda por rendir, en su moneda, lo que entró y salió, y los últimos movimientos.
- **Pagos**: la cantidad, el total y el detalle (hasta 15 líneas).
- **Gasto**: el total por obra y por rubro, separando quién puso la plata.
- **Certificaciones**: por obra y etapa, lo certificado, lo cobrado y lo pendiente.

Si no queda claro de qué obra o de quién, te pregunta. Una consulta nunca se toma como respuesta
a una pregunta pendiente.

---

## 7 · Qué pasa después

### Dónde queda

- **La planilla del estudio** («FACHADO — Gestión de Obras»): una fila por movimiento, con quién lo cargó.
- **La planilla personal** («FACHADO — Personal»): lo personal, con su propio número P-.
- **Los comprobantes**, en Drive, en `comprobantes/<obra>/<mes>/`, con el número del movimiento en el nombre. Lo personal va a `personal/<mes>/`; lo que no tiene obra, a `_sin-imputar/<mes>/`.
- **Todo lo que mandás**, tal cual, en una copia de respaldo (la «captura»), aunque no se haya cargado.

### Cuentas corrientes por obra

- Cada obra tiene su hoja en la planilla: **`CC_LENNON`**, **`CC_MORENO`**, etc. Los inmuebles personales tienen la suya en la planilla personal.
- Muestran aportes del comitente, lo pagado por contratista y por rubro, y el detalle día por día con el link al comprobante.
- **Se rehacen solas todas las noches. No las edites a mano**: lo que escribas ahí se pisa.
- Una obra nueva tiene su hoja a la noche siguiente.

### Cierre semanal

- **Los lunes a la mañana** (8:00), el sistema escribe en la planilla del estudio **una línea por cuenta** que resume lo personal de la semana anterior: el estudio ve cuánto salió, no en qué.
- Por eso el saldo del estudio puede ir **hasta una semana atrasado** en lo personal.
- Si cargás algo personal de una semana ya cerrada, el lunes siguiente se suma un ajuste.

### El tablero (Data Studio)

- Se actualiza **todas las noches** (a las 3:00) con lo que haya en la planilla. Lo que cargás hoy aparece mañana.
- Se abre desde el celular. Tiene tres páginas:
  - **Visión general**: saldo por cuenta, semáforo de obras (rojo: caja de obra en negativo o el estudio poniendo plata en la obra; gris: sin movimientos en 30 días) y las cajas de obra.
  - **Por obra**: un selector de obra arriba, lo pagado por rubro en barras, ingresos contra pagos por mes, los proveedores principales y el detalle con link al comprobante.
  - **Proveedores**: el ranking y la evolución de lo pagado.
- **Lo personal tiene su propio tablero** («Retiros»), que solo ven las personas habilitadas.
- Valen te comparte los links. *(A la fecha de este manual todavía no están compartidos.)*

### Mensajes que te puede mandar el bot

- **Petrus, los viernes a la tarde**: el pedido de los extractos de la semana, con lo que falta. Si sigue faltando algo, un solo recordatorio al día hábil siguiente.
- **Los lunes a la mañana**: el resumen contra el banco (según la planilla, según el banco, diferencia y movimientos sin cargar).

*(Estos dos mensajes están listos pero esperan que WhatsApp apruebe el texto. Si están
funcionando ya: a confirmar.)*

---

## 8 · Los rubros

### Cómo nombrarlos

- **No hace falta poner el rubro casi nunca.** Si no lo decís, el bot usa el habitual de ese contratista o el que se usó la última vez con él, y lo marca (supuesto).
- **Si querés decirlo, escribilo en el mensaje**, con la palabra de todos los días:

  ```
  Moreno/Tucu zinguería $80.000
  Austral/contador $150.000
  Austral/nafta $45.000
  Retiro/súper $45.000
  ```

- Las opciones que te ofrece dependen del destino: **en una obra, rubros de obra; en Austral, los del estudio; en lo personal, los personales.**
- En Austral la pregunta muestra los 10 más usados. Si el tuyo no está, **escribilo**.

### La lista general

La lista oficial es la que armó el estudio el 27/10. Tiene tres partes:

**Rubros de obra** (seis generales, cada uno con su detalle y su código):

| Código | Rubro general | Algunos detalles |
|---|---|---|
| 1 | **Materiales** | Áridos, Corralón / albañilería, Maderera, Sanitarios, Electricidad, Pinturería, Ferretería, Zinguería, Revestimientos… (28) |
| 2 | **Mano de obra** | Contratista principal, Sanitarista, Gasista, Pintor, Albañilería, Carpintería, Electricista, Jornales varios… (20) |
| 3 | **Servicios** | Movimiento de suelo, Volteo, Volquetes, Fletes, Baño químico, Alquiler de herramientas… (11) |
| 4 | **Asesoría** | Seguridad e higiene, Calculista, Asesor de instalaciones, Estudio de suelos, Forestal, Ambiental |
| 5 | **Indirectos** | F-931, Control, Administrativos, Operativos |
| 6 | **Varios** | Gastos varios de obra |

**Austral (gastos del estudio)**: Servicios (Internet, Luz, Gas, Celular) · Impuestos · Sueldos ·
Asesorías externas (Contador, Seguridad e Higiene, técnicas) · Contratados (Dibujante, Renders,
Gestores) · Insumos · Gastos corrientes (Librería, Copias, Otros) · Colegio de Arquitectos ·
Alquiler · Inversión · Impuestos y ART (Rentas, F.931, IERIC, UOCRA, UECARA, Caja previsional,
Matrículas, Cámara de Comercio). Además siguen vigentes **Combustible** y **Gastos generales**
hasta que Gabriel decida dónde van.

**Retiros (lo personal)**: Consumos · Salud y prepaga · Club y deporte · Casa · Casa de Buenos
Aires · Autos · Súper · Tarjetas · Educación.

### Dónde ver la lista completa

- En la planilla del estudio, hoja **`RUBROS`**: cada rubro con su código y si está activo.
- El Excel original del estudio: «Listado general de rubros de obra — formato unificado».
- Los rubros viejos no se borraron: los movimientos anteriores se muestran en el tablero y en las cuentas corrientes con el rubro nuevo que los reemplaza. Unos 35 rubros viejos **esperan que Gabriel diga** a cuál de la lista nueva van (ver la última sección).

---

## 9 · Buenas prácticas y errores comunes

Sacados de lo que pasó en las primeras semanas de uso.

1. **Contestá antes de mandar otra cosa.** Si el bot te hizo una pregunta, contestala o confirmá antes de mandar un comprobante nuevo. Hoy el bot ya no mezcla las fichas, pero deja la anterior pendiente y es fácil olvidarla.
2. **Si el bot te dijo «escribí pendientes», escribí `pendientes`**, no el número de la respuesta suelto. Un `4` solo, sin la ficha abierta, no significa nada para el bot.
3. **Para corregir o anular, usá el número** (`M-000014`). «Borrá el de Miguel de ayer» no alcanza.
4. **Poné siempre la moneda si fue en dólares.** «400» sin más se carga en pesos (pasó con un pago de US$ 400 que quedó en pesos).
5. **En Lennon, «efectivo» es la caja de la obra.** Si pagaste con el efectivo del estudio, escribí `efectivo del estudio`. Pagos de Lennon cargados contra el efectivo del estudio hicieron que la obra apareciera con millones «pagados por el estudio».
6. **Mirá lo que dice (supuesto).** Es lo que el bot completó sin datos, casi siempre la cuenta o el rubro.
7. **Para apodos que pueden ser dos personas, usá el apellido**: `Maragaño` u `Orellana` en vez de `Marcelo`. Si no, el bot pregunta.
8. **Un comprobante de Mercado Pago pagado con tarjeta**: el bot lee si fue débito (sale del banco) o crédito. Si ves que la cuenta no es la correcta, corregila.
9. **Combustible en una obra**: hoy queda con el rubro Combustible del estudio, aunque la obra sea otra. *(A confirmar si hace falta un combustible de obra.)*
10. **No mandes lo mismo dos veces.** Si lo repetís a los pocos segundos, el bot lo toma una sola vez. Si es más tarde, te avisa que parece repetido y pregunta **Es el mismo** / **Es otro**.
11. **Lo cargado por los dos**: el acuerdo propuesto es que cada uno carga lo que paga, y lo que reciben los dos lo carga uno solo. Si los dos cargan lo mismo, el bot avisa: «Petrus ya cargó un pago igual el 27/8».
12. **No dejes fichas sin confirmar.** Una ficha esperando Confirmar **vence a las 12 horas**: no se carga y queda solo en la copia de respaldo. Y si el sistema se reinicia (por una actualización), las fichas pendientes se pierden. Confirmá en el momento.
13. **No escribas en las hojas `CC_` ni `VISTA_`** de la planilla: se rehacen cada noche.
14. **Una foto de obra, una charla o un «gracias»** no son movimientos: el bot contesta «Recibido ✅ No encontré un movimiento.» y no pregunta nada.

---

## 10 · Preguntas frecuentes

**¿Tengo que escribir siempre el importe?**
No si mandás el comprobante. Sí si no hay comprobante (por ejemplo, un pago en efectivo).

**¿Importa el orden de «obra/contratista»?**
No. `Lennon/Miguel` y `Miguel/Lennon` son lo mismo.

**¿Y si no sé el rubro?**
No lo pongas. El bot usa el de siempre de ese contratista o te pregunta con opciones.

**Me equivoqué antes de confirmar. ¿Qué hago?**
Tocá **✏️ Corregir** y escribí lo que cambia. O **❌ Descartar** y volvé a mandarlo.

**Me equivoqué y ya confirmé.**
Respondé al acuse o escribí `corregir M-000012`. Si directamente no tenía que estar, `anular M-000012`.

**¿Se borra algo de la planilla?**
Nunca. Una anulación deja una fila que compensa la original. Queda el rastro.

**Mandé algo y el bot no contestó lo que esperaba.**
Todo queda guardado igual. Escribí `pendientes` para ver si quedó algo abierto. Si no se resuelve, usá **Dejar para revisar** o avisale a Valen.

**¿El bot carga solo, sin que confirme?**
No. Durante el período de prueba pide confirmación siempre.

**¿Petrus ve lo personal de Gabriel?**
Sí, hoy los dos lo ven. Quien se sume al estudio no lo ve, salvo que Gabriel lo habilite.

**Soy nuevo en el estudio. ¿Puedo usar el bot?**
Primero Valen tiene que darte de alta. Hasta entonces el bot no carga lo que mandes.

**¿Cuándo veo lo que cargué en el tablero?**
Al día siguiente. El tablero se actualiza todas las noches.

**¿Qué es la «caja de obra»?**
Es la plata que el comitente te dio para pagar esa obra. No es del estudio: es lo que te queda por rendir. Preguntá `¿cuánto hay en la caja chica de Lennon?`.

**¿Puedo cargar una obra nueva desde el bot?**
Sí. Nombrala; el bot pregunta si es obra nueva o contratista nuevo y la da de alta al confirmar.

**¿Qué pasa si mando un extracto antes del 1/11?**
Se importa, pero no se pregunta nada: la conciliación arranca con noviembre.

**¿Puedo mandarle mis facturas emitidas?**
*A confirmar.* La posición de IVA con las facturas emitidas está prevista, pero todavía no está
en marcha.

---

## Para revisar con Valen

Lo que quedó a confirmar o donde el código y la spec (`CONTEXTO-FACHADO.md` v1.13) no coinciden.

**Donde el código y la spec no coinciden**

1. **Fichas que vencen.** §5.12 dice que una ficha sin confirmar «nunca se descarta sola». El gateway (`handlers/obras.py`, `ficha_vence_horas = 12` en el perfil de Fachado) la descarta a las 12 h y avisa «venció sin confirmar; quedó en la captura». ¿Se cambia la spec o el código?
2. **Pendientes en memoria.** La sesión del gateway (`services/session_store.py`) vive en memoria: con un reinicio o un deploy se pierden las fichas pendientes y la cola de la conciliación. La spec no lo menciona. ¿Se avisa a los usuarios o se persiste?
3. **Audios.** §5.3 dice que Gabriel no usa audios; el gateway los transcribe (`transcribir_audio: true`) y los trata como texto. Confirmar que funciona con el motor antes de recomendarlo.
4. **Caja de obra en negativo.** §5.8 dice que el bot pregunta «¿La diferencia la pusiste de Austral o tuya?». No está implementado (supuesto P-28).
5. **Pedido semanal de extractos.** §5.20 dice que el bot se los pide a Petrus una vez por semana; el código existe pero está apagado (`FACHADO_PEDIDO_EXTRACTOS`) hasta que Meta apruebe la plantilla. Lo mismo el resumen del lunes (`FACHADO_RESUMEN_LUNES`). ¿Ya están prendidos?
6. **IVA y facturas emitidas** (§5.10): no implementado. No está claro qué hace hoy el bot con una factura emitida (probablemente la lee como un comprobante de pago). Hay que decirles qué hacer con ellas.

**Decisiones pendientes que afectan lo que dice el manual**

7. **Tarjetas de crédito** (P-34): los pagos de First Data / Visa del extracto son una pregunta por línea, y un comprobante de Mercado Pago pagado con crédito va a Mercado Pago con un aviso.
8. **Rubros a confirmar con Gabriel**: 35 rubros viejos siguen activos (tabla en `handoff-rubros-tablero-2026-10-27.md`), entre ellos Combustible, Gastos generales, Impuestos y tasas › Bancarios, Personal › Familia y los servicios públicos en obra. También: ¿combustible de obra? ¿«Servicios» como rubro personal (Edesur termina en «Casa»)? ¿El rubro de Sofía Cervera?
9. **Corregir un certificado**: no se puede (CERTIFICADOS no tiene número de movimiento y anular es solo para movimientos). Si alguien carga mal un certificado, hoy no tiene cómo arreglarlo por el bot.
10. **Series de certificados de Moreno** («cert.pintura», «certificado 18 obra»): el sistema las trata como números distintos; falta definir si son series.
11. **Correcciones del 9/10 sin correr**: los pagos de Lennon contra Efectivo (unos $ 13,6 M) y M-000005 (US$ 400 cargado en pesos). Mientras tanto, **Lennon aparece en rojo en el tablero** con unos $ 15 M de capital propio. Conviene correrlas antes de compartir el tablero.
12. **El tablero**: los dos informes no están compartidos todavía; falta la tarjeta de diferencia contra el banco (después del 1/11, «Actualizar campos» en la fuente VISTA_GENERAL). El «capital propio inmovilizado» está a validar con Gabriel. Cuando se compartan, sumar los links al manual.
13. **Reporte de Mercado Pago**: el lector del PDF está armado contra un formato supuesto; falta la muestra real. Puede que el primer reporte no se reconozca.
14. **Lennon con una transferencia sin el CUIT del comitente legible**: hoy va a Banco (el comprobante le gana a la obra). ¿Debería ir a «Pagado por el comitente»?
15. **`al_dia` del pedido de extractos**: una cuenta sin movimientos en la semana figura como faltante aunque Petrus mande el extracto.
16. **Chequera en los saldos de apertura del 31/10**: quedó afuera de la plantilla.
17. **El cierre semanal del 26/10 falló** (clave vieja). La línea de la semana del 19 al 25/10 se completa sola el 2/11, o se corre a mano antes.

**Comportamientos que no pude confirmar leyendo el código (convendría una prueba en ensayo)**

18. **Enseñar un apodo** con `Rodrigo = Rodrigo sanitarista` (está en el corpus): el sistema lo reconoce y guarda el apodo al confirmar una ficha, pero no está claro qué ve el usuario si lo manda solo.
19. **El prefijo «Corrección!»** (`Corrección! Rodrigo/Moreno`, del corpus): el sistema lo marca como corrección, pero sin una ficha abierta probablemente arma un movimiento nuevo. Recomendé usar «Corregir» o `corregir M-…`.
20. **Dos movimientos en un texto**: solo se separan con «e imputar / e ingresar / e registrar / e cargar». Recomendé un mensaje por movimiento.
21. **Alta de un usuario nuevo**: hace falta la fila en USUARIOS (con `ve_personal`) y además el teléfono en la configuración del gateway. Falta el paso a paso para «quien se sume».
22. **Privacidad de los extractos**: los extractos de la caja de ahorro a nombre de Gabriel quedan en la planilla del estudio con descripciones personales (pregunta abierta del 15/10).
