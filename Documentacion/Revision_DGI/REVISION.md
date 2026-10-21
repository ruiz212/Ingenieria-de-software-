# Revisión fiscal y técnica de Brajher’s Cake

Fecha de cierre de pruebas: 13 de octubre de 2026.

## Resultado y alcance

Se revisaron las rutas y servicios de POS, cotizaciones, monitor, catálogo,
inventario, producción, caja, contabilidad, estadísticas, clientes, RRHH,
asistencia, usuarios y configuración. Se implementaron los controles descritos
abajo y se verificaron con SQL Server aislado. Esta revisión no equivale a una
certificación de la DGI ni a una auditoría exhaustiva de todas las operaciones.

La aplicación configurada utiliza Azure SQL Database. El intento de conexión
remota terminó con SQLSTATE 08001. No se aplicó la migración a esa base ni se
publicó esta versión en Azure. El código local requiere la migración fiscal;
no debe desplegarse por separado de ella. No se modificaron registros reales.

## Base documental consultada

La DT 03-2007 contempla autorización, acceso identificado, correlativos,
conservación de documentos anulados, respaldos, contingencia, manuales y reportes
contables en córdobas y español. La balanza debe mostrar saldo anterior,
movimientos y saldo final. Fuente: [La Gaceta 104, 4 de junio de 2007,
páginas impresas 3273–3274](https://sajurin.enriquebolanos.org/docs/G-2007-06-04.pdf).

La facturación computarizada también tiene formalidades y trámite de
autorización. Se consultaron la [DT 09-2007, La Gaceta del 16 de julio de
2007](https://sajurin.enriquebolanos.org/docs/G-2007-07-16.pdf) y las
[preguntas frecuentes de la DGI](https://www.dgi.gob.ni/FAQ/otros_tramites.htm).

El aviso DGI del 2 de febrero de 2024 describe el reporte de rangos utilizados,
facturas anuladas, series y sucursales en DMI 2.1. Fuente:
[comunicado DGI](https://www.dgi.gob.ni/pdfNoticia/3203).
El CSV incorporado es auxiliar: no se presenta como archivo oficial importable
ni realiza declaraciones. Deben confirmarse con Rentas la vigencia del trámite,
el régimen inscrito y los requisitos particulares del contribuyente.

## Cambios implementados

| Módulo | Problema encontrado | Cambio aplicado |
|---|---|---|
| Facturación | Se aceptaban importes enviados por el navegador | Precio, descuentos, extras e IVA se calculan desde el catálogo en el servidor |
| Fiscal | No había configuración y conservación suficiente del documento | Pantalla de emisor/régimen, clasificación tributaria por producto e instantánea de factura |
| Numeración | Correlativos expuestos a concurrencia | Incremento transaccional, índices únicos y prueba concurrente |
| Reintentos | Un reenvío podía duplicar operaciones | Clave de solicitud persistida; repetir devuelve la misma factura; cambiar la solicitud con igual clave se rechaza |
| Anulaciones | Riesgo de eliminar o ignorar el efecto contable | Conservación del documento, motivo, usuario, reversión y contrapartida de pagos en caja abierta |
| Impresión | Documento reconstruido desde datos que podían cambiar | Original/copia de factura conservada; comprobantes contables con instantánea del emisor |
| Contabilidad | Validación y reportes incompletos | Partida doble exacta a centavos; bloqueo de períodos cerrados; balanza con saldo anterior; mayor con apertura |
| Caja | Cierre simplificado y conversión de dólares inconsistente | Conteo y supervisor distinto; bloqueo de ventas durante arqueo; USD calculado en servidor y registrado en NIO |
| Inventario | IVA de compras calculado siempre como si aplicara 15% | Comprobante del proveedor e IVA documentado; crédito fiscal bloqueado fuera de régimen general |
| Producción | Consumos concurrentes podían usar el mismo stock | Bloqueo de insumos y descuento condicionado dentro de una transacción |
| Catálogo | Precios/descuentos sin límites coherentes | Importes finitos, positivos y descuento acotado; IVA configurable por producto |
| Cotizaciones/tienda | Clientes podían intentar emitir ventas | Solicitudes web separadas del cobro; precios cotizados positivos y rechazo limitado al propietario o personal autorizado |
| Monitor | Cualquier transición de estado era aceptada | Secuencia Pendiente → En Proceso → Listo → Entregado y registro de cambio |
| Estadísticas/CRM | Facturas anuladas seguían inflando métricas | Exclusión de anuladas y ajuste del conteo de compras al anular |
| Nómina | Lotes sin asiento y redondeos inconsistentes | Contabilización por empleado, importes a centavos y rechazo de períodos superpuestos |
| RRHH | Eliminación del expediente y sus dependencias | Suspensión del empleado preservando historial |
| Vales | Se podía cambiar la marca de descuento sin asiento | Liquidación vinculada a nómina; correcciones requieren ajuste contable |
| Seguridad | Exenciones CSRF y privilegios insuficientemente restringidos | CSRF común, validación JSON, controles de roles, contraseñas nuevas de 12 caracteres, protección de SuperAdmin y auditoría |
| Asistencia/kiosco | Registro administrativo expuesto | Alta biométrica y marcación manual restringidas a administradores |
| Interfaz | Formularios, navegación y tablas difíciles de usar en móvil | CSS compartido, menú móvil, tablas desplazables, foco de teclado, controles táctiles y POS apilado |
| Operación | Sin procedimiento de respaldo verificable | Script SQL Server COPY_ONLY/CHECKSUM/VERIFYONLY y manual de contingencia; Azure requiere su mecanismo administrado |

Las bases de pasteles personalizables conservan su precio de catálogo más los
extras configurados. No se acepta un precio libre del cliente como precio fiscal.

## Evidencia de comprobación

- **57 pruebas aprobadas**, sin omisiones: reglas monetarias, documentos,
  reintentos, autorización, compras, stock, nómina individual y por lote,
  reversión, cierre mensual, correlativos simultáneos y carga de 20 pantallas.
- Base independiente `PanaderiaQA_DGI_20261012`; solo datos ficticios.
- 41 plantillas Jinja y 10 archivos JavaScript comprobados sin errores de sintaxis.
- `git diff --check` sin errores.
- Respaldo de la base QA creado y validado con `RESTORE VERIFYONLY`.
  Esto no es una prueba de restauración completa ni un respaldo de Azure.
- Hubo inspección visual inicial del control fiscal en escritorio y ancho móvil.
  El navegador dejó de estar disponible en la sesión posterior; queda pendiente
  la comprobación visual interactiva completa de la última versión de todos los
  módulos. Los GET y la compilación de plantillas no sustituyen esa comprobación.

## Pendientes que impiden declarar cumplimiento integral

1. Confirmar cuota fija o régimen general; completar razón social, RUC,
   dirección y autorización real. Ningún texto ingresado comprueba autorización.
2. Recuperar conexión a Azure, validar restauración, ejecutar migración y publicar
   código y esquema coordinadamente. Revisar los datos históricos antes de
   crear índices únicos; nunca borrar duplicados automáticamente.
3. Conciliar saldos iniciales y documentos históricos. Las facturas antiguas sin
   instantánea no se convierten retrospectivamente en documentos certificados.
4. Completar flujo de cobro posterior de encargos y asociación de cada cobro a su
   turno; el nuevo flujo validado cubre venta/anticipo y anulación en caja abierta.
5. Implementar notas de crédito/débito y correcciones posteriores al cierre.
   Actualmente se bloquea la anulación cuando la caja ya cerró.
6. Completar valoración de inventarios, costo de producción/ventas y conciliación
   de mermas con inventario terminado. El control de cantidades no es un costeo
   contable completo.
7. La nueva nómina validada es mensual. No se habilitó cálculo semanal,
   catorcenal o quincenal. La liquidación laboral, aguinaldo, tasas y tablas
   preexistentes requieren revisión especializada; no fueron certificados aquí.
8. No hay consolidación de sucursales, emisión de cheques ni integración directa
   con DMI. Esta instalación mantiene una sola serie FAC.
9. Configurar y comprobar respaldo operativo, retención, restauración, zona
   horaria, mínimos privilegios SQL y HTTPS en el entorno definitivo. Los
   desencadenadores no sustituyen el control de acceso del administrador SQL.

## Documentos relacionados

[Manual de operación, instalación, respaldo y contingencia](MANUAL.md).
