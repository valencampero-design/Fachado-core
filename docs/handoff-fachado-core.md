# Handoff — `fachado-core`, el motor de imputación de Fachado

> **Estado técnico del repo al 2026-09-25**, después de las cinco tandas del handoff del
> proyecto (`docs/handoff-proyecto-2026-09-25.md`). Qué está hecho, qué falta, cómo se corre y
> qué variables hacen falta.
>
> **Las reglas de negocio NO viven acá: viven en `CONTEXTO-FACHADO.md`** (v1.5), que se edita
> en el proyecto de Claude de A&C y baja a los dos repos. Si este documento y el contexto se
> contradicen, **gana el contexto**. Este handoff dice dónde está implementada cada regla, no
> cuál es.
>
> Repo hermano: `chatbot-contable`, el gateway de WhatsApp, en producción en Railway.
> Su handoff del paso 0: `chatbot-contable/docs/handoff-fachado.md`.

## 0. Dónde quedó (para retomar)

| | |
|---|---|
| ✅ Motor en producción | `https://web-production-6c935.up.railway.app` · `/salud`, `/interpretar` y `/confirmar` desplegados. **Las tandas 1 a 5 están commiteadas y sin pushear**: producción corre la versión anterior |
| ✅ GitHub | `valencampero-design/Fachado-core`, rama `main` |
| ✅ Lee y escribe el Sheet | Con la service account del gateway, compartida como Editor |
| ✅ Lee los comprobantes | Token de Drive en Railway, app OAuth publicada |
| ✅ Métrica del corpus | 92 % contando las preguntas de diseño, igual antes y después de las cinco tandas (§4) |
| ✅ Maestro alineado al contexto v1.5 | Cajas de obra, Petrus con teléfono y activo, Pinturería Andina, cobros de Moreno en su caja (§8) |
| ✅ Hojas nuevas en el Master | `ETAPAS` (vacía: las carga el arquitecto) y `CERTIFICADOS` (vacía) |
| ⏳ Pushear y desplegar | Después de revisar los cinco commits |
| ⏳ «FACHADO — Personal» | El archivo no existe todavía: hasta que se cree y se cargue `FACHADO_PERSONAL_SHEET_ID`, lo personal da 503 en `/confirmar` (§5) |
| ⏳ Cron del cierre semanal | Un servicio aparte en Railway (§5) |
| ⏳ Conectar el gateway | Lo que necesita, en §6 |
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
  interpretar.py   orquesta: resolver → LLM → comprobante → ficha → duplicados
  llm.py           cliente de Anthropic, prompts y esquemas de salida
  comprobante.py   nombre de archivo → texto del PDF → visión; reconoce certificados
  certificados.py  el PDF del certificado, el número como clave, lo cobrado y lo pendiente
  duplicados.py    el mismo hecho cargado dos veces: referencias y búsqueda
  confirmar.py     /confirmar: valida, asigna id_mov bajo lock, enruta al libro, archiva, alias
  cierre.py        la línea semanal de gastos personales en el libro del estudio
  consultas.py     /consultar: pagos a un contratista, gasto por obra, certificaciones
  filtros.py       qué entra en IVA y en la conciliación (informales, cierre semanal)
  libro.py         el puerto al libro (MOVIMIENTOS, ALIAS, CERTIFICADOS): real o en memoria
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
  test_casos.py          los casos del handoff del 25/09, con su resultado esperado
  test_confirmar.py      /confirmar, /cierre-semanal y /consultar contra libros en memoria
```

### Endpoints

| Ruta | Estado |
|---|---|
| `GET /salud` | ok, sin auth |
| `POST /interpretar` | Nunca escribe. Lee los libros solo para buscar duplicados |
| `POST /confirmar` | Escribe una fila en MOVIMIENTOS del estudio, en el libro personal o en CERTIFICADOS; mueve el comprobante; escribe el alias |
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
  "contexto_previo": null               // la ficha anterior, si esto es una corrección
}
```

Salida:

