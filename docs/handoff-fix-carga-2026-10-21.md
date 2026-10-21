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

**Semana 8 (20/10) y fix de la carga (21/10) juntos, en este orden.** Cada script corre
primero sin `--aplicar` (simulacro) y después con `--aplicar`. Todos son idempotentes.

1. **Push de `fachado-core`**: 16 commits, de `64313c8` al cierre de M6. Railway despliega
   `web`; después, `curl.exe https://web-production-6c935.up.railway.app/salud`.
2. **Las columnas**: `python scripts/preparar_sheet.py`. El simulacro del 21/10 contra el
   Master da solo `CUENTAS!I1 cuentas_banco` y `BANCO_RAW!R1 origen`; lo del 15/10 ya está.
3. **Las cuentas de la conciliación** (semana 8):
   `python scripts/migraciones/2026_10_20_cuentas_conciliacion.py`. Pone las cuentas del banco
   de Banco, Banco USD y Mercado Pago, y Mercado Pago pasa a conciliar. Necesita el paso 2.
4. **Los rubros de estructura** (21/10): `python scripts/migraciones/2026_10_21_rubros_estructura.py`.
   Agrega Gastos generales, Combustible y cinco alias de tipo `rubro`. Va **después** del
   push: el motor viejo no conoce el alias de tipo `rubro` (lo avisa y no lo aplica, sin
   romper nada).
5. **`POST /maestros/recargar`** y leer las advertencias. Tienen que quedar solo las que ya
   se conocen: Elias Rodriguez con «Zinguería / Zinguería», Contador Pasolli y el alias «Sofi»
   de tipo «personal».
6. **Las CC**: `python scripts/crear_cc_obras.py`, con `FACHADO_PERSONAL_SHEET_ID` en el
   entorno. Crea 13 hojas en el Master (5 nuevas) y 4 en el libro personal.
7. **El cron de vistas**:
   - el servicio `vistas` en Railway, con los pasos de `docs/handoff-fachado-core.md` §5;
   - después, `python scripts/recalcular_vistas.py --simulacro` y la corrida de verdad;
   - tienen que aparecer `VISTA_GENERAL` y `VISTA_OBRAS_MES`.
8. **Push del gateway** (`chatbot-contable`, sus commits de la semana 8 y del 21/10), según
   su resultado en este archivo:
   - las dos plantillas de Meta;
   - `FACHADO_RESUMEN_LUNES` y `FACHADO_PEDIDO_EXTRACTOS` cuando estén aprobadas;
   - `"conciliacion": true` en el tenant de Petrus.

   Va en el 8 por coherencia, no porque dependa de los pasos 1 a 7. Según la sesión del
   gateway, su código funciona con el motor del 15/10 que está hoy en producción: los campos
   nuevos se leen solo si vienen, y el pedido semanal está apagado. Si la mezcla de fichas
   (falla 4, que pisa importes) no puede esperar, el gateway se puede pushear antes, solo. Sin
   el motor nuevo, igual faltan la pregunta de obra nueva y los rubros de Austral.
9. **Prueba en producción**, con Gabriel o Petrus:
   - el ticket de YPF sin texto → solo «¿A qué obra?», con Austral primero;
   - «Austral/Mathias» con su comprobante de MP → los rubros de estructura;
   - «Retiro/Abucoque» con un comprobante → solo el rubro personal, y al contestarlo, ninguna
     pregunta de obra;
   - un comprobante con «Minas» → «No conozco «Minas»…» → «Obra nueva» → confirmar → «Di de
     alta la obra Minas»; mirá la fila nueva en OBRAS y completá tipo, servicio y comitente;
   - un extracto → el resumen con el signo («libro −$ …»).
10. **Looker Studio**, con `docs/tablero-looker.md`.
11. **El 1/11**: `python scripts/cargar_saldos_apertura.py --csv docs/saldos-apertura-31-10.csv`
    (completado por Gabriel y Petrus) y los extractos de octubre.

Opcional, después del paso 5: `python scripts/snapshot_maestros.py` y commitear el snapshot. El
del repo ya tiene aplicadas las dos migraciones.

**No** bajar `CONCILIACION_DESDE` en Railway. **No** correr todavía las correcciones del 9/10
(Lennon contra Efectivo, M-000005 en dólares): siguen esperando las respuestas de Gabriel. Pero
mientras no se corran, el tablero muestra Lennon en rojo con unos $ 15 millones de capital
propio.

