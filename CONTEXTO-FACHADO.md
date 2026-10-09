# CONTEXTO-FACHADO.md

**Memoria compartida del proyecto Fachado.** Este archivo es la verdad de negocio: qué tiene
que hacer el sistema y por qué. Vive en tres lugares y tiene que ser idéntico en los tres:

- el proyecto de Claude de A&C (fuente, se edita ahí),
- `fachado-core/CONTEXTO-FACHADO.md` — ese repo es solo de Fachado, va en la raíz,
- `chatbot-contable/docs/clientes/fachado/CONTEXTO-FACHADO.md` — ese repo atiende a **cinco
  clientes**, así que lo de Fachado vive en su carpeta, no en la raíz.

**Versión 1.8 · 9 de octubre de 2026.** Si estás leyendo una copia con fecha anterior a
la del proyecto, está vieja: pedí la actualizada antes de tomar decisiones de modelo.

---

## 1. Qué estamos construyendo

**Estudio Fachado Arquitectura** (Gabriel Fachado, Villa La Angostura) gestiona quince obras
y hoy lleva todo a mano: del extracto a una caja en Excel, de la caja a una planilla de
cuenta corriente por obra, y de ahí a la hoja de cada contratista. Cada movimiento se
escribe tres veces.

**El problema que venimos a resolver es la carga manual, no la falta de información.** El
arquitecto sabe en qué anda cada obra; lo que le cuesta es sostener el registro. Todo el
diseño existe para que esa carga se haga una sola vez, por WhatsApp, y todo lo demás se
derive solo.

Implementación: ocho semanas, USD 1.200 en dos pagos, más un mantenimiento mensual chico.
Arrancó el 3 de septiembre de 2026.

---

## 2. El mapa de piezas

| Pieza | Qué es | Dónde vive |
|---|---|---|
| **Gateway** `chatbot-contable` | El canal. WhatsApp Cloud API, un solo número para **tres clientes** (contabilidad, Belakay, Fachado). Ruteo por teléfono → `config/tenants/<phone>.json` | FastAPI en Railway, en producción |
| **Motor** `fachado-core` | La inteligencia de negocio. Interpreta, imputa, escribe, concilia. **No sabe nada de WhatsApp** | FastAPI en Railway, fase 1 hecha |
| **Sheet maestro** | La fuente de verdad de los datos. No hay base de datos | Google Sheets |
| **Drive** | Los comprobantes | Google Drive |
| **Tablero** | Las vistas para el arquitecto | Looker Studio, semana 6 |

**Por qué el motor está separado:** el gateway atiende tres clientes y no se puede tocar
todos los días; el parser de Fachado va a cambiar todos los días durante seis semanas. Y el
motor, al no tener estado, se prueba con `curl` contra un corpus de 101 mensajes reales sin
mandar un solo WhatsApp.

| | Gateway | Motor |
|---|---|---|
| Sabe de | Conversar | Obras |
| Tiene estado | Sí: sesión, botones, flujo de confirmación | **No** |
| Hace | Webhook, seguridad, dedup, descarga de media, transcripción, mandar mensajes y botones | Interpretar, imputar, escribir en Sheets y Drive, conciliar |

Si el motor está caído, el gateway sigue archivando el mensaje crudo (modo captura) y
responde ✅. **Nunca se pierde un dato por una falla del procesamiento.**

---

## 3. Identificadores vivos

| Qué | Valor |
|---|---|
| Teléfono del arquitecto | `5492944341132` |
| Sheet maestro «FACHADO — Gestión de Obras» | `1yoakmhO1--WXCtWWStNrmczgYkaT1g0H54fTK2QCc9A` |
| Sheet de captura | `1eRVuLLrcMem730fjSIpiAblDm6MlIQbpqIUTUw41FIg` |
| Carpeta de Drive de captura | `1_W6Stl_qakpvSws3j7oSJMd60Mr2Mg0v` |
| Comitente de la obra Lennon | Lucas Mariano Lennon · CUIT 20-13851988-1 |

Los secretos **solo viven en variables de entorno de Railway**. Nunca en un archivo, nunca
en un doc, nunca en un commit.

---

## 4. Glosario

