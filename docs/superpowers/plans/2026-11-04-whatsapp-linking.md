# Vinculación y pedidos de WhatsApp — Implementation Plan

> Ejecutar por Codex en el checkout actual, sin delegación, con pruebas antes de los cambios.

**Objetivo:** vincular la cuenta de empresa desde Administración > WhatsApp, retirarla de forma protegida y recibir sus cotizaciones en Solicitudes de clientes del POS.

**Arquitectura:** conservar Flask/Jinja, Neonize, el proceso separado y el bloqueo exclusivo SQL. Una solicitud administrativa persistida coordina vinculación/desvinculación; el proceso revoca la sesión remota antes de confirmar su retirada. En local se puede iniciar el proceso desde el panel. Gemini se inicializa al atender mensajes, no al generar el QR.

**Límites:** solo Admin/SuperAdmin, CSRF, contraseña actual y TOTP cuando esté habilitado; límite compartido de intentos. No borrar cotizaciones ni conversaciones. No ejecutar migraciones o acciones sobre cuentas reales durante la validación local. Mantener la identidad visual existente.

### 1. Seguridad y ciclo de conexión
- [x] Escribir y comprobar pruebas fallidas de reautenticación, permisos y fallo de revocación.
- [x] Añadir migración aditiva `07_whatsapp_vinculacion.sql`: revisión optimista, solicitudes y auditoría administrativa; permisos mínimos.
- [x] Implementar solicitudes en repositorio, control de conexión y arranque local con proceso separado.
- [x] Separar Gemini de la conexión; garantizar que desvincular no procese mensajes pendientes ni conserve consentimientos para otra cuenta.
- [x] Verificar pruebas del proceso sin conectar a WhatsApp ni escribir en SQL operativo.

### 2. Panel administrativo
- [x] Añadir estado privado sin caché y actualización de QR en vivo, solo después de reautenticación reciente.
- [x] Mostrar siempre el área de conexión, instrucciones de escaneo, estados y formulario protegido para retirar la cuenta.
- [x] Conservar gestión humana de conversaciones y añadir acceso visible a Solicitudes de clientes.
- [x] Verificar móvil/escritorio, formularios, errores y ausencia de desbordamiento con datos sintéticos.

### 3. Cotizaciones y entrega
- [x] Comprobar creación en `crm.Cotizaciones` y lectura por el mismo endpoint del POS.
- [x] Cambiar el nombre Solicitudes Web por Solicitudes de clientes y actualizar la lista abierta sin perder precios en edición; escapar contenido del cliente.
- [x] Ejecutar pruebas focalizadas, suite segura sin QA, compilación CSS y revisión del diff.
- [x] Documentar migración, inicio del proceso y limitaciones que requieren una cuenta real.

**Evidencia final:** 421 pruebas aprobadas y 168 omitidas sin destino QA configurado;
Chrome a 390/1440 px, llegada de solicitudes, conservación de precio/foco y HTML escapado;
46 paquetes CSS verificados. Diez lotes SQL analizados con PARSEONLY, sin ejecutarlos.
El usuario eligió expresamente dejar preparada la migración sin modificar PanaderiaDB.
Pendientes de operación: aplicar/verificar en QA y en el destino elegido, reiniciar el
servicio y probar escaneo/desvinculación con un teléfono controlado. No se publicaron cambios.
