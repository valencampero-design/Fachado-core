# Handoff — `fachado-core`, el motor de imputación de Fachado

> **Estado técnico del repo al 2026-09-24.** Qué está hecho, qué falta, cómo se corre y qué
> variables hacen falta.
>
> **Las reglas de negocio NO viven acá: viven en `CONTEXTO-FACHADO.md`** (v1.3), que se edita
> en el proyecto de Claude de A&C y baja a los dos repos. Si este documento y el contexto se
> contradicen, **gana el contexto**. Este handoff dice dónde está implementada cada regla, no
> cuál es.
>
> Repo hermano: `chatbot-contable`, el gateway de WhatsApp, en producción en Railway.
> Su handoff del paso 0: `chatbot-contable/docs/handoff-fachado.md`.

## 0. Dónde quedó (para retomar)

| | |
|---|---|
| ✅ Motor en producción | `https://web-production-6c935.up.railway.app` · `/salud`, `/interpretar` y `/confirmar` desplegados |
| ✅ GitHub | `valencampero-design/Fachado-core` (se renombró con mayúscula), rama `main` |
| ✅ Lee y escribe el Sheet | Con la service account del gateway, compartida como Editor |
| ✅ Lee los comprobantes | Token de Drive cargado en Railway. Verificado en producción: «Felipe J/Lennon» + su PDF da importe $300.000 y fecha 02/09 **desde el comprobante** |
| ✅ App OAuth publicada | En producción: el token ya no vence a los 7 días. Solo falta la verificación de **marca**, que es cosmética (la pantalla de consentimiento dice «no verificada») y no hace falta |
| ✅ Métrica del corpus | Obra 84 %, contratista 84 %, **92 % contando las preguntas de diseño**, 6/6 casos obligatorios (§4) |
| ✅ `/confirmar` | Idempotencia por `msg_id`, lock del `id_mov`, `tests/test_confirmar.py`. Verificado en producción que un teléfono desconocido da 403. **Todavía no escribió ninguna fila real** |
| ✅ Maestro alineado al contexto | Mercado Libre, Silla Cuádruple, Andina y Municipalidad corregidos el 24/09 (§8) |
| ⏳ Primera fila real | Con un movimiento verdadero, antes de conectar el gateway |
| ⏳ Petrus | Falta su teléfono en USUARIOS: lo asigna el arquitecto |
| ⏳ Conectar el gateway | Es el paso que hace que el sistema exista para el arquitecto (§6) |
| ⏳ `/consultar`, conciliación, IVA | No empezados (§7) |

## 1. Qué es este repo

El motor de imputación: sabe de obras, contratistas, rubros y conciliación, y **no sabe nada
de WhatsApp**. API HTTP **sin estado**. El reparto con el gateway y el porqué están en el
contexto §2.

Lo que eso implica acá: se prueba con `curl` y con el corpus de 101 mensajes reales sin mandar
un WhatsApp, y si el motor se cae el gateway sigue archivando en modo captura.

## 2. Qué hay implementado

