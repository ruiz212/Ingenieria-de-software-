# Especificación Detallada de Requerimientos: Sistema Integral "Panadería Amada" (Versión 2.0)

A continuación se presenta la especificación detallada de los requerimientos funcionales y no funcionales para el sistema integral de Punto de Venta (POS), Producción, Inventario, Recursos Humanos, Asistencia Biométrica y Contabilidad Formal de la Panadería Amada Calero Leiva, desglosado a nivel granular de operaciones para garantizar una cobertura exhaustiva del desarrollo.

---

## 1. Requerimientos Funcionales (RF)

### 1.1 Módulo de Seguridad, Accesos y Auditoría
Este módulo controla el ingreso a la plataforma y audita las modificaciones, previniendo accesos indebidos y brindando trazabilidad completa a los administradores.

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF01 |
| **Nombre del Requerimiento:** | Autenticación de inicio de sesión (Login) |
| **Características:** | Seguridad y Accesos |
| **Descripción del requerimiento:** | El sistema deberá proveer un formulario de inicio de sesión que reciba nombre de usuario y contraseña, validando el hash criptográfico contra la base de datos para autenticar al usuario y crear la cookie de sesión. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF02 |
| **Nombre del Requerimiento:** | Validación de estado de cuenta de usuario |
| **Características:** | Seguridad y Accesos |
| **Descripción del requerimiento:** | El sistema deberá bloquear el intento de inicio de sesión y mostrar un mensaje de "Acceso Denegado" si la credencial pertenece a un usuario cuyo campo `Activo` sea igual a 0. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF03 |
| **Nombre del Requerimiento:** | Solicitud obligatoria de Token TOTP |
| **Características:** | Seguridad y Accesos |
| **Descripción del requerimiento:** | El sistema deberá interrumpir el flujo de login si la variable global `totp_obligatorio` está activada o si el usuario tiene `TOTPEnabled = 1`, forzando la redirección a una pantalla para el ingreso del código de 6 dígitos. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF04 |
| **Nombre del Requerimiento:** | Verificación criptográfica de TOTP |
| **Características:** | Seguridad y Accesos |
| **Descripción del requerimiento:** | El sistema deberá comparar el código de 6 dígitos ingresado por el usuario contra la clave secreta generada en `TOTPSecret` mediante el algoritmo HMAC-SHA1. Si es válido, emitirá el token final de sesión. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF05 |
| **Nombre del Requerimiento:** | Cierre seguro de sesión (Logout) |
| **Características:** | Seguridad y Accesos |
| **Descripción del requerimiento:** | El sistema deberá proveer un botón de cierre de sesión que destruya las variables de sesión del servidor y expire las cookies del navegador, redirigiendo inmediatamente a la pantalla de login. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF06 |
| **Nombre del Requerimiento:** | Creación de cuentas de empleado |
| **Características:** | Seguridad y Accesos |
| **Descripción del requerimiento:** | El sistema deberá permitir al Administrador crear cuentas de usuario en la tabla `Usuarios`, requiriendo un Nombre Completo, Username único, Contraseña y la selección de un `RolID`. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF07 |
| **Nombre del Requerimiento:** | Edición de credenciales de usuario |
| **Características:** | Seguridad y Accesos |
| **Descripción del requerimiento:** | El sistema deberá permitir al Administrador modificar el rol, el nombre o resetear la contraseña de un usuario existente, guardando un nuevo hash si el campo de contraseña fue alterado. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF08 |
| **Nombre del Requerimiento:** | Desactivación (Baja Lógica) de Usuarios |
| **Características:** | Seguridad y Accesos |
| **Descripción del requerimiento:** | El sistema deberá permitir suspender el acceso de un empleado cambiando el estado a `Activo = 0` en lugar de borrar su registro, para mantener la consistencia de facturas vinculadas a su ID. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF09 |
| **Nombre del Requerimiento:** | Restricción de acceso a rutas por Rol (RBAC) |
| **Características:** | Seguridad y Accesos |
| **Descripción del requerimiento:** | El sistema deberá evaluar antes de cada petición HTTP el rol del usuario. Si un cajero (Rol 3) intenta acceder por URL a `/admin`, el sistema deberá retornar un error 403 Forbidden. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF10 |
| **Nombre del Requerimiento:** | Registro de Inserciones en Auditoría |
| **Características:** | Auditoría |
| **Descripción del requerimiento:** | El sistema deberá capturar de fondo (background) el evento de creación de registros maestros (ej. Productos) y guardar en `AuditLog` el ID del autor, la fecha/hora y los datos insertados. |
| **Prioridad del requerimiento:** | Media |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF11 |
| **Nombre del Requerimiento:** | Registro de Modificaciones en Auditoría |
| **Características:** | Auditoría |
| **Descripción del requerimiento:** | El sistema deberá guardar en `AuditLog` la serialización JSON del estado de los datos "Antes" y "Después" de que un usuario modifique un registro crítico, como el precio de un producto. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF12 |
| **Nombre del Requerimiento:** | Visualización del historial de auditoría |
| **Características:** | Auditoría |
| **Descripción del requerimiento:** | El sistema deberá proveer un panel de solo lectura para el SuperAdmin donde pueda consultar con filtros de fecha los eventos guardados en `AuditLog`. |
| **Prioridad del requerimiento:** | Baja |

---

