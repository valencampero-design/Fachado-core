# Handoff — fixes del arranque (29/09) y lo que salió de la reunión 5

> 30/09/2026 · A&C. Mismo archivo en los dos repos: `fachado-core/docs/` y
> `chatbot-contable/docs/clientes/fachado/`. Antes de tocar código leé **`CONTEXTO-FACHADO.md`
> v1.7** (cambiaron §5.7, §5.8, §5.11, §5.15, §5.17, §6 y §8).
>
> Valen te pasa **capturas del WhatsApp** del arranque: son la evidencia del bug 1.

## Reglas de siempre

- Ningún test escribe en el Sheet real (MOVIMIENTOS es append-only). Commits armados, **sin
  pushear**; Valen despliega.
- Métrica del corpus antes y después (`python -m tests.test_corpus`). Si baja, se avisa.
- Gateway: los otros cuatro clientes no cambian; todo va en `handlers/obras.py`.
- Si aparece una decisión de negocio que no está en el contexto v1.7, no se inventa: se
  anota como pregunta abierta al final de este archivo.
- Ojo git: en `fachado-core/.git/` quedó `index.lock.stale-claude`, un lock vacío que se
  corrió de lugar para que no bloquee. Se puede borrar. Los archivos que figuran
  modificados en los dos repos sin cambios reales son finales de línea (CRLF): no los
  mezcles en los commits.

---

## 1 · 🔴 PRIORIDAD · «No lo pude cargar: Falta «cuenta»»

### Qué pasó

En el arranque del 29/09 con Gabriel, **Lennon funcionó, y las otras obras no**. Dos casos
de las capturas:

| Mensaje | Ficha mostrada | Al tocar «Confirmar» |
|---|---|---|
| Comprobante + `Marcelo/Gonzalo` | $ 30.000 · 29/09 (del comprobante) · Gonzalo · Marcelo Maragaño · Mano de obra · Para: obra | `No lo pude cargar: Falta «cuenta». (Gonzalo $ 30.000)` |
| `Metro Gas/Grigera Galpón 11.750` (sin comprobante) | $ 11.750 · 29/09 (del texto) · Grigera Galpón · Metro Gas · Servicios públicos · Para: obra | `No lo pude cargar: Falta «cuenta». (Grigera Galpón $ 11.750)` |

Ninguna de las dos fichas tenía línea «Cuenta», y aun así se ofreció «Confirmar».

### Causa (leída en el código, confirmala)

1. **Motor, `interpretar.py`:** `faltantes` incluye `cuenta` (y seguramente `medio_pago`),
   pero **ninguna regla genera la pregunta** para esos campos. La ficha vuelve con
   faltantes y sin preguntas. En Lennon no se ve porque la obra pone `Pagado por el
   comitente`.
2. **Motor:** con un comprobante de transferencia, `comprobante.py` pone `medio_pago =
   Transferencia`, pero **nada infiere `cuenta = Banco`** a partir de eso.
3. **Gateway, `obras.py`:** ofrece «Confirmar» aunque la ficha traiga `faltantes`, y no
   muestra los campos vacíos. Después del 422 pasa a `corrigiendo` **sin decirle al
   usuario qué hacer**: para Gabriel queda en un callejón sin salida.

### Arreglo en el motor

**1.1 · De qué cuenta salió (contexto §5.7, v1.7).** En este orden:

1. El texto: «efectivo», la `C` de una caja de obra, una cuenta nombrada (ya existe).
2. El comprobante: transferencia o débito → **`Banco`** (o `Banco USD` si el comprobante
   está en dólares); cheque → la cuenta que el libro ya usa para cheques (`Chequera`; no
   cambies el criterio existente); Mercado Pago → `Mercado Pago`. Origen `comprobante`.
3. La obra: Lennon → `Pagado por el comitente` (ya existe).
4. **Nada de lo anterior → `cuenta = Banco`, `medio_pago = Transferencia`, con origen
   nuevo `"supuesto"`** y una advertencia «Cuenta asumida: Banco». No se pregunta.