| Término | Qué significa acá |
|---|---|
| **Obra** | Un proyecto con comitente, cuenta corriente y saldo |
| **Comitente** | Quien encarga y financia la obra. Se hereda del maestro, no se tipea |
| **Ítem** | El contrato con un contratista *en esa obra*. Se deriva de obra + contratista |
| **Certificado** | La unidad con la que el comitente de una obra administrada paga: numerada, a veces cobrada meses después |
| **Rubro** | **Qué se compró.** Árbol de dos niveles. El nivel 2 nunca dice *dónde* se compró |
| **`tipo_gasto`** | **Para quién fue.** `obra` · `estructura` · `personal`. Eje independiente del rubro |
| **`tipo` de obra** | `obra_terceros` · `obra_propia` · `estructura` · `personal` |
| **`servicio`** | Qué hace el estudio ahí: `administración` · `proyecto y dirección` · `todo` |
| **Caja de obra** | Plata del comitente en poder del arquitecto, para pagar esa obra. **No es del estudio: es un pasivo** (§5.8) |
| **`concilia`** | Verdadero solo si `cuenta = Banco`. Evita reclamar en el extracto un pago en efectivo |
| **`PASANTE`** | Depósito neutro: el comitente deposita y sale el mismo día al proveedor |
| **Captura** | El modo actual: el bot archiva todo sin interpretarlo. Es también el fallback permanente |
| **Etapa** | Subdivisión de una obra que se certifica. `Lennon1` = etapa 1 de Lennon (§5.15) |
| **Informal** | Movimiento «en negro», como los depósitos. Fuera del IVA y de la conciliación (§5.17) |
| **Pasarela** | Mercado Libre, tarjeta débito comercios, transferencia e-bank. Dicen *por dónde salió la plata*, no a quién se le pagó |

---

## 5. Las reglas duras

Si algo las contradice, es un bug o es una decisión nueva que hay que escribir acá **antes**
de implementarla.

### 5.1 · Un solo libro

Un único `MOVIMIENTOS` append-only. La cuenta corriente de cada obra, el saldo de caja y el
tablero se derivan por fórmula. **Nadie copia un número de un lado a otro.**

- **El saldo no se guarda, se calcula.**
- **Nada se borra de los maestros.** El que deja de trabajar pasa a `inactivo`.
- **El libro guarda hechos, no asignaciones.** El prorrateo de indirectos es una vista.
- **Excepción deliberada: lo personal vive en un libro aparte** (§5.14). El libro del estudio
  recibe una sola línea semanal que lo resume.

### 5.2 · Reparto de autoridad

**El comprobante manda** en importe, fecha, destinatario, CUIT y número de operación.
**El texto manda** en obra, ítem, rubro y descripción. Si se contradicen en importe o fecha,
el sistema **no elige**: devuelve los dos y pregunta.

### 5.3 · Cómo escribe el arquitecto

De 101 mensajes reales. El sistema se adapta a él, no al revés.

- **Formato `algo/algo`, pero el orden NO es fijo.** `Sofia/Austral` y `Austral/Sofi` son el
  mismo par. No parsear por posición: resolver cada token contra los diccionarios.
- **No escribe el importe cuando hay comprobante.** Cuando cobra en efectivo y no hay papel,
  **sí** escribe importe y fecha.
- **Se corrige por mensaje posterior, sin comando.** A veces enseña un alias solo.
- **Un mensaje puede traer dos movimientos.**
- **No usa audios.**

### 5.4 · La cascada de clasificación

Código, no prompt. Se evalúa en orden, gana la primera que matchea, y la ficha dice cuál fue.

| # | Condición | Resultado |
|---|---|---|
| R1 | Aparece `retiro`, `casa`, `particular`, o una obra con `tipo = personal` | **personal.** Señal fuerte: le gana a cualquier contratista de obra. El contratista se conserva |
| R2 | El contratista está marcado DUAL | Pregunta: ¿obra o personal? |
| R3 | El rubro resuelto es `Personal › …` | **personal** |
| R4 | Hay obra identificada | El `tipo` de esa obra |
| R5 | Contratista con rubro de obra, sin obra **y sin señal personal** | **obra**, obra vacía → pregunta a qué obra |
| R6 | Nada de lo anterior | Pregunta |
| T | Es un TRASPASO | No se clasifica |

**«Retiro» manda siempre.** `Electricidad Angostura/Retiro` es material eléctrico para su
casa, no una obra sin imputar. El proveedor se conserva para poder separar, dentro de su
cuenta, lo de obra de lo personal.

### 5.5 · Resolver primero con diccionario, después con LLM

Exacto → CUIT → palabra única → difuso (≥ 88) → LLM solo para lo que quedó.

- **El LLM solo puede devolver valores que existen en los maestros.**
- **El CUIT no es clave única.** Miguel Soto cobra también con el de Alexis Matamala y para
  el estudio son el mismo proveedor. Los secundarios van en `ALIAS` con `tipo = cuit`.
- **Un apodo puede ser ambiguo a propósito.** Si dos filas de `ALIAS` tienen el mismo
  `como_lo_dice`, el resolver detecta el empate y **pregunta**. Es el mecanismo para «Marce»
  y «Marcelo» (§7).

### 5.6 · Lo que no es un contratista

**Mercado Libre es una pasarela, no un proveedor.** La línea del extracto dice por dónde
salió la plata, no a quién se le compró. Lo mismo con `TARJETA DEBITO COMERCIOS`,
`TRANSFERENCIA E-BANK` y Mercado Pago como cuenta de destino de un tercero. Van a
`medio_pago`, nunca a `CONTRATISTAS`.

