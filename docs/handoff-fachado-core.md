# Handoff — `fachado-core`, el motor de imputación de Fachado

> **Estado técnico del repo al 2026-10-09**, después de las cinco tandas del handoff del
> proyecto (`docs/handoff-proyecto-2026-09-25.md`), de la tanda 6
> (`docs/handoff-tanda-6-2026-09-25.md`), del fix del arranque
> (`docs/handoff-fix-arranque-2026-09-30.md`: «Falta cuenta», etapas, dólares, Gessel) y de
> la parte del motor de la conversación del 9/10 (`docs/handoff-conversacion-2026-10-09.md`:
> pocas preguntas, cajas de obra en dólares, correcciones por contraasiento).
> Qué está hecho, qué falta, cómo se corre y qué variables hacen falta.
>
> **Las reglas de negocio NO viven acá: viven en `CONTEXTO-FACHADO.md`** (v1.8), que se edita
> en el proyecto de Claude de A&C y baja a los dos repos. Si este documento y el contexto se
> contradicen, **gana el contexto**. Este handoff dice dónde está implementada cada regla, no
> cuál es.
>
> Repo hermano: `chatbot-contable`, el gateway de WhatsApp, en producción en Railway.
> Su handoff del paso 0: `chatbot-contable/docs/handoff-fachado.md`.

## 0. Dónde quedó (para retomar)

| | |
|---|---|
| ✅ Motor en producción | Servicio `web` del proyecto Railway `bountiful-trust`, con dos dominios que son el mismo servicio: `web-production-6c935.up.railway.app` (el que usan la documentación y el cron) y `web-production-70e97.up.railway.app`. Las tandas 1 a 5 están desplegadas desde el 25/09 |
| ✅ Tanda 6 | Desplegada el 25/09: PASANTE, TRASPASO, contraasiento, `intencion` / `respuestas` / `texto_compartido`, contratistas inactivos, el nombre de quien escribe en el prompt. Columnas `vinculo` y `anula` en los dos libros. Verificado en producción con `/interpretar`: un texto del corpus, una charla (`otro`) y un comprobante solo (un recibo manuscrito, leído por el modelo) |
| ✅ Fix del arranque (30/09) | Desplegado el 30/09 con sus migraciones aplicadas: la cuenta se decide o se pregunta (origen `supuesto`), una sola lista de obligatorios, etapas con estado, tipo de cambio en dólares, Gessel |
| ⏳ Conversación del 9/10 (D, E, F, G, H, ñ) | Commiteado **sin pushear** (4 commits sobre `70df209`). Después del deploy: la migración de la caja de Lennon en dólares y, cuando Valen lo decida, el script de correcciones (§8). Detalle y métrica al final de `docs/handoff-conversacion-2026-10-09.md` |
| ✅ Libro personal | «FACHADO — Personal» (`1O4bMJXi4kooBvZZ6Wn-SlGhn2g2QjlANrmw3L7rCcZY`), compartido con la service account, con el encabezado de MOVIMIENTOS. `FACHADO_PERSONAL_SHEET_ID` cargada |
| ✅ Cron del cierre semanal | Servicio `cierre-semanal` en el mismo proyecto (`0 11 * * 1`) |
| ✅ GitHub | `valencampero-design/Fachado-core`, rama `main` |
| ✅ Lee y escribe el Sheet | Con la service account del gateway, compartida como Editor |
| ✅ Lee los comprobantes | Token de Drive en Railway, app OAuth publicada |
| ✅ Métrica del corpus | 90 % contando las preguntas de diseño. **Preguntas por movimiento** (§5.12 v1.8, con los comprobantes y la historia real): 1,22 → **0,98**; con obra + contratista + comprobante, 0,63 → **0,45** y 58 % → **65 %** con cero preguntas (§4). Invariante: 0 fichas con un faltante sin pregunta |
| ✅ Maestro alineado al contexto v1.5 | Cajas de obra, Petrus con teléfono y activo, Pinturería Andina, cobros de Moreno en su caja (§8) |
| ✅ Hojas nuevas en el Master | `ETAPAS` (se carga con la migración del 30/09) y `CERTIFICADOS` (vacía) |
| ✅ Gateway conectado | Encendido el 29/09 con Gabriel. En el arranque, fuera de Lennon, la confirmación fallaba con «Falta cuenta»: lo corrige el fix del 30/09 (el gateway tiene su parte: no ofrecer Confirmar con faltantes, 1.4–1.7) |
| ⏳ Conciliación, IVA | No empezados (§7) |

## 1. Qué es este repo

El motor de imputación: sabe de obras, contratistas, rubros y conciliación, y **no sabe nada
de WhatsApp**. API HTTP **sin estado**. El reparto con el gateway y el porqué están en el
contexto §2.

Lo que eso implica acá: se prueba con `curl` y con el corpus de 101 mensajes reales sin mandar
un WhatsApp, y si el motor se cae el gateway sigue archivando en modo captura.

## 2. Qué hay implementado

```
app/
  main.py          FastAPI, rutas, auth por X-API-Key, proveedores de libros y archivador
  config.py        settings desde env
  models.py        Pydantic de entrada y salida + columnas de MOVIMIENTOS y CERTIFICADOS
  maestros.py      carga y cachea OBRAS, CONTRATISTAS, RUBROS, CUENTAS, ALIAS, USUARIOS, ETAPAS
  resolver.py      texto libre → obra (con etapa y C) / contratista / rubro / cuenta, SIN LLM
  clasificador.py  la cascada obra / estructura / personal, SIN LLM
  interpretar.py   orquesta: resolver → LLM → comprobante → ficha → duplicados → preguntas que falten
  obligatorios.py  la lista única de obligatorios de /interpretar y /confirmar (§5.7 v1.7)
  llm.py           cliente de Anthropic, prompts y esquemas de salida
  comprobante.py   nombre de archivo → texto del PDF → visión; reconoce certificados
  certificados.py  el PDF del certificado, el número como clave, lo cobrado y lo pendiente
  duplicados.py    el mismo hecho cargado dos veces: referencias y búsqueda
  confirmar.py     /confirmar: valida, asigna id_mov bajo lock, enruta al libro, archiva, alias;
                   traspasos (dos filas vinculadas) y certificados
  anular.py        GET /movimientos/{id_mov} y POST /anular: el contraasiento (§5.19)
  cierre.py        la línea semanal de gastos personales en el libro del estudio
  consultas.py     /consultar: pagos a un contratista, gasto por obra, certificaciones
  filtros.py       qué entra en cada cálculo: informales, cierre semanal, pares anulados
  libro.py         el puerto al libro (MOVIMIENTOS, ALIAS, CERTIFICADOS, reactivar un
                   contratista): real o en memoria
  archivo.py       dónde queda cada comprobante, y el puerto a Drive
  saldos.py        saldo de una obra y saldo del estudio, derivados del libro
  sheets.py        clientes de Google Sheets (service account) y Drive (OAuth), con reintentos
scripts/
  get_google_token.py    genera el refresh token de Drive, se corre una vez
  snapshot_maestros.py   baja los maestros a tests/maestros_snapshot.json
  preparar_sheet.py      columnas y hojas que el motor necesita. Idempotente, simulacro por defecto
  cierre_semanal.py      lo corre el cron: llama a POST /cierre-semanal
  migraciones/           correcciones de datos del maestro, una por fecha, idempotentes
tests/
  corpus.csv             las 101 filas de la hoja CAPTURA
  maestros_snapshot.json copia de los maestros, para correr reproducible y offline
  fixtures/              cert_loguercio_etapa3.pdf, el certificado real de ejemplo
  dobles.py              libro en memoria y Drive falso
  test_corpus.py         la métrica: cuánto resuelve sin preguntar, en total y por usuario
  test_reglas.py         que lo que resuelve sea lo que el negocio decidió
  test_casos.py          los casos de los handoffs del 25/09 (tandas 1 a 6), con su resultado esperado
  test_confirmar.py      /confirmar, /anular, /movimientos, /cierre-semanal y /consultar contra
                         libros en memoria
```