## Para Valen

Del motor (21/10), una línea por tema; la opción que tomé es la conservadora:

- **Logs de Railway**: no pude leerlos. El CLI de esta PC tiene la sesión de otra cuenta (la
  de Hensel) y no ve el proyecto de Fachado; vincularlo cambiaba la configuración. Las fallas 3
  y 4 están reconstruidas con las capturas, reproduciéndolas en el motor y con la lectura del
  código del gateway (abajo). Si querés confirmarlas con los logs: Railway → `web` y el
  gateway → Logs, el 20/10 de 18:40 a 19:15.
- **El rubro en un gasto personal con un proveedor de obra**: Ferretería Andina, Electricidad
  Angostura o Edesur en «Retiro» o un inmueble ya no llevan su rubro de obra («Materiales ›
  Ferretería»); preguntan el personal, como pide v1.12. Son 3 preguntas más en el corpus.
  Además, en RUBROS personales no hay «Servicios» (Edesur termina en «Casa»): ¿se agrega?
- **«Lennon/nafta»**: lo que el usuario escribe no se cambia; queda Combustible (de
  estructura) en una obra. Si debería haber un combustible de obra, hay que agregarlo a
  RUBROS.
- **Un número suelto es el importe**: «Austral/combustible 77000» → $ 77.000. Es una regla
  nueva del resolver: de 4 a 9 cifras, sin años ni números de operación, cuota, certificado,
  cheque o etapa. Antes había que escribir «$».
- **La retención de IIBB del reporte de Mercado Pago** ahora es una pregunta (v1.12: ingresos
  brutos no es gasto bancario), no parte del lote de S3. Los rendimientos siguen en el lote.
- **El alias de la obra nueva**: se escribe solo si lo escrito difiere del nombre («Minas» y
  «minas» son lo mismo para el motor).
- **La pregunta «nuevo»**: sale solo si el nombre no se parece a ningún contratista; si se
  parece, sigue la de siempre, «¿Quién es…?» con «Es nuevo». También sale en un ingreso sin
  obra.
- **El esquema del lector cambió** (`pagado_con`): la próxima corrida con `--adjuntos` vuelve
  a leer todo (unos USD 0,25), porque la caché local no sirve con el esquema nuevo.
- **El caso «Austral/Sofi» del corpus**: sigue fallando, igual que antes (espera una pregunta
  que se sacó el 15/10). Lo dejo hasta que se decida el rubro de Sofía Cervera.
- **Los Epen de octubre** (M-000022, M-000023, P-000013) siguen cargados en Mercado Pago, y en
  el ensayo no cruzan con las líneas «COMPRAS PATAGONIA 24». No los toqué, como dice M4; desde
  ahora un comprobante de débito va a Banco.

## Al terminar (las dos sesiones)

Debajo de esta línea, cada sesión deja su resultado.

---

## Resultado — Motor (sesión del 21/10)

M1 a M5 commiteados encima de la semana 8, **sin pushear**: `9c5d5f7` (M1+M2), `b20ea6b` (M3),
`5569768` (M4), `735e690` (M5) y el de este cierre. Antes, `3904a46`: el CONTEXTO v1.12 y este
handoff, como vinieron. Nada se escribió en los Sheets reales: la migración nueva se aplicó
solo al snapshot, y su simulacro y el de `crear_cc_obras` corrieron contra el Master real,
en solo lectura. No se tocó `CONCILIACION_DESDE`.

Las seis suites en verde: `test_casos`, `test_confirmar`, `test_reglas`, `test_conciliar`,
`test_vistas` y `test_apertura`. Cada falla de las capturas tiene su test de conversación con
el texto real.

### Qué quedó

**M1 · Rubros según el destino** (fallas 1 y 2). Lo de la l. 1141 era la causa, pero no la
única: el tipo de rubro también salía mal en `_completar_preguntas`, en el habitual del
contratista, en `_ultimo_rubro` y en la sugerencia del LLM. Los cinco lugares usan ahora el
destino:
- Austral o un contratista de estructura → estructura, más los «otro»: IVA, Rentas, Honorarios;
- personal → personales;
- obra → obra.

