# Handoff — `fachado-core`, tanda 6: lo que el motor necesita para conectar el gateway

> 25/09/2026 · A&C. Antes de tocar código leé **`CONTEXTO-FACHADO.md` v1.6** (§5.6, §5.12,
> §5.13, §5.17, §5.18, §5.19 son nuevos o cambiaron) y `docs/handoff-fachado-core.md`.
> Esta tanda cierra los 422 de §7 y agrega lo que el gateway va a consumir. **En paralelo**,
> otra sesión de Code construye el lado del gateway en `chatbot-contable` contra los
> contratos de abajo: **no los cambies sin anotarlo en este archivo.**

## Reglas de siempre

- Ningún test escribe en el Sheet real ni en el libro personal. Mocks o una copia.
- Commits armados, **sin pushear**. Valen despliega.
- Medí la métrica (`python -m tests.test_corpus`) **antes y después** de 6.7. Si baja, no se
  mergea sin avisar.
- Al terminar, actualizá `docs/handoff-fachado-core.md` (§2 contratos, §7 pendientes) y
  corregí la inconsistencia vieja de §5 (dice que la variable del libro personal está vacía).

---

## 6.1 · PASANTE en `/confirmar` (§5.17)

- Una sola fila, `tipo = PASANTE`, **`cuenta = Pagado por el comitente`** (forzada por el
  motor, venga lo que venga en la ficha), `informal = VERDADERO`, `concilia = FALSO`.
- Obligatorios: obra, contratista, importe, fecha. Si falta uno → 422 como siempre.
- Suma a la cuenta corriente del contratista en la obra como un pago del comitente (§5.9).
  **No toca el saldo del estudio.** Verificá que `Pagado por el comitente` esté en `CUENTAS`
  con un tipo que no sume al saldo (si hoy no existe ese tipo, `externa`).
- Test: un pasante no mueve el saldo del estudio ni aparece en lo que concilia.

## 6.2 · TRASPASO (§5.18)

- `/interpretar` devuelve una ficha `tipo = TRASPASO` con `cuenta_origen`, `cuenta_destino`,
  importe y fecha. Frases típicas: «saqué efectivo», «extracción», «repuse la caja de
  LennonC», «pasé a la caja». Una `C` pegada a la obra es su caja (§5.8).
- `/confirmar` escribe **dos filas en un solo append**: salida de origen y entrada en
  destino, mismo importe, vinculadas entre sí (columna nueva `vinculo` con el `id_mov` de la
  otra, o la solución que te resulte más limpia; anotala). `msg_id`: `<wamid>#<i>` y
  `<wamid>#<i>b`. La idempotencia tiene que reconocer el par completo.
- Salida: `id_mov` de la primera y **`id_mov_vinculado`** de la segunda.
- 422 si falta una cuenta, si son la misma, o si alguna no existe o está inactiva.

## 6.3 · Contraasiento: `GET /movimientos/{id_mov}` y `POST /anular` (§5.19)

```jsonc
// GET /movimientos/M-000012?telefono=549...
→ { "id_mov", "libro", "campos": {...}, "anulado_por": null, "vinculado": null }
// 404 si no existe; 403 si es P- y el teléfono no tiene ve_personal.

// POST /anular
{ "telefono": "549...", "id_mov": "M-000012", "msg_id": "wamid...", "motivo": "otra obra" }
→ { "id_mov_anulacion": "M-000031", "anula": "M-000012", "libro": "estudio",
    "ficha_original": { "campos": {...}, "extras": {...} }, "ya_existia": false }
```

- La fila de anulación va **al mismo libro** que la original: mismos campos, **importe con
  signo contrario**, columna nueva **`anula = <id_mov>`**, `cargado_por` = quien anula,
  `origen = ANULACION`. La original no se toca.
- Anular una fila de un traspaso anula **las dos**.
- 409 si ya estaba anulada (devolvé la anulación existente). Idempotente por `msg_id`.
- `ficha_original` es para que el gateway la mande como `contexto_previo` de la corrección.
- **Verificá que todo lo derivado dé bien con un par anulado**: saldo del estudio, cuentas
  corrientes, `/consultar` («cuántos pagos a X» no cuenta ni la original ni la anulación),
  `/cierre-semanal` (la anulación de un personal genera ajuste) y las cajas de obra.