### 1.2 Módulo de CRM (Gestión de Clientes)
Módulo encargado de centralizar la base de datos de compradores, permitiendo otorgar niveles de fidelidad y capturar su contacto para cotizaciones web.

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF13 |
| **Nombre del Requerimiento:** | Registro de perfiles de clientes nuevos |
| **Características:** | CRM |
| **Descripción del requerimiento:** | El sistema deberá permitir desde la plataforma web o el POS registrar un cliente insertando su Nombre, Apellidos, Teléfono, Género y Fecha de Nacimiento en la tabla `Clientes`. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF14 |
| **Nombre del Requerimiento:** | Validación de unicidad de teléfono |
| **Características:** | CRM |
| **Descripción del requerimiento:** | El sistema deberá rechazar la creación o actualización de un cliente si el número de teléfono ingresado ya existe en otro registro, mostrando un mensaje de advertencia. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF15 |
| **Nombre del Requerimiento:** | Edición de expediente de cliente |
| **Características:** | CRM |
| **Descripción del requerimiento:** | El sistema deberá permitir al Administrador buscar a un cliente por su nombre o teléfono para actualizar sus datos de contacto o cambiar manualmente su nivel de confianza. |
| **Prioridad del requerimiento:** | Media |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF16 |
| **Nombre del Requerimiento:** | Carga de fotografía de perfil de cliente |
| **Características:** | CRM |
| **Descripción del requerimiento:** | El sistema deberá permitir la subida de un archivo de imagen en formato JPG/PNG para el cliente, almacenando la ruta física del archivo en el campo `RutaFotoPerfil`. |
| **Prioridad del requerimiento:** | Baja |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF17 |
| **Nombre del Requerimiento:** | Visualización de historial de compras por cliente |
| **Características:** | CRM |
| **Descripción del requerimiento:** | El sistema deberá mostrar en la vista de detalle del cliente un listado en tabla de todas las facturas y montos gastados vinculados a su `ClienteID`. |
| **Prioridad del requerimiento:** | Media |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF18 |
| **Nombre del Requerimiento:** | Uso de Cliente Genérico (Mostrador) |
| **Características:** | CRM |
| **Descripción del requerimiento:** | El sistema deberá cargar un cliente predeterminado marcado como "Invitado" al abrir el POS, para facturar de inmediato a las personas que no deseen dar sus datos. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF19 |
| **Nombre del Requerimiento:** | Creación de Niveles de Confianza (Fidelidad) |
| **Características:** | CRM |
| **Descripción del requerimiento:** | El sistema deberá permitir definir múltiples niveles de confianza (ej. Frecuente, VIP) indicando la cantidad de compras mínimas requeridas para alcanzarlo. |
| **Prioridad del requerimiento:** | Media |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF20 |
| **Nombre del Requerimiento:** | Incremento de contador de compras |
| **Características:** | CRM |
| **Descripción del requerimiento:** | El sistema deberá incrementar en +1 el campo `TotalCompras` de un cliente específico cada vez que se le registre un pago exitoso de factura en el POS. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF21 |
| **Nombre del Requerimiento:** | Auto-asignación de nivel por métrica |
| **Características:** | CRM |
| **Descripción del requerimiento:** | El sistema deberá comparar el total de compras del cliente contra la tabla `NivelesConfianza` y actualizar el `NivelConfianzaID` automáticamente si sobrepasa el umbral del siguiente escalón. |
| **Prioridad del requerimiento:** | Media |

---

### 1.3 Módulo de Catálogo de Productos
Módulo encargado de agrupar todos los bienes que se venderán al público, abarcando panes, repostería, ingredientes extra e impuestos aplicables.

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF22 |
| **Nombre del Requerimiento:** | Creación de Categorías de Producto |
| **Características:** | Catálogo |
| **Descripción del requerimiento:** | El sistema deberá permitir crear clasificaciones de inventario en la tabla `Categorias` definiendo el nombre (ej. Bebidas, Repostería) y su descripción. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF23 |
| **Nombre del Requerimiento:** | Inserción de Productos base |
| **Características:** | Catálogo |
| **Descripción del requerimiento:** | El sistema deberá proveer un formulario para insertar un nuevo artículo en la tabla `Productos`, exigiendo Nombre, Precio Base mayor a 0 y seleccionando una Categoría existente. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF24 |
| **Nombre del Requerimiento:** | Tipificación de Productos Ficticios |
| **Características:** | Catálogo |
| **Descripción del requerimiento:** | El sistema deberá incluir un check o variable booleana `EsFicticio` al crear un producto para marcar aquellos ítems que son plantillas para pasteles especiales (que no se descuentan directamente del inventario estándar). |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF25 |
| **Nombre del Requerimiento:** | Subida de imagen de Producto |
| **Características:** | Catálogo |
| **Descripción del requerimiento:** | El sistema deberá permitir adjuntar una imagen ilustrativa del producto que se guardará en la carpeta estática del servidor, enlazando la ruta en `ImagenUrl`. |
| **Prioridad del requerimiento:** | Media |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF26 |
| **Nombre del Requerimiento:** | Asignación de Porcentaje de Descuento |
| **Características:** | Catálogo |
| **Descripción del requerimiento:** | El sistema deberá permitir establecer un valor numérico en el campo `PorcentajeDescuento` de un producto para rebajar su precio dinámicamente en el POS sin modificar el precio base original. |
| **Prioridad del requerimiento:** | Media |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF27 |
| **Nombre del Requerimiento:** | Baja temporal de Productos |
| **Características:** | Catálogo |
| **Descripción del requerimiento:** | El sistema deberá permitir al Administrador cambiar el estado de un producto a `Activo = 0`, ocultándolo inmediatamente de la parrilla visual del POS sin borrar los datos transaccionales previos. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF28 |
| **Nombre del Requerimiento:** | Registro de Ingredientes Extra (Adicionales) |
| **Características:** | Catálogo - Extras |
| **Descripción del requerimiento:** | El sistema deberá permitir registrar ítems en la tabla `Ingredientes` definiendo su nombre (ej. Cajeta, Extra Fruta) y su precio fijo adicional para personalización de pedidos. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF29 |
| **Nombre del Requerimiento:** | Configuración de Unidades de Medida (UOM) |
| **Características:** | Catálogo - UOM |
| **Descripción del requerimiento:** | El sistema deberá permitir añadir y editar unidades de medida (Litro, Kilogramo, Unidad) con su respectiva abreviatura para asociarlas posteriormente al inventario. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF30 |
| **Nombre del Requerimiento:** | Edición de Parámetros Globales (Configuración) |
| **Características:** | Catálogo - Config |
| **Descripción del requerimiento:** | El sistema deberá permitir editar el JSON de valores de `ConfiguracionSistema`, como cambiar la tasa de IVA de 15% a 0% o modificar la Razón Social de los tickets. |
| **Prioridad del requerimiento:** | Alta |

