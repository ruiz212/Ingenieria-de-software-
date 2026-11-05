# Arquitectura observada

Inspección estática del árbol de trabajo en `prueba-login`, 31-10-2026. No se ejecutó la aplicación, la suite ni una conexión a base de datos. Los documentos históricos se usan como contexto, no como prueba de estado productivo.

## Mapa comprobado

| Capa | Evidencia | Responsabilidad observada |
| --- | --- | --- |
| Entrada y composición | `run.py`, `app/__init__.py`, `app/extensions.py` | Factory Flask; registra login, CSRF, seguridad, sesiones y seis blueprints. |
| Web | `app/auth/`, `hub/`, `pos/`, `monitor/`, `admin/`, `kiosco/`; `templates/`, `static/` | Rutas HTTP, plantillas Jinja y JavaScript/CSS. `admin` usa prefijo `/admin`; `kiosco`, `/kiosco`. |
| Servicios | `app/services/` | Lógica de contabilidad, fiscal, DGI, RR. HH., mercadotecnia, validación, autenticación y alertas, entre otras. Sus límites exactos se revisan por tarea. |
| Acceso a datos | `app/db.py`, `app/models.py`, `app/qa_safety.py` | Conexión `pyodbc`, ejecución de SP, modelos de usuario/cliente y protección de conexiones QA. Hay SQL directo en rutas y servicios; la transición a SP no debe suponerse completa. |
| Persistencia definida | `database/01_esquemas_migracion.sql`, `03_stored_procedures.sql`, otros SQL; `database/README.md` | Scripts de SQL Server para `seguridad`, `crm`, `catalogo`, `ventas`, `produccion`, `rrhh`, `contabilidad` y `fiscal`. El esquema efectivamente instalado no se inspeccionó. |
| Pruebas | `pytest.ini`, `tests/test_*.py`, `tests/browser/*.mjs` | Pruebas Python y de navegador. No se ejecutaron en esta inspección; algunas pruebas SQL requieren QA aislada y pueden escribir datos. |
| Entrega | `Dockerfile`, `.github/workflows/main_brajherscake.yml`, `requirements.txt`, `requirements.lock` | Docker usa Python 3.12, Gunicorn y ODBC 18; workflow declara Python 3.14 y despliegue a Azure App Service. No se verificó entorno externo. |

Dependencias declaradas: Flask 3.1.3, Flask-Login, Flask-WTF, pyodbc, Pillow, qrcode, Twilio, requests, pyotp, NumPy, OpenCV, Gunicorn y WhiteNoise en `requirements.txt`; `package.json` declara Bootstrap. La interfaz usa HTML/CSS/JavaScript según `README.md` y archivos del árbol.

## Flujos e interfaces comprobados

- `auth`: `/login`, TOTP, registro e ingreso de cliente; `hub`: `/` y recursos públicos.
- `pos`: `/tienda`, `/pos`, `/api/factura`, cotizaciones y recomendaciones. `monitor`: `/monitor`, consulta de pedidos y actualización de estado.
- `admin`: dashboard, catálogo, inventario, producción, caja, RR. HH., contabilidad, fiscal, DGI, fidelización, mercadotecnia y usuarios. Ejemplos verificables: `/admin/dgi`, `/admin/contabilidad`, `/admin/mercadotecnia`.
- `kiosco`: marcaje y reconocimiento de asistencia bajo `/kiosco`.
- La ruta de factura, arqueos, contabilidad y DGI cruzan límites entre ventas, caja, inventario, asientos y/o fiscalidad. La dependencia exacta y transaccionalidad deben trazarse para cada cambio.

## Hechos, inferencias e incógnitas

**Hechos del árbol:** existen los módulos, rutas, dependencias y scripts citados. `app/db.py` contiene `get_db_connection` y `execute_sp`; el código conserva consultas SQL directas. El README declara SQL Server y hay scripts de ese motor. Git estaba limpio al comenzar esta inspección.

**Inferencia limitada:** estos módulos componen un POS y control de producción con áreas administrativas; su operación conjunta en producción no se deduce de la presencia de código. Los ocho esquemas son una definición en archivos, no una comprobación de la base desplegada.

**Desconocido:** versión y estado de la base operativa, permisos efectivos, activación de migraciones, cobertura real, configuración externa, despliegue actual, integraciones activas y correspondencia exacta entre `requirements.lock` y los entornos en ejecución. Los informes de `docs/` contienen hallazgos fechados que pueden haber cambiado; revalidar antes de convertirlos en tareas.

**Riesgos a verificar por tarea:** operaciones con dinero o nómina, cruces de estado entre POS/monitor/contabilidad/fiscal, SQL directo frente a roles/SP, efectos de pruebas SQL, datos personales en RR. HH. y autenticación, diferencia Python 3.12/3.14 entre rutas de entrega. Ninguno se afirma aquí como incidente actual.
