# Ingenieria-de-software- (Proyecto Panadería - Amada Calero Leiva)

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

## Documentación del Corte 4

La entrega revisada conserva ocho módulos y desarrolla los contenidos RUP
4.1 a 4.10 con correspondencia a los cortes anteriores.
Consulte [el documento corregido](Documentacion/Corte4/Proyecto%20Corte%204%20UNIDAD%20IV%20corregido%20-%20Brajhers%20Cake.docx)
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

## Distribución de Ramas y Estructuración de Versiones

> [!NOTE]

> **Para el Equipo de Desarrollo:** Este proyecto utiliza Git para el control de versiones alineado con nuestros Sprints (SCRUM). Sigan esta estructura estrictamente para evitar conflictos:
> 
> * **`main` (Producción):** Contiene únicamente versiones estables, probadas y listas para entregar a la panadería. **No hacer commits directos aquí.**
> * **`develop` (Integración):** Rama central de desarrollo. Todo código nuevo que se finalice en un Sprint debe integrarse aquí primero.
> * **`sprint-X-feature` (Desarrollo):** Para cada nueva tarea o épica (ej. `sprint-1-pos-async`), crea una rama con este formato a partir de `develop`. Al finalizar, envía un Pull Request hacia `develop`.