---

### 1.4 Módulo POS, Caja y Arqueos Avanzados (V2)
Centro principal de facturación, gestión de pagos y control de fraude mediante aperturas de turnos, arqueos ciegos y operaciones multimoneda, integrando desglose de denominaciones.

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF31 |
| **Nombre del Requerimiento:** | Restricción de módulo POS sin turno activo |
| **Características:** | Caja y Turnos |
| **Descripción del requerimiento:** | El sistema deberá ocultar la cuadrícula de ventas si el cajero no ha iniciado una sesión en `TurnosCaja`. Deberá presentar un botón mandatorio para "Abrir Turno". |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF32 |
| **Nombre del Requerimiento:** | Registro de Apertura de Turno |
| **Características:** | Caja y Turnos |
| **Descripción del requerimiento:** | El sistema deberá insertar en `TurnosCaja` la fecha/hora actual y el ID del cajero al momento de apertura, declarando el turno en estado `Cerrado = 0`. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF33 |
| **Nombre del Requerimiento:** | Filtrado visual de productos por Categoría |
| **Características:** | POS UI |
| **Descripción del requerimiento:** | El sistema deberá proveer botones en el frontend POS para filtrar y renderizar únicamente los productos que pertenezcan a la Categoría seleccionada por el cajero. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF34 |
| **Nombre del Requerimiento:** | Búsqueda por texto en catálogo POS |
| **Características:** | POS UI |
| **Descripción del requerimiento:** | El sistema deberá incorporar una barra de búsqueda que filtre dinámicamente los productos en pantalla por coincidencias en su nombre, sin recargar la página web. |
| **Prioridad del requerimiento:** | Media |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF35 |
| **Nombre del Requerimiento:** | Inserción de productos al carrito |
| **Características:** | POS Operaciones |
| **Descripción del requerimiento:** | El sistema deberá permitir hacer clic sobre un producto de la parrilla y añadirlo instantáneamente a un panel lateral de "Carrito", estableciendo su cantidad base a 1. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF36 |
| **Nombre del Requerimiento:** | Incremento y decremento de cantidad |
| **Características:** | POS Operaciones |
| **Descripción del requerimiento:** | El sistema deberá proporcionar botones [+] y [-] en el carrito para modificar la cantidad del ítem, recalculando su precio parcial en tiempo real. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF37 |
| **Nombre del Requerimiento:** | Inclusión de ingredientes extra al ítem |
| **Características:** | POS Operaciones |
| **Descripción del requerimiento:** | El sistema deberá permitir abrir un modal de "Personalizar" para un producto del carrito y seleccionar uno o varios extras (ej. Cobertura de Fresa), sumando su costo al ítem padre. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF38 |
| **Nombre del Requerimiento:** | Remoción completa de un ítem del carrito |
| **Características:** | POS Operaciones |
| **Descripción del requerimiento:** | El sistema deberá poseer un botón de borrado total por línea en el carrito que extraiga el producto y recalcule la totalidad de la orden. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF39 |
| **Nombre del Requerimiento:** | Cálculo dinámico de Subtotal y Descuentos |
| **Características:** | POS Matemáticas |
| **Descripción del requerimiento:** | El sistema deberá iterar sobre el carrito en JavaScript para sumar precios unitarios * cantidades, restando los porcentajes de descuento pre-configurados para mostrar un Subtotal Neto en pantalla. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF40 |
| **Nombre del Requerimiento:** | Cálculo y reflejo de IVA global |
| **Características:** | POS Matemáticas |
| **Descripción del requerimiento:** | El sistema deberá extraer la tasa de IVA de la configuración global (ej. 15%) y aplicarla sobre el Subtotal, mostrando explícitamente el monto de impuesto antes del Total a Pagar. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF41 |
| **Nombre del Requerimiento:** | Asignación de Cliente a la venta |
| **Características:** | POS Operaciones |
| **Descripción del requerimiento:** | El sistema deberá proveer un buscador autocompletable para buscar clientes por nombre o teléfono, para asociar la factura final a su `ClienteID` en lugar de facturar como "Mostrador". |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF42 |
| **Nombre del Requerimiento:** | Generación de cabecera de Factura B2C |
| **Características:** | POS Base de Datos |
| **Descripción del requerimiento:** | El sistema deberá procesar el pago insertando un registro en la tabla `Facturas`, asignando un número de ticket, código de seguimiento, TurnoID y Cajero responsable. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF43 |
| **Nombre del Requerimiento:** | Generación de Detalle de Factura |
| **Características:** | POS Base de Datos |
| **Descripción del requerimiento:** | El sistema deberá recorrer cada ítem del carrito y crear un registro hijo en `DetalleFacturas`, bloqueando en la misma fila el precio unitario pactado para evitar desajustes futuros si el precio del producto cambia. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF44 |
| **Nombre del Requerimiento:** | Generación de Detalle de Ingredientes |
| **Características:** | POS Base de Datos |
| **Descripción del requerimiento:** | El sistema deberá, si un detalle de factura tiene extras seleccionados, registrar la asociación en la tabla `DetalleIngredientes` para auditoría y cocina. |
| **Prioridad del requerimiento:** | Media |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF45 |
| **Nombre del Requerimiento:** | Activación de Facturación con RUC (B2B) |
| **Características:** | POS Fiscal |
| **Descripción del requerimiento:** | El sistema deberá habilitar un toggle en la ventana de pago que, al ser activado (`IncluyeRUC=1`), expanda campos de texto adicionales para Empresa y RUC. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF46 |
| **Nombre del Requerimiento:** | Validación obligatoria de campos RUC |
| **Características:** | POS Fiscal |
| **Descripción del requerimiento:** | El sistema deberá denegar la transacción si la Factura B2B está marcada pero los campos de Razón Social o Número RUC están vacíos, insertando el registro final en `FacturasRUC`. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF47 |
| **Nombre del Requerimiento:** | Selección de Método de Pago: Efectivo Córdobas |
| **Características:** | POS Pagos |
| **Descripción del requerimiento:** | El sistema deberá registrar el pago como "Efectivo" si se selecciona C$, permitiendo ingresar el dinero recibido y calculando la devuelta o cambio para el cliente en pantalla. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF48 |
| **Nombre del Requerimiento:** | Selección de Método de Pago: Transferencia |
| **Características:** | POS Pagos |
| **Descripción del requerimiento:** | El sistema deberá exigir el nombre completo del emisor si el método es "Transferencia" y almacenar dicho registro en la tabla `Pagos` sin calcular vuelto físico. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF49 |
| **Nombre del Requerimiento:** | Selección de Método de Pago: USD Dólares |
| **Características:** | POS Pagos |
| **Descripción del requerimiento:** | El sistema deberá convertir el total a pagar de C$ a USD utilizando la tasa del día en la tabla `TipoCambio` para que el cajero sepa cuántos dólares debe cobrar de forma exacta. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF50 |
| **Nombre del Requerimiento:** | Registro de Tipo de Cambio Diario |
| **Características:** | POS y Arqueo |
| **Descripción del requerimiento:** | El sistema deberá poseer un panel para que el administrador agregue la tasa de compra y venta oficial del dólar en `TipoCambio` antes de iniciar la facturación del día. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF51 |
| **Nombre del Requerimiento:** | Cierre de Turno de Caja (Formulario ciego) |
| **Características:** | Arqueo |
| **Descripción del requerimiento:** | El sistema deberá requerir al cajero que declare manualmente (conteo ciego) el efectivo en córdobas, billetes de dólar y el monto de transferencias observados físicamente para cerrar la jornada. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF52 |
| **Nombre del Requerimiento:** | Generación de reporte de Arqueo (Cuadre) |
| **Características:** | Arqueo |
| **Descripción del requerimiento:** | El sistema deberá calcular el total de ventas teóricas (Efectivo y Bancos) asociadas al turno y restarlas del conteo ciego, almacenando un registro en `ArqueoCaja` detallando Faltantes o Sobrantes monetarios. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF52-A |
| **Nombre del Requerimiento:** | Desglose de Denominaciones en Arqueo (V2) |
| **Características:** | Arqueo |
| **Descripción del requerimiento:** | El sistema deberá permitir al cajero ingresar la cantidad exacta de billetes y monedas por denominación (ej. 5 billetes de C$500), calculando el monto total automáticamente en `ArqueoDetalleDenominacion`. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF52-B |
| **Nombre del Requerimiento:** | Auditoría de Arqueos Modificados (V2) |
| **Características:** | Arqueo |
| **Descripción del requerimiento:** | El sistema deberá registrar cualquier modificación post-cierre de un arqueo en la tabla `ArqueoAuditLog`, capturando quién, cuándo y por qué ajustó los montos del cierre ciego. |
| **Prioridad del requerimiento:** | Media |

