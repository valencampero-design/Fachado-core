# Rubros: de la lista vieja a la del estudio (27/10)

> Hecho con `scripts/migraciones/2026_10_27_rubros_estudio.py` a partir de
> `Listado_general_rubros_obra_formato_unificado.xlsx` (CONTEXTO-FACHADO.md §5.4 v1.13). Nada se
> borra: el rubro viejo pasa a `inactivo` con `reemplazado_por`, y el tablero muestra los
> movimientos viejos con el rubro nuevo. MOVIMIENTOS no se toca.

- Rubros nuevos agregados: **92**
- Rubros que ya estaban con el mismo nombre (toman el código): **17**
- Viejos que pasan a inactivo (equivalente claro): **26**
- Viejos **a confirmar con Gabriel** (siguen activos): **35**

## Viejo → nuevo (pasan a inactivo)

| Rubro viejo | Rubro nuevo | Por qué |
|---|---|---|
| Materiales › Albañilería | 1.2 · Materiales › Corralón / albañilería | «Corralón / albañilería» |
| Materiales › Hormigón | 1.3 · Materiales › Estructura | el hormigón es material de la estructura |
| Materiales › Maderas | 1.4 · Materiales › Maderera | «Maderera» |
| Materiales › Sanitarias | 1.6 · Materiales › Sanitarios | «Sanitarios» |
| Materiales › Amoblamiento | 1.10 · Materiales › Amoblamientos: placares y cocina | «Amoblamientos: placares y cocina» |
| Materiales › Grifería | 1.16 · Materiales › Griferías | «Griferías» |
| Materiales › Artefactos Sanitarios. | 1.17 · Materiales › Artefactos de baño | «Artefactos de baño» |
| Materiales › Accesorios de Baños | 1.21 · Materiales › Accesorios de baño | «Accesorios de baño» |
| Materiales › Climatización A.A. | 1.24 · Materiales › Aire acondicionado | «Aire acondicionado» |
| Mano de obra › Contratistas | 2.1 · Mano de obra › Contratista principal | «Contratista principal» |
| Mano de obra › Zinguería | 2.8 · Mano de obra › Zinguero | «Zinguero» |
| Mano de obra › Albañil | 2.9 · Mano de obra › Albañilería | «Albañilería» (mano de obra) |
| Mano de obra › Carpintero | 2.10 · Mano de obra › Carpintería | «Carpintería» (mano de obra) |
| Mano de obra › Jornales | 2.11 · Mano de obra › Jornales varios | «Jornales varios» |
| Servicios de obra › Movimiento de suelos | 3.1 · Servicios › Movimiento de suelo | «Movimiento de suelo» |
| Servicios de obra › Volteo de árboles | 3.3 · Servicios › Volteo | «Volteo» |
| Servicios de obra › Baños químicos | 3.5 · Servicios › Baño químico | «Baño químico» |
| Servicios de obra › Volquetes | 3.6 · Servicios › Volquetes | el mismo, con rubro general «Servicios» |
| Servicios de obra › Contenciones y gaviones | 3.7 · Servicios › Contenciones | «Contenciones» |
| Servicios de obra › Fletes | 3.8 · Servicios › Fletes | el mismo, con rubro general «Servicios» |
| Servicios de obra › Alquiler de equipos | 3.11 · Servicios › Alquiler de herramientas | «Alquiler de herramientas» |
| Estructura del estudio › Sueldos y cargas sociales | A3.1 · Sueldos › Sueldos fijos | Austral › Sueldos › Sueldos fijos |
| Honorarios › Contador | A4.1 · Asesorías externas › Contador | Austral › Asesorías externas › Contador |
| Estructura del estudio › Alquiler | A9.1 · Alquiler › Alquiler | Austral › Alquiler |
| Personal › Supermercado | R7 · Personal › Súper | Retiros › Súper |
| Personal › Tarjeta | R8 · Personal › Tarjetas | Retiros › Tarjetas |

## A confirmar con Gabriel (siguen activos hasta que diga)