Además:
- **Ticket de estación de servicio**: YPF, Shell, Axion, Puma o Gulf en la razón social, o
  «combustible / nafta / gasoil» → Combustible sin preguntar; sin destino, solo «¿A qué
  obra?», con Austral primero.
- **Un rubro que no dijo el usuario** y no le corresponde al destino final se borra y se
  pregunta. Ejemplos: el combustible si contesta Lennon; el último rubro de Mathias, que era
  de obra, en Austral.
- **Migración** `2026_10_21_rubros_estructura.py`, con su simulacro contra el Master real.
  ALIAS admite el tipo `rubro`.

Tests con las capturas 03-04 y 05-06, más «Austral/combustible 77000», «Sofia/Austral»,
nafta, gasoil y gastos generales.

**M2 · «¿A qué obra?» completa** (falla 3):
- las opciones son todas las obras activas y Austral, 12 hoy (hasta 15), las usadas hace menos
  primero; en lo personal, los inmuebles; Jardín Maternal no;
- con la obra abierta, el rubro espera;
- la secuencia de las capturas 07-09, con «Club y deporte» (el «4»), conserva Abucoque;
- un «4» suelto sin ficha es `intencion = "otro"`;
- invariante nuevo, en `test_corpus` y en `test_casos`: ninguna ficha con obra pregunta la obra.
  Da 0 en el corpus.

**M3 · Obra nueva** (falla 4):
- la pregunta es `campo = "nuevo"`, con `__obra_nueva__` / `__nuevo__`, y reemplaza a «¿A qué
  obra?»;
- con «Obra nueva»: `extras.obra_nueva`, la advertencia y las preguntas normales;
- `/confirmar` escribe el movimiento y da de alta la obra (`Libro.agregar_obra`, con
  `obra_creada`). Si el alta falla, devuelve una advertencia;
- después, el mensaje siguiente con «Minas» ya la encuentra y el recálculo de vistas le arma
  `CC_MINAS`;
- «Lennon/Minas» sigue siendo contratista nuevo.

**M4 · Mercado Pago pagado con tarjeta**:
- `pagado_con` sale del texto del PDF (solo si es de Mercado Pago) y del lector. En el esquema
  va como string o null, **sin enum**: un enum mixto con null podía hacer que la API rechace
  el esquema y que no se lea ningún comprobante;
- débito → Banco, medio «Tarjeta de débito»;
- crédito → Mercado Pago, con el aviso de P-34.

**M5 · Conciliación**:
- las transferencias a MERCADOLIBRE S.R.L. salen del lote MeLi y se concilian o preguntan «a
  una cuenta de Mercado Pago»;
- DPR Sellos, rentas e IIBB salen de gastos bancarios: pregunta con Impuestos y tasas › Rentas;
- desempate por fecha: las ambiguas se deciden al final del extracto, así que funciona en
  cualquier orden;
- el signo en el resumen y en `consultas.pesos`;
- las tarjetas de crédito no se tocaron.

### El ensayo de octubre, antes y después de M5

Es el mismo del 21/10: copia en memoria de BANCO_RAW real (50 líneas de octubre) y de los dos
libros, con `CONCILIACION_DESDE=2026-10-01` solo en ese proceso.

| | Antes | Después |
|---|---|---|
| Conciliadas solas | 13 | **15**: los dos $ 200.000, por fecha |
| Con más de un candidato | 2 | **0** |
| Internas / traspasos de dólares | 1 / 5 | 1 / 5 |
| Lote gastos bancarios | 1 línea (DPR Sellos) | **0**: DPR va como pregunta con Rentas |
| Lote MeLi | 12 líneas, $ 1.609.900 | **5 líneas, $ 384.900**: solo las compras (PCT) |
| Preguntas sueltas | 21 | 29: 7 transferencias a un CVU y 1 DPR |
| Resumen | «libro $ 7.280.047,16» | «libro **−$** 7.280.047,16» |

Las 7 transferencias a un CVU se vuelven traspasos solos cuando llegue el reporte de Mercado
Pago con el ingreso, si son cargas a la cuenta del estudio. Si no, son pagos a quien cobra por
Mercado Pago, y la pregunta lo resuelve.

### La métrica de siempre (gratis: `--sin-llm --historia`, la misma historia del 20/10)