---

### 1.5 Módulo de Encargos y Portal de Cotizaciones
Módulo enfocado en la interacción web con clientes externos, canalizando solicitudes comerciales (B2C) hasta convertirlas en facturas y órdenes de producción (taller).

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF53 |
| **Nombre del Requerimiento:** | Acceso a formulario web de encargos |
| **Características:** | Cotizaciones |
| **Descripción del requerimiento:** | El sistema deberá habilitar una URL pública donde cualquier visitante, usando una cookie o `SessionID`, pueda llenar un formulario para solicitar cotizaciones de repostería especial. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF54 |
| **Nombre del Requerimiento:** | Adjunto de imagen de referencia para cotización |
| **Características:** | Cotizaciones |
| **Descripción del requerimiento:** | El sistema deberá permitir al cliente cargar una fotografía inspiracional del diseño del pastel, almacenándola en servidor web vinculada al registro `Cotizaciones`. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF55 |
| **Nombre del Requerimiento:** | Establecimiento de fecha de entrega y texto |
| **Características:** | Cotizaciones |
| **Descripción del requerimiento:** | El sistema deberá requerir obligatoriamente en el formulario web la "Fecha Deseada", un teléfono para contactar, y un campo de texto con las "Especificaciones" del diseño. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF56 |
| **Nombre del Requerimiento:** | Panel Administrativo de Cotizaciones entrantes |
| **Características:** | Gestión de Encargos |
| **Descripción del requerimiento:** | El sistema deberá listar en una tabla privada todas las cotizaciones con estado "Pendiente" para que la gerencia evalúe la viabilidad de producirlas. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF57 |
| **Nombre del Requerimiento:** | Asignación de Precio o Rechazo de Cotización |
| **Características:** | Gestión de Encargos |
| **Descripción del requerimiento:** | El sistema deberá permitir al Administrador fijar un valor numérico (`PrecioCotizado`) y pasar el estado a "Cotizada", o bien cancelar la orden cambiando su estado a "Rechazada". |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF58 |
| **Nombre del Requerimiento:** | Vista de seguimiento para el cliente |
| **Características:** | Cotizaciones |
| **Descripción del requerimiento:** | El sistema deberá reflejar en tiempo real al cliente (en su portal de seguimiento) que su pedido ha sido "Cotizado", mostrándole el precio impuesto para que pase a pagar al local. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF59 |
| **Nombre del Requerimiento:** | Conversión de Cotización a Factura B2C |
| **Características:** | Gestión de Encargos |
| **Descripción del requerimiento:** | El sistema deberá permitir al cajero buscar la cotización, cobrar el monto (como una factura de POS estándar), marcándola automáticamente con un flag especial `EsEncargo = 1`. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF60 |
| **Nombre del Requerimiento:** | Creación de ficha técnica de Encargo (Taller) |
| **Características:** | Producción |
| **Descripción del requerimiento:** | Tras el pago del anticipo, el sistema deberá insertar una fila en `Encargos`, copiando la imagen, texto y fechas a una vista simplificada sin precios, destinada exclusivamente para los panaderos del taller. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF61 |
| **Nombre del Requerimiento:** | Monitor táctil de pedidos en cocina |
| **Características:** | Monitor UI |
| **Descripción del requerimiento:** | El sistema deberá mostrar tarjetas grandes y claras (estilo Kanban) con los encargos pagados del día ordenados por proximidad de fecha de entrega. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF62 |
| **Nombre del Requerimiento:** | Avance de estado de producción (Workflow) |
| **Características:** | Monitor UI |
| **Descripción del requerimiento:** | El sistema deberá permitir al pastelero tocar botones para mover el encargo secuencialmente entre estados: "Pendiente" -> "En Proceso" -> "Listo" -> "Entregado", afectando el portal público del cliente. |
| **Prioridad del requerimiento:** | Alta |