### Lo del 9/10: pocas preguntas y cajas en dólares (§5.8 y §5.12 v1.8)

Dónde está cada cosa (el porqué, en el handoff de la conversación del 9/10):

- **Rubro sin preguntar** (`interpretar._ultimo_rubro`, `_rubros_por_uso`): habitual del
  contratista (`inferido`) → el último usado con él en los dos libros, del mismo lado obra o
  personal (`supuesto`) → LLM. Si hay que preguntarlo, las opciones van por uso. **No se
  pregunta mientras esté abierta la pregunta de contratista u obra/personal**
  (`obligatorios.PREGUNTAS_QUE_DEFINEN_EL_RUBRO`): sale de esa respuesta.
- **Frases libres** (`resolver.resolver_segmento`): «Lennon me pasó us$20.000 para la caja»
  → obra, contratista y cuenta firmes de adentro de la frase, y la frase a la descripción;
  dos palabras solo si las dos resuelven firme («Miguel efectivo» sí, «Juan Pérez» no).
  Fechas «28 de septiembre», tipo con typos («INGRRSO»).
- **Personal**: no lleva la obra de un tercero (se descarta con advertencia); Retiro + dual →
  Familia como `supuesto`. El ingreso de una obra administrada ofrece «Adelanto para la caja
  de obra».
- **F · «efectivo» en una obra con caja es la caja** (`_armar`, bloque de la caja de obra),
  lo diga el texto o el comprobante; «efectivo del estudio» (`resolver.RE_EFECTIVO_ESTUDIO`)
  fuerza `Efectivo`. La C y «efectivo del estudio» viajan en `extras` (`caja_de`,
  `efectivo_estudio`) para que una respuesta posterior no los pierda.
- **G · cajas en dólares** (`obligatorios.necesita_tc`): dólares a una caja de obra en
  dólares van **sin tc ni `importe_ars`**; un pago en pesos desde una cuenta en dólares
  lleva el tc del día: se pregunta en el primer pago de esa caja en el día y los siguientes
  lo leen del libro (`_tc_del_dia`, `extras.tc_de_hoy`, advertencia «TC 1.450 (de hoy)»).
  `/confirmar` rechaza ese pago sin tc o con el tc 1 de relleno. El saldo de la caja sale
  en su moneda (`saldos.en_moneda_de_la_cuenta`, `CajaObra.moneda`). «Lo dejamos en
  dólares», «en dólares», «no hay tipo de cambio» contestan el tc si la cuenta está en
  dólares (`RE_SIN_CONVERSION`). `caja_de_obra` también encuentra «Caja obra X USD».
- **Razones sociales completas** (`resolver.contratista_por_razon_social`): «Marcelo
  Alfredo Maragano Guerr» es Marcelo Maragaño. La ñ ya la plegaba `normalizar` (NFKD).

### Endpoints

| Ruta | Estado |
|---|---|
| `GET /salud` | ok, sin auth |
| `POST /interpretar` | Nunca escribe. Lee los libros solo para buscar duplicados |
| `POST /confirmar` | Escribe una fila en MOVIMIENTOS del estudio, en el libro personal o en CERTIFICADOS (dos filas en un traspaso); mueve el comprobante; escribe el alias; reactiva un contratista |
| `GET /movimientos/{id_mov}` | Una fila del libro, quién la anuló y la vinculada. Solo lee |
| `POST /anular` | El contraasiento de §5.19, en el mismo libro que la original |
| `POST /cierre-semanal` | Escribe las líneas semanales de gastos personales. Idempotente. Lo dispara el cron |
| `POST /consultar` | Las tres preguntas del arquitecto. Solo lee |
| `POST /maestros/recargar` | Relee el Sheet y devuelve las advertencias |

Todos menos `/salud` piden `X-API-Key` contra `MOTOR_API_KEY`: el único cliente HTTP es el
gateway. Las personas son otra cosa: viven en `USUARIOS` y se identifican por el `telefono`
que manda el gateway.

### Contrato de `/interpretar`

Entrada:

```jsonc
{
  "telefono": "549294...",              // quien escribe: decide qué libros se miran para duplicados
  "texto": "Felipe J/Lennon",          // texto del mensaje, o el caption del adjunto
  "adjuntos": [
    { "url": "https://drive.google.com/...", "mime": "application/pdf", "nombre": "Cheque9679_....pdf",
      "sha256": "…" }                  // el que manda WhatsApp; si no viene, el motor lo calcula
  ],
  "fecha_mensaje": "2026-09-08T19:29:00Z",
  "contexto_previo": null,              // la ficha anterior: una corrección, o la ficha que se está contestando
  "respuestas": [                       // opcional: respuestas a las preguntas de contexto_previo
    { "ficha": 0, "campo": "obra", "valor": "Lennon" }
  ],
  "texto_compartido": 1                 // N comprobantes con un mismo texto: el gateway llama una vez por comprobante
}
```

Salida:

```jsonc
{
  "intencion": "movimiento",            // movimiento | consulta | otro
  "fichas": [{
    "campos": { /* las columnas de MOVIMIENTOS, o las de un CERTIFICADO o un TRASPASO; null donde falta */ },
    "origen_campo": { "importe": "comprobante", "obra": "texto", "tipo_gasto": "inferido" },
    "faltantes": ["rubro_2"],
    "conflictos": [],
    "confianza": 0.86,
    "regla": "R4: tipo de la obra (obra_terceros)",
    "extras": { "certificado": "4", "fecha_pago": "2026-09-28", "alias_propuesto": {...} },
    "posible_duplicado": null,          // o { id_mov, cargado_por, fecha, importe, fuerza, libro }
    "requiere_confirmacion": true
  }],
  "preguntas": [
    { "campo": "obra", "texto": "¿A qué obra?", "opciones": [...], "motivo": "falta_dato", "ficha": 0 }
  ],
  "requiere_confirmacion": true,        // true si alguna ficha lo requiere
  "diagnostico": { "uso_llm": false, "llm_llamadas": 0, "resoluciones": [...], "advertencias": [] }
}
```

Lo que el gateway tiene que respetar:

- **`origen_campo`** dice de dónde salió cada valor (`texto`, `comprobante`, `maestro`,
  `inferido`, `llm`, `fecha_mensaje`, `contexto_previo`). Es lo que permite mostrar «del
  comprobante» al lado del dato en la ficha de confirmación.
- **`fichas` es una lista.** Casi siempre trae una, pero un mensaje puede traer dos
  movimientos. Cada pregunta dice a qué ficha aplica con `ficha`.
- **`intencion`** (§5.12). `consulta`: una pregunta del estilo de `/consultar` («¿cuánto le
  pagué a…?»); el gateway llama a `/consultar` con el mismo texto. `otro`: charla, «después te
  paso el ticket», un acuse («gracias»), una foto sin nada de un comprobante; `fichas` y
  `preguntas` vienen vacías, `requiere_confirmacion` es false y el gateway responde el acuse
  corto. **Ante la duda, `movimiento`**: una o dos palabras sueltas pueden ser un contratista
  nuevo, y un adjunto que no se pudo leer puede ser un comprobante.
