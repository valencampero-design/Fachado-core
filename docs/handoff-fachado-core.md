# Handoff — `fachado-core`, el motor de imputación de Fachado

> **Estado técnico del repo al 2026-09-18.** Qué está hecho, qué falta, cómo se corre y qué
> variables hacen falta.
>
> **Las reglas de negocio NO viven acá: viven en `CONTEXTO-FACHADO.md`** (v1.1), que se edita
> en el proyecto de Claude de A&C y baja a los dos repos. Si este documento y el contexto se
> contradicen, **gana el contexto**. Este handoff dice dónde está implementada cada regla, no
> cuál es.
>
> Repo hermano: `chatbot-contable`, el gateway de WhatsApp, en producción en Railway.
> Su handoff del paso 0: `chatbot-contable/docs/handoff-fachado.md`.

## 0. Dónde quedó (para retomar)

| | |
|---|---|
| ✅ Motor de fase 1 en producción | `https://web-production-6c935.up.railway.app` · `/salud` y `/interpretar` verificados |
| ✅ GitHub | `valencampero-design/fachado-core`, rama `main` |
| ✅ Lee el Sheet en vivo | Con la service account del gateway, compartida como Editor |
| ✅ Métrica del corpus | Obra 84 %, contratista 84 %, **92 % contando las preguntas de diseño**, 6/6 casos obligatorios (§4) |
| ✅ Reglas de la reunión 3 | Aplicadas al Sheet y al código (§3), con `tests/test_reglas.py` que las verifica |
| ⏳ Token OAuth de Drive | Falta. Sin él no se leen los comprobantes: el motor interpreta el texto igual y deja `error: adjunto_no_leido` en el diagnóstico |
| ⏳ Publicar la app OAuth | Diferido a pedido del cliente. Mientras siga en «Prueba», el token de Drive caduca cada ~7 días |
| ⏳ `/confirmar`, `/consultar`, conciliación | No empezados (§7) |

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
  maestros.py      carga y cachea OBRAS, CONTRATISTAS, RUBROS, CUENTAS, ALIAS
  resolver.py      texto libre → obra / contratista / rubro / cuenta, SIN LLM
  clasificador.py  la cascada obra / estructura / personal, SIN LLM
  interpretar.py   orquesta: resolver → LLM para lo que falta → comprobante → ficha
  llm.py           cliente de Anthropic, prompts y esquemas de salida
  comprobante.py   nombre de archivo → texto del PDF → visión
  sheets.py        clientes de Google Sheets (service account) y Drive (OAuth)
scripts/
  get_google_token.py    genera el refresh token de Drive, se corre una vez
  snapshot_maestros.py   baja los maestros a tests/maestros_snapshot.json
tests/
  corpus.csv             las 101 filas de la hoja CAPTURA
  maestros_snapshot.json copia de los maestros, para correr reproducible y offline
  test_corpus.py         la métrica: cuánto resuelve sin preguntar
  test_reglas.py         que lo que resuelve sea lo que el negocio decidió