**Cómo se resuelve Mercado Libre** *(definido 18/09)*: lo de obra **sí** tiene comprobante y
el arquitecto lo manda; lo personal **no** tiene comprobante del otro lado. Entonces la
conciliación cruza por **fecha e importe** los comprobantes recibidos contra las líneas de
Mercado Libre del extracto, y **todo lo que no cruza queda como gasto personal sin
clasificar**. La ausencia de comprobante es, en este caso, información.

**Contratistas inactivos** *(definido 25/09)*: en la carga diaria **no se proponen por
parecido** (ni difuso, ni palabra única, ni LLM). Solo aparecen si el usuario escribe el
nombre exacto, un alias exacto o el CUIT, y en ese caso el bot pregunta «X está inactivo,
¿lo reactivo?» antes de usarlo. En la migración de históricos sí se reconocen. Mercado Libre
queda inactivo en `CONTRATISTAS` justamente por esto: su lugar es `medio_pago`.

### 5.7 · Una sola cuenta bancaria

Con tramos en pesos y en dólares. Caja de ahorro y cuenta corriente son una división
operativa del banco. **La conciliación es global.**

**«Personal» no es una cuenta, es una clasificación.** La plata sale del mismo banco. En
cambio **el efectivo sí es una cuenta**: sacar del cajero es `TRASPASO`, no un gasto.

**De qué cuenta salió** *(definido 30/09, después del arranque)*. En orden:

1. Lo que dice el mensaje: «efectivo», la `C` de una caja de obra (§5.8), una cuenta
   nombrada. **En una obra que tiene caja de obra, «efectivo» es esa caja**, con o sin la
   `C` (§5.8, v1.8).
2. Lo que dice el comprobante: una transferencia o un débito es **Banco**; un cheque va a la
   cuenta que el libro ya usa para cheques; un comprobante de Mercado Pago, a Mercado Pago.
3. Lo que dice la obra: en Lennon, `Pagado por el comitente` (§5.9).
4. **Si nada lo dice, se asume `Banco` / transferencia y la ficha lo muestra marcado como
   «supuesto»**, para que el usuario lo vea y lo corrija si no fue así. No se pregunta.

**Nunca se ofrece «Confirmar» con un dato obligatorio vacío.** Si falta algo que el libro
necesita, el bot lo completa por una regla de este archivo o lo pregunta antes de mostrar
la ficha.

**Dólares** *(definido 29/09)*. No hay un tipo de cambio fijo: depende de cada caso. **Cada
vez que se carga un movimiento en dólares, o se pasa plata entre la cuenta en dólares y la
de pesos, el bot pregunta a qué tipo de cambio fue.** Con eso se calcula el importe en
pesos. Un traspaso entre monedas son dos filas, cada una en su moneda.

### 5.8 · La plata de las obras administradas no es del estudio

*Definido el 18/09. Es el cambio de modelo más importante después del libro único.*

En las obras que el estudio **administra**, la plata de la obra **no entra a la caja del
estudio**. Lo que entra a su caja son **sus honorarios, y nada más**. El registro de los
pagos de obra existe como **control de gestión**: sirve para saber que se está pagando y
cuánto lleva cada contratista, no para mover la tesorería del estudio.

Hay dos formas, y se tratan distinto:

| | **El comitente paga directo** | **El comitente le da efectivo** |
|---|---|---|
| Ejemplo | Lennon | El caso más delicado |
| Quién paga | El comitente, desde sus cuentas | El arquitecto, con plata ajena |
| Qué recibe el arquitecto | Los comprobantes, que reenvía al bot | Efectivo, y después rinde |
| Cuenta | `Pagado por el comitente` | `Caja obra <X>` |
| ¿Tiene saldo? | **No.** Es informativo | **Sí, y hay que rendirlo** |

**La caja de obra es una fila de `CUENTAS` por obra administrada**, con `tipo = caja_obra` y
`concilia = no`. El comitente entrega efectivo → `INGRESO` a esa caja. El arquitecto paga a
un contratista → `EGRESO` de esa caja. **El saldo de la caja es lo que le queda por rendir**;
si da negativo, puso plata propia y hay que avisarle.

**Regla de oro:** el saldo de caja del estudio suma Banco, Banco USD, Efectivo, Chequera y
Mercado Pago. **Las cajas de obra NO suman.** Es plata de terceros en su poder: un pasivo,
no patrimonio. Mezclarlas infla el saldo con plata que no es suya, que es exactamente el
error que el sistema viene a evitar.

**Cualquier obra puede tener caja chica** *(definido 24/09)*. Hoy pasa en Lennon, pero
aparece por necesidad en cualquiera. Se marca en el mensaje con una **`C` pegada al nombre
de la obra**: `Barba/LennonC`, o con etapa, `Barba/Lennon1C` (§5.15). Sin la `C`, el pago no
sale de la caja de obra.