- **Tres formas de ficha.** Un movimiento trae las columnas de MOVIMIENTOS (con `etapa`,
  `informal` y `ref_comprobante`). Un certificado trae `campos.tipo = "CERTIFICADO"` y solo
  `obra · etapa · numero · fecha · saldo_a_cobrar · fuente · comprobante_url`. Un traspaso
  (§5.18) trae `campos.tipo = "TRASPASO"` y `fecha · importe · moneda · tc · importe_ars ·
  cuenta_origen · cuenta_destino · obra · descripcion · comprobante_url · ref_comprobante`;
  `obra` es la de la caja de obra si una de las dos cuentas lo es.
- **Ninguna ficha sale con un obligatorio vacío sin su pregunta** (§5.7 v1.7). La lista de
  obligatorios es una sola, `app/obligatorios.py`, y la usan `/interpretar` (faltantes) y
  `/confirmar` (422). Un paso final genera la pregunta de cada faltante que ninguna otra
  completa: su `campo` puede ser `cuenta`, `contratista`, `rubro`, `importe`, `fecha`,
  `obra`, `etapa`, `tipo_cambio`… y se contesta con `respuestas` como cualquier otra. El
  gateway **no ofrece Confirmar** mientras haya faltantes o preguntas.
- **La cuenta** (§5.7 v1.7): el texto; el comprobante (transferencia o débito → Banco, o
  Banco USD en dólares; cheque → Chequera; Mercado Pago → Mercado Pago; si el originante es
  el comitente de la obra → Pagado por el comitente); la obra (`OBRAS.cuenta_habitual`:
  Lennon → Pagado por el comitente); y si nada lo dice, **Banco / transferencia con origen
  `supuesto`** y la advertencia «Cuenta asumida: Banco». El gateway muestra el `supuesto`
  marcado.
- **La etapa** (§5.15 v1.7): puede ser un número o un nombre (`extras`). Sin etapa en el
  mensaje: una sola en curso → esa, con `origen_campo.etapa = "maestro"` (la ficha dice
  «etapa 1, en curso»); dos o más → pregunta `etapa` con esas. Una futura o terminada nombrada
  → pregunta `activar_etapa` (Sí / No); con «Sí», `extras.activar_etapa` y `/confirmar` la
  pasa a en curso (`ConfirmarOut.etapa_activada`).
- **Dólares** (§5.7 v1.7): todo movimiento en USD y todo traspaso entre Banco USD y pesos
  pregunta `tipo_cambio`, texto libre («1.450», «1450,50»); se guarda en `tc`.
- **`preguntas[].motivo`**: `apodo_ambiguo` y `dual` son preguntas **de diseño**; `conflicto`
  es texto contra comprobante (o cuerpo del PDF contra nombre de archivo); `falta_dato` es que
  no se pudo resolver; `posible_duplicado` es «ya está cargado, ¿es el mismo?», con botones
  «Es el mismo» / «Es otro»; `inactivo` (campo `inactivo`) es «Mercado Libre está inactivo,
  ¿lo reactivo?», con «Reactivar» / «Es otro».
- **`respuestas`.** Cuando el usuario toca un botón (o escribe la respuesta), el gateway manda
  la ficha como `contexto_previo` y la respuesta como `{ficha, campo, valor}`, con el mismo
  `campo` de la pregunta. El motor pone el valor, **vuelve a correr la cascada** (cambiar la
  obra puede cambiar `tipo_gasto`) y devuelve la ficha con las preguntas que sigan faltando;
  cada campo conserva su `origen_campo` («del comprobante» sigue siendo del comprobante). Si
  `valor` no es una de las opciones, se resuelve con el diccionario como cualquier texto.
  `contexto_previo` es **una ficha**: con dos fichas en un mensaje, una llamada por ficha (el
  `ficha` de la respuesta es informativo). Las respuestas a `clasificacion`, `duplicado` e
  `inactivo` quedan en `extras` (`clasificacion_respondida`, `no_es_duplicado` / `es_el_mismo`,
  `reactivar`) para las rondas siguientes: **el gateway tiene que mandar la ficha que devolvió
  el motor**, no la original.
- **`texto_compartido`** (§5.12: varios comprobantes con un texto). Con N > 1, importe y fecha
  salen del comprobante y el importe del texto no genera conflicto (queda una advertencia); si
  ese comprobante no trae importe, se pregunta. Obra, contratista y rubro salen del texto.
- **Un comprobante solo, sin texto**, funciona: importe, fecha y CUIT del comprobante, el
  contratista por CUIT, y el resto a `preguntas`.
- **`requiere_confirmacion`** (contexto §5.12) es la orden para el gateway: si es true, muestra
  la ficha y espera el botón. Hoy es true para todos (ningún usuario tiene `auto_confirmar`).
- **`campos["tipo_gasto"]`** lo decide la cascada, nunca el LLM, y `regla` dice qué regla lo
  decidió.
- **`extras`** lleva lo que no tiene columna: certificado del cobro, fecha de pago del cheque
  diferido, número de operación, CUIT, razón social, advertencias, `alias_propuesto` y, en un
  certificado, lo leído del PDF (`certificado_pdf`).

### Contrato de `/confirmar`

Entrada:

```jsonc
{
  "msg_id": "wamid.HBgN...",     // el wamid del MENSAJE que se confirma, no el del botón «Sí»
  "telefono": "549294...",       // quien confirma: tiene que estar activo en USUARIOS
  "ficha": { "campos": { ... }, "extras": { ... } },   // la de /interpretar, con lo corregido
  "ficha_indice": 0,             // 0, o 1 para el segundo movimiento de un mismo mensaje
  "alias_propuesto": null        // o { "como_lo_dice", "valor_canonico", "tipo" }
}
```

Salida:

```jsonc
{
  "id_mov": "M-000010",          // P-000001 en el libro personal; en un certificado, «Moreno etapa 1 · certificado 5»
  "id_mov_vinculado": null,      // en un traspaso: la segunda fila (la entrada en la cuenta de destino)
  "fila": 11,
  "libro": "estudio",            // estudio | personal | certificados
  "comprobante_url": "https://drive.google.com/...",  // mismo id de archivo, ya en su carpeta
  "obra": { "nombre": "Lennon", "adelantado": 0, "pagado_con_plata_del_estudio": 0,
            "pagado_por_el_comitente": 22110441.70, "saldo": 0, "caja_obra": null },
  "certificado": null,           // en un certificado o en un cobro que nombra uno:
                                 // { obra, etapa, numero, fecha, saldo_a_cobrar, cobrado, pendiente, cobros }
  "alias_escrito": false,
  "contratista_reactivado": false, // la ficha traía extras.reactivar y el contratista estaba inactivo
  "ya_existia": false,           // true si el msg_id ya estaba: se devuelve la fila existente
  "cargado_por": "Gabriel Fachado",
  "advertencias": []
}
```

`id_mov` viene **siempre**: el gateway lo muestra en el acuse para que el usuario pueda
escribir «corregir M-000012». En un certificado es descriptivo (la hoja CERTIFICADOS no tiene
`id_mov`): un certificado no se corrige con `/anular`.

Lo que el gateway tiene que saber:

