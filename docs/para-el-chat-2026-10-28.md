# Para el chat del proyecto: lo del 28/10

> Índice de lo que se hizo el 28/10, para trabajarlo en el chat del proyecto. Cada punto apunta a
> su documento; los tres se pueden subir tal cual.

## 1 · El tablero, más lindo y con tortas por rubro

Está en `docs/tablero-looker.md`, en «Cómo quedó (28/10)» y «Retoques de la tarde del 28/10».

Hay dos informes en Data Studio, **sin compartir** (compartir lo hace Valen):

| Informe | Link | Páginas |
|---|---|---|
| Fachado — Tablero del estudio | <https://datastudio.google.com/reporting/2c7984bd-2bae-4e34-a492-b48a9bf2fd73> | Visión general, Por obra, Proveedores |
| Fachado — Personal | <https://datastudio.google.com/reporting/d9779551-7295-4456-9f76-589fc0777da9> | Retiros |

Lo nuevo de la tarde:
- el tema «Acentuado»;
- tres tortas por rubro:
  - la de todas las obras;
  - la de la obra elegida en «Por obra»;
  - la de los retiros;
- los importes compactos en las tarjetas;
- los nombres de las columnas legibles;
- «-» en lugar de «null».

Las capturas en 400 px de ancho están en `docs/tablero/capturas/2026-10-28/`.

## 2 · La revisión de lo cargado y lo que falta

Está en `docs/revision-datos-2026-10-28.md`: es una foto del Master al 28/10, leída solo para
lectura. Los títulos:
- **32 movimientos**: 22 de WhatsApp (Gabriel 15, Petrus 7) y 10 del cierre semanal. No hay
  ninguno conciliado ni anulado.
- **No se carga nada desde el 21/10**: hace 7 días. Petrus no carga desde el 17/10.
- **8 de las 13 obras no tienen ningún movimiento**: Cerro Bayo, Lumaia, Muelle de piedra,
  Tonga, Moquehue, Grigera Galpón, Tres Cerros y Jardín Maternal (cerrada).
- **Con muy poco**: Hua Huan (1), Austral (2, uno mal cargado: US$ 400 como $ 400) y Moreno
  (4 pagos, ningún cobro).
- **Lennon y Moreno en rojo por cómo se cargaron**:
  - Lennon tiene pendientes las correcciones del 9/10, y M-000013 seguramente lo pagó Lennon
    directo;
  - Moreno no tiene cargado ningún cobro de certificado.
- **Hay cosas en el banco que no están en el Master**:
  - Sofía Cervera;
  - el cobro de Bosque de Lumas (Lumaia);
  - un crédito de $ 2,2 M sin identificar;
  - unas 8 transferencias;
  - las capturas del 20/10.
- **Rubros**:
  - 14 movimientos con un rubro viejo y 6 con uno «a confirmar»;
  - contratistas duplicados (Maderera Misiones, Marcelo Maragaño, Fábrica de Calcos);
  - el 21,5 % de lo gastado no tiene rubro.
- **Para el 1/11**: los saldos de apertura (el CSV está vacío), los extractos desde el 17/10 y la
  muestra del PDF de Mercado Pago.
- Cierra con un **checklist de 21 pendientes** con responsable y **14 preguntas para Gabriel**.

**Limitación**: el libro personal no se leyó porque falta su ID en el `.env` local. Lo
personal sale del cierre semanal y de los handoffs.

## 3 · El manual para los usuarios

Está en `docs/manual-usuarios.md`. Es para Gabriel, Petrus y quien se sume: tono simple, para
leer en el celular. Cubre:
- cómo cargar («Obra/Contratista importe» y todo lo que se le puede agregar);
- los comprobantes;
- la ficha y las preguntas: cómo confirmar, corregir y anular;
- los casos especiales: personal, Austral, contratista u obra nuevos, pagos del comitente,
  cajas de obra, certificados, etapas, varios pagos en un mensaje, traspasos y extractos;
- las consultas;
- qué pasa después: la planilla, las cuentas corrientes, el cierre semanal y el tablero;
- los rubros;
- las buenas prácticas y las preguntas frecuentes.

Al final, **«Para revisar con Valen»** junta 14 puntos donde el código y la spec no coinciden o
algo no está decidido. Los principales:
- una ficha sin confirmar se descarta a las 12 horas, y la spec dice que nunca;
- los pendientes viven en memoria y se pierden con un deploy;
- los audios no están probados;
- los mensajes automáticos (extractos de los viernes, resumen de los lunes) esperan que Meta
  apruebe las plantillas;
- IVA, facturas emitidas y tarjetas sin definir;
- un certificado mal cargado no se puede corregir.

Antes de pasárselo a Gabriel conviene resolver esos puntos o sacarlos del texto. Cuando se
compartan los informes, hay que agregar los links del tablero.

## 4 · Lo técnico del día

- `/maestros/recargar` devuelve 503 cuando el Sheet falla y el motor sigue con la copia en caché
  (`d61ac43`). Está pusheado, pero **sin desplegar**: Railway tiene los deploys pausados por un
  incidente. Se despliega solo cuando lo reanuden. Si no arranca, «Redeploy» en `web`.
- El cierre semanal del 26/10 falló con 401, por una clave vieja. Ya está corregido. La semana
  del 19 al 25/10 la completa el cierre del lunes 2/11, como decidió Valen.

## 5 · Qué conviene decidir en el chat

1. **La carga quedó frenada desde el 21/10.** ¿Gabriel y Petrus saben que el bot está andando?
   El manual sirve para retomar.
2. **Lennon**: aplicar las correcciones del 9/10 antes de compartir el tablero. Si no, sale en
   rojo con $ 15 M.
3. **Los 35 rubros a confirmar, los duplicados de CONTRATISTAS y lo «Sin rubro»**: una sesión
   con Gabriel.
4. **El 1/11**: los saldos de apertura, la Chequera y si «Caja obra Gonzalo» sobra.
5. **Las 8 obras sin movimientos**: ¿están paradas o falta cargarlas?
6. **Los puntos «Para revisar con Valen» del manual.**
