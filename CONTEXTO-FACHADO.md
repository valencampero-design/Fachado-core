# CONTEXTO-FACHADO.md

**Memoria compartida del proyecto Fachado.** Este archivo es la verdad de negocio: lo que el
sistema tiene que hacer y por qué. Vive en tres lugares y tiene que ser idéntico en los tres:

- el proyecto de Claude de A&C (fuente, se edita ahí),
- `chatbot-contable/CONTEXTO-FACHADO.md`,
- `fachado-core/CONTEXTO-FACHADO.md`.

**Versión 1.0 · 17 de septiembre de 2026.** Si estás leyendo una copia con fecha anterior a
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
| **Gateway** `chatbot-contable` | El canal. WhatsApp Cloud API, un solo número para **tres clientes** (contabilidad, Belakay, Fachado). Ruteo por teléfono → `config/tenants/<phone>.json` | FastAPI en Railway, ya en producción |
| **Motor** `fachado-core` | La inteligencia de negocio. Interpreta, imputa, escribe, concilia. **No sabe nada de WhatsApp** | FastAPI en Railway, fase 1 hecha |
| **Sheet maestro** | La fuente de verdad de los datos. No hay base de datos | Google Sheets |
| **Drive** | Los comprobantes | Google Drive |
| **Tablero** | Las vistas para el arquitecto | Looker Studio, semana 6 |

**Por qué el motor está separado:** el gateway atiende tres clientes y no se puede tocar
todos los días; el parser de Fachado va a cambiar todos los días durante seis semanas. Y el
motor, al no tener estado, se prueba con `curl` contra un corpus de 101 mensajes reales sin
mandar un solo WhatsApp.

**El reparto de responsabilidad, que es la decisión de la que se desprende todo:**

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

Los secretos (client id, client secret, refresh tokens, API keys) **solo viven en variables
de entorno de Railway**. Nunca en un archivo, nunca en un doc, nunca en un commit.

---

## 4. Glosario

Palabras que significan algo preciso en este proyecto. Usarlas mal produce bugs silenciosos.

| Término | Qué significa acá |
|---|---|
| **Obra** | Un proyecto con comitente, cuenta corriente y saldo. Es lo que el tablero sigue |
| **Comitente** | Quien encarga y financia la obra. Se hereda del maestro, no se tipea |
| **Ítem** | El contrato con un contratista *en esa obra*. Se deriva de obra + contratista. Es lo que hoy es cada hoja de la Planilla CC |
| **Certificado** | La unidad con la que el comitente de Moreno paga: numerada, cobrada en efectivo, a veces meses después |
| **Rubro** | **Qué se compró.** Árbol de dos niveles. El nivel 2 nunca dice *dónde* se compró |
| **`tipo_gasto`** | **Para quién fue.** `obra` · `estructura` · `personal`. Es un eje independiente del rubro |
| **`tipo` de obra** | `obra_terceros` · `obra_propia` · `estructura` · `personal` |
| **`servicio`** | Qué hace el estudio en esa obra: `administración` · `proyecto y dirección` · `todo` |
| **`concilia`** | Verdadero solo si `cuenta = Banco`. Evita que el sistema reclame en el extracto un pago en efectivo |
| **`PASANTE`** | Depósito neutro: el comitente deposita y sale el mismo día al proveedor. Se carga una vez, mueve la obra y no la caja |
| **Captura** | El modo actual: el bot archiva todo sin interpretarlo. Es también el fallback permanente |
| **Pasarela** | Mercado Libre, tarjeta débito comercios, transferencia e-bank. Dicen *por dónde salió la plata*, no a quién se le pagó |

---

## 5. Las reglas duras

Estas no se discuten en cada sesión. Si algo las contradice, es un bug o es una decisión
nueva que hay que escribir acá antes de implementarla.

### 5.1 · Un solo libro

Un único `MOVIMIENTOS` append-only. La cuenta corriente de cada obra, el saldo de caja y el
tablero se derivan por fórmula. **Nadie copia un número de un lado a otro.**

- **El saldo no se guarda, se calcula.** Si aparece una columna «saldo» en MOVIMIENTOS, algo
  se hizo mal.
