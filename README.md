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

## Instalación
1. Crear entorno virtual: `python -m venv venv`
2. Activar entorno virtual.
3. Instalar dependencias: `pip install -r requirements.txt`
4. Ejecutar: `python app.py`

## Distribución de Ramas y Estructuración de Versiones

> [!WARNING]
> **Para el Equipo de Desarrollo:** Este proyecto utiliza Git para el control de versiones alineado con nuestros Sprints (SCRUM). Sigan esta estructura estrictamente para evitar conflictos:
> 
> * **`main` (Producción):** Contiene únicamente versiones estables, probadas y listas para entregar a la panadería. **No hacer commits directos aquí.**
> * **`develop` (Integración):** Rama central de desarrollo. Todo código nuevo que se finalice en un Sprint debe integrarse aquí primero.
> * **`sprint-X-feature` (Desarrollo):** Para cada nueva tarea o épica (ej. `sprint-1-pos-async`), crea una rama con este formato a partir de `develop`. Al finalizar, envía un Pull Request hacia `develop`.