---

### 1.6 Módulo de Inventario (Materia Prima)
Lleva el control de existencias, adquisiciones y configuración de proveedores de materias primas crudas.

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF63 |
| **Nombre del Requerimiento:** | Registro de Proveedores |
| **Características:** | Inventario |
| **Descripción del requerimiento:** | El sistema deberá permitir crear proveedores capturando su Razón Social y Teléfono en la tabla `Proveedores`, para asociar responsabilidades en facturas de compra posteriores. |
| **Prioridad del requerimiento:** | Media |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF64 |
| **Nombre del Requerimiento:** | Mantenimiento del catálogo de Materia Prima |
| **Características:** | Inventario |
| **Descripción del requerimiento:** | El sistema deberá permitir dar de alta ingredientes crudos especificando el nombre (ej. Harina de Trigo), su Unidad de Medida (ej. Quintal/Kg) y el valor de "Stock Mínimo" para emitir alertas futuras. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF65 |
| **Nombre del Requerimiento:** | Procesamiento de Facturas de Compra (Ingresos) |
| **Características:** | Inventario |
| **Descripción del requerimiento:** | El sistema deberá poseer un módulo para ingresar mercancía, solicitando seleccionar al Proveedor, la Materia Prima recibida, la Cantidad Comprada y el Costo Total de la factura. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF66 |
| **Nombre del Requerimiento:** | Acumulación automática de Stock físico |
| **Características:** | Inventario |
| **Descripción del requerimiento:** | El sistema deberá, dentro de una transacción SQL, sumar el valor de "Cantidad Comprada" al `StockActual` del registro pertinente en la tabla `MateriaPrima` al momento de confirmar el ingreso de almacén. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF67 |
| **Nombre del Requerimiento:** | Alertas visuales por desabastecimiento |
| **Características:** | Inventario |
| **Descripción del requerimiento:** | El sistema deberá cambiar a color rojo los indicadores de inventario en el dashboard administrativo si el `StockActual` de una materia prima es menor o igual a su límite inferior de `StockMinimo`. |
| **Prioridad del requerimiento:** | Media |

---