- **Qué `msg_id` mandar.** El del mensaje original que se está confirmando. Si manda el del
  botón «Sí», dos toques al botón son dos wamid distintos y **se escriben dos filas**.
- **`ficha_indice`.** Un mensaje con dos movimientos manda dos `/confirmar` con el mismo
  `msg_id` e índices 0 y 1. En la columna `msg_id` se guarda `<wamid>#<índice>`.
- **A qué libro va.** `tipo_gasto = personal` va a «FACHADO — Personal» con su propia
  secuencia `P-`; un `CERTIFICADO` va a la hoja CERTIFICADOS; el resto, a MOVIMIENTOS del
  estudio. La idempotencia mira los dos libros de movimientos.
- **Qué es un error y qué no.** 403 si el teléfono no está en USUARIOS, o si lo personal lo
  confirma alguien sin `ve_personal`. 503 si lo personal llega y el libro personal no está
  configurado: **nunca cae en el libro del estudio**. 422 con `{"campo", "detalle"}` si falta
  un obligatorio, la obra o la cuenta no existen, la caja es de otra obra, la etapa no
  corresponde, o un EGRESO llega sin `tipo_gasto`. En todos esos casos no se escribe nada.
  Que el comprobante no se pueda mover o que el alias no se pueda escribir **no** es error.
- **PASANTE** (§5.17): una sola fila con `cuenta = Pagado por el comitente` (la fija el
  motor, venga lo que venga), `informal = VERDADERO` y `concilia = FALSO`. Obligatorios: obra,
  contratista, importe y fecha; `tipo_gasto` se deriva de la obra si falta. Suma a lo pagado
  por el comitente en la obra y no toca el saldo del estudio.
- **TRASPASO** (§5.18): **dos filas en una sola escritura**, las dos `tipo = TRASPASO`, con el
  importe **negativo en la cuenta de origen y positivo en la de destino**, vinculadas por la
  columna `vinculo` (cada una lleva el `id_mov` de la otra) y con `msg_id` `<wamid>#<i>` y
  `<wamid>#<i>b`. La idempotencia reconoce el par. Cada fila concilia según su cuenta y lleva
  la obra si su cuenta es una caja de obra. 422 si falta una cuenta, son la misma, no existe o
  está inactiva, es `externa` («Pagado por el comitente») o las monedas difieren. Van siempre
  al libro del estudio. 500 si el Sheet no tiene la columna `vinculo` (no escribe nada).
- **Reactivar** (§5.6): con `extras.reactivar = true` y un contratista inactivo, después de
  escribir el movimiento pone `estado = activo` en CONTRATISTAS. Si falla, advertencia.

Lo que completa el motor, sin importar qué venga en la ficha: `id_mov`, `origen`,
`concilia`, `estado_conc`, `importe_ars`, `comitente` (de OBRAS), `cargado_por` (de
USUARIOS, nunca «bot»), `ts` (hora local), `msg_id`, `certificado`, `informal` y `vinculo`.

### `GET /movimientos/{id_mov}` y `POST /anular` (§5.19)

```jsonc
// GET /movimientos/M-000012?telefono=549...
→ { "id_mov": "M-000012", "libro": "estudio", "campos": { /* la fila cruda, para mostrarla */ },
    "anulado_por": null, "vinculado": null,
    "extras": { "certificado": "4" },                       // lo que no tiene columna en la ficha
    "ficha": { "campos": {...}, "extras": {...} } }         // lista para contexto_previo de la corrección

// POST /anular
{ "telefono": "549...", "id_mov": "M-000012", "msg_id": "wamid...", "motivo": "otra obra" }
→ { "id_mov_anulacion": "M-000031", "anula": "M-000012", "libro": "estudio",
    "id_mov_anulacion_vinculado": null, "anula_vinculado": null,   // la otra fila, en un traspaso
    "ficha_original": { "campos": {...}, "extras": {...} }, "ya_existia": false }
```

- El libro sale del prefijo: `M-` el del estudio, `P-` el personal. **403** si es personal (un
  `P-`, o un personal viejo que quedó en el libro del estudio) y el teléfono no tiene
  `ve_personal`; 403 si el teléfono no está en USUARIOS; **404** si no existe; 503 si es `P-`
  y el libro personal no está configurado.
- El contraasiento va **al mismo libro**: los mismos campos, el importe con signo contrario,
  **`anula = <id_mov>`**, `origen = ANULACION`, `cargado_por` = quien anula, `descripcion` =
  «Anulación de M-000012 · <motivo>». La original no se toca.
- **Un traspaso se anula entero**: anular cualquiera de sus dos filas escribe los dos
  contraasientos, vinculados entre sí, en una sola escritura.
- **409** si ya estaba anulada: el `detail` trae `id_mov_anulacion`. **422** si se pide anular
  un contraasiento o la línea del cierre semanal (esa se recalcula sola: se anula el personal).
- **Idempotente por `msg_id`**, con clave propia `<wamid>#anula` (y `#anulab`): el mismo
  wamid del «corregir…» puede confirmar después la fila correcta con `<wamid>#0`.
- `ficha_original` (de `/anular`) y `ficha` (de `GET /movimientos`) son la misma: la que va
  como `contexto_previo` de la corrección. Sin `id_mov`, con el certificado en `extras`, y en
  un traspaso con `cuenta_origen`, `cuenta_destino` e importe positivo. **No armarla con los
  `campos` crudos**: un traspaso llegaría con el importe negativo de una sola fila.
- Lo derivado saca el par original + contraasiento (`filtros.sin_anulados`): saldos del
  estudio y de las obras, cajas de obra, `/consultar` («cuántos pagos a X» no cuenta ninguno
  de los dos), cobros de certificados, duplicados y conciliación. En el cierre semanal, un
  personal anulado genera el ajuste de su semana en la corrida siguiente.
- 500 si el Sheet no tiene la columna `anula` (no escribe nada).

### `/cierre-semanal`

`{"semana": "2026-W39"}` o vacío (la semana anterior). Escribe en MOVIMIENTOS del estudio una
fila por semana y cuenta con los egresos personales de esa semana: `origen = CIERRE`,
`concilia = FALSO`, `tipo_gasto = personal`, fecha = el domingo de la semana, `cargado_por =
Cierre semanal`. Revisa todas las semanas hasta la pedida, así que una carga atrasada o una
semana que el cron se salteó generan una fila de **ajuste** por la diferencia; nunca edita una
fila anterior. Idempotente: la clave está en `msg_id` (`cierre:<semana>:<cuenta>#<n>`).

### `/consultar`

```jsonc
{ "telefono": "549294...", "texto": "¿Cuántos pagos se le hicieron a Marcelo por la obra Moreno?" }
// o explícito: { "telefono", "consulta": "pagos" | "gasto" | "certificaciones", "obra", "contratista" }
```

Devuelve `{ consulta, datos, texto, preguntas, advertencias }`. `texto` está listo para
WhatsApp. Si falta algo (un apodo ambiguo, el contratista), `preguntas` trae qué preguntar.
Del texto solo se toman coincidencias firmes del diccionario: nada difuso, nada de LLM.

## 3. Dónde está implementada cada regla

El contexto dice **qué**; esta tabla dice **dónde**. Si cambia una regla allá, se toca acá.