## 6.4 · `/interpretar`: tres campos nuevos de entrada y uno de salida

**Salida — `intencion`**: `"movimiento" | "consulta" | "otro"`.

- `consulta`: preguntas del estilo de `/consultar` («¿cuánto le pagué a…?»). El gateway,
  al verla, llama a `/consultar` con el mismo texto.
- `otro`: charla, «después te paso el ticket», una foto de obra, un audio sin importe. Con
  `otro`, `fichas` y `preguntas` van vacías y el gateway responde el acuse corto (§5.12).
- Ante la duda entre `movimiento` y `otro`, **`movimiento`** con preguntas: es peor perder un
  pago que hacer una pregunta de más.

**Entrada — `respuestas`**: la respuesta a una pregunta, aplicada de forma determinística.

```jsonc
"contexto_previo": { ...la ficha... },
"respuestas": [ { "ficha": 0, "campo": "obra", "valor": "Lennon" } ]
```

El motor pone el valor, **vuelve a correr la cascada** (cambiar la obra puede cambiar
`tipo_gasto`) y devuelve la ficha actualizada con las preguntas que sigan faltando. El
`valor` es siempre uno de los `opciones` que el motor ofreció, o texto libre si el usuario
escribió otra cosa (en ese caso, resolvelo con el diccionario como cualquier texto).

**Entrada — `texto_compartido`** (entero, default 1). Cuando el usuario manda N comprobantes
y un texto, el gateway llama a `/interpretar` **una vez por comprobante** con el mismo texto
y `texto_compartido = N`. Con N > 1, **el importe y la fecha salen del comprobante**: un
importe del texto no genera `conflicto` (probablemente es el total o de otro comprobante);
obra, contratista y rubro sí salen del texto.

**Comprobante sin texto** (`texto = ""`, un adjunto): tiene que funcionar. Importe, fecha y
CUIT del comprobante; el resto a `preguntas`. Agregá un test.

## 6.5 · Contratistas inactivos (§5.6)

El resolver deja de proponer contratistas con `estado = inactivo` por difuso, palabra única
o LLM. Solo coinciden por nombre exacto, alias exacto o CUIT, y en ese caso la ficha trae
una pregunta `motivo = "inactivo"` («Mercado Libre está inactivo, ¿lo reactivo?», opciones
«Reactivar» / «Es otro»). Reactivar lo hace `/confirmar` si la ficha trae
`extras.reactivar = true` (escribe `activo` en el maestro, igual que el alias). Un flag del
resolver habilita reconocerlos en la migración de históricos.

## 6.6 · Qué devuelve `/confirmar` para el acuse

Nada nuevo salvo `id_mov_vinculado` (6.2). Confirmá que la salida trae siempre `id_mov`:
el gateway lo muestra en el acuse para que el usuario pueda escribir «corregir M-000012».

## 6.7 · El nombre de quien escribe en el prompt del LLM (§5.13)

`llm.py` deja de decir «el arquitecto» y usa el `nombre` de `USUARIOS` del teléfono que
escribe. Si Petrus escribe «pagué», pagó el estudio; «Retiro» sigue siendo personal del
arquitecto. Medí la métrica antes y después.

## 6.8 · Deploy

Orden: tests → commits → Valen despliega → `/salud` → una llamada real a `/interpretar`
(nunca escribe) con un texto del corpus y un comprobante solo. No hacer `/confirmar` ni
`/anular` de prueba contra el Sheet real.

## Al terminar, dejá anotado en `docs/handoff-fachado-core.md`

- Los contratos nuevos (`intencion`, `respuestas`, `texto_compartido`, `/anular`,
  `/movimientos/{id}`, `id_mov_vinculado`), con cualquier diferencia respecto de este doc.
- Las columnas nuevas del Sheet (`anula`, `vinculo` o la que hayas elegido) y en qué libros.
- La métrica antes y después de 6.7.
