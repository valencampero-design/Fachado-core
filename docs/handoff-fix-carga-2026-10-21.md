# Handoff — que Gabriel y Petrus carguen sin trabas (Austral, lo personal, obra nueva)

> 21/10/2026 · A&C. Mismo archivo en `fachado-core/docs/` y en
> `chatbot-contable/docs/clientes/fachado/`. Leé primero **`CONTEXTO-FACHADO.md` v1.12**
> (viene con este handoff). Cambiaron:
> - §5.6: transferencias a MERCADOLIBRE S.R.L. y **obra nueva**;
> - §5.7: comprobante de Mercado Pago pagado con débito → Banco;
> - §5.12: un comprobante no se suma a una ficha que ya tiene uno; **las opciones dependen
>   del destino**;
> - §5.20: impuestos de otros organismos, desempate por fecha, tarjetas pendientes.
>
> **Capturas:** `chatbot-contable/docs/clientes/fachado/capturas/2026-10-21/` (10 imágenes).
> Los pares impares son el mensaje con el comentario de Gabriel o Petrus; los pares, la
> captura sola. Miralas antes de empezar.
>
> **Prioridad: la carga diaria.** Gabriel y Petrus se están trabando con todo lo que no es
> una obra. Las partes 1 a 3 de cada lado van primero; la conciliación (M5) después.
> Producción corre lo del 15/10. Los commits de la semana 8 siguen sin pushear y **se
> despliegan juntos con estos**: trabajá encima de ellos.

## Reglas de siempre

- Commit por parte, **sin pushear**. Ningún test ni script escribe en los Sheets reales;
  migraciones con simulacro por defecto.
- **No te frenes a preguntar**: Valen no está mirando. Una duda se resuelve con la opción
  más conservadora y se anota en «## Para Valen» al final de este archivo.
- `CONCILIACION_DESDE` no se toca. Gateway: los otros clientes (HENSEL incluido) no cambian;
  la suite completa antes y después.
- **Cada falla de abajo termina en un test de conversación que la reproduce** con el texto
  real de la captura.

---

## Lo que pasó (20/10, producción)

| # | Capturas | Quién y qué mandó | Qué hizo el bot | Qué tiene que hacer |
|---|---|---|---|---|
| 1 | 03-04 | Petrus: ticket de YPF $ 77.000, sin texto | «¿Qué rubro?» con Carpintero, EPEN, Albañilería… | Leer YPF → rubro **Combustible**. Preguntar solo el destino, **con Austral primero** |
| 2 | 05-06 | Gabriel: comprobante MP a Mathias Flores + «Austral/Mathias» | «¿Qué rubro?» con rubros de obra. «En Austral no me despliega los ítems de gastos generales» | Rubros **de estructura** (Gastos generales, Movilidad, Servicios…) |
| 3 | 07-09 | Gabriel: MP $ 50.000 a Natalia Livio + «Retiro/Abucoque» | Pregunta bien el rubro personal; contesta «4» y le pide «¿A qué obra?» con Lennon, Moreno… | El destino es **Abucoque** (inmueble personal): rubro personal y listo, **nunca** «¿A qué obra?» |
| 4 | 10 | Gabriel: comprobante de $ 1.000.000 de una obra nueva, **Minas** | Lo mezcló con Abucoque: «Retomo: Abucoque $ 1.000.000» y otra vez «¿A qué obra?» | Ficha propia. «No conozco «Minas». ¿Es una obra nueva o un contratista nuevo?» → alta de la obra |
| 5 | 01-02 | Petrus: 3 extractos | Tres resúmenes. «libro $ 7.166.358,10 … diferencia $ 10.218.307,01» | El libro está en **−$ 7,1 M**: mostrar el signo. (Lo de un resumen por archivo ya lo arregla G2 de la semana 8) |

Causas leídas en el código (confirmalas):

- **Motor, `interpretar.py` ~l. 1141:** `afecta = "personal" if … else "obra"`. **Nunca
  vale `"estructura"`**, así que en Austral se ofrecen rubros de obra. Además, en
  RUBROS no existen «Gastos generales» ni «Combustible» de estructura.
- **Motor, ~l. 1116 y 543:** las opciones de «¿A qué obra?» son solo obras de terceros y
  propias, cortadas en `MAX_OPCIONES = 10`. Así quedan afuera **Austral, los inmuebles
  personales y Tres Cerros** (es la undécima).
- **Las fallas 3 y 4** hay que reconstruirlas desde los logs de Railway del gateway y del
  motor (20/10, 18:40 a 19:15, teléfono de Gabriel). Dejá al final la secuencia real de
  mensajes y llamadas, y qué lado falló.

---

## 1 · Motor (`fachado-core`)

### M1 · Rubros según el destino (fallas 1 y 2) — lo primero

