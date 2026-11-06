# Cotizaciones del POS y WhatsApp

## Fallos reproducidos

- El refresco del POS conservaba la fila completa aunque el bot hubiera cambiado
  el estado o el precio. Además, ofrecía actualizar/rechazar cotizaciones Aceptadas,
  aunque el servidor protege esas operaciones y responde 409.
- Las funciones del POS ocultaban ese mensaje y mostraban un error genérico.
- La API común de aceptar/rechazar declaraba JSON pero no enviaba un objeto;
  la validación común rechazaba esa petición con HTTP 400.
- Rechazo y aceptación hacían commit antes de encolar su aviso. Una segunda
  lectura de la base SQLite de prueba confirmó que el cambio persistía sin aviso;
  si fallaba el aviso, tampoco se podía revertir el cambio ya confirmado.
- El helper mezclaba el SP transaccional con otra conexión y con el procedimiento
  de metadatos del worker, ausente en Azure. Las cotizaciones ahora usan únicamente
  `crm.sp_WhatsAppNotificar` sobre el cursor del POS, dentro de su transacción.

## Comportamiento resultante

Precio, rechazo y aceptación encolan el aviso antes de confirmar. Si falla el
encolado habilitado, se revierten cambio y aviso. Se conserva la idempotencia y
selección de destinatario del SP publicado, sin conceder permisos nuevos.

Los botones usan la API común con CSRF y objeto JSON; muestran el mensaje del
servidor. El refresco incorpora cambios de WhatsApp y conserva el borrador de
precio cuando la cotización remota no cambió. Una solicitud ya Aceptada muestra
el precio confirmado y permite continuar a caja, sin ofrecer editar/rechazar.

Se actualizan las versiones de JS en POS y tienda para invalidar la caché anterior.
El alcance es cotizaciones; no se modifican las reglas de facturación ni los
avisos de pedidos y OTP.

## Validación

- 484 pruebas aprobadas, 168 omitidas; 46 paquetes CSS vigentes.
- SQLite aislado con conexiones separadas: commit y rollback de precio/estado y
  outbox, protección de solicitudes aceptadas y propiedad de cotizaciones.
  La regresión de errores SQL detecta silenciar un fallo del aviso.
- Ocho recorridos Edge con APIs sintéticas: actualizar, rechazar, errores del
  servidor, JSON de aceptar/rechazar, aceptación y precio remoto, borrador y móvil.
- Comprobación de metadatos Azure de solo lectura: SP de mutación y notificación
  instalados, ejecución permitida a cajero, gerencia y superadmin; canal conectado
  y heartbeat reciente. No se probaron cambios en cotizaciones operativas.
- Detector UI limitado por enlaces Jinja: avisos sobre imágenes dinámicas y
  jerarquía sin CSS resuelto ya presentes en las plantillas. Las vistas nuevas
  se verificaron visualmente a 1440 y 390 px; no se cambió el diseño.

No se enviaron mensajes reales de prueba, reenviaron avisos anteriores ni se
aplicaron migraciones. El envío externo definitivo depende del worker y de la
cuenta WhatsApp vinculada, además del commit del aviso.