**«Efectivo» en una obra con caja es la caja de la obra** *(definido 9/10)*. Gabriel no
usa la `C`: escribe «Lennon/Miguel efectivo». En una obra que tiene caja de obra, el
efectivo sale de esa caja aunque no esté la `C`. Si alguna vez paga con el efectivo del
estudio, lo aclara («efectivo del estudio»). Hasta el 9/10 esos pagos se cargaron contra el
Efectivo del estudio y la cuenta corriente de Lennon mostró −$ 13,6 M «pagado por el
estudio»: hay que corregirlos.

**Cajas de obra en dólares** *(definido 9/10)*. Un comitente puede darle dólares para la
caja (Lennon: USD 20.000 el 28/09). **El saldo de esa caja se lleva en dólares**, pero los
pagos casi siempre se hacen en pesos: cada pago en pesos **descuenta de la caja los dólares
equivalentes al tipo de cambio del momento del pago**. Por eso la caja de obra puede tener
moneda USD, y un pago en pesos desde una caja en dólares necesita su tipo de cambio.
*Decisión de A&C para no preguntar de más:* el bot pide el tipo de cambio en el primer
pago del día de esa caja y lo reutiliza el resto del día, mostrándolo en la ficha.

**Cómo se rinde** *(definido 29/09)*: no hay una regla general; cada cuánto y contra qué
depende de cada obra. El sistema no impone un ciclo de rendición: muestra el saldo de cada
caja y lo que se pagó con ella.

**Cuando la caja no alcanza, a veces pone plata propia.** Ese aporte se clasifica según de
dónde salió: **Austral** (plata del estudio: un traspaso de una cuenta del estudio a la caja
de la obra) o **Gabriel** (plata personal suya). *Supuesto a confirmar:* el bot lo detecta
cuando un pago deja la caja en negativo y pregunta «¿La diferencia la pusiste de Austral o
tuya?».

**Moreno cobra dos cosas distintas** *(definido 24/09)*: **honorarios de proyecto**, que son
del estudio, y **certificaciones de obra**, que le paga el comitente al arquitecto para que
él pague a la gente. Las certificaciones son plata de la obra: van a **`Caja obra Moreno`**,
no a la caja del estudio.

### 5.9 · El comitente que paga directo

En Lennon el comitente paga directo a los contratistas desde sus propias cuentas. Se
registra con `cuenta = Pagado por el comitente` y `concilia = no`. Si no se modela, la
cuenta corriente de Lennon queda vacía y el saldo de caja queda *bien*: el error no se ve,
que es el peor tipo de error.

### 5.10 · IVA — alcance completo

*Decidido el 18/09.* Se hace la **posición de IVA completa**, no solo el crédito fiscal.

- El arquitecto manda al bot **sus facturas emitidas**, además de las recibidas.
- De cada comprobante se guardan neto, IVA, CUIT, tipo (A/B/C), número y fecha.
- Posición del mes = **IVA débito** (sus facturas) − **IVA crédito** (facturas A recibidas).
- Sus facturas emitidas son además la fuente de los **ingresos por honorarios** por obra, que
  es lo que necesitan las obras de «proyecto y dirección» para tener seguimiento.

Esto es **alcance por encima de la propuesta original de ocho semanas**. La contrapartida es
que resuelve el modelo de ingresos por honorarios, que hacía falta igual.

Nota fiscal: Miguel Soto y Alexis Matamala son el mismo proveedor para el estudio, pero
**dos contribuyentes para AFIP**. En el crédito fiscal van separados.

### 5.11 · Certificados: lo que falta cobrar

*Actualizado el 24/09: el cruce entra ahora, ya no queda para la etapa siguiente.*

El arquitecto manda al bot **cada certificado que emite**, como PDF o como un simple
mensaje. De cada uno solo interesan **cuatro datos: obra, etapa, número y el saldo a cobrar
de la presente certificación**, con su fecha. Nada más del documento.

**Llega como PDF o como texto, y las dos vías valen igual.** El texto no tiene formato
obligatorio. En el PDF —lo genera él desde Excel— **el único monto que importa es el punto 7
de la primera tabla, «Saldo a cancelar en la presente certificación»**. Número, fecha, obra y
etapa se toman solo para identificarlo.

**Numeración** *(definido 29/09)*: los certificados son **correlativos dentro de cada
etapa**. En Moreno, los «extras» son una etapa aparte (§5.15), así que «cert 4 extras» es el
certificado 4 de la etapa *extras*, distinto del certificado 4 de la etapa 1.

Cada certificado es una **cuenta por cobrar**. Cada cobro que registra el certificado lo
cancela. La diferencia contesta la pregunta que él hace: **«¿el comitente me pagó todo lo
que certifiqué?»**, por obra y por etapa.

### 5.12 · Nada se escribe sin confirmación humana