| Regla (contexto) | Dónde vive |
|---|---|
| §5.3 · el orden `algo/algo` no es fijo | `resolver.parsear` + `resolver_token`: se parte por `/` y cada token se resuelve contra los diccionarios |
| §5.5 · diccionario antes que LLM | `resolver.resolver_token` (exacto → palabra única → difuso ≥ 88) y `interpretar._resolver_con_llm` |
| §5.5 · el LLM solo devuelve valores de los maestros | `interpretar._validar`: lo que no existe se descarta |
| §5.5 · un apodo ambiguo **pregunta** | `resolver_token` devuelve `categoria="ambiguo"` → `Pregunta(motivo="apodo_ambiguo")` |
| §5.5 · el CUIT no es clave única | `resolver.contratista_por_cuit` |
| §5.4 · la cascada completa | `clasificador.clasificar`, una regla por rama; la ficha devuelve cuál ganó en `regla` |
| §5.2 · reparto de autoridad texto/comprobante | `interpretar._armar` y `_armar_certificado`, bloques 1 y 2 |
| §5.8 · las cajas de obra no suman al saldo | `maestros.TIPOS_CUENTA_DEL_ESTUDIO` (lista blanca) y `saldos.saldo_estudio`. **Cualquier saldo del estudio sale de ahí** |
| §5.8 · la `C` pegada a la obra y los cobros de certificados en obras administradas | `resolver._obra_con_sufijo` y el bloque «Caja de obra» de `interpretar._armar`; `Maestros.caja_de_obra` |
| §5.8 y §5.9 · el saldo de la obra solo cuenta plata del estudio | `saldos.saldo_obra` |
| §5.11 · el certificado es un documento, no un gasto | `interpretar._es_certificado` / `_armar_certificado`; el PDF en `certificados.parsear` (anclado en «Saldo a cancelar en la presente certificación», texto en modo layout) |
| §5.11 · el cobro cancela al certificado | `certificados.estados`: obra, etapa y número (`clave_numero`) tienen que coincidir |
| §5.12 · nada se escribe sin confirmación; período de prueba | Solo `/confirmar` escribe; `interpretar._requiere_confirmacion` con `USUARIOS.auto_confirmar` |
| §5.13 · un teléfono fuera de USUARIOS no escribe | `confirmar.confirmar` → 403 antes de tocar nada; `cargado_por` = `Usuario.nombre` |
| §5.13 y §5.14 · lo personal, por persona y en otro libro | `confirmar.confirmar` (ruteo, 403, 503), `consultas._visibles`, `interpretar._marcar_duplicados` |
| §5.14 · la línea semanal | `cierre.cierre_semanal`; `filtros.para_conciliacion` la excluye |
| §5.15 · etapas (v1.7: estado, nombre, una en curso) | `Maestros.etapas_en_curso` / `etapa_por_nombre`; `resolver._obra_con_sufijo` (`Lennon1`), `_obra_con_etapa` (`Moreno extras`); `interpretar._decidir_etapa` y `_etapa_del_certificado`; `confirmar.validar_etapa` y `_activar_etapa` |
| §5.7 (v1.7) · de qué cuenta salió | `interpretar._cuenta_del_comprobante`, `Obra.cuenta_habitual` y el bloque «De qué cuenta salió» de `_armar` (origen `supuesto`) |
| §5.7 (v1.7) · nunca Confirmar con un obligatorio vacío | `app/obligatorios.py` (la lista única) e `interpretar._completar_preguntas`; lo verifica `tests/test_corpus.py` (invariante) |
| §5.7 (v1.7) · dólares | pregunta `tipo_cambio` desde `obligatorios` (`tc`); `confirmar.armar_traspaso` (dos monedas) |
| §5.16 · el mismo hecho cargado dos veces | `duplicados.buscar` (referencias fuertes y probables), `interpretar._marcar_duplicados` y `_marcar_certificados_repetidos` |
| §5.17 · depósito = PASANTE informal en «Pagado por el comitente» | `resolver.PALABRAS_TIPO`, `interpretar._armar` y `confirmar.armar_fila` (cuenta forzada, `informal = VERDADERO`), `saldos.saldo_obra`, `filtros.para_iva` / `para_conciliacion` |
| §5.18 · traspasos: dos filas vinculadas | `resolver.RE_EXTRACCION` / `RE_REPOSICION` / `RE_PASE` y `resolver.escanear`; `interpretar._armar_traspaso` (origen y destino por la preposición y la frase); `confirmar.confirmar_traspaso`; `saldos` (importe con signo) |
| §5.19 · corregir con un contraasiento | `anular.anular` y `anular.movimiento`; `filtros.sin_anulados` en todo lo derivado |
| §5.6 · contratistas inactivos | `Contratista.activo`; `resolver.resolver_token` (sin palabra única ni difuso, salvo `incluir_inactivos`), `interpretar._validar` y el prompt de `llm.py`; la pregunta en `interpretar._armar`; `Libro.reactivar_contratista` |
| §5.12 · lo que no es un movimiento | `interpretar._intencion` |
| §5.12 · varios comprobantes con un texto | `texto_compartido` en `interpretar._armar` (y en certificados y traspasos) |
| §5.13 · el LLM sabe quién escribe | `llm.resolver_tokens(quien=, titular=)`, llamado desde `interpretar._resolver_con_llm` con los nombres de USUARIOS |
| §5.1 · libro append-only | `confirmar.py`, `anular.py` y `cierre.py`: filas completas y validadas en memoria; idempotencia, `id_mov` y escritura bajo el mismo lock |
| Lectura de comprobantes | `comprobante.leer` / `leer_bytes`: nombre de archivo → texto del PDF → modelo |
| Destino del comprobante confirmado | `archivo.carpetas` / `nombre_base`; certificados en `archivo.carpetas_certificado` |

`tests/test_reglas.py` y `tests/test_casos.py` verifican las de esta tabla que se pueden
probar sin escribir nada.

## 4. La métrica

```bash
python -m tests.test_corpus            # diccionario + LLM (necesita ANTHROPIC_API_KEY)
python -m tests.test_corpus --sin-llm  # solo diccionario
python -m tests.test_corpus --sheet    # contra el Sheet en vivo, no el snapshot
python -m tests.test_corpus --adjuntos # además baja y lee los comprobantes (requiere OAuth)
python -m tests.test_reglas            # las reglas de negocio, sin métrica
python -m tests.test_casos             # los casos de los handoffs del 25/09 (tandas 1 a 6)
python -m tests.test_confirmar         # /confirmar, /anular, /movimientos, /cierre-semanal y /consultar en memoria
```

**Ningún test escribe en el Sheet real**: MOVIMIENTOS es append-only y una fila de prueba no
se puede borrar. Si alguna vez hace falta probar contra el libro de verdad, que sea con un
movimiento real que el usuario confirma.

La métrica sale **en total y por usuario**. Hoy el corpus es 100 % del titular; cuando Petrus
empiece a cargar, alcanza con que el CSV traiga una columna `telefono` para que cada fila se
atribuya a quien la mandó.

Las 101 filas de CAPTURA se reagrupan en 57 mensajes (50 con texto, 5 correcciones, 2
adjuntos sin texto). Contra el snapshot, con LLM:

| | Antes de las tandas del 25/09 | Después |
|---|---|---|
| Obra/destino sin preguntar | 42/50 (84 %) | 42/50 (84 %) |
| Contratista sin preguntar | 42/50 (84 %) | 42/50 (84 %) |
| Las dos cosas | 34/50 (68 %) | 34/50 (68 %) |
| **Contando las preguntas de diseño** | **46/50 (92 %)** | **46/50 (92 %)** |
| Gabriel Fachado | 68 % · 92 % | 68 % · 92 % |
| Petrus | sin mensajes en el corpus | sin mensajes en el corpus |
| Necesitaron LLM | 9/55 | 9/55 |
| Casos obligatorios | 6/6 | 6/6 |

