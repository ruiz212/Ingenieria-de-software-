# Cotizaciones POS y WhatsApp

**Objetivo:** corregir precio/rechazo en POS y mantener estado y aviso WhatsApp coherentes, sin modificar pedidos reales durante las pruebas.

**Evidencia:** la lista devuelve también solicitudes Aceptadas, pero siempre ofrece editar/rechazar; el refresco conserva filas aunque el bot cambie su estado. Rechazo y aceptación confirman SQL antes de encolar el aviso. El helper mezcla el SP transaccional publicado con otra conexión y un SP de metadatos inexistente en Azure y reservado al worker. Los métodos JSON de aceptar/rechazar omiten el cuerpo exigido por la validación común. Los SP de cotizar/cancelar y sus permisos sí están instalados.

**Decisión:** usar el SP de aviso de cotizaciones ya publicado en la misma transacción del cambio; mantener OTP y otros canales fuera del alcance. Conservar la protección de precios ya aceptados. El navegador usará la API común con CSRF y cuerpo JSON, mostrará el error del servidor y actualizará las filas cuando cambie el estado/precio remoto. Invalidar la caché de JS.

- [x] Regresiones de commit/rollback con SQLite aislado y de notificación por el cursor del POS.
- [x] Corregir transacciones y API, manteniendo permisos, propiedad y reglas de estado.
- [x] Regresiones en navegador real: actualizar, rechazar, errores descriptivos y cambio de estado por WhatsApp durante polling.
- [ ] Suite, navegador, revisión de secretos y diff; PR/CI Linux, merge y despliegue por main autorizados previamente.

No se actualizan ni rechazan cotizaciones operativas para probar; no se envían mensajes reales ni se aplican migraciones.

Validación local: 484 aprobadas, 168 omitidas, ocho comprobaciones Edge y CSS
vigente. Informe `docs/REPARACION_COTIZACIONES_POS_2026-11-06.md`.