### 1.7 Módulo de Producción y Mermas
Control de descargas automatizadas mediante formulación de recetas y la contabilización del desperdicio (costo hundido).

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF68 |
| **Nombre del Requerimiento:** | Construcción de plantillas de Recetas (BOM) |
| **Características:** | Producción |
| **Descripción del requerimiento:** | El sistema deberá permitir vincular 1 Producto Terminado con "N" Materias Primas mediante el formulario "Crear Receta", registrando explícitamente en la tabla `RecetaProducto` la cantidad estándar en gramos/litros que se consume por unidad. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF69 |
| **Nombre del Requerimiento:** | Edición y re-estructuración de Recetas |
| **Características:** | Producción |
| **Descripción del requerimiento:** | El sistema deberá permitir al Administrador borrar o añadir ingredientes a la composición de una receta existente para reajustar los perfiles de descargo automático si los procesos de cocina varían. |
| **Prioridad del requerimiento:** | Media |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF70 |
| **Nombre del Requerimiento:** | Declaración operativa de Lote Producido |
| **Características:** | Producción |
| **Descripción del requerimiento:** | El sistema deberá proveer un formulario para que el operario declare el fin de un horneado, solicitando elegir el Producto cocinado y la "Cantidad Producida" en unidades físicas reales. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF71 |
| **Nombre del Requerimiento:** | Inserción de Consumo de Lotes por trazabilidad |
| **Características:** | Producción |
| **Descripción del requerimiento:** | El sistema deberá leer la receta vinculada al lote horneado e insertar en la tabla `ConsumoLote` la multiplicación matemática (Cantidad Producida * Cantidad de Receta) para guardar qué cantidad teórica exacta se gastó de cada ingrediente. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF72 |
| **Nombre del Requerimiento:** | Descuento dinámico e irreversible de Stock (Descargo) |
| **Características:** | Producción |
| **Descripción del requerimiento:** | El sistema deberá ejecutar una resta directa contra el campo `StockActual` de las materias primas procesadas en la declaración de lote anterior, automatizando el control de existencias sin intervención manual del bodeguero. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF73 |
| **Nombre del Requerimiento:** | Registro estructurado de mermas y desperdicios |
| **Características:** | Control de Calidad |
| **Descripción del requerimiento:** | El sistema deberá requerir al operario un formulario para reportar pan dañado. Exigirá elegir el producto, cantidad de unidades perdidas y el Operario Responsable, almacenando la reducción de inventario temporal del POS. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF74 |
| **Nombre del Requerimiento:** | Tipificación restrictiva de motivos de baja |
| **Características:** | Control de Calidad |
| **Descripción del requerimiento:** | El sistema deberá obligar al usuario a seleccionar el motivo de la merma mediante una lista desplegable estática ('Pan Frio', 'Defectuoso', 'Merma Horneado', 'Vencido', 'Otro') para estandarizar las causas de pérdida. |
| **Prioridad del requerimiento:** | Media |

---

### 1.8 Módulo de Contabilidad Privada
Un submódulo administrativo para el control de los flujos de dinero no vinculados directamente a la facturación de productos.

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF75 |
| **Nombre del Requerimiento:** | Inserción de Egresos Operativos Fijos |
| **Características:** | Contabilidad |
| **Descripción del requerimiento:** | El sistema deberá permitir al Administrador registrar pagos a servicios básicos o de mantenimiento en el panel de `EgresosPrivados`, forzando el registro de Fecha, Concepto descriptivo y Monto gastado. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF76 |
| **Nombre del Requerimiento:** | Emisión de Adelantos de Salario (Vales) |
| **Características:** | Contabilidad |
| **Descripción del requerimiento:** | El sistema deberá registrar salidas de caja etiquetadas como Vales prestados a un empleado específico (`EmpleadoID`), estableciendo por defecto el booleano `Descontado = 0`. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF77 |
| **Nombre del Requerimiento:** | Actualización de estado de liquidación de vales |
| **Características:** | Contabilidad |
| **Descripción del requerimiento:** | El sistema deberá permitir (mediante el generador de Nómina) cambiar dinámicamente el estado del vale prestado a `Descontado = 1` para no volver a deducirlo en quincenas futuras. |
| **Prioridad del requerimiento:** | Alta |

---

### 1.9 Módulo de Recursos Humanos y Nómina (Ley Nicaragua)
Módulo adaptado a las regulaciones formales, cálculos de impuestos progresivos y retenciones patronales.

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF78 |
| **Nombre del Requerimiento:** | Registro integral de expediente laboral (Ley 185) |
| **Características:** | RRHH - Contratación |
| **Descripción del requerimiento:** | El sistema deberá crear la ficha del empleado capturando campos legalmente exigidos: Cédula, Número INSS, Salario Base estipulado, Tipo de Contrato (Indefinido, Fijo) y Tipo de Jornada, en la tabla `Empleados`. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF79 |
| **Nombre del Requerimiento:** | Registro de Aprobación de Datos (Ley 787) |
| **Características:** | RRHH - Legal |
| **Descripción del requerimiento:** | El sistema deberá forzar al área de RRHH a marcar una casilla de `ConsentimientoDatos` garantizando que el trabajador ha firmado el papel físico de retención de datos personales (Cumplimiento de Privacidad). |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF80 |
| **Nombre del Requerimiento:** | Control de Incidentes y Siniestros Ocupacionales |
| **Características:** | RRHH - Ley 618 |
| **Descripción del requerimiento:** | El sistema deberá habilitar una pantalla para el reporte de incidentes en planta, capturando Tipo, Gravedad, Descripción de hechos, y un check de confirmación de "Notificación realizada al MITRAB". |
| **Prioridad del requerimiento:** | Media |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF81 |
| **Nombre del Requerimiento:** | Inserción de órdenes de embargo / Pensión (Ley 870) |
| **Características:** | RRHH - Legal |
| **Descripción del requerimiento:** | El sistema deberá permitir dar de alta obligaciones judiciales atadas al salario del empleado. Solicitará ingresar el % del sueldo o el monto fijo, Beneficiario, y rango de fechas de aplicación para retención obligatoria en nómina. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF82 |
| **Nombre del Requerimiento:** | Generación de Cabecera de Nómina |
| **Características:** | RRHH - Planillas |
| **Descripción del requerimiento:** | El sistema deberá, mediante la pantalla de generación, crear una transacción madre en la tabla `Nomina` estipulando el periodo quincenal/mensual, iterando sobre los empleados `Activos`. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF83 |
| **Nombre del Requerimiento:** | Deducción porcentual de INSS Laboral |
| **Características:** | RRHH - Cálculos |
| **Descripción del requerimiento:** | El sistema deberá multiplicar el "Salario Bruto + Extras" por la variable global `inss_laboral` (ej. 7%) y descontar matemáticamente el monto resultante durante la generación de la planilla para cada empleado. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF84 |
| **Nombre del Requerimiento:** | Deducción estructurada por Impuesto sobre la Renta |
| **Características:** | RRHH - Cálculos |
| **Descripción del requerimiento:** | El sistema deberá proyectar el ingreso neto anual y buscar en qué rango del JSON global `ir_tabla` (Art 23. Ley 822) calza el empleado. Deberá calcular el (Sobre-exceso * % Tasa) + Impuesto Base y descontar la fracción equivalente de la nómina mensual. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF85 |
| **Nombre del Requerimiento:** | Deducción acumulada de Vales y Pensiones en cascada |
| **Características:** | RRHH - Cálculos |
| **Descripción del requerimiento:** | El sistema deberá ubicar y sumar la deuda en la tabla `ValesEmpleados` y los mandatos de `DeduccionesJudiciales` vigentes, restando finalmente ambos valores del Salario Neto, y generando las filas descriptivas en `DetalleNomina`. |
| **Prioridad del requerimiento:** | Alta |

