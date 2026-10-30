# Mercadotecnia local basada en ventas

## Intención

La tienda debe ayudar a descubrir productos relevantes y la dueña debe entender qué ventas cambian y qué acciones comerciales podría probar. Toda la inferencia y el entrenamiento ocurren en el servidor con Python y SQL Server, sin API de IA ni dependencia pesada de aprendizaje automático.

## Datos y límites

- Entrenar con renglones de facturas `Emitida` de los últimos 180 días, acotados a 30 000 renglones recientes. Excluir anulaciones, cantidades no positivas y productos ficticios de las sugerencias públicas.
- El modelo persistido contiene agregados por producto, cesta y día; nunca nombres, teléfonos ni identificadores de clientes.
- Cada invitado comparte la cuenta técnica `ClienteID=1`; por ello jamás se usa ese ID como perfil personal. Los invitados ven tendencias generales y promociones configuradas en Catálogo.
- Un cliente registrado puede obtener recomendaciones basadas en su propia compra; el procedimiento SQL valida su identidad desde `SESSION_CONTEXT`, sin aceptar un ID de cliente desde HTTP.
- Las recomendaciones son sugerencias. Descuentos y precios solo cambian por la edición existente del Catálogo hecha por personal autorizado.

## Comportamiento

1. Un administrador entra en Mercadotecnia y el sistema entrena si no hay modelo o tiene más de 24 horas. También puede actualizarlo a pedido. El entrenamiento toma datos de la base, calcula popularidad con decaimiento temporal y asociaciones entre productos comprados en la misma factura, y guarda un JSON pequeño en SQL Server.
2. La tienda pública lee ese JSON mediante un procedimiento de solo lectura y muestra hasta seis recomendaciones de productos activos. Para usuarios registrados combina el modelo con su historial propio; para invitados usa solo el modelo agregado. El catálogo y sus promociones siguen funcionando aunque el modelo todavía no exista.
3. Mercadotecnia muestra cobertura, fecha de entrenamiento, productos con más movimiento, cambios frente al periodo anterior, ventas por día y propuestas concretas con la evidencia que las motiva. Cuando los datos son insuficientes, muestra ese estado en lugar de inventar una tendencia.

## Fuera de alcance

- Aplicar descuentos automáticamente, enviar campañas a clientes o atribuir causalidad a cambios de ventas.
- Analizar información personal de visitantes anónimos o rastrearlos entre sesiones.
- Predecir rentabilidad sin costes de producto fiables.

## Decisiones de implementación

- Python estándar para el modelo; no se añaden dependencias.
- SQL Server guarda la instantánea para compartirla entre procesos de Azure App Service.
- Una migración idempotente crea tabla y procedimientos con permisos limitados por rol.
- La interfaz usa los estilos y componentes existentes, con CSS propio por página.