```jsonc
{
  "fichas": [{
    "campos": { /* las columnas de MOVIMIENTOS, o las de un CERTIFICADO; null donde falta */ },
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
- **Dos formas de ficha.** Un movimiento trae las columnas de MOVIMIENTOS (con las nuevas
  `etapa`, `informal` y `ref_comprobante`). Un certificado trae `campos.tipo = "CERTIFICADO"` y
  solo `obra · etapa · numero · fecha · saldo_a_cobrar · fuente · comprobante_url`.
- **`preguntas[].motivo`**: `apodo_ambiguo` y `dual` son preguntas **de diseño**; `conflicto`
  es texto contra comprobante (o cuerpo del PDF contra nombre de archivo); `falta_dato` es que
  no se pudo resolver; `posible_duplicado` es «ya está cargado, ¿es el mismo?», con botones
  «Es el mismo» / «Es otro».
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
  "fila": 11,
  "libro": "estudio",            // estudio | personal | certificados
  "comprobante_url": "https://drive.google.com/...",  // mismo id de archivo, ya en su carpeta
  "obra": { "nombre": "Lennon", "adelantado": 0, "pagado_con_plata_del_estudio": 0,
            "pagado_por_el_comitente": 22110441.70, "saldo": 0, "caja_obra": null },
  "certificado": null,           // en un certificado o en un cobro que nombra uno:
                                 // { obra, etapa, numero, fecha, saldo_a_cobrar, cobrado, pendiente, cobros }
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
- **TRASPASO y PASANTE todavía no se pueden confirmar** (422): el traspaso necesita cuenta de
  origen y de destino; qué cuenta lleva un pasante (§5.17) no está definido. Están en §7.

Lo que completa el motor, sin importar qué venga en la ficha: `id_mov`, `origen`,
`concilia`, `estado_conc`, `importe_ars`, `comitente` (de OBRAS), `cargado_por` (de
USUARIOS, nunca «bot»), `ts` (hora local), `msg_id`, `certificado` e `informal`.

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
| §5.15 · etapas | `resolver._obra_con_sufijo` (`Lennon1`), `resolver.RE_ETAPA` («etapa 1»), el bloque «Etapa» de `_armar`, y la validación en `confirmar.armar_fila` |
| §5.16 · el mismo hecho cargado dos veces | `duplicados.buscar` (referencias fuertes y probables), `interpretar._marcar_duplicados` y `_marcar_certificados_repetidos` |
| §5.17 · depósito = PASANTE informal | `resolver.PALABRAS_TIPO`, `interpretar._armar` (`informal = sí`), `saldos.saldo_obra`, `filtros.para_iva` / `para_conciliacion` |
| §5.1 · libro append-only | `confirmar.py` y `cierre.py`: fila completa y validada en memoria; idempotencia, `id_mov` y escritura bajo el mismo lock |
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
python -m tests.test_casos             # los casos del handoff del 25/09
python -m tests.test_confirmar         # /confirmar, /cierre-semanal y /consultar en memoria
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

El test corre contra `tests/maestros_snapshot.json` para ser reproducible; se regenera a
propósito con `python scripts/snapshot_maestros.py`.

## 5. Configuración y deploy

Railway, al lado del gateway, desde GitHub. `nixpacks.toml` fija Python 3.11 y arranca
`uvicorn app.main:app`.

| Variable | Para qué |
|---|---|
| `MOTOR_API_KEY` | Secreto compartido con el gateway (header `X-API-Key`) |
| `FACHADO_SHEET_ID` | `1yoakmhO1--WXCtWWStNrmczgYkaT1g0H54fTK2QCc9A` |
| `FACHADO_PERSONAL_SHEET_ID` | «FACHADO — Personal» (§5.14). **Vacía hasta que se cree el archivo**: mientras tanto, lo personal da 503 |
| `GOOGLE_CREDENTIALS_JSON` | Service account del gateway, para **leer y escribir los Sheets** |
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` / `_REFRESH_TOKEN` | OAuth de usuario, para **bajar y mover los adjuntos** |
| `DRIVE_CARPETA_COMPROBANTES_ID` | Carpeta raíz «comprobantes». Si queda vacía, el motor la crea la primera vez y devuelve el id en una advertencia |
| `ANTHROPIC_API_KEY` | |
| `LLM_MODELO` · `LLM_EFFORT` | Default `claude-opus-5` y `low` |
| `MAESTROS_TTL_SEGUNDOS` · `LEER_ADJUNTOS` · `UTC_OFFSET_HORAS` | Default 300 · true · -3 |
| `MAESTROS_SNAPSHOT` | Solo para correr offline; en Railway va vacía |

**El libro personal.** Crear el Google Sheet «FACHADO — Personal» con una hoja `MOVIMIENTOS`
con el mismo encabezado que la del Master, compartirlo como Editor con la service account y
cargar su id en `FACHADO_PERSONAL_SHEET_ID`. No lleva maestros: usa los del Master.

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

