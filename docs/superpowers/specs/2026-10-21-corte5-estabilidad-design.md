# Corte 5: búsqueda, continuidad y trazabilidad

El objetivo es que una persona pueda encontrar una factura reciente dentro del período DGI, continuar un formulario después de una interrupción, registrar empleados con un perfil de puesto claro y entender en qué cuenta cayó cada anticipo. La aplicación actual es Flask con SQL Server y plantillas administradoras; se extienden esas rutas y estilos, sin cambiar el cálculo ni la definición de salarios.

## Decisiones de implementación

- La búsqueda DGI consulta SQL Server por página y período; el navegador solicita resultados al escribir o cambiar filtros. Se limita a 10, 25 o 50 filas y se refresca al volver a la pestaña. El resultado muestra número, cliente, fecha, tipo y estado. La fecha del período usa la misma convención de facturas existente.
- La sesión de administración usa un ping autenticado condicionado a actividad real del usuario y un aviso dos minutos antes del vencimiento. Se guardan borradores por usuario y pestaña de los formularios indicados, excluyendo fotos, secretos y tokens. Se borran después de guardar o cerrar sesión.
- Los perfiles de puestos son un catálogo nuevo en `rrhh`, vinculado opcionalmente a `Empleados` para mantener compatibles los expedientes previos. La contingencia de asistencia requiere un supervisor autenticado y un motivo obligatorio; registra auditoría en la misma transacción del marcaje. No se agrega un PIN público.
- La contabilidad conserva los importes existentes y muestra descripciones más precisas para el anticipo y el saldo. Se valida con pruebas de asiento y arqueo; los movimientos reales nacen al cobrar, sin depender de la entrega.

## Restricciones

- No modificar salarios ni escalas salariales por puesto.
- No aplicar cambios a la base ordinaria ni desplegar a Azure durante la implementación; validar la migración en la base QA antes de activarla en destino.
- Evitar datos personales en los reportes de pruebas y no ejecutar envíos reales de correo.
