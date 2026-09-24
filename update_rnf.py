import os

md_path = r"C:\Users\miure\.gemini\antigravity-ide\brain\8b21a557-f969-4b90-9029-c5d149a901d1\Requerimientos_Panaderia_Amada.md"

new_rnf = """
## 2. Requerimientos No Funcionales (RNF)
Conjunto ampliado y exhaustivo de restricciones técnicas, rendimiento, arquitectura y usabilidad del software para garantizar su fiabilidad a largo plazo.

### 2.1 Seguridad y Control de Acceso

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF01 |
| **Nombre del Requerimiento:** | Hashing criptográfico estándar de la industria |
| **Características:** | Seguridad |
| **Descripción del requerimiento:** | El sistema deberá almacenar todas las contraseñas utilizando el algoritmo `PBKDF2:HMAC:SHA256` provisto por Werkzeug Security. Queda estrictamente prohibido el uso de MD5 o almacenamiento en texto plano. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF02 |
| **Nombre del Requerimiento:** | Cierre por inactividad de sesión (Time-Out) |
| **Características:** | Seguridad |
| **Descripción del requerimiento:** | El sistema deberá expirar automáticamente la sesión de un usuario y requerir nuevas credenciales tras 30 minutos consecutivos sin registrar actividad HTTP, previniendo el secuestro de sesiones en terminales desatendidas. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF03 |
| **Nombre del Requerimiento:** | Prevención de ataques de inyección SQL (SQLi) |
| **Características:** | Seguridad |
| **Descripción del requerimiento:** | El backend deberá ejecutar toda consulta a la base de datos haciendo uso estricto de parámetros de enlace segura (Ej. `WHERE username = ?`). No se concatenarán variables de usuario directamente en los strings SQL. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF04 |
| **Nombre del Requerimiento:** | Protección contra Cross-Site Scripting (XSS) |
| **Características:** | Seguridad |
| **Descripción del requerimiento:** | El sistema deberá delegar el renderizado de HTML al motor Jinja2 con la directiva `autoescape` activada por defecto, sanitizando toda entrada proveniente de los formularios (ej. especificaciones de encargo). |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF05 |
| **Nombre del Requerimiento:** | Encapsulamiento de credenciales de servidor |
| **Características:** | Seguridad |
| **Descripción del requerimiento:** | El sistema deberá cargar la cadena de conexión a SQL Server y la clave secreta de Flask exclusivamente a través del archivo de variables de entorno `.env`. No deberán existir claves hardcodeadas en el código fuente. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF06 |
| **Nombre del Requerimiento:** | Manejo seguro de excepciones 500 genéricas |
| **Características:** | Seguridad |
| **Descripción del requerimiento:** | En producción, el sistema no deberá mostrar volcados de pila (Stack Traces) ni estructuras de las tablas de SQL en pantalla si ocurre un error. Retornará una pantalla amigable de "Error 500", enviando los detalles solo a los logs del servidor. |
| **Prioridad del requerimiento:** | Alta |

### 2.2 Eficiencia y Rendimiento (Performance)

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF07 |
| **Nombre del Requerimiento:** | Latencia sub-segundo en interacciones del POS |
| **Características:** | Rendimiento |
| **Descripción del requerimiento:** | El sistema deberá resolver el cálculo de subtotales, lectura de códigos y adición al carrito del cajero en menos de 0.5 segundos empleando renderizado local asíncrono para agilizar la fila de clientes. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF08 |
| **Nombre del Requerimiento:** | Tiempo de carga inicial del portal web (TTFB) |
| **Características:** | Rendimiento |
| **Descripción del requerimiento:** | La pantalla de bienvenida de clientes y la tienda en línea deberán estar listas para interactuar (Time To Interactive) en un máximo de 2 segundos en conexiones de banda ancha residencial estándar. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF09 |
| **Nombre del Requerimiento:** | Límite de carga de imágenes (Payload) |
| **Características:** | Rendimiento |
| **Descripción del requerimiento:** | El sistema deberá rechazar a nivel del servidor web cualquier archivo multimedia (imágenes de referencia de pastel) que supere el tamaño máximo de carga (Max Content Length) de 2 Megabytes. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF10 |
| **Nombre del Requerimiento:** | Paginación restrictiva en consultas masivas |
| **Características:** | Rendimiento DB |
| **Descripción del requerimiento:** | El sistema deberá limitar la extracción de datos a 100 registros máximos por página al listar la tabla de `AuditLog`, el histórico de `Facturas` o la `Nomina`, evitando bloqueos de red o desbordamiento de RAM. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF11 |
| **Nombre del Requerimiento:** | Indexación preventiva contra Full Table Scans |
| **Características:** | Rendimiento DB |
| **Descripción del requerimiento:** | El esquema de SQL Server deberá aplicar y mantener los 14 índices No-Clustered definidos en campos críticos (`FechaHora`, `TurnoID`, `Estado`) para asegurar velocidad en reportes analíticos a largo plazo. |
| **Prioridad del requerimiento:** | Alta |

### 2.3 Usabilidad y Experiencia de Usuario (UX)

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF12 |
| **Nombre del Requerimiento:** | Dimensiones mínimas de Hitboxes para Kioscos Táctiles |
| **Características:** | Usabilidad |
| **Descripción del requerimiento:** | El frontend del POS, Kiosco y Monitor deberán contar con áreas táctiles funcionales mínimas de 44x44 píxeles en todos los botones y teclados virtuales, para prevenir toques accidentales por el cajero. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF13 |
| **Nombre del Requerimiento:** | Contrastes accesibles según norma WCAG |
| **Características:** | Usabilidad |
| **Descripción del requerimiento:** | La aplicación deberá garantizar un contraste mínimo de color de 4.5:1 (Nivel AA) entre los textos principales de los botones y el fondo oscuro, asegurando legibilidad en pantallas industriales con brillo deficiente. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF14 |
| **Nombre del Requerimiento:** | Empleo de notificaciones emergentes (Toasts) |
| **Características:** | Usabilidad |
| **Descripción del requerimiento:** | El sistema deberá emplear notificaciones efímeras tipo `Flashes` o `Toasts` en una esquina de la pantalla para reportar éxitos (Ej. "Producto guardado") sin interrumpir el flujo visual del usuario con modales intrusivos de alerta bloqueantes. |
| **Prioridad del requerimiento:** | Media |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF15 |
| **Nombre del Requerimiento:** | Consistencia visual sin dependencias de terceros |
| **Características:** | Usabilidad e Interfaz |
| **Descripción del requerimiento:** | La interfaz deberá estar construida íntegramente con HTML y Vanilla CSS utilizando variables nativas (Custom Properties). El sistema debe evitar incrustar bibliotecas pesadas como Bootstrap o Tailwind para reducir los tiempos de carga en navegadores de hardware limitado. |
| **Prioridad del requerimiento:** | Media |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF16 |
| **Nombre del Requerimiento:** | Navegabilidad completa por teclado (Keybindings) |
| **Características:** | Usabilidad |
| **Descripción del requerimiento:** | El sistema deberá permitir al Administrador rellenar y enviar los formularios de creación de productos, clientes y compras de materia prima empleando exclusivamente las teclas `Tab` y `Enter`. |
| **Prioridad del requerimiento:** | Media |

### 2.4 Arquitectura, Mantenibilidad y Soporte

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF17 |
| **Nombre del Requerimiento:** | Segregación modular (Modelo-Vista-Controlador) |
| **Características:** | Arquitectura |
| **Descripción del requerimiento:** | El sistema deberá estructurarse rígidamente separando la lógica de conexión (`db.py`), la estructura de datos (`models.py`), los flujos de HTML (`/templates`) y la orquestación (`routes.py`). |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF18 |
| **Nombre del Requerimiento:** | Segmentación de end-points mediante Blueprints |
| **Características:** | Arquitectura |
| **Descripción del requerimiento:** | El desarrollo del framework Flask deberá registrar controladores fragmentados (`Blueprints`) para cada sub-módulo (Admin, POS, Monitor, Auth, Hub) impidiendo que exista un único archivo espagueti masivo de rutas en el proyecto. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF19 |
| **Nombre del Requerimiento:** | Parámetros dinámicos libres de código duro (Hardcoding) |
| **Características:** | Mantenibilidad |
| **Descripción del requerimiento:** | El código backend no deberá declarar valores absolutos de impuestos (Ej. `iva = 0.15`) en la lógica. Todas las variables financieras y operacionales deben leerse directamente de la tabla en base de datos `ConfiguracionSistema`. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF20 |
| **Nombre del Requerimiento:** | Adopción integral de Borrados Lógicos (Soft Deletes) |
| **Características:** | Arquitectura de Datos |
| **Descripción del requerimiento:** | Ningún script o método de la aplicación deberá tener instrucciones `DELETE FROM` para entidades como `Productos`, `Empleados` o `Usuarios`. El ocultamiento de la información se hará transicionando el estado booleano a `Activo = 0`. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF21 |
| **Nombre del Requerimiento:** | Generación automatizada de reportes en memoria RAM |
| **Características:** | Arquitectura |
| **Descripción del requerimiento:** | Los cálculos de dashboards analíticos (ventas diarias, sobrantes) deberán ser procesados y agregados temporalmente en el backend, absteniéndose de almacenar reportes consolidados temporales en disco físico para ahorrar ciclos de escritura. |
| **Prioridad del requerimiento:** | Media |

### 2.5 Confiabilidad y Tolerancia a Fallos (Reliability)

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF22 |
| **Nombre del Requerimiento:** | Transaccionalidad ACID para flujos financieros y de inventario |
| **Características:** | Confiabilidad |
| **Descripción del requerimiento:** | Operaciones encadenadas críticas (Ej. Pagar Factura = Insertar Cabecera + Insertar Múltiples Detalles + Restar Inventario de Productos) deberán estar encapsuladas en `Transactions`. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF23 |
| **Nombre del Requerimiento:** | Reversión de Cambios por Fallas (Rollbacks) |
| **Características:** | Confiabilidad |
| **Descripción del requerimiento:** | Si una transacción SQL encadenada detecta una excepción (timeout, variable indefinida), el sistema ejecutará de inmediato un `Rollback` que deshaga todo el avance parcial insertado, evitando desincronizaciones entre caja chica e inventario físico. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF24 |
| **Nombre del Requerimiento:** | Tolerancia ante caída de servicios asíncronos externos |
| **Características:** | Resiliencia |
| **Descripción del requerimiento:** | Procesos como envíos hipotéticos de correo electrónico de recibos o sincronizaciones externas en segundo plano, no deberán crashear o paralizar el hilo principal de renderizado HTTP. Fallarán silenciosamente en background si no hay conectividad a Internet. |
| **Prioridad del requerimiento:** | Media |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF25 |
| **Nombre del Requerimiento:** | Mantenimiento de integridad referencial rígida (Foreign Keys) |
| **Características:** | Integridad |
| **Descripción del requerimiento:** | La base de datos deberá restringir la creación de tablas huérfanas asegurando que el 100% de los `DetalleFacturas` posean una relación fuerte y validada a nivel motor (Constraints) hacia la tabla de `Productos`. |
| **Prioridad del requerimiento:** | Alta |

### 2.6 Portabilidad, Compatibilidad y Estandarización

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF26 |
| **Nombre del Requerimiento:** | Diseño Responsive Web Design Universal (Mobile First) |
| **Características:** | Portabilidad |
| **Descripción del requerimiento:** | Todo módulo orientado a cliente externo (Ej. Tienda web) deberá utilizar CSS Flexbox y Grid dinámicos que permitan una lectura perfecta y no horizontalmente desbordada en resoluciones desde los 320px de ancho (móviles verticales). |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF27 |
| **Nombre del Requerimiento:** | Renderizado estandarizado en múltiples navegadores |
| **Características:** | Portabilidad |
| **Descripción del requerimiento:** | Las interfaces visuales de POS y Admin no deberán usar propiedades web experimentales. Deben funcionar uniformemente en motores WebKit, Blink y Gecko (Chrome, Edge, Firefox, Safari recientes). |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF28 |
| **Nombre del Requerimiento:** | Virtualización y despliegue por contenedores |
| **Características:** | Portabilidad Server |
| **Descripción del requerimiento:** | El software deberá empacarse incluyendo sus dependencias en un entorno Docker (`Dockerfile` provisto), posibilitando levantar el aplicativo en Windows Server, Linux o macOS de manera determinista e idéntica. |
| **Prioridad del requerimiento:** | Media |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF29 |
| **Nombre del Requerimiento:** | Motor de Base de Datos Agnóstico pero Optimizado |
| **Características:** | Portabilidad Server |
| **Descripción del requerimiento:** | Aunque el código use pyodbc y asuma un backend MS SQL Server por defecto, la sintaxis de las consultas ANSI SQL insertadas en el controlador no usarán comandos propietarios oscuros que impidan en un futuro una migración a PostgreSQL. |
| **Prioridad del requerimiento:** | Baja |

### 2.7 Cumplimiento Legal, Fiscal y Normativo (Compliance)

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF30 |
| **Nombre del Requerimiento:** | Sujeción de cálculos de IR Progresivo a la Ley 822 de Nicaragua |
| **Características:** | Legal Tributario |
| **Descripción del requerimiento:** | El proceso batch de Nómina deberá ejecutar el cálculo del Impuesto sobre la Renta basado matemáticamente y de manera rígida en la estructura progresiva (Rangos de Sobrantes, Tasa %, e Impuesto Base) del Artículo 23, configurada en JSON. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF31 |
| **Nombre del Requerimiento:** | Ajuste automático de INSS al Código del Trabajo |
| **Características:** | Legal Laboral |
| **Descripción del requerimiento:** | El sistema deberá tomar el salario devengado integral e imponer las tasas de la seguridad social laboral estipuladas legalmente (actualizadas globalmente) antes del pago neto al personal, protegiendo a la empresa ante auditorías del MITRAB. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF32 |
| **Nombre del Requerimiento:** | Documentación de consentimiento explícito (Ley 787) |
| **Características:** | Protección de Datos |
| **Descripción del requerimiento:** | El formulario del expediente de Empleado deberá bloquear el guardado a menos que el usuario RRHH verifique explícitamente haber recopilado el permiso físico del uso de la información del individuo en cumplimiento a la Ley 787 de Protección de Datos Personales. |
| **Prioridad del requerimiento:** | Alta |

| Campo | Descripción |
| :--- | :--- |
| **Identificación del requerimiento:** | RNF33 |
| **Nombre del Requerimiento:** | Parametrización dinámica de feriados de Ley (Ley 185) |
| **Características:** | Legal Laboral |
| **Descripción del requerimiento:** | El sistema deberá incorporar una tabla aislada para registrar feriados inamovibles (Navidad, 1ero Mayo) y habilitar una gestión separada para compensación de asuetos móviles en el cálculo de la planilla por horas extra. |
| **Prioridad del requerimiento:** | Media |
"""

with open(md_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the RNF section
split_marker = "## 2. Requerimientos No Funcionales (RNF)"
if split_marker in content:
    rf_part = content.split(split_marker)[0]
    new_content = rf_part + new_rnf
    
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("RNF UPDATED")
else:
    print("MARKER NOT FOUND")