1. El tipo de rubro sale **del destino**:
   - obra de tipo `estructura` (Austral) o contratista de estructura (Sofía Cervera, A&C)
     → `"estructura"`;
   - personal → `"personal"`;
   - obra → `"obra"`.
   Revisá **todos** los lugares que arman opciones de rubro o validan un rubro contra el
   destino, no solo el de la l. 1141.
2. Migración en simulacro (`2026_10_21_rubros_estructura.py`): agrega
   `Estructura del estudio › Gastos generales` y `Estructura del estudio › Combustible`
   (afecta `estructura`). Alias: `combustible`, `nafta`, `gasoil` → Combustible;
   `gastos generales`, `generales` → Gastos generales.
3. **Ticket de estación de servicio** (YPF, Shell, Axion, Puma, Gulf en la razón social del
   comprobante, o «combustible» / «nafta» en el texto) → rubro Combustible, sin preguntar.
   Sin destino, la única pregunta es «¿A qué obra?», **con Austral primero** (es lo más
   probable para combustible).
4. Si el contratista tiene un rubro habitual de otro tipo que el destino (Mathias en
   Austral), ese rubro no se propone. Las opciones son las del destino, ordenadas por uso.
5. Tests: las capturas 03-04 y 05-06 con el texto real; «Austral/combustible 77000»;
   «Sofia/Austral».

### M2 · «¿A qué obra?» completa (falla 3)

1. Opciones:
   - **todas las obras activas + Austral**, ordenadas por uso reciente;
   - en un gasto personal, **los inmuebles personales**;
   - Jardín Maternal no, porque está cerrada.
   Para esta pregunta sube `MAX_OPCIONES` a 15: el gateway muestra una lista numerada
   (contrato en §3).
2. **Un destino ya dicho no se vuelve a preguntar.** «Retiro/Abucoque»: Abucoque es la obra
   (tipo `personal`) y la clasificación es personal. Después de contestar el rubro, la ficha
   que vuelve con `contexto_previo` + `respuestas` **conserva** la obra. Reproducí la
   secuencia de las capturas 07-09 completa, con la respuesta «4».
3. Invariante nuevo en el test del corpus: **ninguna ficha con obra ya resuelta trae una
   pregunta `obra`**.

### M3 · Obra nueva (§5.6 v1.12, falla 4)

1. Un token que no resuelve a nada del maestro (ni obra, ni contratista, ni alias, ni
   CUIT), **en un mensaje sin obra**, da una pregunta:
   - `campo = "nuevo"`, texto «No conozco «Minas». ¿Es una obra nueva o un contratista
     nuevo?»;
   - opciones `["__obra_nueva__", "__nuevo__"]`.
   Si hay obra en el mensaje, el token sigue siendo contratista nuevo, como hoy.
2. Si contesta **obra nueva**:
   - la ficha lleva `extras.obra_nueva = {nombre, tipo: "obra_terceros", estado:
     "activa", notas: "Alta por el bot el dd/mm: tipo, servicio y comitente a completar por
     A&C"}`;
   - una advertencia «Minas es nueva: la doy de alta como obra»;
   - el resto de las preguntas normales: contratista, rubro de obra.
   Si contesta **contratista nuevo**, el circuito de hoy.
3. `/confirmar` escribe el movimiento y da de alta la obra en OBRAS (alias = lo escrito, en
   minúscula). `ConfirmarOut.obra_creada = "Minas"`. Si falla el alta, advertencia, no
   error. Un segundo mensaje con «Minas» ya la encuentra (recargar maestros en memoria).
4. Tests: «Minas/Juan Pérez» + comprobante → pregunta; obra nueva → alta y CC al recalcular
   vistas; «Lennon/Minas» → contratista nuevo, sin pregunta.

### M4 · Comprobante de Mercado Pago pagado con tarjeta (§5.7 v1.12)

El lector suma el campo `pagado_con`:
- `"dinero en cuenta"` → cuenta Mercado Pago (como hoy);
- `"débito"` → cuenta **Banco**, medio «Tarjeta de débito», origen `comprobante`;
- `"crédito"` → Mercado Pago como hoy, con la advertencia «pagado con tarjeta de crédito»
  (P-34, pendiente).

Lo que ya está cargado (Epen) no se toca: es de octubre y no se concilia.

### M5 · Conciliación: los ajustes del ensayo de octubre

1. **`TRANSFERENCIA … MERCADOLIBRE S.R.L.`** (CUIT 30-70308853-4) sale del lote
   `meli_personal`:
   - se concilia contra el libro (el CUIT o el nombre del destinatario del comprobante de
     MP);
   - si no, contra el reporte de Mercado Pago (traspaso);
   - si no, pregunta suelta.
   Al lote van solo las compras (`PAGO CON TRANSFERENCIA … MERCADOLIBRE`, compras de
   Mercado Libre).