No aplica a PASANTE (la cuenta es fija) ni a TRASPASO (sin las dos cuentas, se pregunta).

**1.2 · Invariante: ninguna ficha sale con un obligatorio vacío y sin pregunta.** Un paso
final en `/interpretar`: por cada campo de `faltantes` que no tenga una pregunta y no se
haya podido completar por regla, **se genera la pregunta** (con opciones del maestro cuando
existan). Y que la lista de obligatorios sea **una sola** para `/interpretar` y `/confirmar`
(hoy están en dos lugares: `requeridos` en `interpretar.py` y la validación de
`confirmar.py`). Si difieren, este bug vuelve.

**1.3 · Tests:**

- Los dos casos de la tabla: ficha con `cuenta = Banco` (origen `comprobante` en el
  primero, `supuesto` en el segundo), sin faltantes, y `/confirmar` en memoria sin 422.
- **Sobre todo el corpus y los casos:** ninguna ficha devuelve un faltante sin su pregunta.
  Es el test que tendría que haber atrapado esto.

### Arreglo en el gateway

**1.4 ·** Nunca mostrar «✅ Confirmar» si alguna ficha trae `faltantes` o hay preguntas
pendientes: primero las preguntas. Si llegara una ficha con faltantes y sin preguntas
(no debería pasar después de 1.2), mostrar el campo como «Cuenta: falta» y ofrecer solo
«✏️ Corregir» y «❌ Descartar».

**1.5 ·** Mostrar el origen `"supuesto"` en la ficha: `Cuenta: Banco · transferencia
(supuesto)`. Sumarlo a `_ORIGEN`.

**1.6 · Un 422 no puede ser un callejón.** Al recibir 422 `{campo}`, volver a llamar a
`/interpretar` con `contexto_previo` = la ficha. Si vuelven preguntas, hacerlas. Si no,
decirlo claro: «No lo pude cargar: falta la cuenta. Escribime de qué cuenta salió (por
ejemplo "banco" o "efectivo"), o tocá Descartar», con los botones. La ficha **sigue
pendiente**; no se pierde.

**1.7 · Tests:** ficha con `faltantes` → no se ofrece Confirmar; 422 → se repregunta o se
explica, y la ficha queda en la cola.

### Recuperar lo que falló

Listá, desde los logs del gateway en Railway (29/09 en adelante), **todos los 422** con su
`msg_id`, obra e importe, y dejalos al final de este archivo. Valen le pide a Gabriel que
los reenvíe después del deploy. Como `/confirmar` es idempotente por `msg_id` y esos no se
escribieron, no hay riesgo de duplicar.

---

## 2 · Etapas (contexto §5.15, v1.7)

**2.1 · Datos.** Cargar en `ETAPAS` con una migración idempotente en
`scripts/migraciones/` (simulacro por defecto, como las demás). Sumar la columna `estado`
si no existe:

| obra | etapa | descripcion | estado |
|---|---|---|---|
| Lennon | 1 | Etapa 1 | en curso |
| Lennon | 2 | Etapa 2 | futura |
| Lennon | 3 | Etapa 3 | futura |
| Moreno | 1 | Etapa 1 | en curso |
| Moreno | extras | Extras | en curso |
| Moreno | 2 | Etapa 2 | futura |

El resto de las obras no tiene etapas: no se cargan filas.

**2.2 · Resolver:**

- Sin etapa en el mensaje: **una sola etapa `en curso` → se usa**, con origen `"maestro"` y
  la ficha dice «etapa 1, en curso». **Dos o más en curso → pregunta** con botones (Moreno:
  «¿Etapa 1 o extras?»).
- Etapa con nombre: `Moreno extras`, `Morenoextras`, `Moreno ext` → etapa `extras`. Con caja
  chica: `MorenoC extras` o `Moreno extras C`. Si no es inequívoco, pregunta.