El bot propone, un usuario confirma con un botón. La ficha muestra **de dónde salió cada
dato** —del comprobante, del texto, del maestro— porque es lo que hace que confíe.

**Período de prueba** *(definido 24/09)*: mientras dure, **el bot pide confirmación
siempre**. Después, cuando un movimiento está completamente claro, se escribe sin volver a
preguntar. «Completamente claro» es una regla, no una sensación: importe, fecha y
destinatario del comprobante, obra y contratista del maestro, sin preguntas, sin conflictos
y sin sospecha de duplicado. El fin del período lo habilita A&C por usuario, cuando la
métrica de ese usuario lo justifique.

**Cómo se arma un movimiento a partir de varios mensajes** *(definido 25/09)*. El arquitecto
manda el texto y los comprobantes por separado, y a veces varios comprobantes seguidos:

- **El texto cierra el grupo.** Un texto (o un audio transcripto, o el epígrafe de una
  foto) se aplica **a todos los comprobantes sueltos que llegaron antes** y todavía no
  tienen texto.
- **Un comprobante sin texto espera 90 segundos.** Cada comprobante nuevo reinicia la
  espera. Si llega el texto, cierra el grupo; si no llega, el bot **lee cada comprobante
  solo** —importe, fecha, CUIT— y pregunta únicamente lo que falta («¿De qué obra?»).
- **Varios comprobantes con un texto son varios movimientos**: una ficha por comprobante,
  cada una con su importe y su fecha, y la obra y el contratista del texto. Se confirman
  **juntas con un solo «sí»**. Cada una concilia con su propio pago del banco.
- **Un texto solo, sin comprobantes pendientes, se interpreta en el momento.** Si mientras
  esa ficha espera confirmación llega un comprobante, el bot pregunta si es de esa ficha.
- **El mismo texto repetido** a pocos segundos se toma una sola vez (queda capturado igual).
- **Una ficha sin confirmar nunca se escribe sola ni se descarta sola.** Si el usuario
  sigue mandando otra cosa, la ficha queda pendiente y el bot se lo recuerda; «pendientes»
  las lista.

**Pocas preguntas** *(definido 9/10, después de la primera semana de uso)*. El mensaje de
Gabriel tiene que alcanzar: **«Lennon/Miguel» más el comprobante es suficiente** para cargar
un pago sin preguntar nada. La obra y el contratista salen del texto; el importe, la fecha y
la cuenta, del comprobante y de la obra; **el rubro, del rubro habitual del contratista o
del que se usó la última vez con él**. Lo que se deduce y no es seguro va a la ficha marcado
«supuesto», y Gabriel lo corrige si hace falta. Solo se pregunta lo que de verdad no se
puede deducir (por ejemplo, la obra cuando el texto no la nombra, o el importe cuando el
comprobante no se lee), y nunca algo que no aplica: **a un gasto personal no se le pregunta
la obra; a un ingreso no se le pregunta a quién se le pagó**.

**La conversación tiene que seguir el hilo** *(definido 9/10)*:

- **Un mensaje nuevo no es la respuesta a una pregunta vieja.** Si hay una pregunta
  pendiente y llega un comprobante, o un texto que es claramente otro movimiento, el bot
  arranca un movimiento nuevo y deja el anterior pendiente.
- **Una respuesta que no es ninguna de las opciones se lee como texto**: puede traer otro
  dato («efectivo», «caja chica», «es un ingreso») o pedir algo («¿cuál?»). Nunca se
  responde «no entendí» dos veces seguidas a lo mismo.
- **Nunca un error sin decir qué falta**, y nunca en bucle: después del segundo intento
  fallido el bot ofrece descartar o dejarlo para que A&C lo revise.

**Lo que no es un movimiento** *(definido 25/09)*: charla, «después te paso el ticket», una
foto de obra, un audio sin importe. Se guarda en la captura como todo lo demás y el bot
responde con un **acuse corto** («Recibido, no encontré un movimiento»), para que el usuario
sepa que llegó. No pregunta «¿esto es un gasto?».

**La captura sigue siempre.** Todo mensaje se archiva crudo antes de interpretarse, aunque el
motor esté funcionando. Si el motor está caído o responde con error, el usuario igual recibe
su acuse y el mensaje queda para revisar: nunca se pierde.

### 5.13 · El bot tiene más de un usuario

*Definido el 24/09.* **Petrus se reincorpora como colaborador del estudio y gran parte de la
administración va a pasar por él, a través del bot.** Hasta acá todo el diseño asumía un
único usuario; eso se termina.

- Los usuarios viven en una hoja **`USUARIOS`** del maestro: `telefono · nombre · rol ·
  activo`. Un teléfono que no está ahí **nunca escribe en el libro**.
- **`cargado_por` es la persona que cargó**, no «bot». Con dos usuarios es el dato de
  auditoría más importante del libro.
- **El gateway tiene que mapear varios teléfonos a un mismo cliente.** Hoy el modelo es un
  teléfono = un perfil.