| Rubro viejo | Propuesta | Por qué |
|---|---|---|
| Materiales › Durlock | 1.2 · Materiales › Corralón / albañilería | ¿Corralón / albañilería? |
| Materiales › Steel | 1.3 · Materiales › Estructura | ¿Estructura (steel frame)? |
| Materiales › Ballon | — | no sé qué es: ¿una marca? |
| Materiales › Aberturas | 1.8 · Materiales › Carpinterías de PVC o aluminio | ¿Carpinterías de PVC o aluminio, o de madera (1.9)? |
| Materiales › Aislación | — | no está en la lista: ¿Techo (1.5), Corralón (1.2) o un rubro nuevo? |
| Materiales › Artefactos eléctricos | 1.18 · Materiales › Artefactos de iluminación | ¿Artefactos de iluminación? |
| Materiales › pisos | 1.20 · Materiales › Revestimientos | ¿Revestimientos? |
| Materiales › Mesadas | 1.19 · Materiales › Marmolería | ¿Marmolería? |
| Materiales › Zocalos y contramarcos | 1.9 · Materiales › Carpinterías de madera | ¿Carpinterías de madera, o Maderera (1.4)? |
| Materiales › Terminaciones | — | no está en la lista (Insucom, Sergio González la usan) |
| Mano de obra › Especialistas | — | según el oficio: Electricista (2.16), Sanitarista (2.2)… |
| Servicios de obra › Agrimensura | — | no está en la lista: ¿Asesoría? |
| Servicios públicos › EPEN | 5.4 · Indirectos › Operativos | en una obra, ¿Indirectos › Operativos? (en Austral es Servicios › Luz) |
| Servicios públicos › Camuzzi | 5.4 · Indirectos › Operativos | en una obra, ¿Indirectos › Operativos? (en Austral, Servicios › Gas) |
| Servicios públicos › Metrogas | 5.4 · Indirectos › Operativos | en una obra, ¿Indirectos › Operativos? (en Austral, Servicios › Gas) |
| Servicios públicos › Agua | 5.4 · Indirectos › Operativos | en una obra, ¿Indirectos › Operativos? |
| Honorarios › Arquitectura | — | un ingreso del estudio: no está en la lista |
| Honorarios › Dirección de obra | — | un ingreso del estudio: no está en la lista |
| Honorarios › Escribanía | — | no está en la lista: ¿Asesoría, o Indirectos › Administrativos (5.3)? |
| Honorarios › Asesores | A5 | ¿Austral › Contratados, o Asesorías externas (A4)? |
| Impuestos y tasas › AFIP | A2.1 · Impuestos › Impuestos | ¿Austral › Impuestos? (hoy sirve para obra y estudio) |
| Impuestos y tasas › IVA | A2.1 · Impuestos › Impuestos | ¿Austral › Impuestos? (hoy sirve para obra y estudio) |
| Impuestos y tasas › Rentas | A11.1 · Impuestos y ART › Rentas | ¿Austral › Impuestos y ART › Rentas? (hoy sirve para obra y estudio) |
| Impuestos y tasas › Municipales | — | las tasas de una obra: no está en la lista |
| Impuestos y tasas › Bancarios | — | los gastos bancarios del lote de la conciliación |
| Estructura del estudio › Aportes profesionales | A11.6 · Impuestos y ART › Caja previsional | ¿Caja previsional, o Colegio de Arquitectos (A8.1)? |
| Estructura del estudio › Servicios | A1 | ¿Austral › Servicios (Internet, Luz, Gas, Celular)? Hay que elegir el detalle |
| Estructura del estudio › Software | — | no está en la lista: ¿Insumos (A6.1)? |
| Estructura del estudio › Movilidad | — | no está en la lista |
| Personal › Familia | — | no está en Retiros (las transferencias a la familia) |
| Financiero › Compra-venta de divisas | — | no está en la lista |
| Financiero › Intereses | — | no está en la lista |
| Financiero › Comisiones | — | no está en la lista |
| Estructura del estudio › Gastos generales | A7.3 · Gastos corrientes › Otros | ¿Gastos corrientes › Otros? (21/10) |
| Estructura del estudio › Combustible | — | no está en la lista (21/10, el ticket de YPF) |

## Ya estaban, con el mismo nombre (toman el código)

1.1 Materiales › Áridos, 1.3 Materiales › Estructura, 1.5 Materiales › Techo, 1.7 Materiales › Electricidad, 1.11 Materiales › Pinturería, 1.12 Materiales › Ferretería, 1.14 Materiales › Herrería, 1.15 Materiales › Zinguería, 1.20 Materiales › Revestimientos, 1.23 Materiales › Calefacción, 1.27 Materiales › Riego, 2.2 Mano de obra › Sanitarista, 2.16 Mano de obra › Electricista, R1 Personal › Consumos, R2 Personal › Salud y prepaga, R3 Personal › Club y deporte, R4 Personal › Casa

## Contratistas

El rubro habitual que quedó inactivo pasa al nuevo. Además:

- **Elias Rodriguez** → 2.8 · Mano de obra › Zinguero: su pago M-000012 está en Mano de obra › Zinguería
- **Contador Pasolli** → A4.1 · Asesorías externas › Contador: es el contador del estudio («Honorarios › Terceros» no existía)