El caso obligatorio de Moreno cambió de expectativa con la tanda 2: ahora el cobro del
certificado va a `Caja obra Moreno` con `medio_pago = Efectivo` (§5.8).

**Tanda 6, antes y después de 6.7** (el nombre de quien escribe en el prompt del LLM), con
6.1 a 6.5 ya aplicadas:

| | Antes de 6.7 | Después de 6.7 |
|---|---|---|
| Obra · contratista · las dos | 84 % · 84 % · 68 % | 84 % · 84 % · 68 % |
| **Contando las preguntas de diseño** | **46/50 (92 %)** | **46/50 (92 %)** |
| Necesitaron LLM | 9/55 | 9/55 |
| Casos obligatorios | 6/6 | 6/6 |

Comparados mensaje por mensaje, los 57 resuelven igual (obra, contratista, rubro,
`tipo_gasto` y preguntas). La tanda 6 tampoco cambió la intención de ningún mensaje del
corpus: los 57 siguen siendo `movimiento`, y no hay traspasos ni inactivos en el corpus.

**Fix del arranque (30/09):** 92 % → **90 %** (45/50). La diferencia es «Pago Moreno»: su
ficha salía con el contratista en faltantes y sin pregunta —el mismo bug de la cuenta—; ahora
lo pregunta (su comprobante dice «Maragano», sin ñ, y no se resuelve). El test del corpus
suma **el invariante**: ninguna ficha con un faltante sin pregunta (0 de 59), y cuenta como
falla si aparece uno. El corpus corre sin leer los comprobantes, así que casi todo mensaje
con adjunto pregunta el importe: es un artefacto de la medición y no entra en la métrica.

**Conversación del 9/10 (§5.12 v1.8): preguntas por movimiento.** El test suma el promedio de
preguntas por movimiento y el % con cero, en total y para los que traen obra + contratista +
comprobante, y `--historia ARCHIVO.json` siembra los libros en memoria con MOVIMIENTOS reales
(si el archivo no existe, lo baja). Con `--adjuntos --historia`: **1,22 → 0,98** por
movimiento (33 % → 37 % con cero); con obra + contratista + comprobante, **0,63 → 0,45**
(58 % → 65 % con cero). El rubro pasó de 17 preguntas a 4. Detalle al final de
`docs/handoff-conversacion-2026-10-09.md`.

El test corre contra `tests/maestros_snapshot.json` para ser reproducible; se regenera a
propósito con `python scripts/snapshot_maestros.py`. **Desde el 30/09 el snapshot va un paso
adelante del Sheet**: tiene aplicadas las tres migraciones del fix (`--snapshot`). Después
de correrlas en el Sheet, regenerarlo.

## 5. Configuración y deploy

Railway, al lado del gateway, desde GitHub. `nixpacks.toml` fija Python 3.11 y arranca
`uvicorn app.main:app`.