- **Nada se borra de los maestros.** El que deja de trabajar pasa a `inactivo`.
- **El libro guarda hechos, no asignaciones.** El prorrateo de indirectos es una vista
  derivada, nunca filas en el libro.

### 5.2 · Reparto de autoridad

**El comprobante manda** en importe, fecha, destinatario, CUIT y número de operación.
**El texto manda** en obra, ítem, rubro y descripción.

Si se contradicen en importe o fecha, el sistema **no elige**: devuelve los dos valores y
pregunta.

### 5.3 · Cómo escribe el arquitecto

Sacado de 101 mensajes reales. El sistema se adapta a él, no al revés.

- **Formato `algo/algo`, pero el orden NO es fijo.** `Sofia/Austral` y `Austral/Sofi` son el
  mismo par. No parsear por posición: resolver cada token contra los diccionarios.
- **No escribe el importe cuando hay comprobante.** Cuando cobra en efectivo y no hay papel,
  **sí** escribe importe y fecha.
- **Se corrige por mensaje posterior, sin comando.** Y a veces enseña un alias solo
  («Rodrigo = Rodrigo sanitarista»).
- **Un mensaje puede traer dos movimientos.**
- **No usa audios.** Cero en cien mensajes.

### 5.4 · La cascada de clasificación

Código, no prompt. Se evalúa en orden, gana la primera que matchea, y la ficha dice cuál fue.

| # | Condición | Resultado |
|---|---|---|
| R1 | Aparece `retiro`, `casa`, `particular`, o una obra con `tipo = personal` | **personal.** Señal fuerte: le gana a cualquier contratista de obra. El contratista se conserva |
| R2 | El contratista está marcado DUAL (Sofía, Juan Manuel) | Pregunta: ¿obra o personal? |
| R3 | El rubro resuelto es `Personal › …` | **personal** |
| R4 | Hay obra identificada | El `tipo` de esa obra |
| R5 | Contratista con rubro de obra, sin obra **y sin señal personal** | **obra**, obra vacía → pregunta a qué obra |
| R6 | Nada de lo anterior | Pregunta |
| T | Es un TRASPASO | No se clasifica |

**«Retiro» manda siempre.** `Electricidad Angostura/Retiro` es material eléctrico para su
casa, no una obra sin imputar. El proveedor se conserva para poder separar, dentro de la
cuenta de ese proveedor, lo que fue obra de lo que fue personal.

### 5.5 · Resolver primero con diccionario, después con LLM

Más barato, más rápido y mucho más predecible. Orden: exacto → CUIT → palabra única →
difuso (≥ 88) → LLM solo para lo que quedó.

- **El LLM solo puede devolver valores que existen en los maestros.** Lo que inventa se
  descarta.
- **El CUIT no es clave única.** Un proveedor puede cobrar con más de uno: Miguel Soto cobra
  también con el de Alexis Matamala y para el estudio son el mismo. Los secundarios van en
  `ALIAS` con `tipo = cuit`.

### 5.6 · Lo que no es un contratista

**Mercado Libre es una pasarela, no un proveedor.** La línea del extracto dice por dónde
salió la plata, no a quién se le compró. El vendedor real solo está en el comprobante.

Lo mismo con `TARJETA DEBITO COMERCIOS`, `TRANSFERENCIA E-BANK` y Mercado Pago cuando es la
cuenta de destino de un tercero. Van a `medio_pago`, nunca a `CONTRATISTAS`.

*Riesgo operativo:* hay 28 líneas de Mercado Libre en dos meses de extracto. De cada una el
banco aporta importe y fecha y nada más. Sin comprobante, ese gasto queda sin proveedor y
sin rubro para siempre.

### 5.7 · Una sola cuenta bancaria

Con tramos en pesos y en dólares. Caja de ahorro y cuenta corriente son una división
operativa del banco, no cuentas distintas del estudio. **La conciliación es global**: un pago
cargado como «banco» concilia contra cualquier línea del extracto.

**«Personal» no es una cuenta, es una clasificación.** La plata sale del mismo banco.
En cambio **el efectivo sí es una cuenta**: sacar del cajero es `TRASPASO`, no un gasto.

### 5.8 · El comitente que paga directo