```
app/
  main.py          FastAPI, rutas, auth por X-API-Key
  config.py        settings desde env
  models.py        Pydantic de entrada y salida + las columnas de MOVIMIENTOS
  maestros.py      carga y cachea OBRAS, CONTRATISTAS, RUBROS, CUENTAS, ALIAS, USUARIOS
  resolver.py      texto libre → obra / contratista / rubro / cuenta, SIN LLM
  clasificador.py  la cascada obra / estructura / personal, SIN LLM
  interpretar.py   orquesta: resolver → LLM para lo que falta → comprobante → ficha
  llm.py           cliente de Anthropic, prompts y esquemas de salida
  comprobante.py   nombre de archivo → texto del PDF → visión
  confirmar.py     /confirmar: valida, asigna id_mov bajo lock, escribe, archiva, alias
  libro.py         el puerto al libro (MOVIMIENTOS y ALIAS): real o en memoria para tests
  archivo.py       dónde queda cada comprobante, y el puerto a Drive
  saldos.py        saldo de una obra y saldo del estudio, derivados del libro
  sheets.py        clientes de Google Sheets (service account) y Drive (OAuth), con reintentos
scripts/
  get_google_token.py    genera el refresh token de Drive, se corre una vez
  snapshot_maestros.py   baja los maestros a tests/maestros_snapshot.json
  preparar_sheet.py      deja el Sheet listo para /confirmar (columnas y USUARIOS). Idempotente
tests/
  corpus.csv             las 101 filas de la hoja CAPTURA
  maestros_snapshot.json copia de los maestros, para correr reproducible y offline
  test_corpus.py         la métrica: cuánto resuelve sin preguntar, en total y por usuario
  test_reglas.py         que lo que resuelve sea lo que el negocio decidió
  test_confirmar.py      /confirmar contra un libro en memoria: nunca escribe en el Sheet real
```

### Endpoints

| Ruta | Estado |
|---|---|
| `GET /salud` | ok, sin auth |
| `POST /interpretar` | **implementado.** Nunca escribe nada |
| `POST /confirmar` | **implementado.** Escribe una fila en MOVIMIENTOS, mueve el comprobante, escribe el alias |
| `POST /maestros/recargar` | implementado: relee el Sheet y devuelve las advertencias |
| `POST /consultar` | 501, pendiente |

Todos menos `/salud` piden `X-API-Key` contra `MOTOR_API_KEY`: el único cliente HTTP es el
gateway. Las personas son otra cosa: viven en `USUARIOS` y se identifican por el `telefono`
que manda el gateway en cada `/confirmar`.

### Contrato de `/interpretar`

Entrada:

```jsonc
{
  "telefono": "549294...",              // quien escribe, como llega de WhatsApp
  "texto": "Felipe J/Lennon",          // texto del mensaje, o el caption del adjunto
  "adjuntos": [
    { "url": "https://drive.google.com/...", "mime": "application/pdf", "nombre": "Cheque9679_....pdf" }
  ],
  "fecha_mensaje": "2026-09-08T19:29:00Z",
  "contexto_previo": null               // la ficha anterior, si esto es una corrección
}
```

Salida:

```jsonc
{
  "fichas": [{
    "campos": { /* las columnas de MOVIMIENTOS, null donde falta */ },
    "origen_campo": { "importe": "comprobante", "obra": "texto", "tipo_gasto": "inferido" },
    "faltantes": ["rubro_2"],
    "conflictos": [],
    "confianza": 0.86,
    "regla": "R4: tipo de la obra (obra_terceros)",
    "extras": { "certificado": "4", "fecha_pago": "2026-09-28", "alias_propuesto": {...} }
  }],
  "preguntas": [
    { "campo": "obra", "texto": "¿A qué obra?", "opciones": [...], "motivo": "falta_dato", "ficha": 0 }
  ],
  "diagnostico": { "uso_llm": false, "llm_llamadas": 0, "resoluciones": [...] }
}
```

Lo que el gateway tiene que respetar:

- **`origen_campo`** dice de dónde salió cada valor (`texto`, `comprobante`, `maestro`,
  `inferido`, `llm`, `fecha_mensaje`, `contexto_previo`). Es lo que permite mostrar «del
  comprobante» al lado del dato en la ficha de confirmación.
- **`fichas` es una lista.** Casi siempre trae una, pero un mensaje puede traer dos
  movimientos. Cada pregunta dice a qué ficha aplica con `ficha`.
- **`preguntas[].motivo`**: `apodo_ambiguo` y `dual` son preguntas **de diseño** —el maestro
  dice que hay que preguntar—; `conflicto` es texto contra comprobante; `falta_dato` es que no
  se pudo resolver. Sirve para mostrarlas distinto y para medir bien.
- **`campos["tipo_gasto"]`** lo decide la cascada, nunca el LLM, y `regla` dice qué regla lo
  decidió.
