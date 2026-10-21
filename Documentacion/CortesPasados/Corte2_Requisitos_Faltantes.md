# Apéndice del Proyecto Corte 2
## Requisitos funcionales identificados en la revisión del sistema

**Fecha de revisión:** 13-10-2026  
**Base de contraste:** `Requerimientos_Panaderia_Amada_V2.md`, rutas Flask, servicios, plantillas, JavaScript y migraciones del repositorio.

Este apéndice complementa los RF01-RF94 del documento de Corte 2. Los requisitos siguientes no estaban descritos con suficiente precisión en ese documento y corresponden a capacidades incorporadas posteriormente o necesarias para describir fielmente el sistema actual.

## Requisitos funcionales complementarios

| ID | Módulo | Requisito | Prioridad |
| :--- | :--- | :--- | :--- |
| RF95 | Fiscal | El sistema deberá permitir configurar el régimen fiscal, razón social, RUC, dirección, teléfono, correo, autorización y serie fiscal del emisor, conservando el valor usado por cada comprobante. | Alta |
| RF96 | Fiscal | El sistema deberá generar números de factura correlativos por serie, con bloqueo transaccional y restricción de unicidad para evitar duplicados ante operaciones concurrentes. | Alta |
| RF97 | Fiscal | El sistema deberá guardar una instantánea JSON inmutable de cada comprobante emitido, incluyendo emisor, líneas, impuestos, pagos, QR, serie y totales para su impresión o reimpresión posterior. | Alta |
| RF98 | Fiscal | El sistema deberá permitir anular una factura solamente mientras el turno sea corregible, exigir un motivo y registrar la reversión contable y la devolución de pagos sin eliminar el comprobante original. | Alta |
| RF99 | Auditoría fiscal | El sistema deberá registrar en una bitácora inmutable la acción, entidad, usuario, fecha, IP y detalle JSON de emisiones, anulaciones, cambios fiscales y operaciones sensibles. | Alta |
| RF100 | POS | El servidor deberá recalcular el precio, descuento, IVA, extras y total a partir del catálogo vigente, sin confiar en los importes enviados por el navegador. | Alta |
| RF101 | POS | El sistema deberá aceptar una clave de solicitud por venta, detectar reintentos de la misma operación y devolver el comprobante existente sin duplicar factura, pagos ni asiento contable. | Alta |
| RF102 | POS | El sistema deberá permitir pagos múltiples en efectivo, efectivo USD y transferencia, validar referencias de transferencia, aplicar el tipo de cambio y calcular el cambio únicamente con medios que permitan devolución. | Alta |
| RF103 | POS | El sistema deberá emitir una respuesta de comprobante con número, QR, enlace de seguimiento, desglose de pagos, cambio, condición de pago y enlace de impresión. | Alta |
| RF104 | Arqueos | El sistema deberá registrar el conteo ciego de efectivo, dólares y transferencias, incluyendo cantidades por denominación, tipo de cambio utilizado, observaciones y diferencias frente al sistema. | Alta |
| RF105 | Arqueos | El sistema deberá separar el envío del arqueo por el cajero de su verificación por un supervisor distinto, impedir la auto-verificación y cerrar el turno solo después de la verificación. | Alta |
| RF106 | Contabilidad formal | El sistema deberá abrir o localizar automáticamente el periodo contable de una operación, impedir asientos en periodos cerrados y permitir el cierre del periodo únicamente bajo las reglas contables configuradas. | Alta |
| RF107 | Contabilidad formal | El sistema deberá permitir crear asientos manuales de diario con número de comprobante, referencia, descripción y líneas Debe/Haber, rechazando cualquier asiento descuadrado. | Alta |
| RF108 | Contabilidad formal | El sistema deberá generar asientos automáticos para ventas, compras, egresos, nómina, anulaciones y cierres, conservando el vínculo con el documento de origen. | Alta |
| RF109 | Contabilidad formal | El sistema deberá mostrar balance de comprobación, mayor contable y estado de resultados filtrables por periodo, calculados a partir de asientos contabilizados. | Media |
| RF110 | Kiosco biométrico | El sistema deberá registrar o actualizar el descriptor facial de un empleado a partir de una imagen válida, rechazando imágenes sin rostro o con más de un rostro. | Alta |
| RF111 | Kiosco biométrico | El sistema deberá cargar los descriptores activos en memoria, reconocer el rostro de un frame y registrar automáticamente entrada o salida según el registro del día y la tolerancia del turno laboral. | Alta |
| RF112 | Asistencia | El sistema deberá permitir consultar la asistencia diaria, diferenciar llegada a tiempo y tardía, registrar salida y exponer el estado actualizado para el monitor administrativo. | Alta |
| RF113 | Portal de encargos | El sistema deberá permitir que un cliente autenticado o visitante identificado por sesión consulte el estado, precio, fecha, imagen y especificaciones de sus cotizaciones sin acceder a datos de otros clientes. | Alta |
| RF114 | Producción | El sistema deberá publicar en el monitor de cocina los encargos pagados, ordenar por fecha de entrega y persistir la transición Pendiente, En Proceso, Listo y Entregado para reflejarla en el seguimiento público. | Alta |
| RF115 | CRM | El sistema deberá registrar clientes desde el portal mediante verificación del código enviado al teléfono, evitando crear cuentas con teléfonos duplicados o códigos vencidos. | Media |
| RF116 | Reportes | El sistema deberá presentar indicadores de ventas, ticket promedio, productos más vendidos, ventas por categoría, encargos pendientes, mermas, rotación y asistencia para apoyar decisiones de gerencia. | Media |
| RF117 | Operación | El sistema deberá permitir generar respaldos de la base de datos y ejecutar migraciones aditivas identificables sin reconstruir el esquema ni borrar información histórica. | Alta |