- Una etapa `futura` o `terminada` no se propone nunca. Si el usuario la nombra
  (`Lennon2`), pregunta: «La etapa 2 de Lennon figura como futura, ¿la paso a en curso?».
  Con «sí», `/confirmar` actualiza el estado en el maestro (igual que reactivar un
  contratista).

**2.3 · Certificados (§5.11):** numeración correlativa **dentro de cada etapa**. «cert 4
extras» → etapa `extras`, número 4. «cert 4» en Moreno → como hay dos etapas en curso,
pregunta cuál.

**2.4 · Gateway:** en la ficha, «Obra: Lennon, etapa 1 (en curso)» cuando la etapa vino del
maestro por ser la única en curso.

**2.5 · Tests:** Lennon sin etapa → etapa 1 sin pregunta; Moreno sin etapa → pregunta;
`Lennon2` → pregunta de activación; «cert 4 extras» → etapa extras. Correr la métrica: los
mensajes de Lennon y Moreno del corpus pueden cambiar.

---

## 3 · Dólares: el tipo de cambio (contexto §5.7, v1.7)

- Cada movimiento con `moneda = USD`, y cada traspaso entre `Banco USD` y una cuenta en
  pesos, **lleva una pregunta `tipo_cambio`**: «¿A qué tipo de cambio?». Respuesta
  numérica libre (aceptá «1.450», «1450», «1450,50»). Con eso, `importe_ars = importe × tc`.
- **Destraba el traspaso entre monedas** (hoy 422): dos filas, cada una en su moneda e
  importe, vinculadas como cualquier traspaso, y las dos con el mismo `tipo_cambio`.
- El `tipo_cambio` se guarda en una columna (sumala con `preparar_sheet.py` si no existe).
- Gateway: una pregunta de texto libre, sin botones. Validar que sea un número antes de
  mandarla al motor.
- Tests: egreso en USD, traspaso USD→ARS y respuesta mal escrita.

---

## 4 · Maestro

- **Gessel**: inmueble personal, igual que Sur, Abucoque y Belelli (misma forma de alta,
  mismo circuito personal). Alias `gessel`.
- Alias `belleli` → Belelli (lo escribió así en la reunión).
- Migración idempotente, simulacro por defecto.

---

## 5 · Opcional, si queda tiempo · caja de obra en negativo (§5.8, supuesto)

Si un pago con la `C` deja la caja de la obra en negativo, la ficha lo avisa y pregunta:
«La caja de Lennon queda en −$ X. ¿La diferencia la pusiste de Austral o tuya?».

- **Austral** → además del pago, un TRASPASO de `Efectivo` (plata del estudio) a la caja
  por la diferencia.
- **Tuya** → un INGRESO a la caja por la diferencia, marcado como aporte personal de Gabriel.

Es un supuesto (registro P-28): implementalo detrás de un flag apagado por defecto y
dejalo anotado. Si no llegás, no pasa nada.

---

## Orden de deploy (Valen)

1. Motor (1.1–1.3, 2, 3, 4) → `/salud` → una llamada real a `/interpretar` con
   `Metro Gas/Grigera Galpón 11.750`: tiene que volver con `cuenta = Banco (supuesto)` y sin
   faltantes.
2. Gateway (1.4–1.7, 2.4, 3) → en ensayo (`FACHADO_MOTOR_ENSAYO=1`), Gabriel o Valen
   mandan un mensaje de una obra que no sea Lennon y uno de Moreno sin etapa. Se miran
   las fichas.
3. `ENSAYO=0` y reenviar los que fallaron el 29/09.

## Al terminar

- Actualizá `docs/handoff-fachado-core.md` y `docs/handoff-fachado.md` (lo hecho, los
  contratos nuevos: origen `supuesto`, pregunta `tipo_cambio`, estado de etapas).
- Dejá al final de este archivo la lista de 422 recuperables y la métrica antes/después.