| | Antes (`3904a46`) | Después |
|---|---|---|
| Obra/destino sin preguntar | 45/50 (90 %) | 45/50 (90 %) |
| Obra y contratista · con las de diseño | 38/50 · 45/50 | 38/50 · 45/50 |
| Preguntas por movimiento | 1,54 | 1,56 |
| Con obra + contratista + comprobante | 1,11 | 1,16 |
| Qué se pregunta | rubro 5, obra 6 | rubro 6, obra 6 |
| Invariante §5.7 / el nuevo de §5.12 | 0 / — | 0 / **0** |

El rubro sube por dos cambios que van en direcciones opuestas:
- 3 gastos personales con proveedor de obra ahora preguntan el rubro personal (ver «Para
  Valen»);
- los 2 comprobantes sin texto ya no preguntan el rubro junto con la obra: el rubro espera a
  la obra.

«Austral/Sofi» falla igual antes y después: es el caso viejo del 15/10.

### Reconstrucción de las fallas 3 y 4

No hubo logs de Railway (ver «Para Valen»). Esto sale de tres fuentes:
- las capturas, con sus horas;
- haber reproducido cada paso en el motor, con el código de producción (el del 15/10);
- el código del gateway, que leyó su sesión.

Las dos sesiones llegamos a lo mismo.

**Falla 3** (Gabriel, «Retiro/Abucoque»):
1. 18:46. «Austral/Mathias» con el comprobante de MP. El motor pregunta el rubro con los de
   obra (falla 2). Esa ficha queda esperando respuesta.
2. 18:55. Llega el comprobante de Natalia Livio con «Retiro/Abucoque».
   - **Motor**: personal, obra Abucoque, una sola pregunta, el rubro personal (captura 08).
     Correcto.
   - **Gateway**: avisa «…movimiento anterior (1 sin confirmar). Escribí "pendientes"…».
3. 18:56. Gabriel contesta «4». Cuando llegó, la ficha de Abucoque ya no estaba activa: a las
   19:09 el bot dice «Retomo: Abucoque». El gateway le mandó el «4» al motor **como mensaje
   nuevo, sin `contexto_previo`**.
4. **Motor**: un «4» sin contexto dio «¿A qué obra?» con Lennon…Grigera Galpón, que es
   exactamente la captura 09. Con la ficha entera y la respuesta (sea «Club y deporte»,
   «Familia», «Honorarios» o «4»), el motor conserva Abucoque siempre.

Qué lado falló: **el gateway**. Estacionaba la ficha sin su pregunta y mandaba un número suelto
como movimiento nuevo; lo arregló su sesión. Del lado del motor queda la defensa: el «4» sin
contexto es «otro».

**Falla 4** (Minas):
1. 19:09. Llega un comprobante de $ 1.000.000 de la obra nueva mientras había una pregunta
   abierta.
2. **Gateway**: la rama del comprobante con `estado == "preguntando"` lo sumó a la ficha en
   curso, porque esa ficha no tenía comprobante y estaba dentro de los 90 s. Es justo lo que
   v1.12 prohíbe, y de ahí sale «Retomo: Abucoque $ 1.000.000», con el importe pisado
   (arreglado en su G1).
3. **Motor**: aun como ficha propia, «Minas» habría dado «¿A qué obra?» más «¿Quién es
   «Minas»?», sin la opción de obra nueva. Eso es M3.

Qué lado falló: **los dos**. La mezcla es del gateway; la pregunta que faltaba, del motor.

### Supuestos (conservadores; ninguno cambia §3)

Están en «Para Valen», arriba. El que más pesa es el primero: en un gasto personal, el rubro
habitual de obra del proveedor ya no se usa y se pregunta. Los abiertos del 15/10 (el rubro
de Sofía Cervera, MeLi como `Personal › Consumos`, el capital propio) y P-34 (tarjetas de
crédito) no se tocaron.

### Cambios de contrato

Ninguno respecto de §3. Lo cruzamos con la sesión del gateway: la pregunta `nuevo` y sus dos
valores, `obra_creada`, hasta 15 opciones de obra (12 hoy) y `pagado_con` solo informativo.
Agregados que no rompen nada: `extras.obra_nueva` también trae `alias`, y un texto de 1 o 2
dígitos sin contexto devuelve `intencion = "otro"`.