| Variable | Para qué |
|---|---|
| `MOTOR_API_KEY` | Secreto compartido con el gateway (header `X-API-Key`) |
| `FACHADO_SHEET_ID` | `1yoakmhO1--WXCtWWStNrmczgYkaT1g0H54fTK2QCc9A` |
| `FACHADO_PERSONAL_SHEET_ID` | «FACHADO — Personal» (§5.14): `1O4bMJXi4kooBvZZ6Wn-SlGhn2g2QjlANrmw3L7rCcZY`, **cargada en Railway desde el 25/09**. Si se vaciara, lo personal da 503 y nunca cae en el libro del estudio |
| `GOOGLE_CREDENTIALS_JSON` | Service account del gateway, para **leer y escribir los Sheets** |
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` / `_REFRESH_TOKEN` | OAuth de usuario, para **bajar y mover los adjuntos** |
| `DRIVE_CARPETA_COMPROBANTES_ID` | Carpeta raíz «comprobantes», **cargada el 27/09**. Si se vaciara, el motor la busca o la crea la primera vez y devuelve el id en una advertencia. Para obtener el id sin esperar un `/confirmar`: `python -c "from app import sheets; print(sheets.carpeta_drive('comprobantes', None))"` (tiene que correr con las credenciales OAuth del motor) |
| `ANTHROPIC_API_KEY` | |
| `LLM_MODELO` · `LLM_EFFORT` | Default `claude-opus-5` y `low` |
| `MAESTROS_TTL_SEGUNDOS` · `LEER_ADJUNTOS` · `UTC_OFFSET_HORAS` | Default 300 · true · -3 |
| `MAESTROS_SNAPSHOT` | Solo para correr offline; en Railway va vacía |

**El libro personal** ya existe: una hoja `MOVIMIENTOS` con el mismo encabezado que la del
Master, compartida como Editor con la service account. No lleva maestros: usa los del Master.

**El deploy del fix del arranque (30/09).** Después de desplegar el motor, y no antes (la
versión anterior no entiende etapas con nombre ni el estado «futura»), las migraciones del
maestro, en este orden. Cada una muestra primero el simulacro si se corre sin `--aplicar`:

```bash
python scripts/preparar_sheet.py --aplicar                          # OBRAS.cuenta_habitual
python scripts/migraciones/2026_09_30_cuenta_habitual.py --aplicar  # Lennon → Pagado por el comitente
python scripts/migraciones/2026_09_30_etapas.py --aplicar           # Lennon 1; Moreno 1 y extras
python scripts/migraciones/2026_09_30_gessel.py --aplicar           # alias «gessel»
```

Después: `POST /maestros/recargar`, `/interpretar` con `Metro Gas/Grigera Galpón 11.750`
(→ Banco, `supuesto`, sin faltantes) y con `Felipe J/Lennon $300.000` (→ Pagado por el
comitente, `maestro`), y `python scripts/snapshot_maestros.py`. Cada migración se puede
correr con `--snapshot tests/maestros_snapshot.json` para aplicarla solo a la copia de los
tests (`scripts/migraciones/_comun.py`).

**Las columnas de la tanda 6.** `vinculo` (la otra fila de un traspaso, §5.18) y `anula` (la
fila que anula un contraasiento, §5.19) van al final de MOVIMIENTOS **en los dos libros**.
Sin ellas, un traspaso o un `/anular` dan 500 sin escribir nada; el resto sigue funcionando,
y la versión anterior del motor convive con ellas (escribe por nombre de columna). Antes del
deploy de la tanda 6:

```bash
python scripts/preparar_sheet.py --aplicar
python scripts/preparar_sheet.py --personal 1O4bMJXi4kooBvZZ6Wn-SlGhn2g2QjlANrmw3L7rCcZY --aplicar
```

Después del deploy (6.8 del handoff de la tanda): `/salud` y una llamada real a
`/interpretar` —que nunca escribe— con un texto del corpus y con un comprobante solo. **Nunca
un `/confirmar` ni un `/anular` de prueba contra el Sheet real.**

**El cron del cierre semanal.** Un segundo servicio en Railway, desde el mismo repo, con:

- start command `python scripts/cierre_semanal.py`;
- cron schedule `0 11 * * 1` (lunes 8:00 de Argentina, en UTC);
- variables `MOTOR_URL` (la URL pública del motor) y `MOTOR_API_KEY`.

Llama al motor por HTTP para que el cierre use el mismo lock del `id_mov` que `/confirmar`. Si
corre dos veces, la segunda no escribe nada.

Para cargar las variables de una, el editor **Raw** de Railway acepta un pegado estilo `.env`:

```powershell
$vars = Get-Content .env | Where-Object { $_ -match '^[A-Z_]+=.+' -and $_ -notmatch '^GOOGLE_CREDENTIALS_PATH' }
$json = (Get-Content ..\chatbot-contable\config\google_credentials.json -Raw | ConvertFrom-Json | ConvertTo-Json -Compress -Depth 10)
(($vars + "GOOGLE_CREDENTIALS_JSON=$json") -join "`n") | Set-Clipboard
```

### Por qué cada API usa una credencial distinta

- **Sheets → service account** (la del gateway, con el Sheet compartido como **Editor**), con
  scope `spreadsheets`. Usarlo por OAuth de usuario sería un scope **sensible**: publicar la
  app requeriría verificación, y en «Prueba» el token caduca cada 7 días.
- **Drive → OAuth de usuario.** Una service account no tiene cuota en un Drive personal, y
  `drive.file` solo alcanza a los archivos que creó **esa misma app OAuth**: los adjuntos del
  gateway y las carpetas que crea el motor. Por eso **la carpeta «comprobantes» tiene que
  crearla el motor**, y el cliente OAuth tiene que ser el mismo del gateway, con otro refresh
  token:

```bash
pip install google-auth-oauthlib
python scripts/get_google_token.py <client_secret.json>   # autorizar con valencampero@gmail.com
```

## 6. Qué necesita el gateway (nada de esto está hecho del lado del gateway)

El circuito:

1. El gateway sigue archivando en CAPTURA: es la red de seguridad, no se toca.
2. Llama a `POST /interpretar` con el `telefono`, el texto, los adjuntos ya subidos a Drive
   —**con el `sha256` que trae el payload de WhatsApp**— y, si el mensaje es una corrección,
   la ficha anterior **de ese mismo usuario** en `contexto_previo`.
3. Si `requiere_confirmacion` es true (hoy siempre), muestra la ficha con el origen de cada
   campo y los botones de `preguntas`.
4. Cuando el usuario confirma, llama a `POST /confirmar` con el `msg_id` **del mensaje
   original**, el `telefono` de quien confirma y el `ficha_indice`, y responde con lo que
   vuelve (el saldo de la obra, o lo pendiente del certificado).
5. El perfil del tenant pasa de `mode: "captura"` a un modo propio del proyecto `obras`.

Lo nuevo de las tandas del 25/09:

- **Campos nuevos de la ficha**: `etapa`, `informal`, `ref_comprobante`, `posible_duplicado`,
  `requiere_confirmacion`, y la ficha de tipo `CERTIFICADO`, con sus propios campos.
- **La pregunta de duplicado** (`motivo = posible_duplicado`): «Petrus ya cargó un pago igual
  el 27/8 (M-000001). ¿Es el mismo?», con «Es el mismo» / «Es otro». Si es el mismo, el
  gateway **no** llama a `/confirmar`. Si es otro, confirma normalmente.
- **`adjuntos[].sha256`**: es la referencia más fuerte para reconocer el mismo archivo
  mandado por dos usuarios.
- **`ConfirmarOut.libro`** (`estudio · personal · certificados`) y
  **`ConfirmarOut.certificado`** (cuánto queda por cobrar).
- **403 y 503 de lo personal**: sin `ve_personal`, el gateway tiene que decir que esa persona
  no carga lo personal; con 503, que el libro personal todavía no está configurado.
- **`/consultar`**: el gateway puede pasarle el texto tal cual; si vuelven `preguntas`, las
  muestra con botones y repregunta con `consulta`, `obra` y `contratista` explícitos.
- **El cron** del cierre semanal no pasa por el gateway: es un servicio de Railway (§5).

Lo nuevo de la tanda 6 (contratos en §2; las diferencias con el handoff de la tanda están
anotadas al final de `docs/handoff-tanda-6-2026-09-25.md`):

- **`intencion`**: con `consulta`, llamar a `/consultar` con el mismo texto; con `otro`,
  responder el acuse corto («Recibido, no encontré un movimiento») sin preguntar nada.
- **`respuestas`**: cada botón vuelve como `{ficha, campo, valor}` junto con la ficha **que
  devolvió el motor** en `contexto_previo`. La ficha nueva reemplaza a la anterior.
- **`texto_compartido`**: N comprobantes y un texto → N llamadas a `/interpretar` con el mismo
  texto y `texto_compartido = N`; las N fichas se confirman juntas con un solo «sí» (§5.12).
- **Traspasos**: la ficha `TRASPASO` se confirma como cualquier otra; el acuse puede mostrar
  `id_mov` e `id_mov_vinculado`.
- **Corregir**: «corregir M-000012» (o la respuesta al acuse) → `GET /movimientos/M-000012`
  para mostrarlo → `POST /anular` → la `ficha_original` como `contexto_previo` de la ficha
  correcta, que se confirma con `/confirmar`. 409 = ya estaba anulado.
- **Inactivos**: la pregunta `inactivo` («¿lo reactivo?») se contesta con `respuestas`; si
  dijo «Reactivar», la ficha trae `extras.reactivar` y `/confirmar` lo reactiva.
- **Arranque escalonado** (§5.13): primero solo Gabriel; Petrus después de la primera semana.

Lo nuevo del 9/10 (motor; lo del gateway está en su propio handoff):

- **El rubro puede llegar después**: con la pregunta de contratista u obra/personal abierta,
  el motor no pregunta el rubro; lo deduce (o lo pregunta) cuando vuelve la respuesta. El
  gateway ya recalcula las preguntas con cada `respuestas`: no hace falta cambiar nada.
- **`obra.caja_obra.moneda`** en `ConfirmarOut`: «USD» para la caja de Lennon después de
  la migración. El acuse tiene que mostrar el saldo de la caja con esa moneda (US$), no «$».
- **La pregunta de tipo de cambio** de un pago en pesos desde la caja en dólares dice «Caja
  obra Lennon está en dólares. ¿A qué tipo de cambio pagaste hoy? …». Los siguientes pagos
  del día vienen sin pregunta y con la advertencia «TC 1.450 (de hoy)», para mostrar en la
  ficha. «Lo dejamos en dólares» / «en dólares» / «no hay tipo de cambio» son respuestas
  válidas cuando la cuenta está en dólares: el gateway las manda como el `valor` de
  `tipo_cambio`, sin validarlas como número.

Lo que el gateway tiene que cambiar para tener dos usuarios (contexto §5.13): hoy un teléfono
es un perfil (`config/tenants/<telefono>.json`). **Varios teléfonos tienen que mapear al mismo
cliente**, y la sesión —la ficha pendiente, la anterior para las correcciones— tiene que
seguir siendo por teléfono, para que la corrección de uno no se aplique a la ficha del otro.

Dos cosas del corpus que el agrupamiento del gateway tiene que contemplar (contexto §8): **el
adjunto a veces llega 8 a 18 segundos antes que el texto** que lo etiqueta, y **el usuario
manda mensajes repetidos** con un segundo de diferencia.

## 7. Lo que falta

**Operativo**

- [ ] Confirmar que el primer cierre semanal corrió el lunes 28/09 (logs del servicio
      `cierre-semanal` en Railway).
- [ ] **Encender el gateway**: el runbook de `chatbot-contable/docs/handoff-fachado.md` §6, en
      la reunión del martes 29/09 (ensayo primero, después la primera fila real).
- [ ] **La primera fila real**, con un movimiento verdadero, mirándola en el Sheet.
- [x] ~~**Desplegar el fix del 30/09 y correr sus cuatro migraciones**~~ — 30/09.
- [ ] **Desplegar lo del 9/10** y después, en orden: `scripts/migraciones/2026_10_09_caja_lennon_usd.py
      --aplicar` (la caja no tiene movimientos: cambia la moneda), regenerar el snapshot
      (`python scripts/snapshot_maestros.py`) y, cuando Valen lo decida,
      `scripts/migraciones/2026_10_09_correcciones.py --aplicar` (con `--con-ingreso-usd`
      solo si Gabriel confirmó el ingreso de USD 20.000). Simulacro de las dos: al final del
      handoff del 9/10.
- [x] ~~`DRIVE_CARPETA_COMPROBANTES_ID`~~ — fijada el 27/09 (la carpeta «comprobantes» la creó
      la misma app OAuth del motor).
- [x] ~~Claves y réplicas~~ — verificado el 27/09: `MOTOR_API_KEY` igual a
      `FACHADO_MOTOR_API_KEY` del gateway, y una sola réplica de `web`.
- [ ] Correr `python -m tests.test_corpus --sheet --adjuntos`: la métrica con los
      comprobantes reales.
- [ ] Correr en Python 3.11 (local hay 3.14; Railway ya está fijado en 3.11).

**Código, esperando una decisión del contexto**

- [ ] **Lennon con un comprobante de transferencia sin el CUIT del comitente legible**: por
      el orden de §5.7 (el comprobante antes que la obra) va a Banco. ¿Debería ganar la obra?
- [x] ~~**La ñ en las razones sociales**~~ — 9/10: la ñ ya se plegaba; lo que faltaba era
      emparejar la razón social completa («Marcelo Alfredo Maragano Guerr»).
- [ ] **Las preguntas abiertas del 9/10** (al final de `docs/handoff-conversacion-2026-10-09.md`):
      el rubro de Edesur, Sofía Cervera / Sofía Fachado, los pagos de Lennon de febrero y
      agosto antes del adelanto del 28/09, la etapa de Moreno (13 preguntas en el corpus).
- [ ] **Caja de obra en negativo** (5 del handoff del 30/09, supuesto P-28): no se hizo.
- [ ] **Corregir un certificado**: CERTIFICADOS no tiene `id_mov` y `/anular` es solo para
      MOVIMIENTOS. Un certificado mal cargado hoy no tiene cómo corregirse.
- [ ] **Las series de certificados de Moreno** («cert 4» y «cert 4 extras», «cert.pintura»,
      «certificado 18 obra»): el motor las trata como números distintos y no las mezcla, pero
      el contexto no dice si son series ni cómo se numeran.
- [ ] Qué es «Estudio» en `Estudio/Austral`, y a qué certificado corresponden las cuatro
      fotos del 11/9 que dicen solo «ingreso» (abiertas en el handoff del proyecto).

**Código, sin decisión pendiente**

- [ ] El lock del `id_mov` es de proceso: alcanza con un solo worker, que es como está
      desplegado. Si algún día se escala a más de una réplica, hay que moverlo.
- [ ] `intencion = otro` para texto se decide por reglas (sin nada reconocible, y un acuse o
      una frase de tres palabras o más). Si en la carga real aparecen movimientos marcados
      como `otro`, ajustar `interpretar._intencion` y sumar el caso al test.
- [ ] Conciliación contra `BANCO_RAW` (§5.6), con los filtros de `app/filtros.py`.
- [ ] IVA con alcance completo (§5.10), con `filtros.para_iva`. Se planifica aparte.

## 8. Estado de los datos del Sheet

**Pendiente del 9/10** (nada aplicado; los dos scripts con simulacro por defecto):

- `Caja obra Lennon` en ARS en el Sheet → USD con `2026_10_09_caja_lennon_usd.py`. El
  snapshot de los tests **sigue igual al Sheet** (ARS): los tests la pasan a dólares solo
  mientras dura el caso (`tests/dobles.cuenta_en_moneda`).
- Los tres pagos de Lennon contra `Efectivo` (M-000001, M-000008, M-000010, $ 13.640.000),
  P-000001 (obra Moreno y contratista Tucu en un personal) y el `medio_pago = Otro` de
  P-000004/5: `2026_10_09_correcciones.py`, por contraasiento.

El maestro lo mantiene una persona a mano, así que llega sucio. El motor no lo corrige solo:
resuelve lo que puede y **deja advertencias**, que se ven en `POST /maestros/recargar`.

**Corregido el 25/09** (`scripts/migraciones/2026_09_25_tanda1.py`, idempotente; nada se
borró):

- `CUENTAS` tiene una columna `estado`. La fila mal cargada «caja_obra» pasó a `inactiva`, y
  hay una «Caja obra X» por cada obra de terceros activa (Lennon, Moreno, Cerro Bayo, Lumaia,
  Muelle de piedra, Tonga, Moquehue). Las obras propias no tienen caja.
- **Los tres cobros de Moreno (M-000007 a M-000009)** pasaron de `Efectivo` a `Caja obra
  Moreno` (§5.8). **El saldo del estudio bajó $5.245.596**, de $5.245.596 a $0; esa plata
  queda como `por_rendir` en la caja de Moreno.
- `USUARIOS` tiene `ve_personal` y `auto_confirmar`, y Petrus su teléfono. En `TERCEROS`,
  Petrus volvió a `activo` (§5.13).
- «Pint Andina» → «Pinturería Andina», con los alias `pint andina` y `ferr andina` (§7).
- Hojas nuevas: `ETAPAS` y `CERTIFICADOS`, vacías.
- **«Luis Pereyra» → `inactivo`** (`scripts/migraciones/2026_09_25_luis_pereyra.py`): es la
  misma persona que «Luis Pereira», confirmado por Valentín. El alias `luis pereyra` ya
  apuntaba a Pereira. Efecto en el corpus: en «Retiro/Luis/CASA», «Luis» ahora identifica a
  un único contratista activo y se atribuye a Luis Pereira (sigue siendo personal, sin
  preguntas; la métrica no cambia).
- MOVIMIENTOS de los dos libros tiene las columnas `vinculo` y `anula` (tanda 6).

Lo que el motor todavía avisa:

- **Filas repetidas en CONTRATISTAS** (Maderera Misiones, Marcelo Maragaño, Silla Cuádruple):
  se fusionan tomando los valores no vacíos de la última.
- **Rubros habituales que no existen en RUBROS**: Contador Pasolli («Honorarios / Terceros»).
  Los contratistas inactivos no se revisan: su rubro habitual no se usa.
- **Filas que no se aplican**: un alias con un `tipo` fuera de `contratista·obra·cuit·tipo`, o
  un contratista con `rubro_habitual_2` sin `rubro_habitual_1`.
- **M-000001 y M-000002 tienen `cargado_por = bot`**, de antes de que existiera USUARIOS.
  *(Nota del 9/10: esos eran los del libro anterior; en el libro actual M-000001 es el pago a
  Luis Pereira del 7/02.)*
- Los cobros de Moreno ya cargados (M-000007 a M-000009) tienen el certificado solo en la
  descripción («Certificado 4», «4 extras», «pintura»), no en la columna `certificado`: en
  `/consultar` no cancelan ningún certificado.