- **`extras`** lleva lo que no tiene columna: certificado, fecha de pago del cheque diferido,
  número de operación, CUIT, razón social, advertencias y `alias_propuesto`. `/confirmar`
  persiste el certificado en su propia columna (contexto §5.11).

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
  "id_mov": "M-000010",
  "fila": 11,
  "comprobante_url": "https://drive.google.com/...",  // mismo id de archivo, ya en su carpeta
  "obra": {
    "nombre": "Lennon",
    "adelantado": 0,
    "pagado_con_plata_del_estudio": 0,
    "pagado_por_el_comitente": 22110441.70,
    "saldo": 0,                   // solo cuenta la plata del estudio
    "caja_obra": null             // { ingresado, pagado, por_rendir } si la obra tiene caja
  },
  "alias_escrito": false,
  "ya_existia": false,           // true si el msg_id ya estaba: se devuelve la fila existente
  "cargado_por": "Gabriel Fachado",
  "advertencias": []
}
```

Lo que el gateway tiene que saber:

- **Qué `msg_id` mandar.** El del mensaje original que se está confirmando. Si manda el del
  botón «Sí», dos toques al botón son dos wamid distintos y **se escriben dos filas**.
- **`ficha_indice`.** Un mensaje con dos movimientos manda dos `/confirmar` con el mismo
  `msg_id` e índices 0 y 1. En la columna `msg_id` del libro se guarda `<wamid>#<índice>`.
- **Qué es un error y qué no.** 403 si el teléfono no está en USUARIOS; 422 con
  `{"campo", "detalle"}` si falta un obligatorio, la obra o la cuenta no existen, o un EGRESO
  llega sin `tipo_gasto`. En todos esos casos no se escribe nada. Que el comprobante no se
  pueda mover o que el alias no se pueda escribir **no** es error: la fila se escribe y vuelve
  una advertencia.
- **Un TRASPASO todavía no se puede confirmar** (422): MOVIMIENTOS tiene una sola columna
  `cuenta` y un traspaso necesita origen y destino. Está en §7.

Lo que completa el motor, sin importar qué venga en la ficha: `id_mov`, `origen`,
`concilia`, `estado_conc`, `importe_ars`, `comitente` (de OBRAS), `cargado_por` (de
USUARIOS, nunca «bot»), `ts` (hora local), `msg_id` y `certificado`.

## 3. Dónde está implementada cada regla

El contexto dice **qué**; esta tabla dice **dónde**. Si cambia una regla allá, se toca acá.

| Regla (contexto) | Dónde vive |
|---|---|
| §5.3 · el orden `algo/algo` no es fijo | `resolver.parsear` + `resolver_token`: se parte por `/` y cada token se resuelve contra los diccionarios |
| §5.5 · diccionario antes que LLM | `resolver.resolver_token` (exacto → palabra única → difuso ≥ 88) y `interpretar._resolver_con_llm` |
| §5.5 · el LLM solo devuelve valores de los maestros | `interpretar._validar`: lo que no existe se descarta |
| §5.5 · un apodo ambiguo **pregunta** | `resolver_token` devuelve `categoria="ambiguo"` con las opciones cuando empatan dos filas de ALIAS → `Pregunta(motivo="apodo_ambiguo")` |
| §5.5 · el CUIT no es clave única | `resolver.contratista_por_cuit`, que junta los CUIT de CONTRATISTAS y los de ALIAS |
| §5.4 · la cascada completa | `clasificador.clasificar`, una regla por rama; la ficha devuelve cuál ganó en `regla` |
| §5.2 · reparto de autoridad texto/comprobante | `interpretar._armar`, bloques 1 y 2; los choques de importe o fecha van a `conflictos` |
| §5.8 · las cajas de obra no suman al saldo | `maestros.TIPOS_CUENTA_DEL_ESTUDIO` (lista blanca: un tipo mal cargado queda afuera, no adentro) y `saldos.saldo_estudio`. **Cualquier cálculo de saldo del estudio tiene que salir de ahí** |
| §5.8 y §5.9 · el saldo de la obra solo cuenta plata del estudio | `saldos.saldo_obra`: lo que pagó el comitente se informa aparte y la caja de obra también |
| §5.11 · el certificado viaja con el cobro | `extras["certificado"]` → columna `certificado` de MOVIMIENTOS al confirmar |
| §5.12 · nada se escribe sin confirmación | Solo `/confirmar` escribe; `/interpretar` es una función pura |
| §5.13 · un teléfono fuera de USUARIOS no escribe | `confirmar.confirmar` → 403 antes de tocar nada; `cargado_por` = `Usuario.nombre` |
| §5.1 · libro append-only | `confirmar.py`: fila completa y validada en memoria, idempotencia por `msg_id`, `id_mov` y escritura bajo un mismo lock |
| Lectura de comprobantes | `comprobante.leer`: nombre de archivo → texto del PDF → modelo |
| Destino del comprobante confirmado | `archivo.carpetas` y `archivo.nombre_base` |