```

### Endpoints

| Ruta | Estado |
|---|---|
| `GET /salud` | ok, sin auth |
| `POST /interpretar` | **implementado.** Nunca escribe nada |
| `POST /maestros/recargar` | implementado: relee el Sheet y devuelve las advertencias |
| `POST /confirmar` · `POST /consultar` | 501, fase 2 |

Todos menos `/salud` piden `X-API-Key` contra `MOTOR_API_KEY`. No hay usuarios: el único
cliente es el gateway.

### Contrato de `/interpretar`

Entrada:

```jsonc
{
  "telefono": "5492944341132",
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
  número de operación, CUIT, razón social, advertencias y `alias_propuesto`. **`/confirmar`
  tiene que persistir el certificado** (contexto §5.11).

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
| §5.8 · las cajas de obra no suman al saldo | `maestros.TIPOS_CUENTA_FUERA_DEL_ESTUDIO` y `Maestros.cuentas_del_estudio()`. **Cualquier cálculo de saldo del estudio tiene que salir de ahí** |
| §5.11 · el certificado viaja con el cobro | `extras["certificado"]` y la descripción |
| Lectura de comprobantes | `comprobante.leer`: nombre de archivo → texto del PDF → modelo |

`tests/test_reglas.py` verifica las de esta tabla que se pueden probar sin escribir nada.

## 4. La métrica

```bash
python -m tests.test_corpus            # diccionario + LLM (necesita ANTHROPIC_API_KEY)
python -m tests.test_corpus --sin-llm  # solo diccionario
python -m tests.test_corpus --sheet    # contra el Sheet en vivo, no el snapshot
python -m tests.test_corpus --adjuntos # además baja y lee los comprobantes (requiere OAuth)
python -m tests.test_reglas            # las reglas de negocio, sin métrica
```

Las 101 filas de CAPTURA se reagrupan en 57 mensajes (50 con texto, 5 correcciones, 2
adjuntos sin texto). Contra el Sheet en vivo:

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
| `GOOGLE_CREDENTIALS_JSON` | Service account del gateway, para **leer el Sheet** |
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` / `_REFRESH_TOKEN` | OAuth de usuario, solo para **bajar los adjuntos** |
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

- **Sheets → service account** (la del gateway, con el Sheet compartido como Editor). Leerlo
  con OAuth de usuario exige el scope `spreadsheets.readonly`, que Google considera
  **sensible**: con un scope sensible, publicar la app OAuth requiere verificación, y en
  «Prueba» el token caduca cada 7 días. La service account no tiene consentimiento ni
  vencimiento. Si no hay service account configurada, el motor cae a OAuth y lo avisa por log.
- **Drive → OAuth de usuario.** Una service account no tiene cuota en un Drive personal, y
  `drive.file` solo alcanza a los archivos que subió **esa misma app OAuth**, que son los
  adjuntos del gateway. Por eso tiene que ser el mismo cliente OAuth, con otro refresh token:

```bash
pip install google-auth-oauthlib
python scripts/get_google_token.py <client_secret.json>   # autorizar con valencampero@gmail.com
```

## 6. Cómo se conecta el gateway (nada de esto está hecho)

1. El gateway sigue archivando en CAPTURA: es la red de seguridad, no se toca.
2. Además llama a `POST /interpretar` con el texto, los adjuntos ya subidos a Drive y, si el
   mensaje parece una corrección, la ficha anterior en `contexto_previo`.
3. Muestra la ficha con el origen de cada campo y los botones de `preguntas`.
4. Con la respuesta llama a `POST /confirmar` (a implementar).
5. El perfil del tenant pasa de `mode: "captura"` a un modo propio del proyecto `obras`.

Dos cosas del corpus que el agrupamiento del gateway tiene que contemplar (también anotadas en
el contexto §8): **el adjunto a veces llega 8 a 18 segundos antes que el texto** que lo
etiqueta, y **el usuario manda mensajes repetidos** con un segundo de diferencia.

## 7. Lo que falta

**Operativo**

- [ ] Generar el refresh token de Drive y cargarlo acá y en Railway; después correr
      `python -m tests.test_corpus --sheet --adjuntos`, que es la única parte del motor que
      todavía no se ejecutó contra datos reales.
- [ ] Publicar la app OAuth (diferido).
- [ ] Cargar en `CUENTAS` una fila por obra administrada con `tipo = caja_obra` (contexto
      §5.8). El motor ya las entiende y las excluye del saldo del estudio.
- [ ] Correr en Python 3.11 (local hay 3.14; Railway ya está fijado en 3.11).

**Código**

- [ ] `POST /confirmar` — escribir en MOVIMIENTOS, mover el adjunto, aprender el alias
      confirmado y **persistir el certificado**. Hay que subir el scope de la service account
      a `spreadsheets` (hoy `spreadsheets.readonly`).
- [ ] `POST /consultar` — saldos y cuentas corrientes por obra. El saldo del estudio tiene que
      salir de `Maestros.cuentas_del_estudio()`.
- [ ] Conciliación contra `BANCO_RAW`, que incluye **la regla de cruce de Mercado Libre**
      (contexto §5.6): cruzar por fecha e importe los comprobantes recibidos contra las líneas
      del extracto, y lo que no cruza queda como personal sin clasificar.
- [ ] **IVA con alcance completo** (contexto §5.10): distinguir factura emitida de comprobante
      de gasto, extraer neto / IVA / tipo / número / CUIT, y usar las emitidas como fuente de
      los ingresos por honorarios. Alcance nuevo, se planifica aparte.
- [ ] Detección de pagos duplicados, para cuando exista `/confirmar`. **Ojo con el falso
      positivo conocido**: el cheque 510 y la transferencia del 27/08 a Eco Aislación, los dos
      por $4.032.391,70, **son dos pagos distintos** (reunión 3). Hoy el motor no tiene
      ninguna heurística de duplicados, así que no los marca.

## 8. Estado de los datos del Sheet

El maestro lo mantiene una persona a mano, así que llega sucio. El motor no lo corrige solo:
resuelve lo que puede y **deja advertencias**, que se ven en `POST /maestros/recargar`. Lo que
avisa hoy:

- **Filas repetidas en CONTRATISTAS** (Maderera Misiones, Marcelo Maragaño, Silla Cuádruple):
  se fusionan tomando los valores no vacíos de la última.
- **Rubros habituales que no existen en RUBROS**: Contador Pasolli («Honorarios / Terceros») y
  Luis Pereyra («Pintura»).
- **Alias que apuntan a nombres inexistentes**: `andina` → «Ferretería Andina» (la fila se
  llama «Ferr. Andina») y `pinturería andina` → «Pinturería Andina» (es «Pint Andina»).
  Renombrar las dos filas al nombre canónico del contexto §7 haría desaparecer el aviso.
- **Filas que no se aplican**: un alias con un `tipo` fuera de `contratista·obra·cuit·tipo`, o
  un contratista con `rubro_habitual_2` sin `rubro_habitual_1`.

Pendientes de dato que **no** son del motor:

- **Mercado Libre sigue cargado en CONTRATISTAS** y marcado DUAL, pero el contexto §5.6 dice
  que es una pasarela, no un proveedor. Correspondería pasarlo a `inactivo` (nada se borra) y
  dejarlo solo como `medio_pago`. **Falta confirmarlo.**
- **Silla Cuádruple** figura como contratista con rubro `Personal / Club y deporte` («las
  cuotas de esquí»), pero el contexto §7 dice que **no es un proveedor: es parte de la obra
  Cerro Bayo**. Las dos cosas no pueden ser ciertas. **Falta resolverlo.**
