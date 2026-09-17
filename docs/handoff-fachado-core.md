# Handoff — `fachado-core`, el motor de imputación de Fachado

> Estado al 2026-09-17. Fase 1 (esqueleto + `/interpretar` + test del corpus) terminada y
> corriendo local. Sin deploy todavía, sin remote de git. Fuente de verdad = repo + este doc.
>
> Repo hermano: `chatbot-contable` (el gateway de WhatsApp, ya en producción en Railway).
> Handoff del paso 0 de Fachado: `chatbot-contable/docs/handoff-fachado.md`.

## 1. Qué es esto y por qué está separado del gateway

El gateway atiende **tres clientes sobre un mismo número de WhatsApp** (contabilidad,
Belakay, Fachado) y no se puede tocar todos los días. Este repo es el motor de Fachado:
sabe de obras, contratistas, rubros y conciliación, y **no sabe nada de WhatsApp**.

| | Gateway (`chatbot-contable`) | Motor (`fachado-core`) |
|---|---|---|
| Sabe de | Conversar | Obras |
| Tiene estado | Sí: sesión, botones, flujo de confirmación | **No** |
| Hace | Webhook, seguridad, dedup, descarga de media, transcripción, mandar mensajes y botones | Interpretar, imputar, escribir en Sheets y Drive, conciliar |

Consecuencias de que el motor no tenga estado:

- Se prueba con `curl` y con el corpus de 101 mensajes reales, **sin mandar un WhatsApp**.
  Eso es lo que hace viable iterar el parser todos los días.
- Si el motor está caído, el gateway sigue archivando el mensaje crudo (modo captura) y le
  responde ✅ al usuario. No se pierde un dato por una falla del procesamiento.

## 2. Qué hay implementado

```
app/
  main.py          FastAPI, rutas, auth por X-API-Key
  config.py        settings desde env
  models.py        Pydantic de entrada y salida + las 23 columnas de MOVIMIENTOS
  maestros.py      carga y cachea OBRAS, CONTRATISTAS, RUBROS, CUENTAS, ALIAS
  resolver.py      texto libre → obra / contratista / rubro / cuenta, SIN LLM
  clasificador.py  la cascada obra / estructura / personal, SIN LLM
  interpretar.py   orquesta: resolver → LLM para lo que falta → comprobante → ficha
  llm.py           cliente de Anthropic, prompts y esquemas de salida
  comprobante.py   nombre de archivo → texto del PDF → visión
  sheets.py        cliente de Google Sheets y Drive (OAuth de usuario)
scripts/
  get_google_token.py    genera el refresh token (Sheets + Drive), se corre una vez
  snapshot_maestros.py   baja los maestros a tests/maestros_snapshot.json
tests/
  corpus.csv             las 101 filas de la hoja CAPTURA
  maestros_snapshot.json copia de los maestros, para correr el test offline
  test_corpus.py         corre el corpus y reporta aciertos
```

### Endpoints

| Ruta | Estado |
|---|---|
| `GET /salud` | ok, sin auth |
| `POST /interpretar` | **implementado.** Nunca escribe nada |
| `POST /maestros/recargar` | implementado: fuerza la relectura del Sheet |
| `POST /confirmar` | 501, fase 2 |
| `POST /consultar` | 501, fase 2 |

Todos menos `/salud` piden el header `X-API-Key` contra `MOTOR_API_KEY`. No hay usuarios:
hay un solo cliente, que es el gateway.

### Contrato de `/interpretar`

Entrada:

```jsonc
{
  "telefono": "5492944341132",
  "texto": "Felipe J/Lennon",          // texto del mensaje, o el caption del adjunto
  "adjuntos": [                         // ya descargados y subidos por el gateway
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
    "campos": { /* las 23 columnas de MOVIMIENTOS, null donde falta */ },
    "origen_campo": { "importe": "comprobante", "obra": "texto", "rubro_1": "inferido" },
    "faltantes": ["rubro_2"],
    "conflictos": [],
    "confianza": 0.86,
    "clasificacion": "obra",            // obra | estructura | personal | null
    "regla": "R4: tipo de la obra (obra_terceros)",
    "extras": { "certificado": "4", "fecha_pago": "2026-09-28", "alias_propuesto": {...} }
  }],
  "preguntas": [
    { "campo": "obra", "texto": "¿A qué obra?", "opciones": ["Lennon","Moreno"], "ficha": 0 }
  ],
  "diagnostico": { "uso_llm": false, "llm_llamadas": 0, "resoluciones": [...] }
}
```

Cosas del contrato que importan para el gateway:

- **`origen_campo`**: es lo que permite mostrar «del comprobante» al lado de cada valor en
  la ficha de confirmación. Valores: `texto`, `comprobante`, `maestro`, `inferido`, `llm`,
  `fecha_mensaje`, `contexto_previo`.
- **`fichas` es una lista.** Casi siempre trae un elemento, pero un mensaje puede traer dos
  movimientos (*«Ingreso Moreno/cert. 22 e imputar pago aparte Marcelo/Moreno»*). Cada
  pregunta dice a qué ficha corresponde con `ficha`.
- **`clasificacion` y `regla` no son columnas de MOVIMIENTOS.** Ver la deuda #1 en §8.
- **`extras`** lleva lo que no tiene columna: número de certificado, fecha de pago del
  cheque diferido, número de operación, CUIT, razón social, advertencias y el
  `alias_propuesto` cuando el usuario enseña un alias.
- **`confianza`** arranca en 1 y baja por método difuso, uso de LLM, rubro inferido,
  preguntas y conflictos.

## 3. Cómo resuelve (el orden importa)

**Primero el diccionario, después el LLM.** Es más barato, más rápido y mucho más predecible.

1. **Se parte por `/` y NO se parsea por posición.** `Sofia/Austral` y `Austral/Sofi` son el
   mismo par: cada token se resuelve contra los diccionarios y el que matchea una obra es la
   obra. Antes de partir se sacan las fechas (que también tienen `/`) y los importes.
2. **Exacto**: primero ALIAS (es lo que el usuario enseñó), después `OBRAS.obra`,
   `OBRAS.codigo`, `CONTRATISTAS.contratista`, `CUENTAS`, `RUBROS`. Todo normalizado a
   minúsculas y sin acentos. Si un token matchea obra **y** contratista, se pregunta.
3. **CUIT** (de un comprobante): se busca en `CONTRATISTAS.cuit` y en `ALIAS` con
   `tipo = cuit`. **Un contratista puede tener más de un CUIT** (Miguel Soto cobra también
   con el de Alexis Matamala): el CUIT no es clave única, siempre se resuelve al nombre
   canónico. Para los INGRESO, el CUIT del originante se busca en `OBRAS.cuit_comitente`
   para deducir la obra.
4. **Palabra única** (agregado, no estaba en el brief): si el token es una sola palabra que
   es el nombre de pila de un único contratista, se resuelve sin LLM («Sofia» → Sofia
   Cervera). Si coincide con dos (Miguel Soto / Miguel Matuz), no se resuelve.
5. **Difuso** con rapidfuzz, umbral ≥ 88 («Metrogas» → «Metro Gas»). Empate entre
   categorías → se pregunta.
6. **LLM** solo para lo que quedó sin resolver, y solo si eso puede llenar un campo vacío.
   Se le pasan las listas canónicas en el system prompt (con prompt caching) y **solo puede
   devolver valores que existen en los maestros**: lo que inventa se descarta. También se le
   pide el rubro cuando el contratista está resuelto pero no tiene rubro habitual.

El rubro se infiere de `CONTRATISTAS.rubro_habitual_1/2` cuando el contratista está resuelto.

### La cascada de clasificación (código, no prompt)

Se evalúa en orden, gana la primera que matchea, y la ficha dice cuál fue en `regla`.

| # | Condición | Resultado |
|---|---|---|
| R1 | Un token es `casa`, `particular`, o la obra es de `tipo = personal` (Sur, Abucoque, Belelli) | `personal`, **aunque cobre un contratista de obra**. El destino manda sobre el proveedor |
| R2 | El contratista está marcado DUAL | Pregunta con botones: ¿obra o personal? |
| R3 | El rubro resuelto tiene `afecta = personal` | `personal` |
| R4 | Hay obra identificada | El tipo de la obra (`obra_terceros`/`obra_propia` → obra, `estructura` → estructura) |
| R4 | Contratista con rubro de obra y sin obra | `obra`, obra vacía → pregunta a qué obra |
| R1b | Quedó un `Retiro` suelto y nada más fuerte decidió | `personal`, y se pregunta el rubro |
| R5 | Nada de lo anterior | Pregunta |
| T | Es un TRASPASO | No se clasifica |

Dos cosas que están en el código y conviene no perder:

- **`Retiro` es una señal débil a propósito.** `Electricidad Angostura/Retiro` da *obra* (y
  pregunta cuál), no personal, porque el contratista de obra pesa más. `Retiro/club` sí da
  personal. `Maragaño/Retiro/casa` también, porque `casa` es señal fuerte.