---

### 1.10 Módulo de Asistencia y Kiosco Facial (NUEVO)
Módulo diseñado para el registro automatizado de entradas y salidas de los empleados empleando hardware táctil y biometría.

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF86 |
| **Nombre del Requerimiento:** | Creación de Turnos Laborales |
| **Características:** | Kiosco - Configuración |
| **Descripción del requerimiento:** | El sistema deberá permitir a RRHH configurar turnos en `TurnosLaborales` definiendo la "Hora de Entrada" oficial y los "Minutos de Tolerancia" permitidos antes de marcar una llegada tardía. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF87 |
| **Nombre del Requerimiento:** | Captura y Encodificación de Rostro Biométrico |
| **Características:** | Kiosco - Biometría |
| **Descripción del requerimiento:** | El sistema deberá extraer y vectorizar los rasgos faciales de la foto de perfil del empleado, guardando el modelo matemático (descriptor) en formato JSON en el campo `FaceDescriptor` de la tabla `Empleados`. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF88 |
| **Nombre del Requerimiento:** | Reconocimiento Facial en Tiempo Real (Kiosco) |
| **Características:** | Kiosco - Biometría |
| **Descripción del requerimiento:** | El sistema deberá procesar frames de cámara web del kiosco (`/api/kiosco/reconocer`), comparando la imagen recibida contra los `FaceDescriptor` cacheados para identificar al empleado con una tolerancia de distancia pre-configurada (ej. 0.45). |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF89 |
| **Nombre del Requerimiento:** | Registro Automático de Entrada y Tardanza |
| **Características:** | Kiosco - Marcaje |
| **Descripción del requerimiento:** | Al reconocer un rostro sin registros de hoy en `Asistencia`, el sistema insertará la Hora de Entrada, y la catalogará como "A Tiempo" o "Llegada Tardía" dependiendo de los límites del `TurnoID` activo. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF90 |
| **Nombre del Requerimiento:** | Registro Automático de Salida |
| **Características:** | Kiosco - Marcaje |
| **Descripción del requerimiento:** | Si el kiosco reconoce a un empleado que ya posee Hora de Entrada pero no de Salida en la tabla `Asistencia` durante el día actual, el sistema actualizará el registro insertando la `HoraSalida`. |
| **Prioridad del requerimiento:** | Alta |

---

### 1.11 Módulo de Contabilidad Formal (Libro Diario) (NUEVO)
Módulo para el control de la partida doble corporativa y registro estructurado del libro mayor contable.

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF91 |
| **Nombre del Requerimiento:** | Estructuración del Catálogo de Cuentas |
| **Características:** | Contabilidad Formal |
| **Descripción del requerimiento:** | El sistema deberá permitir la creación de cuentas contables jerárquicas (Activos, Pasivos, Capital, Ingresos, Egresos) asignando un número de cuenta estructurado en la tabla `CatalogoCuentas`. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF92 |
| **Nombre del Requerimiento:** | Apertura y Cierre de Periodos Contables |
| **Características:** | Contabilidad Formal |
| **Descripción del requerimiento:** | El sistema deberá requerir al contador la creación mensual de un registro en `PeriodosContables` (Ej: 'Enero 2026'), impidiendo asentar partidas en periodos cerrados. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF93 |
| **Nombre del Requerimiento:** | Creación Manual de Asientos de Diario |
| **Características:** | Contabilidad Formal |
| **Descripción del requerimiento:** | El sistema deberá proveer un formulario para insertar Partidas Dobles (`AsientosDiario` y `DetalleAsientos`), validando obligatoriamente que la suma de movimientos al "Debe" sea exactamente igual a la suma de movimientos al "Haber". |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RF94 |
| **Nombre del Requerimiento:** | Integración Automática POS-Contabilidad |
| **Características:** | Contabilidad Formal |
| **Descripción del requerimiento:** | El sistema deberá ser capaz de generar automáticamente un Asiento de Diario aglomerado que refleje los ingresos generados durante un Cierre de Turno en el POS, debitando caja y acreditando la cuenta de ingresos por ventas. |
| **Prioridad del requerimiento:** | Media |


---