## Estado de cobertura verificado

| Área | Estado observado | Evidencia principal |
| :--- | :--- | :--- |
| Facturación fiscal, numeración e instantánea | Implementado | `app/pos/routes.py`, `app/services/fiscal_service.py`, `app/admin/routes_fiscal.py` |
| Anulación y reversión contable | Implementado | `app/admin/routes_fiscal.py`, `app/services/contabilidad_service.py` |
| Idempotencia de ventas | Implementado | `ClaveSolicitud`, bloqueo transaccional y `DocumentoJSON` en `app/pos/routes.py` |
| Arqueo ciego y verificación segregada | Implementado | `app/admin/routes_pos.py` |
| Partida doble, periodos y reportes | Implementado | `app/services/contabilidad_service.py`, `app/admin/routes_accounting.py` |
| Kiosco facial y asistencia automática | Implementado con dependencia de modelos ONNX | `app/kiosco/routes.py`, `app/services/face_service.py`, `scripts/download_models.py` |
| Portal de encargos y monitor de cocina | Implementado | `app/pos/routes.py`, `app/monitor/routes.py` |
| Verificación SMS de clientes | Implementado: exige teléfono verificado y código con vigencia de 10 minutos; Twilio es opcional en desarrollo | `app/auth/routes.py` |
| Edición e historial de CRM | Implementado en API; falta exponer el formulario de edición en la vista administrativa | `app/admin/routes_fidelizacion.py` |
| Imágenes de catálogo y encargos | Implementado con ImgBB opcional y almacenamiento local seguro como alternativa | `app/pos/routes.py`, `app/admin/routes_catalog.py` |
| Mantenimiento de inventario | Implementado en API para materias primas, proveedores y unidades; falta completar controles de edición en algunas vistas | `app/admin/routes_inventory.py` |
| Pensiones, embargos e incidentes laborales | Implementado en API y usado por el cálculo de nómina; falta completar formularios administrativos dedicados | `app/admin/routes_hr.py` |
| Auditoría general de usuarios y productos | Implementado mediante `AuditLog` | `app/services/audit.py`, `app/admin/routes_users.py`, `app/admin/routes_catalog.py` |
| Consulta de auditoría para SuperAdmin | Implementado con filtros de fecha y entidad | `app/admin/routes_users.py`, `templates/admin/auditoria.html` |
| Respaldos automatizados | Parcial: existe comando seguro y verificado, no se observa programación automática | `scripts/backup_database.py` |

## Hallazgos que deben corregirse en la documentación base

1. RF31 indica que el POS debe bloquearse sin turno activo, pero `app/pos/routes.py` crea un turno si no encuentra uno. El requisito debe describir la política real o el código debe cambiarse.
2. RF10-RF12 mencionan `AuditLog`; la implementación fiscal usa `BitacoraFiscal` y auditoría específica. Debe unificarse el nombre o aclararse que son bitácoras distintas.
3. RF25 describe almacenamiento local de imágenes; ahora existe almacenamiento local seguro y ImgBB queda como integración opcional mediante `IMGBB_API_KEY`.
4. RF49 exige convertir el total a USD para mostrar lo que se cobra, mientras el servicio normaliza el pago USD a córdobas para contabilizarlo. Debe documentarse explícitamente la moneda mostrada y la moneda registrada.
5. RF59 y RF60 describen convertir una cotización web pagada a encargo, pero el POS también permite crear el encargo directamente. Deben documentarse ambos flujos.
6. RF94 describe el asiento del cierre de turno; actualmente la integración contable se realiza durante la venta y otras operaciones. Debe aclararse si el cierre genera un asiento adicional o solo consolida los existentes.

## Criterio de aceptación documental

Cada requisito complementario deberá conservar su identificador, módulo, prioridad y una descripción verificable. La etiqueta de estado no sustituye las pruebas: los requisitos marcados como implementados deben validarse con pruebas unitarias, integración SQL o prueba manual con una base aislada antes de declarar el sistema listo para producción.