- **Retirar efectivo del cajero es `TRASPASO` de Banco a Efectivo, no un gasto.** No existe
  el rubro «retiro de efectivo».

### Comprobantes

Del más barato al más caro: **nombre de archivo → texto del PDF → modelo**.

- `Cheque9679_SOTO MIGUEL ANGEL_20217263256.pdf` ya da número de cheque, razón social y
  CUIT sin abrir nada.
- Los PDF del homebanking son texto: se extraen con pypdf y se parsean con regex (fecha,
  importe, CUIT, razón social, CBU, número de operación).
- Solo se llama al modelo si es una foto, o si el PDF no dio importe y fecha.
- **Cheques diferidos**: la fecha del hecho económico es la de emisión; la de pago va en
  `extras.fecha_pago`.

**Reparto de autoridad**: el comprobante manda en importe, fecha, destinatario, CUIT y
número de operación; el texto manda en obra, ítem, rubro y descripción. Si se contradicen
en importe o fecha, el motor **no elige**: devuelve los dos valores en `conflictos` y
pregunta.

### Correcciones

El usuario corrige por mensaje posterior, sin comando: *«Corrección! Rodrigo/Moreno»*,
*«08/02/26»*, *«Rodrigo = Rodrigo sanitarista»*. El estado lo tiene el gateway; el motor
recibe la ficha anterior en `contexto_previo` y la mezcla: se hereda lo que dijo el usuario
o el comprobante, y lo derivado (comitente, rubro inferido, clasificación) se **recalcula**
con lo nuevo. Cuando enseña un alias, vuelve en `extras.alias_propuesto` para que el
gateway lo confirme y `/confirmar` lo escriba en ALIAS.

## 4. La métrica

```bash
python -m tests.test_corpus            # diccionario + LLM (necesita ANTHROPIC_API_KEY)
python -m tests.test_corpus --sin-llm  # solo diccionario
python -m tests.test_corpus --sheet    # contra el Sheet real, no el snapshot
python -m tests.test_corpus --url http://localhost:8000   # contra un motor corriendo
```

Las 101 filas de CAPTURA se reagrupan en 57 mensajes (50 con texto, 5 correcciones, 2
adjuntos sin texto). Al 2026-09-17:

| | |
|---|---|
| Obra/destino resuelto sin preguntar | 41/50 (82%) |
| Contratista resuelto sin preguntar | 49/50 (98%) |
| Las dos cosas | 40/50 (80%) |
| Ídem, contando como bien los 4 duales (preguntan a propósito) | 44/50 (88%) |
| Necesitaron LLM | 10 de 55 mensajes; solo 1 cambió el resultado |
| Casos obligatorios del brief | 6/6 |

**Que ese porcentaje suba es el trabajo de las próximas semanas.** El test corre contra
`tests/maestros_snapshot.json` para que sea reproducible: si cambia la métrica, es por
código o porque se regeneró el snapshot a propósito (`scripts/snapshot_maestros.py`).

Lo que queda preguntando hoy: 4 capturas cuyo único texto es «ingreso» (sin obra; se
resolverían leyendo el comprobante), `Valen/Austral` (no existe ningún «Valen» en los
maestros) y `Electricidad Angostura/Retiro` (pregunta la obra, es lo correcto).

## 5. Configuración y deploy

Railway, al lado del gateway. `nixpacks.toml` fija Python 3.11 y arranca
`uvicorn app.main:app`.