## 2. Requerimientos No Funcionales (RNF)
Conjunto ampliado de restricciones técnicas de software para la operatividad continua.

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF01 |
| **Nombre del Requerimiento:** | Tiempo de latencia sub-segundo en POS |
| **Características:** | Rendimiento (Performance) |
| **Descripción del requerimiento:** | El sistema deberá renderizar la interfaz de caja y agregar elementos al carrito del POS en un tiempo menor a 0.5 segundos empleando renderizado del lado del cliente (Vanilla JS) sin incurrir en peticiones completas de recarga (Full Page Reload) para evitar retrasos en facturación. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF02 |
| **Nombre del Requerimiento:** | Cifrado unidireccional irrecuperable (Hashing) |
| **Características:** | Seguridad y Privacidad |
| **Descripción del requerimiento:** | La aplicación no deberá utilizar algoritmos deprecados como MD5. Debe emplearse obligatoriamente `werkzeug.security.generate_password_hash` con esquemas (PBKDF2/SHA256) garantizando que un administrador jamás logre descifrar la clave original de un empleado. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF03 |
| **Nombre del Requerimiento:** | Áreas de golpe (Hitboxes) Optimizadas para Kioscos Táctiles |
| **Características:** | Usabilidad e Interfaz |
| **Descripción del requerimiento:** | Las pantallas de Monitor de Cocina y POS deberán tener botones de acción, incrementadores de carrito y teclados con un radio mínimo de 48x48 píxeles. Esto asegura pulsaciones correctas en hardware POS Touch sin dependencia estricta del cursor. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF04 |
| **Nombre del Requerimiento:** | Arquitectura Responsiva orientada a Mobile-First (Portal) |
| **Características:** | Portabilidad Web |
| **Descripción del requerimiento:** | Las páginas orientadas al cliente (Login de visitantes, Seguimiento de Cotizaciones) deberán construirse usando CSS Grid y Flexbox en lugar de píxeles absolutos, ajustándose perféctamente a ventanas minimizadas de 320px de ancho y tablets (768px). |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF05 |
| **Nombre del Requerimiento:** | Blindaje Atómico con Transacciones (ACID) en SQL |
| **Características:** | Confiabilidad de Datos |
| **Descripción del requerimiento:** | Operaciones encadenadas como el Cierre de Turno o Producción de Lotes no deberán ejecutarse como secuencias aisladas `cursor.execute()`. Deben agruparse bajo bloque Transaccional. Si hay un `Exception` en la línea 3 del proceso, la base de datos debe lanzar `Rollback` íntegro. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF06 |
| **Nombre del Requerimiento:** | Segregación Lógica con Blueprints de Flask |
| **Características:** | Arquitectura (Mantenibilidad) |
| **Descripción del requerimiento:** | El desarrollo del backend Python deberá abstenerse de almacenar todas las rutas en un solo archivo `app.py`. Debe emplearse la arquitectura Flask Blueprints para encapsular modularmente `/pos`, `/hr`, `/admin`, facilitando la colaboración multi-desarrollador. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF07 |
| **Nombre del Requerimiento:** | Implementación de Índices Pre-Calculados de SQL Server |
| **Características:** | Escalabilidad de Motor |
| **Descripción del requerimiento:** | El script maestro de la base de datos deberá poseer la creación explícita de `CREATE INDEX` en columnas extranjeras como `Facturas(UsuarioID)` y `DetalleFacturas(FacturaID)`. Previniendo tiempos excesivos (Timeout) de reporte al acumular cientos de miles de registros históricos. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF08 |
| **Nombre del Requerimiento:** | Defensa activa contra inyección de código SQL/XSS |
| **Características:** | Seguridad Preventiva |
| **Descripción del requerimiento:** | Todos los campos de entrada, en especial el textarea de "Especificaciones de Pastel" en la web y los formularios de búsqueda, deberán parametrizar sus consultas (`WHERE username = ?`) o escaparse en las plantillas Jinja2 (`{{ valor | e }}`) para neutralizar ataques XSS o SQL Injection. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF09 |
| **Nombre del Requerimiento:** | Tratamiento dinámico e inmutable de Soft-Deletes |
| **Características:** | Arquitectura de Registros |
| **Descripción del requerimiento:** | El sistema prohibirá estrictamente la instrucción `DELETE FROM` en tablas transaccionales maestras (`Productos`, `Empleados`, `Usuarios`). Se deberá implementar obligatoriamente el uso de flags (banderas) booleanas como `Activo=0` para ocultar información, preservando la integridad histórica-financiera (Auditoría Ciega). |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF10 |
| **Nombre del Requerimiento:** | Tolerancia a Fallas en Envíos de Correo/Cotizaciones |
| **Características:** | Resiliencia |
| **Descripción del requerimiento:** | El envío de alertas o la inserción de cotizaciones masivas web no deberán bloquear la carga asíncrona del cliente. En caso de timeout de base de datos o fallo del servicio SMTP, el servidor deberá loguear el fallo limpiamente mediante un decorador `try-except`, devolviendo una respuesta controlada y unificada de error al navegador en formato JSON 500. |
| **Prioridad del requerimiento:** | Media |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF11 |
| **Nombre del Requerimiento:** | Procesamiento Biométrico Optimizado en Memoria (NUEVO) |
| **Características:** | Rendimiento (Performance) |
| **Descripción del requerimiento:** | El cálculo de distancias para el reconocimiento facial en el kiosco no deberá golpear la base de datos por cada frame de video recibido. Los `FaceDescriptors` deben almacenarse en un caché en RAM (`face_service`) para agilizar las respuestas biométricas a menos de 100ms. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF12 |
| **Nombre del Requerimiento:** | Consistencia Estricta de Partida Doble (NUEVO) |
| **Características:** | Confiabilidad Contable |
| **Descripción del requerimiento:** | El backend deberá bloquear a nivel lógico la confirmación de cualquier Asiento de Diario si la sumatoria global de los movimientos "Debe" y "Haber" tiene una diferencia absoluta mayor a `0.00`, garantizando así la balanza de comprobación cuadrada por diseño. |
| **Prioridad del requerimiento:** | Alta |