- **El corpus es 100 % del arquitecto.** Cómo escribe Petrus no se sabe: la métrica del
  parser se mide por usuario.
- **Petrus tiene las mismas atribuciones que el arquitecto** *(definido 24/09)*: confirma
  solo, sin aprobación; maneja efectivo, así que vuelve a estar activo en `TERCEROS`; y ve y
  carga lo personal del arquitecto. Si Petrus escribe «Retiro», es personal **del
  arquitecto**.
- **Pero el acceso a lo personal es por persona, no por rol de colaborador.** El día que
  Petrus tenga un reemplazo, ese reemplazo **no** tiene que ver lo personal. Por eso lo
  personal se separa ahora (§5.14), aunque Petrus lo vea: separarlo después, con datos
  adentro, es mucho más caro. `USUARIOS` lleva una columna `ve_personal`.
- **Si Gabriel y Petrus cargan el mismo movimiento, el sistema lo tiene que detectar**
  (§5.16).
- **Arranque escalonado** *(definido 25/09)*: el bot conectado al motor arranca **solo con
  Gabriel**. Petrus se suma después de la primera semana de carga real; ahí se habilita el
  segundo teléfono y se prueban los duplicados entre usuarios.
- **El LLM sabe quién escribe.** El prompt nombra a la persona (de `USUARIOS`), no a «el
  arquitecto»: si Petrus escribe «pagué», pagó el estudio.

### 5.14 · Lo personal vive en un libro aparte

*Definido el 24/09.*

- Los movimientos con `tipo_gasto = personal` se escriben en un **segundo archivo**,
  «FACHADO — Personal», con la misma estructura de `MOVIMIENTOS`. Tiene su **propio
  tablero**. Solo lo ven los usuarios con `ve_personal = sí`.
- Para cerrar la caja del estudio, **una vez por semana** se escribe en el libro del estudio
  **una línea «Gastos personales · semana N» por cuenta** (Banco, Efectivo…) que resume todo
  lo personal de esa semana. El estudio ve cuánto salió, no en qué.
- Esa línea **no concilia contra el banco**: el banco se cruza contra las filas del libro
  personal, una por una. Si concilia la línea resumen, se cuenta dos veces.
- Consecuencia a tener en cuenta: el saldo del estudio **va hasta una semana atrasado** en
  lo personal, hasta que se escribe la línea semanal.
- Los maestros (obras, contratistas, rubros, alias) son **uno solo** y viven en el archivo
  del estudio. El libro personal no tiene maestros propios.

### 5.15 · Etapas de obra

*Definido el 24/09.*

Una obra puede dividirse en **etapas**, que son las que se certifican. Se indican con un
número pegado al nombre de la obra: **`Lennon1`** es la etapa 1 de Lennon.

- Las etapas de cada obra viven en una hoja **`ETAPAS`** del maestro. **Una obra sin filas
  en `ETAPAS` no tiene etapas** y el bot nunca las pregunta.
- Cada etapa tiene un **estado**: `en curso`, `futura` o `terminada`.
- **Si el mensaje no dice la etapa** *(definido 30/09)*: si la obra tiene **una sola etapa en
  curso**, el bot la usa y la ficha lo muestra («etapa 1, en curso»); **si tiene dos o más
  en curso, repregunta** con botones. Una etapa `futura` o `terminada` no se propone: si el
  usuario la nombra, el bot pregunta si la activa.
- La sintaxis completa del token de obra es **`<obra>[<etapa>][C]`**: `Lennon`, `Lennon1`,
  `LennonC`, `Lennon1C`. La `C` es la caja chica (§5.8). La etapa suele ser un número, pero
  puede tener nombre: `Moreno extras`.
- **Etapa y certificado son cosas distintas** *(confirmado 29/09)*: una etapa tiene varios
  certificados. Por eso son dos campos.

**Las etapas de hoy** *(relevadas el 29/09)*:

| Obra | Etapas |
|---|---|
| Lennon | **1 en curso**; 2 y 3 futuras («va a tener tres por lo menos») |
| Moreno | **1 en curso** y **extras en curso**; 2 futura, más adelante |
| Moquehue, Gonzalo, Hua Huan, Grigera Galpón, Belleli, Gessel, Tres Cerros | Sin etapas |

Moreno tiene dos etapas en curso, así que un pago a Moreno sin etapa se pregunta: «¿Etapa 1
o extras?».

### 5.16 · El mismo movimiento cargado dos veces

*Definido el 24/09.* Con dos usuarios, el mismo pago puede llegar por Gabriel y por Petrus.
Antes de proponer la ficha, el sistema busca en el libro un movimiento que coincida por
**referencia del comprobante** (número de operación, número de cheque o el archivo mismo) o,
si no hay referencia, por **importe, fecha cercana y contratista u obra**. Si encuentra uno,
**no lo descarta solo**: avisa quién y cuándo lo cargó, y pregunta si es el mismo.

