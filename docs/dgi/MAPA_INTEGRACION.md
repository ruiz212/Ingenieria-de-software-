# Integración DGI en Brajher’s Cake

Inspección: 15/10/2026, Nicaragua. Rama de trabajo existente: `prueba-login`.
Hay modificaciones locales anteriores en POS, autenticación, monitor, CSS,
configuración, migraciones y documentos. Se conservan; no se publica ni se crea un commit.

## Sistema encontrado

Flask 3, Jinja, JavaScript, Flask-Login/WTF y SQL Server mediante pyodbc.
`app/db.py` concentra conexiones. No hay ORM. La conexión configurada es Azure SQL;
la consulta de metadatos fue posible (53 tablas). Se verificará con una base local
independiente, sin migrar Azure. Una instalación representa una empresa y serie FAC.

| Fuente / integración | Archivos y datos reales | Decisión |
|---|---|---|
| Emisor | `ConfiguracionSistema`, `fiscal_service.configuration`, `routes_fiscal.py` | Reutilizar razón social, RUC y régimen; añadir obligación, responsable y vigencia para la preparación interna |
| Ventas | `Facturas`, `DetalleFacturas`, `DocumentoJSON`, `app/pos/routes.py` | Consultar emisión/anulación, base, IVA registrado, total y detalle, sin modificar originales |
| Compras | `ComprasMateriaPrima`, `Proveedores`, `routes_inventory.py` | Consolidar costo e IVA documentado; son líneas de materia prima, no un libro fiscal certificado |
| Contabilidad | `AsientosDiario`, `DetalleAsientos`, `CatalogoCuentas`, `contabilidad_service.py` | Comparar base comercial con Haber−Debe de clase Ingreso; incluir originales anulados y contrapartidas para conservar efecto neto |
| Permisos | `models.User`, `roles_required`, CSRF global | Admin/SuperAdmin preparan y revisan; SuperAdmin aprueba, exporta y cierra |
| Auditoría | `BitacoraFiscal`, `fiscal_service.audit` | Reutilizar bitácora append-only; registrar IDs, estados y hashes, sin copiar el perfil sensible al log |
| Interfaz | `admin_bp`, `admin_base.html`, `admin/sidebar.html` | Agregar `/admin/dgi` y enlaces al control fiscal existente |
| Evolución | `scripts/migrate_fiscal.py`, contabilidad V2 | Nueva migración aditiva independiente; reversión solo si las tablas nuevas están vacías |

## Brechas verificadas

No existe una obligación y plantilla vigente verificadas para 2026. No se calcularán
impuestos, créditos deducibles, multas ni retenciones nuevas. Proveedores no tiene RUC;
no se inventará. No hay notas de crédito/débito completas ni consolidación multiempresa.
La fecha comercial usa el valor guardado por el sistema, sin conversión retrospectiva;
los nuevos eventos DGI usan UTC y se muestran con hora de Nicaragua.

## Incrementos y criterios

1. Agregar períodos de preparación, revisiones versionadas, observaciones y exportaciones.
2. Adaptar fuentes mediante consultas consistentes, motor de reglas internas y SHA-256.
3. Integrar panel, perfil, diagnóstico, fuentes, revisión, aprobación e historial.
4. Exportar XLSX interno identificado como no oficial; bloquear exportación oficial.
5. Probar con SQL Server aislado y documentos sintéticos, incluyendo 120000−110000=10000.
6. Entregar manual, matriz normativa, trazabilidad, diagramas y estimación incremental.

El cierre DGI solo cierra la preparación interna; no cierra el período contable ni
significa que se presentó una declaración. Una fuente modificada invalida aprobación
y descarga; se debe generar una nueva versión y volver a revisar.
