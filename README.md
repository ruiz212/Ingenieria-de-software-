
## Descripción
Sistema de Punto de Venta (POS) y control de producción para la panadería. 
Diseñado utilizando SCRUM.

## Roles del Equipo
- **Product Owner:** (Dueño del Producto)
- **Scrum Master:** Anderson
- **Equipo de Desarrollo:** Erick, Rodrigo.

## Tecnologías
- Python (Flask)
- SQL Server
- HTML/CSS/JS (Vanilla)

La organización de estilos, convenciones de clases, sistema de movimiento y comandos de compilación se explican en [docs/CSS.md](docs/CSS.md). Después de editar una fuente CSS, ejecutar `python scripts/build_css.py`; validar la entrega con `python scripts/build_css.py --check`.

## Mercadotecnia local

La tienda pública (`/tienda`) y la vista de clientes muestran sugerencias de productos activos basadas en ventas emitidas y en el carrito actual. Solo los clientes registrados reciben sugerencias basadas en su propio historial; las visitas invitadas usan tendencias generales. La gerencia dispone de `/admin/mercadotecnia` para ver tendencias y acciones comerciales con su evidencia. El entrenamiento usa Python estándar en este servidor y guarda una instantánea compartida en SQL Server; no usa API de IA.

Antes de activar el análisis en una base existente, aplique `database/05_mercadotecnia.sql` con la migración de esquemas (`python scripts/migrate_esquemas_roles_sp.py --connection-env TEST_DB_CONNECTION_STRING` primero en QA). El modelo se entrena automáticamente al entrar al panel de gerencia si falta o tiene 24 horas, y también se puede actualizar con su botón. Hasta el primer entrenamiento, la tienda recomienda desde el catálogo activo. Los descuentos siguen bajo control del Catálogo.

## Documentación del Corte 4

La entrega revisada conserva ocho módulos y desarrolla los contenidos RUP
4.1 a 4.10 con correspondencia a los cortes anteriores.
Consulte [el documento corregido (DOCX)](Documentacion/Corte4/Proyecto%20Corte%204%20UNIDAD%20IV%20corregido%20-%20Brajhers%20Cake.docx),
[el documento corregido (PDF)](Documentacion/Corte4/Proyecto%20Corte%204%20UNIDAD%20IV%20corregido%20-%20Brajhers%20Cake.pdf)
y [la revisión del alcance y sus pruebas](Documentacion/Corte4/REVISION_ALCANCE.md).
Las versiones anteriores del Corte 4 se conservan como antecedentes.

## Instalación
1. Crear entorno virtual: `python -m venv venv`
2. Activar entorno virtual.
3. Instalar dependencias: `pip install -r requirements.txt`
4. Ejecutar: `python run.py`

## Revisión fiscal y técnica — octubre de 2026

Los cambios fiscales requieren ejecutar `scripts/migrate_fiscal.py` antes de iniciar
esta versión contra una base existente. No ejecutar `database/esquema.sql` sobre
datos reales: ese archivo reconstruye tablas.

En una base que aún no tenga la evolución contable V2, ejecute primero
`python scripts/migrate_contabilidad_v2.py` y después
`python scripts/migrate_fiscal.py --connection-env DB_CONNECTION_STRING`.
Ambas migraciones son aditivas y deben ejecutarse contra la misma conexión que usa
la aplicación (incluido `.env`).

Consulte [la revisión y el estado de activación](Documentacion/Revision_DGI/REVISION.md)
y [el manual de operación y despliegue](Documentacion/Revision_DGI/MANUAL.md).
La configuración inicial es **Pendiente**: las nuevas facturas se identifican como
comprobantes de prueba hasta completar la configuración tributaria correspondiente.

Defina `SECRET_KEY` persistente y `DB_CONNECTION_STRING` mediante variables del
entorno o `.env`. Para HTTPS configure `SESSION_COOKIE_SECURE=True`. El servidor
de desarrollo escucha en `127.0.0.1:5000`, con depuración desactivada por defecto.
En producción use el servidor WSGI de la plataforma. Nunca publique `.env`.

Pruebas unitarias: `python -m pytest tests/test_fiscal.py -q`.
Las pruebas SQL requieren `TEST_DB_CONNECTION_STRING` apuntando a una base
aislada cuyo nombre empiece por `PanaderiaQA_`; insertan datos ficticios y rechazan
otros nombres de base. Requieren el esquema existente y sus migraciones previas.
Instale `pytest` además de las dependencias de la aplicación.

## Gestión tributaria DGI — preparación académica

**Versión 1.1:** análisis interno con perfil pendiente, diagnósticos descargables,
validación por Admin y fechas comerciales consistentes entre ventas y asientos.
Consulte [la revisión funcional y sus 131 pruebas](docs/dgi/REVISION_FUNCIONAL.md).
En revisiones antiguas, use **Revalidar fuentes** para aplicar las nuevas reglas.

El menú **DGI / Gestión tributaria** (`/admin/dgi`) integra perfil, períodos,
consolidación de ventas/compras, conciliación contable, hallazgos, revisión,
aprobación interna, historial y XLSX no oficial. Reutiliza el sistema Flask/SQL
Server existente. No presenta declaraciones ni calcula obligaciones sin validar.

Después de las migraciones contables/fiscales previas, ejecute
`python scripts/migrate_dgi.py --connection-env TEST_DB_CONNECTION_STRING`
en una base de pruebas. Esta entrega no aplica la migración a Azure.
Consulte [el manual y la demostración](docs/dgi/MANUAL.md),
[el mapa de integración](docs/dgi/MAPA_INTEGRACION.md),
[la matriz normativa](docs/dgi/MATRIZ_NORMATIVA.md) y
[el informe de validación](docs/dgi/ENTREGA.md).
Dependencias de pruebas: `python -m pip install -r requirements-dev.txt`.

## Correcciones de la auditoría

Las correcciones de la auditoría del 17/10/2026, sus pruebas y las dos migraciones necesarias están documentadas en [el cierre de reparaciones](docs/REPARACIONES_AUDITORIA_2026-10-17.md). El entorno verificado utiliza Python 3.12 y `requirements.lock`; las pruebas requieren `requirements-dev.txt` y sólo admiten SQL con destino QA explícito.

## Distribución de Ramas y Estructuración de Versiones

> [!NOTE]

> **Para el Equipo de Desarrollo:** Este proyecto utiliza Git para el control de versiones alineado con nuestros Sprints (SCRUM). Sigan esta estructura estrictamente para evitar conflictos:
> 
> * **`main` (Producción):** Contiene únicamente versiones estables, probadas y listas para entregar a la panadería. **No hacer commits directos aquí.**
> * **`develop` (Integración):** Rama central de desarrollo. Todo código nuevo que se finalice en un Sprint debe integrarse aquí primero.
> * **`sprint-X-feature` (Desarrollo):** Para cada nueva tarea o épica (ej. `sprint-1-pos-async`), crea una rama con este formato a partir de `develop`. Al finalizar, envía un Pull Request hacia `develop`.