Esto es distinto de la idempotencia por `msg_id`, que evita que un mismo mensaje se escriba
dos veces. Acá son dos mensajes distintos que describen el mismo hecho.

### 5.17 · Los depósitos «en negro»

*Definido el 24/09.* Cuando el arquitecto dice **«depósito»**, habla de un pago informal
hecho a la cuenta de otra persona: indirectamente es plata que entra para él y, a la vez,
un gasto con el que canceló algo.

Se registra como **`PASANTE`** *(definido 25/09, confirmado por el arquitecto el 29/09)*: **una sola fila** con `cuenta = Pagado por el comitente`, que
suma a la cuenta corriente del contratista en la obra igual que un pago directo del
comitente (§5.9). **No toca el saldo del estudio** y va marcada **`informal`**. Los
movimientos informales quedan **fuera de la posición de IVA y fuera de la conciliación
bancaria**. `Pagado por el comitente` es una cuenta de tipo externa: existe para que la fila
tenga cuenta, pero no suma al saldo del estudio ni concilia.

### 5.18 · Traspasos entre cuentas

*Definido 25/09.* Sacar efectivo del banco, reponer la caja chica de una obra, pasar plata de
la caja de obra al banco: **dos filas vinculadas** que salen del mismo mensaje, una salida de
la cuenta de origen y una entrada en la de destino, con el mismo importe y la misma
referencia. Entre cuentas del estudio el total no cambia, y **cada cuenta concilia sola**.
Cuando una de las dos es una caja de obra, cada fila cae en su cuenta y el saldo de cada una
se lee con las reglas de §5.8: el traspaso no agrega ninguna regla nueva.

### 5.19 · Corregir algo ya confirmado

*Definido 25/09.* El libro no se edita nunca. Si un movimiento confirmado estaba mal —otra
obra, otro importe, otro contratista— **el bot lo corrige con un contraasiento**: escribe una
fila que anula la original (mismo importe con signo contrario, marcada `anula = <id_mov>`) y
después la fila correcta, que se confirma como cualquier otra. Queda el rastro de qué se
cargó, quién lo corrigió y cuándo.

- El usuario lo pide **respondiendo al acuse** del movimiento o escribiendo «corregir
  M-000012». El acuse de cada confirmación muestra el `id_mov` para eso.
- **Solo lo puede corregir quien tenga acceso a ese libro**: lo personal, solo con
  `ve_personal`.
- La conciliación ignora el par original + contraasiento y concilia la fila correcta.

---

## 6. Las quince obras

| Obra | tipo | servicio | Comitente |
|---|---|---|---|
| Lennon | obra_terceros | administración | Lucas Mariano Lennon · *paga directo* |
| Moreno | obra_terceros | administración | Gonzalo Fernández Moreno · *por certificados* |
| Cerro Bayo | obra_terceros | proyecto y dirección | Cerro Bayo S.A. |
| Lumaia | obra_terceros | proyecto y dirección | Bosque de Lumas S.A. |
| Muelle de piedra | obra_terceros | proyecto y dirección | Muelle de Piedra Consorcio |
| Tonga | obra_terceros | proyecto y dirección | Gastón Maggi |
| Moquehue | obra_terceros | todo | Alicia Marson |
| Gonzalo | obra_propia | todo | El arquitecto |
| Hua Huan | obra_propia | todo | El arquitecto |
| Grigera Galpón | obra_propia | todo | El arquitecto |
| **Tres Cerros** | obra_propia | **todo** | El arquitecto |
| Austral | estructura | — | Indirectos del estudio |
| Sur · Abucoque · Belelli · Gessel | personal | — | Inmuebles personales. Gessel se sumó el 29/09; «Belleli» es otra forma de escribir Belelli |
| Jardín Maternal | obra_terceros | administración | **cerrada** · obra de referencia |

**Las cuatro obras propias —Gonzalo, Hua Huan, Grigera Galpón y Tres Cerros— son
inversiones**, no consumo. El costo se sigue como **capital inmovilizado** y el resultado se
mide contra la venta. No van al circuito personal, y se quedan en el libro del estudio, no en el libro
personal (§5.14; confirmado 29/09).

**Las de «proyecto y dirección» no llevan cuenta corriente de costos**: el estudio no mueve
plata ahí, solo cobra honorarios.

---

## 7. Personas y alias

| Quién | Qué es |
|---|---|
| **Gabriel Fachado** | El arquitecto. Titular: escribe al bot y decide |
| **Petrus** | Colaborador del estudio. **Se reincorpora en septiembre de 2026** y va a manejar gran parte de la administración por el bot. Ya trabajó en el estudio: en el histórico figura en 106 pagos, casi todos en efectivo por cuenta del estudio |
| **Sofía Cervera · Juan Manuel** | Sus hijos. **Duales**: a veces contratistas, a veces gasto personal |
| **Valentín Campero** | A&C. Honorarios de consultoría → `estructura`, imputados a Austral |
| **Miguel Soto** | Cobra también con el CUIT de **Alexis Matamala**. Para el estudio es el mismo proveedor |