| Variable | Para qué |
|---|---|
| `MOTOR_API_KEY` | Secreto compartido con el gateway (header `X-API-Key`) |
| `FACHADO_SHEET_ID` | `1yoakmhO1--WXCtWWStNrmczgYkaT1g0H54fTK2QCc9A` |
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` | Las mismas del gateway |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | **Token nuevo**: ver abajo |
| `ANTHROPIC_API_KEY` | |
| `LLM_MODELO` | Default `claude-opus-5` |
| `LLM_EFFORT` | Default `low` |
| `MAESTROS_TTL_SEGUNDOS` | Default 300 |
| `LEER_ADJUNTOS` | Default true |
| `UTC_OFFSET_HORAS` | Default -3 |
| `MAESTROS_SNAPSHOT` | Solo para correr offline; en Railway va vacía |

**El refresh token del gateway NO sirve.** Ese token tiene scope `drive.file`, que solo da
acceso a los archivos que creó la app: alcanza para bajar los adjuntos, pero no para leer el
Sheet maestro, que lo creó el usuario a mano. El motor necesita
`spreadsheets.readonly` + `drive.file`:

```bash
pip install google-auth-oauthlib
python scripts/get_google_token.py <client_secret.json>   # autorizar con valencampero@gmail.com
```

Mismo cliente OAuth, token distinto. Y sigue en pie el pendiente del gateway: **la app
OAuth está en estado «Prueba», así que el refresh token caduca a los ~7 días.** Publicarla
(scope `drive.file` no requiere verificación) lo vuelve permanente.

## 6. Cómo se conecta el gateway (fase 2, nada de esto está hecho)

1. El gateway sigue archivando en CAPTURA (no se toca ese camino: es la red de seguridad).
2. Además llama a `POST /interpretar` con el texto, los adjuntos ya subidos a Drive y, si el
   mensaje parece una corrección, la ficha anterior en `contexto_previo`.
3. Muestra la ficha con el origen de cada campo y los botones de las `preguntas`.
4. Con la respuesta del usuario llama a `POST /confirmar` (a implementar), que asigna
   `id_mov`, appendea a MOVIMIENTOS, mueve el adjunto a la carpeta de la obra y, si hubo
   `alias_propuesto`, lo escribe en ALIAS.
5. El perfil del tenant pasa de `mode: "captura"` a un modo propio del proyecto `obras`.

Dos detalles del corpus que el gateway tiene que contemplar al agrupar:

- **El adjunto a veces llega antes que el texto** (Edesur, Metrogas, Retiro/visa: el PDF
  llega entre 8 y 18 segundos antes del mensaje que lo etiqueta). Hay que mirar para los dos
  lados, no solo hacia atrás.
- **El usuario manda cosas repetidas** (`AUSTRAL/IVA` y `Austral/iva` con un segundo de
  diferencia). Vale la pena detectar el duplicado antes de escribir dos movimientos.

## 7. Lo que falta

- [ ] `POST /confirmar` — escribir en MOVIMIENTOS, mover el adjunto, aprender el alias.
- [ ] `POST /consultar` — saldos y cuentas corrientes por obra.
- [ ] Conciliación contra `BANCO_RAW`.
- [ ] Deploy en Railway + generar el token OAuth con el scope de Sheets.
- [ ] Probar la lectura de comprobantes reales punta a punta (hoy solo se probó el parser de
      nombres de archivo y de texto de PDF con ejemplos, no con los PDF del cliente).
- [ ] Correr en Python 3.11 (local hay 3.14; Railway queda fijado en 3.11).

## 8. Deudas y hallazgos del Sheet

1. **MOVIMIENTOS no tiene columna para obra / estructura / personal.** Un `Retiro/club` no
   tiene obra, así que hoy esa clasificación no tiene dónde vivir. El motor la devuelve
   aparte en `clasificacion`. **Hay que decidir si se agrega la columna** (y, si se agrega,
   el motor solo tiene que sumarla a `COLUMNAS_MOVIMIENTOS`). Además la hoja real tiene 25
   columnas: `cargado_por` y `ts` se completan al confirmar.
2. **Alias que apuntan a nombres que no existen en CONTRATISTAS**: `marce` → «Marcela»
   (por contexto parece Marcelo Maragaño), `andina` → «Ferretería Andina» (el contratista se
   llama «Ferr. Andina»), `pinturería andina` → «Pinturería Andina» (es «Pint Andina»). El
   motor los resuelve igual pero deja una advertencia.
3. **Filas repetidas en CONTRATISTAS**: Marcelo Maragaño (una con rubro y otra sin),
   Maderera Misiones, Silla Cuadruple/Cuádruple. El motor las fusiona y lo avisa en
   `/maestros/recargar`.
4. **Rubros habituales que no existen en RUBROS**: Contador Pasolli («Honorarios /
   Terceros») y Luis Pereyra («Pintura»).
5. **Edesur tiene rubro habitual «Servicios públicos / Agua»** y es electricidad.
6. **Contradicción pendiente**: las notas de la reunión 3 dicen que Alexis Matamala y Miguel
   Soto son personas distintas; el Sheet (ALIAS, las notas de Miguel Soto y M-000006) dice
   que son el mismo proveedor. **El motor sigue al Sheet.**
7. **Marcado el 2026-09-17**: Sofia Cervera (fila 60) y Juanma (fila 65) quedaron con
   `DUAL:` en `notas`, que es como el motor reconoce un contratista dual (eso, o una columna
   `dual`). Mercado Libre ya estaba.
8. Sigue sin definirse: qué tipo de servicio es Tres Cerros, quién es Lalo, y si
   «Municipalidad» es un contratista o solo un rubro.