Lo que el gateway tiene que cambiar para tener dos usuarios (contexto §5.13): hoy un teléfono
es un perfil (`config/tenants/<telefono>.json`). **Varios teléfonos tienen que mapear al mismo
cliente**, y la sesión —la ficha pendiente, la anterior para las correcciones— tiene que
seguir siendo por teléfono, para que la corrección de uno no se aplique a la ficha del otro.

Dos cosas del corpus que el agrupamiento del gateway tiene que contemplar (contexto §8): **el
adjunto a veces llega 8 a 18 segundos antes que el texto** que lo etiqueta, y **el usuario
manda mensajes repetidos** con un segundo de diferencia.

## 7. Lo que falta

**Operativo**

- [ ] Revisar los cinco commits del 25/09, pushear y verificar el deploy.
- [ ] Crear «FACHADO — Personal», compartirlo con la service account y cargar
      `FACHADO_PERSONAL_SHEET_ID` (§5).
- [ ] Crear el servicio cron del cierre semanal (§5).
- [ ] Cargar las etapas en `ETAPAS` (hoy vacía: ninguna obra tiene etapas y el bot no las
      pregunta).
- [ ] **La primera fila real**, con un movimiento verdadero, mirándola en el Sheet.
- [ ] La primera vez que un `/confirmar` mueva un comprobante, el motor crea la carpeta
      «comprobantes» y devuelve su id en una advertencia: cargarlo en
      `DRIVE_CARPETA_COMPROBANTES_ID` en Railway.
- [ ] Correr `python -m tests.test_corpus --sheet --adjuntos`: la métrica con los
      comprobantes reales.
- [ ] Correr en Python 3.11 (local hay 3.14; Railway ya está fijado en 3.11).

**Código, esperando una decisión del contexto**

- [ ] **PASANTE en `/confirmar`**: §5.17 dice que no toca la caja del estudio, pero no qué
      cuenta lleva. Hasta que se defina, 422.
- [ ] **TRASPASO en `/confirmar`**: MOVIMIENTOS tiene una sola columna `cuenta`.
- [ ] **Corregir un movimiento ya confirmado**: decisión de diseño abierta.
- [ ] **Las series de certificados de Moreno** («cert 4» y «cert 4 extras», «cert.pintura»,
      «certificado 18 obra»): el motor las trata como números distintos y no las mezcla, pero
      el contexto no dice si son series ni cómo se numeran.
- [ ] Qué es «Estudio» en `Estudio/Austral`, y a qué certificado corresponden las cuatro
      fotos del 11/9 que dicen solo «ingreso» (abiertas en el handoff del proyecto).
- [ ] El prompt del LLM habla de «el arquitecto» (`llm.py`): con Petrus escribiendo, puede
      necesitar el nombre de quien escribe. No se tocó porque mueve la métrica.

**Código, sin decisión pendiente**

- [ ] El lock del `id_mov` es de proceso: alcanza con un solo worker, que es como está
      desplegado. Si algún día se escala a más de una réplica, hay que moverlo.
- [ ] **El resolver no mira `estado` de CONTRATISTAS**: un contratista inactivo se sigue
      reconociendo (Mercado Libre). Las cuentas inactivas ya no se reconocen.
- [ ] Conciliación contra `BANCO_RAW` (§5.6), con los filtros de `app/filtros.py`.
- [ ] IVA con alcance completo (§5.10), con `filtros.para_iva`. Se planifica aparte.

## 8. Estado de los datos del Sheet

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

Lo que el motor todavía avisa:

- **Filas repetidas en CONTRATISTAS** (Maderera Misiones, Marcelo Maragaño, Silla Cuádruple):
  se fusionan tomando los valores no vacíos de la última.
- **Rubros habituales que no existen en RUBROS**: Contador Pasolli («Honorarios / Terceros») y
  Luis Pereyra («Pintura»).
- **Filas que no se aplican**: un alias con un `tipo` fuera de `contratista·obra·cuit·tipo`, o
  un contratista con `rubro_habitual_2` sin `rubro_habitual_1`.
- **M-000001 y M-000002 tienen `cargado_por = bot`**, de antes de que existiera USUARIOS.
- Los cobros de Moreno ya cargados (M-000007 a M-000009) tienen el certificado solo en la
  descripción («Certificado 4», «4 extras», «pintura»), no en la columna `certificado`: en
  `/consultar` no cancelan ningún certificado.