En Lennon, **el comitente paga directo a los contratistas** desde sus propias cuentas. Esa
plata nunca toca la caja del estudio pero sí es costo de la obra. Se registra con
`cuenta = Pagado por el comitente` y `concilia = no`.

Si no se modela, la cuenta corriente de Lennon queda vacía y el saldo de caja queda *bien*:
el error no se ve, que es el peor tipo de error.

### 5.9 · Nada se escribe sin confirmación humana

El bot propone, el arquitecto confirma con un botón. Y la ficha de confirmación muestra
**de dónde salió cada dato** —del comprobante, del texto, del maestro— porque es lo que hace
que confíe.

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
| Tres Cerros | obra_propia | **a definir** | El arquitecto |
| Austral | estructura | — | Indirectos del estudio |
| Sur · Abucoque · Belelli | personal | — | Inmuebles personales |
| Jardín Maternal | obra_terceros | administración | **cerrada** · obra de referencia |

**Las de «proyecto y dirección» no llevan cuenta corriente de costos**: el estudio no mueve
plata ahí, solo cobra honorarios.

---

## 7. Personas y alias

| Quién | Qué es |
|---|---|
| **Gabriel Fachado** | El arquitecto. El único que escribe al bot |
| **Sofía Cervera · Juan Manuel** | Sus hijos. **Duales**: a veces contratistas, a veces gasto personal. El bot siempre pregunta |
| **Valentín Campero** | A&C. Sus honorarios son `estructura`, imputados a Austral |
| **Miguel Soto** | Cobra también con el CUIT de **Alexis Matamala**. Para el estudio es el mismo proveedor |
| Felipe J | Felipe Andrés Scherer · movimiento de suelos |
| Fábrica de Calcos | Sergio González |
| Marcos Carpintero | Marcos Ezequiel Lenton |
| Barba | Barbagelata |
| Ecoaislaciones | Eco Aislación SRL |
| Andina | **Ferretería** Andina. La pinturería es otro comercio y él lo aclara |
| Municipalidad | Destinatario válido. Rubro **siempre** `Impuestos y tasas › Municipales` |
| Lalo | Una maderera, **no** Maderera Misiones. Falta el nombre |

---

## 8. Estado y pendientes

**Semana 3 de 8.** Captura operando desde el 3/9 (101 mensajes). Motor fase 1 terminado:
`/interpretar` resuelve el **80 %** de los mensajes sin preguntar, con solo 10 de 55 usando
LLM. Falta `/confirmar`, `/consultar`, conciliación, deploy y conectar el gateway.

Las preguntas abiertas viven en **`fachado-registro-de-preguntas.md`** del proyecto, con
código estable (`P-01`, `P-02`…). No duplicar esa lista acá.

Deudas técnicas que atraviesan los dos repos:

- **Publicar la app OAuth en Producción.** Con scope `drive.file` no requiere verificación y
  son diez minutos. Mientras siga en «Prueba» el refresh token caduca cada siete días y los
  adjuntos dejan de guardarse en silencio.
- **El adjunto a veces llega 8 a 18 segundos ANTES que el texto** que lo etiqueta. La
  ventana de agrupamiento del gateway tiene que mirar para los dos lados.
- **Manda cosas repetidas** con un segundo de diferencia. Detectar duplicados antes de
  escribir.
- **Agregar `tipo_gasto` al final de MOVIMIENTOS.** Sin esa columna el tablero no puede
  separar obras de consumo personal.

---

## 9. Cómo se mantiene este archivo

**La verdad de negocio se decide en el proyecto de Claude de A&C y baja a los repos.**
La verdad técnica de cada repo vive en su `CLAUDE.md` y sus handoffs, y sube al proyecto.

- Si en una sesión de Code aparece una decisión de **negocio** —una regla, un alias, un
  criterio de clasificación— **no la implementes sin escribirla acá primero**. Avisá que
  falta y pedí que se actualice el contexto.
- Si algo de este archivo contradice el código, **gana este archivo**, salvo que el código
  sea más nuevo y la diferencia esté anotada como decisión.
- Cuando cambie, se sube la versión de la cabecera y se copia a los dos repos el mismo día.
  Dos copias con fechas distintas es peor que no tener ninguna.