### Los tres «Marce» *(definido 18/09)*

| Nombre canónico | Qué es | Rubro habitual |
|---|---|---|
| **Marcela** | La esposa. Gasto personal | `Personal › Familia` |
| **Marcelo Maragaño** | Carpintero | `Mano de obra › Carpintero` |
| **Marcelo Orellana** | Albañil | `Mano de obra › Albañil` |

**`marce` es ambiguo entre los tres y `marcelo` entre los dos últimos: el bot tiene que
preguntar.** Se implementa cargando varias filas de `ALIAS` con el mismo `como_lo_dice`
(§5.5). Los apellidos sí son unívocos: `maragaño` → Marcelo Maragaño, `orellana` → Marcelo
Orellana.

### Otros alias confirmados

| Como lo dice | Quién es |
|---|---|
| Lalo · Lalo Martínez | **Martínez Eduardo** — es una maderera. `Materiales › Maderas` |
| Felipe J | Felipe Andrés Scherer · `Servicios de obra › Movimiento de suelos` |
| Fábrica de Calcos | Sergio González |
| Marcos Carpintero | Marcos Ezequiel Lenton |
| Barba | Barbagelata |
| Ecoaislaciones | Eco Aislación SRL |
| Andina · Ferr Andina | **Ferretería Andina** |
| Pint Andina · Pinturería Andina | **Pinturería Andina** — otro comercio. Él lo aclara cuando es la pinturería |
| Municipalidad | Destinatario válido. Rubro **siempre** `Impuestos y tasas › Municipales` |

**Silla Cuádruple no es un proveedor**: es parte de la obra Cerro Bayo.

**«Austral» es también el nombre de su constructora** (Constructora Austral): así firma los
certificados. En el maestro, Austral es la obra de indirectos del estudio. **Dentro de un
certificado, «Austral» es el emisor, nunca la obra.**

---

## 8. Estado y pendientes

**Semana 6 de 8.** Primera semana de uso real (29/09–8/10): el bot carga, pero la
conversación resultó tediosa —demasiadas preguntas, preguntas que no aplican, respuestas que
no siguen el hilo y bucles de error—. La v1.8 fija las reglas de §5.12 («Pocas preguntas» y
«La conversación tiene que seguir el hilo») y la caja de obra (§5.8).

**El bot está en marcha desde el 29/09**, conectado al motor, con Gabriel
como único usuario y confirmación de todo. En el arranque, Lennon funcionó; en otras obras
la ficha llegaba sin cuenta y la confirmación fallaba con «Falta cuenta» (lo corrige §5.7,
v1.7). Siguen: tablero, conciliación, Petrus (después de una semana de carga) y marcha
blanca.

**Los cuatro supuestos quedaron confirmados el 29/09**: etapa y certificado son distintos
(§5.15), el depósito es un pasante (§5.17), las obras propias van en el libro del estudio
(§6) y los certificados los paga el comitente (§5.11).

**Ideas para una etapa futura, a presupuestar aparte:** cuentas por pagar a proveedores por
obra, un reporte para pasarle al comitente con lo pendiente de pagar, y que el comprobante
del pago lo cancele. Contesta «¿qué tengo pendiente de pagar en la obra X?».

Las preguntas abiertas viven en **`fachado-registro-de-preguntas.md`** del proyecto, con
código estable (`P-01`, `P-02`…). No duplicar esa lista acá.

Deudas técnicas que atraviesan los dos repos:

- **El adjunto a veces llega 8 a 18 segundos ANTES que el texto** que lo etiqueta: resuelto
  por la regla de agrupamiento de §5.12 (el texto cierra el grupo, 90 s de espera).
- **Manda cosas repetidas** con un segundo de diferencia: §5.12, se toma una sola vez.

---

## 9. Cómo se mantiene este archivo

**La verdad de negocio se decide en el proyecto de Claude de A&C y baja a los repos.**
La verdad técnica de cada repo vive en su `CLAUDE.md` y sus handoffs, y sube al proyecto.

- Si en una sesión de Code aparece una decisión de **negocio** —una regla, un alias, un
  criterio de clasificación— **no la implementes sin escribirla acá primero**. Avisá que
  falta y pedí que se actualice el contexto.
- Si algo de este archivo contradice el código, **gana este archivo**, salvo que el código
  sea más nuevo y la diferencia esté anotada como decisión.
- **Si el maestro contradice este archivo, se corrige el maestro.** Nada se borra: lo que
  deja de corresponder pasa a `inactivo`.
- Cuando cambie, se sube la versión de la cabecera y se copia a los dos repos el mismo día.
  Dos copias con fechas distintas es peor que no tener ninguna.