`tests/test_reglas.py` verifica las de esta tabla que se pueden probar sin escribir nada.

## 4. La métrica

```bash
python -m tests.test_corpus            # diccionario + LLM (necesita ANTHROPIC_API_KEY)
python -m tests.test_corpus --sin-llm  # solo diccionario
python -m tests.test_corpus --sheet    # contra el Sheet en vivo, no el snapshot
python -m tests.test_corpus --adjuntos # además baja y lee los comprobantes (requiere OAuth)
python -m tests.test_reglas            # las reglas de negocio, sin métrica
python -m tests.test_confirmar         # /confirmar contra un libro en memoria
```

**`test_confirmar` nunca escribe en el Sheet real**: MOVIMIENTOS es append-only y una fila de
prueba no se puede borrar. Si alguna vez hace falta probar contra el libro de verdad, que sea
con un movimiento real que el usuario confirma.

La métrica sale **en total y por usuario**. Hoy el corpus es 100 % del titular; cuando Petrus
empiece a cargar, alcanza con que el CSV traiga una columna `telefono` (la hoja CAPTURA la
tiene) para que cada fila se atribuya a quien la mandó.

Las 101 filas de CAPTURA se reagrupan en 57 mensajes (50 con texto, 5 correcciones, 2
adjuntos sin texto). Contra el Sheet en vivo (sin cambios desde la reunión 3: `/confirmar` no
toca `/interpretar`):

| | Antes de la reunión 3 | Después |
|---|---|---|
| Obra/destino sin preguntar | 42/50 (84 %) | 42/50 (84 %) |
| Contratista sin preguntar | 50/50 (100 %) | 42/50 (84 %) |
| Las dos cosas | 42/50 (84 %) | 34/50 (68 %) |
| **Contando las preguntas de diseño** | 46/50 (92 %) | **46/50 (92 %)** |
| Necesitaron LLM | 10/55 | 9/55 |
| Casos obligatorios | 6/6 | 6/6 |

La caída de «contratista sin preguntar» **es el comportamiento correcto**: antes «Marce» y
«Marcelo» se resolvían solos a una persona, y son tres. Ahora preguntan. La línea que mide la
calidad real del parser es la de preguntas de diseño, que no se movió.

Lo que todavía pregunta por falta de dato: 4 capturas cuyo único texto es «ingreso», que se
resolverían leyendo el CUIT del comitente en el comprobante.

El test corre contra `tests/maestros_snapshot.json` para ser reproducible; se regenera a
propósito con `python scripts/snapshot_maestros.py`.

## 5. Configuración y deploy

Railway, al lado del gateway, desde GitHub. `nixpacks.toml` fija Python 3.11 y arranca
`uvicorn app.main:app`.

