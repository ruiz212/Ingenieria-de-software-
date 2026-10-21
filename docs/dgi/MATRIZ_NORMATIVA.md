# Matriz normativa y compatibilidad oficial

Verificación: 15/10/2026 (Nicaragua). Responsable pendiente: contador/propietario.
El producto implementado es preparación académica interna. No calcula obligaciones
tributarias ni asegura procedencia de créditos, tasas, deducciones o sanciones.

| Obligación / régimen | Período | Evidencia y resultado de la consulta | Estado de habilitación |
|---|---|---|---|
| Diagnóstico comercial y contable interno / perfil declarado | Mes elegido | Aritmética de documentos del propio sistema y conciliación base de ventas versus cuentas de ingresos | Habilitado; regla interna, sin fuerza normativa |
| DMI / régimen general | A partir de febrero 2024 en el aviso histórico | [Aviso DGI 030-02-2024](https://www.dgi.gob.ni/pdfNoticia/3201): el texto recuperado por búsqueda oficial se refiere a DMI-V2.1. El acceso directo devolvió rechazo. El contenido del aviso tiene fecha 01/02/2024, aunque el buscador muestra otra fecha de indexación | Antecedente histórico; NO acredita vigencia en 2026 |
| Plantilla asociada a DMI-V2.1 | Obligación y período exactos aún sin determinar | [Enlace de planilla](https://www.dgi.gob.ni/getDoc/1064): la herramienta de consulta no pudo interpretar el archivo application/octet-stream. No se descargó ni validó una plantilla; no hay SHA-256 original ni mapa de casillas aprobado | PENDIENTE DE VALIDACIÓN |
| Guía asociada a DMI-V2.1 | 2026 pendiente | [Guía](https://www.dgi.gob.ni/getDoc/1065): acceso directo rechazado. No se verificó un texto completo vigente para el período | PENDIENTE DE VALIDACIÓN |
| Procedimiento de planillas y declaración | Histórico | [FAQ declaraciones](https://www.dgi.gob.ni/FAQ/declaraciones_y_archivos_previ.htm) y [FAQ recaudo y anticipo](https://www.dgi.gob.ni/FAQ/declaracion_mensual_de_recaudo.htm): resultados oficiales históricos recuperados por búsqueda; el acceso directo a la primera fue rechazado | Referencia de proceso; no activa reglas ni exportadores |
| Cuota fija / obligaciones concretas de la empresa | No definido por inscripción aportada | No se proporcionó constancia de inscripción aplicable. El perfil se declara manualmente; la demo usa texto e identificación ficticios | No se presume que aplique DMI general |
| Presentación VET | Cualquier período | Requiere intervención externa del contribuyente. No se accede con credenciales ni se confirma una declaración desde el sistema | Fuera del alcance |

## Condiciones para un exportador oficial posterior

1. Acreditar empresa, inscripción, régimen, obligación y período exactos.
2. Obtener guía y plantilla oficiales completas y verificar su vigencia para ese caso.
3. Conservar originales con URL, fecha de recuperación, versión, SHA-256 y responsable.
4. Aprobar mapa campo a campo, obligatoriedad, tipos, longitudes, redondeos y restricciones.
5. Implementar un adaptador separado, sin cambiar el exportador interno.
6. Probar estructura y muestras offline; revisión profesional y aprobación de activación.

`POST /admin/dgi/revisiones/<id>/exportar-oficial` devuelve HTTP 409 incluso si
se llama directamente. El botón deshabilitado refleja ese control del servidor.
No hay tasas fiscales nuevas fijadas por defecto. Los importes de IVA son los
ya registrados en ventas/compras; mostrarlos no valida su tratamiento fiscal.

Los cálculos y controles preexistentes de POS, nómina y clasificación de productos
conservan su comportamiento; este incremento no los certifica normativamente.