2. **DPR Sellos, rentas e ingresos brutos** salen de `gastos_bancarios`: pregunta suelta con
   rubro `Impuestos y tasas`. Revisá que «sellos», «DPR» y «rentas» no estén en las
   palabras de gastos bancarios.
3. **Desempate por fecha**: dos candidatos del mismo importe y uno solo con la misma fecha →
   `CONCILIADO` con ese. Tests con los dos pagos de $ 200.000 del 14 y el 16/10.
4. **Signo**: el `texto` del resumen muestra los negativos con signo (`−$ 7.166.358,10`).
   Revisá `_dinero` y `pesos()`: si alguno usa el valor absoluto, que no lo haga.
5. **Pagos de tarjeta de crédito**: siguen como preguntas sueltas (P-34). No los toques.
6. Corré de nuevo el ensayo de octubre en memoria (como el 21/10) y dejá al final el antes y
   el después: conciliadas, lotes y preguntas sueltas.

### M6 · Cierre

- La métrica de siempre, antes y después.
- `docs/handoff-fachado-core.md` al día.
- Al final de este archivo:
  - qué quedó;
  - la reconstrucción de las fallas 3 y 4;
  - los supuestos;
  - el orden de deploy y de migraciones, **sumado al de la semana 8 en una sola lista**.

---

## 2 · Gateway (`chatbot-contable`)

### G1 · Un comprobante nunca se mezcla con otra ficha (§5.12 v1.12, falla 4) — lo primero

1. Un comprobante que llega dentro de los 90 s se suma a la ficha en curso **solo si esa
   ficha no tiene comprobante y no está esperando una respuesta**. Si no, abre su propio
   grupo y la ficha anterior queda pendiente, como hoy.
2. **Un comprobante nuevo nunca reemplaza el importe** de una ficha que ya tenía uno («Retomo:
   Abucoque $ 1.000.000» es el síntoma).
3. Reconstruí la secuencia real de las capturas 07-10 desde los logs (20/10, 18:40–19:15) y
   dejala al final. Test con esa secuencia: Abucoque queda con $ 50.000, y Minas es su propia
   ficha.

### G2 · Listas largas y la pregunta «nuevo» (fallas 3 y 4)

1. Una pregunta con **más de 10 opciones** va como **lista numerada en texto, completa**.
   Hoy corta en 10 (`obras.py` ~l. 953). La respuesta por número o por nombre funciona igual.
2. Con 3 o menos opciones, botones. Entre 4 y 10, como hoy.
3. Pregunta `campo = "nuevo"`: botones **«Obra nueva»** (`__obra_nueva__`) y **«Contratista
   nuevo»** (`__nuevo__`), con la respuesta tal cual al motor.
4. Acuse: si `ConfirmarOut.obra_creada`, «Di de alta la obra Minas.» (como con el
   contratista nuevo).
5. Que la respuesta «4» a «¿Qué rubro?» viaje con `contexto_previo` completo (la ficha
   **con su obra**). Si el gateway pierde la obra al reenviar, es de acá; si la pierde el
   motor, de M2. Dejalo dicho al final.

### G3 · Cierre

- Suite completa (HENSEL incluido).
- `docs/handoff-fachado.md` al día.
- Al final de este archivo: qué quedó, la reconstrucción de las fallas, cambios de contrato.

---

## 3 · Contratos (fijos para esta tirada)

```jsonc
// Pregunta «nuevo» (motor → gateway)
{ "campo": "nuevo", "texto": "No conozco «Minas». ¿Es una obra nueva o un contratista nuevo?",
  "opciones": ["__obra_nueva__", "__nuevo__"] }
// Respuesta: { "campo": "nuevo", "valor": "__obra_nueva__" | "__nuevo__" }

// Ficha con obra nueva: extras.obra_nueva = { "nombre": "Minas", "tipo": "obra_terceros", "estado": "activa", "notas": "…" }
// ConfirmarOut suma: "obra_creada": "Minas" | null

// «¿A qué obra?» puede traer hasta 15 opciones; el gateway las muestra todas, numeradas.
// Las opciones de obra pueden incluir "Austral" y los inmuebles personales: son nombres de OBRAS, como las demás.

// Comprobante: el lector suma "pagado_con": "dinero en cuenta" | "débito" | "crédito" | null (solo informativo para el gateway).
```

Todo lo demás, igual que en la semana 8.

---

## Orden de deploy (Valen)

Una sola vez, semana 8 + esto, cuando las dos sesiones terminen. Los pasos exactos los deja
el motor en M6.

## Para Valen

## Al terminar (las dos sesiones)

Debajo de esta línea, cada sesión deja su resultado.