| Variable | Para qué |
|---|---|
| `MOTOR_API_KEY` | Secreto compartido con el gateway (header `X-API-Key`) |
| `FACHADO_SHEET_ID` | `1yoakmhO1--WXCtWWStNrmczgYkaT1g0H54fTK2QCc9A` |
| `GOOGLE_CREDENTIALS_JSON` | Service account del gateway, para **leer y escribir el Sheet** |
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` / `_REFRESH_TOKEN` | OAuth de usuario, para **bajar y mover los adjuntos** |
| `DRIVE_CARPETA_COMPROBANTES_ID` | Carpeta raíz «comprobantes». Si queda vacía, el motor la crea la primera vez y devuelve el id en una advertencia |
| `ANTHROPIC_API_KEY` | |
| `LLM_MODELO` · `LLM_EFFORT` | Default `claude-opus-5` y `low` |
| `MAESTROS_TTL_SEGUNDOS` · `LEER_ADJUNTOS` · `UTC_OFFSET_HORAS` | Default 300 · true · -3 |
| `MAESTROS_SNAPSHOT` | Solo para correr offline; en Railway va vacía |

Para cargarlas de una, el editor **Raw** de Railway acepta un pegado estilo `.env`:

```powershell
$vars = Get-Content .env | Where-Object { $_ -match '^[A-Z_]+=.+' -and $_ -notmatch '^GOOGLE_CREDENTIALS_PATH' }
$json = (Get-Content ..\chatbot-contable\config\google_credentials.json -Raw | ConvertFrom-Json | ConvertTo-Json -Compress -Depth 10)
(($vars + "GOOGLE_CREDENTIALS_JSON=$json") -join "`n") | Set-Clipboard
```

### Por qué cada API usa una credencial distinta

- **Sheets → service account** (la del gateway, con el Sheet compartido como **Editor**), con
  scope `spreadsheets`: desde `/confirmar` escribe. Usarlo por OAuth de usuario sería un scope
  **sensible**: publicar la app OAuth requeriría verificación, y en «Prueba» el token caduca
  cada 7 días. La service account no tiene consentimiento ni vencimiento. Si no hay service
  account configurada, el motor cae a OAuth y lo avisa por log.
- **Drive → OAuth de usuario.** Una service account no tiene cuota en un Drive personal, y
  `drive.file` solo alcanza a los archivos que creó **esa misma app OAuth**: los adjuntos del
  gateway y las carpetas que crea el motor. Por eso **la carpeta «comprobantes» tiene que
  crearla el motor**, no una persona a mano, y el cliente OAuth tiene que ser el mismo del
  gateway, con otro refresh token:

```bash
pip install google-auth-oauthlib
python scripts/get_google_token.py <client_secret.json>   # autorizar con valencampero@gmail.com
```

## 6. Cómo se conecta el gateway (nada de esto está hecho del lado del gateway)

1. El gateway sigue archivando en CAPTURA: es la red de seguridad, no se toca.
2. Además llama a `POST /interpretar` con el texto, los adjuntos ya subidos a Drive y, si el
   mensaje parece una corrección, la ficha anterior **de ese mismo usuario** en
   `contexto_previo`.
3. Muestra la ficha con el origen de cada campo y los botones de `preguntas`.
4. Cuando el usuario confirma, llama a `POST /confirmar` con el `msg_id` **del mensaje
   original** (no del botón), el `telefono` de quien confirma y el `ficha_indice`.
5. El perfil del tenant pasa de `mode: "captura"` a un modo propio del proyecto `obras`.

Lo que el gateway tiene que cambiar para tener dos usuarios (contexto §5.13): hoy un teléfono
es un perfil (`config/tenants/<telefono>.json`). **Varios teléfonos tienen que mapear al mismo
cliente**, y la sesión —la ficha pendiente, la anterior para las correcciones— tiene que
seguir siendo por teléfono, para que la corrección de uno no se aplique a la ficha del otro.

Dos cosas del corpus que el agrupamiento del gateway tiene que contemplar (también anotadas en
el contexto §8): **el adjunto a veces llega 8 a 18 segundos antes que el texto** que lo
etiqueta, y **el usuario manda mensajes repetidos** con un segundo de diferencia.

## 7. Lo que falta

**Operativo**

- [ ] **La primera fila real**, con un movimiento verdadero, mirándola en el Sheet antes de
      que el gateway dependa de `/confirmar`: los tests corren contra un libro en memoria.
- [ ] **Cargar el teléfono de Petrus en USUARIOS.** Hasta entonces no puede confirmar nada.
- [ ] La primera vez que un `/confirmar` mueva un comprobante, el motor crea la carpeta
      «comprobantes» y devuelve su id en una advertencia: cargarlo en
      `DRIVE_CARPETA_COMPROBANTES_ID` en Railway.
- [ ] Correr `python -m tests.test_corpus --sheet --adjuntos`: la métrica con los
      comprobantes reales. Hoy la métrica se mide sin leerlos.
- [ ] Revisar el token de Drive **del gateway**: si se generó cuando la app estaba en
      «Prueba», vence cada 7 días aunque la app ya esté publicada. Si los adjuntos siguen
      apareciendo con link en CAPTURA, está bien.
- [ ] Cargar en `CUENTAS` una fila por obra administrada con `tipo = caja_obra` (contexto
      §5.8), y corregir la fila llamada «caja_obra» (§8).
- [ ] Correr en Python 3.11 (local hay 3.14; Railway ya está fijado en 3.11).

**Código**

- [ ] `POST /consultar` — saldos y cuentas corrientes por obra. `app/saldos.py` ya los
      calcula; falta exponerlos.
- [ ] **TRASPASO en `/confirmar`**: MOVIMIENTOS tiene una sola columna `cuenta`. Cómo se
      registra un traspaso (dos filas, o una columna de cuenta destino) es una decisión de
      modelo que tiene que escribirse en el contexto antes de implementarla.
- [ ] Corregir un movimiento ya confirmado. El libro es append-only: hace falta definir si
      una corrección es un contraasiento o una fila que reemplaza a otra.
- [ ] El lock del `id_mov` es de proceso: alcanza con un solo worker, que es como está
      desplegado. Si algún día se escala a más de una réplica, hay que moverlo.
- [ ] **El resolver no mira `estado`**: un contratista inactivo se sigue reconociendo. Hoy
      «Mercado Libre/Moreno» todavía lo toma como contratista, aunque el maestro ya lo marca
      inactivo y el contexto §5.6 dice que va a `medio_pago`. Falta definir en el contexto qué
      hace un inactivo y **dónde viven los medios de pago en el maestro** (hoy no hay hoja ni
      tipo de alias para eso).
- [ ] El número de operación viene en el nombre de algunos PDF del homebanking
      (`13851988_LR92K2y581_1.pdf`) y el parser de texto no lo saca. Mejora chica.
- [ ] Conciliación contra `BANCO_RAW`, que incluye **la regla de cruce de Mercado Libre**
      (contexto §5.6): cruzar por fecha e importe los comprobantes recibidos contra las líneas
      del extracto, y lo que no cruza queda como personal sin clasificar.
- [ ] **IVA con alcance completo** (contexto §5.10): distinguir factura emitida de comprobante
      de gasto, extraer neto / IVA / tipo / número / CUIT, y usar las emitidas como fuente de
      los ingresos por honorarios. Alcance nuevo, se planifica aparte.
- [ ] Detección de pagos duplicados. **Ojo con el falso positivo conocido**: el cheque 510 y
      la transferencia del 27/08 a Eco Aislación, los dos por $4.032.391,70, **son dos pagos
      distintos** (reunión 3). La idempotencia de `/confirmar` es otra cosa: evita escribir dos
      veces el **mismo mensaje**, no detecta dos pagos parecidos.
- [ ] Lugares que todavía asumen un solo usuario y **no** se tocaron porque cambiarlos mueve
      la métrica o es negocio sin definir: el prompt del LLM habla de «el arquitecto»
      (`llm.py`), y las señales personales («retiro», «casa») significan el circuito personal
      *del arquitecto*. Si Petrus escribe «Retiro», ¿de quién es? Es la P-20 del contexto.

## 8. Estado de los datos del Sheet

El maestro lo mantiene una persona a mano, así que llega sucio. El motor no lo corrige solo:
resuelve lo que puede y **deja advertencias**, que se ven en `POST /maestros/recargar`. Lo que
avisa hoy:

- **Filas repetidas en CONTRATISTAS** (Maderera Misiones, Marcelo Maragaño, Silla Cuádruple):
  se fusionan tomando los valores no vacíos de la última.
- **Rubros habituales que no existen en RUBROS**: Contador Pasolli («Honorarios / Terceros») y
  Luis Pereyra («Pintura»).
- **Alias que apunta a un nombre inexistente**: `pinturería andina` → «Pinturería Andina»,
  pero la fila se llama «Pint Andina». El contexto §7 dice que la pinturería es otro comercio,
  sin dar su nombre canónico: por eso no se renombró.
- **Filas que no se aplican**: un alias con un `tipo` fuera de `contratista·obra·cuit·tipo`, o
  un contratista con `rubro_habitual_2` sin `rubro_habitual_1`.
- **CUENTAS: una fila llamada «caja_obra» con tipo «Externa».** Parece el concepto cargado en
  la columna equivocada: una caja de obra es una fila por obra («Caja obra Moreno») con tipo
  `caja_obra`. Hoy queda afuera del saldo del estudio porque su tipo es `externa`.
- **USUARIOS: Petrus sin teléfono.** No puede confirmar hasta que se cargue.

Pendientes de dato que **no** son del motor:

- **Los tres cobros de Moreno (M-000007 a M-000009, $5.245.596) están en la cuenta
  `Efectivo`**, que suma al saldo del estudio. Según el contexto §5.8, en una obra
  administrada la plata del comitente no es del estudio: si esos certificados son plata de la
  obra, tendrían que estar en una «Caja obra Moreno», y hoy **inflan el saldo del estudio en
  $5,2 millones**. Si son honorarios, están bien. Hay que decidirlo; el libro es append-only y
  no se corrigió.
- **Petrus figura en TERCEROS como `inactivo`** («106 pagos del histórico lo referencian»).
  Valentín definió el 24/09 que Petrus tiene **las mismas atribuciones que el arquitecto**;
  cuando eso esté escrito en el contexto (§5.13, P-19 a P-22), corresponde reactivarlo. En el
  código no hace falta nada: el `rol` se lee pero no restringe.
- **M-000001 y M-000002 tienen `cargado_por = bot`**, de antes de que existiera USUARIOS.

**Alineado al contexto el 24/09** (regla: si el maestro contradice al contexto, se corrige el
maestro; nada se borra):

- Mercado Libre → `inactivo` y deja de ser DUAL (§5.6: pasarela, no proveedor).
- Silla Cuádruple, sus dos filas → `inactivo`, más el alias `silla cuádruple` → obra Cerro
  Bayo (§7: no es proveedor, es parte de la obra).
- «Ferr. Andina» → «Ferretería Andina» (§7). Desapareció el aviso del alias `andina`.
- Municipalidad: la nota decía «A DEFINIR»; el contexto §7 lo define.

**RUBROS cambió el 24/09 por fuera del motor**: las categorías combinadas de Materiales se
partieron («Áridos y hormigón» → «Áridos» y «Hormigón», etc.) y hay 20 rubros nuevos
(Durlock, Steel, Herrería, Riego…). No contradice el contexto, ningún contratista quedó
apuntando a un rubro borrado y la métrica no se movió. Detalles menores de carga: «pisos» en
minúscula y «Artefactos Sanitarios.» con punto final.
