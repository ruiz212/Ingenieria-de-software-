# Revisión del alcance del Corte 4

Fecha: 13 de octubre de 2026.

Documento vigente de esta revisión:
[Proyecto Corte 4 corregido](Proyecto%20Corte%204%20UNIDAD%20IV%20corregido%20-%20Brajhers%20Cake.docx).
Los tres documentos anteriores se conservan como antecedentes y no fueron sobrescritos.

## Resultado documental

El Corte 4 por módulos anterior se organizaba en once capítulos funcionales.
La guía local de Unidad IV contiene diez contenidos RUP (4.1 a 4.10), no una
enumeración obligatoria de nueve módulos de negocio. La entrega corregida
desarrolla esos diez contenidos para los ocho módulos de la imagen del usuario.

| Módulo final | Antecedente de Corte 2 sección 5 | Correspondencia en Corte 3 |
|---|---|---|
| Seguridad Accesos y Auditoría | RF01-RF12 | Módulo 1 |
| CRM Gestión de Clientes | RF13-RF21 | Módulo 2 |
| Catálogo de Productos | RF22-RF30 | Módulo 3 |
| POS Caja y Arqueos Avanzados | RF31-RF52 | Módulo 4 |
| Encargos y Portal de Cotizaciones | RF53-RF62 | Módulo 5 |
| Inventario y Producción | RF63-RF74 | Agrupa módulos 6 y 7 |
| Contabilidad Formal y Privada | RF75-RF77 y apéndice RF106-RF109 | Sin capítulo propio; depende de POS, inventario y RRHH |
| Recursos Humanos y Kiosco Asistencia | RF78-RF85 y apéndice RF110-RF112 | Módulo 8 |

Compras y proveedores se ubican en Inventario y Producción. Los indicadores
estadísticos se relacionan con los módulos que producen sus datos. El soporte
SQL, migraciones y respaldo se documenta en arquitectura y operación. Catálogo,
CRM y cotizaciones recuperan capítulos propios en lugar de quedar absorbidos
por Mercadotecnia.

La imagen y el Corte 3 no tienen exactamente la misma partición: la imagen
agrupa inventario y producción e incluye contabilidad. La correspondencia se
explica en el nuevo documento sin atribuir al Corte 3 diagramas que no contiene.

## Precisión de fuentes y estados

- Las matrices usan los RF de la sección 5 actualizada de Corte 2. La lista
  inicial RF01-RF16 reutiliza números con otro significado.
- El cuerpo revisado de Corte 2 contiene RF01-RF85; su apéndice incorpora
  RF95-RF117. RF86-RF94 se encuentran en la especificación adicional
  `Requerimientos_Panaderia_Amada_V2.md` y se distinguen como otra fuente.
- La implementación usa Flask-Login y cookies firmadas de Flask; no se
  describe como JWT, sesión cifrada o almacenamiento de sesión en servidor.
- La apertura actual de caja es explícita. La venta exige turno abierto;
  la nota previa que afirmaba creación automática desde POS quedó desactualizada.
- Se distinguen AuditLog, ArqueoAuditLog y BitacoraFiscal. No se acredita
  cobertura completa de auditoría general por tener una tabla.
- Los umbrales de fidelidad del código no se presentan como aprendizaje
  probabilístico o pronóstico validado.
- Los CP del nuevo Word son criterios de aceptación diseñados. Su inclusión
  no equivale a ejecución exitosa de todos ellos.

## Reparaciones de código realizadas en esta revisión

| Archivo | Defecto | Corrección |
|---|---|---|
| `app/pos/routes.py` | Un import local de os impedía usar os.SEEK_END antes de ese import | Se usa el import del módulo |
| `app/pos/routes.py` | El stream se leía antes del guardado local y producía imagen vacía | La codificación base64 se realiza solo en la rama remota |
| `app/pos/routes.py` | Fotos de referencia guardadas bajo app/static en vez del directorio servido | Se usa current_app.static_folder |
| `app/admin/routes_catalog.py` | Imágenes de producto guardadas fuera del static_folder servido | Se usa current_app.static_folder |
| `app/auth/routes.py` | Fotografías de perfil guardadas fuera del static_folder servido | Se usa current_app.static_folder |
| `app/services/fiscal_service.py` | Anticipo podía ser menor al 50 por ciento exigido en cortes anteriores | Se rechaza un anticipo inferior a la mitad del total redondeada a centavos |

No se movieron imágenes antiguas, no se ejecutaron migraciones ni se modificaron
datos del negocio. Las reparaciones actúan sobre nuevas operaciones. Los cambios
que ya estaban en el repositorio al iniciar la revisión se conservaron.

## Evidencia nueva de pruebas

Comando ejecutado desde la raíz del proyecto, en un entorno de pruebas local:

```text
python -m pytest tests/test_fiscal.py tests/test_uploads.py -q
31 passed
```

- 26 casos de importes, pagos, precios del servidor, partida doble y anticipo.
- 5 casos de imágenes: carga y recuperación de referencia y catálogo,
  extensiones rechazadas y fotografía de perfil recuperable.
- Los casos de anticipo prueban rechazo de 0 y 49.99 para total 100, aceptación
  de 50 y 75, y el límite de centavos para total 2.01.
- Se usan archivos temporales, usuario QA y conexiones simuladas para perfil.
  No se envió SMS ni se contactó ImgBB.
- `git diff --check` no reportó errores de espacios.
- Word final de 34 páginas con índice actualizado. Se renderizó con la
  rasterización de `render_docx.py` usando un PDF exportado desde Microsoft Word,
  porque este runtime de Windows no incluye LibreOffice. Se inspeccionaron
  visualmente las 34 páginas: sin páginas vacías, tablas cortadas ni solapamientos.
- Verificación estructural del DOCX: ocho módulos y ochenta apartados RUP
  (4.1 a 4.10 en cada módulo), sin bordes decorativos bajo el título.

La revisión histórica en `Documentacion/Revision_DGI/REVISION.md` registra 57
pruebas SQL previas. Esas pruebas no se repitieron ni se sumaron al resultado
nuevo de 31. No se acreditó despliegue, aceptación del negocio ni conexión SQL
definitiva en esta revisión.

## Pendientes conservados en el documento

1. Selección de cliente en ventas ordinarias y formulario de edición CRM.
2. Mantenimiento integral de categorías, adicionales y productos ficticios.
3. Conversión trazable cotización-factura-encargo y cobro posterior por turno.
4. Costo promedio, costo de producción/ventas, stock terminado y mermas.
5. Auditoría general y recuperación funcional de respaldos.
6. Unificar horario individual y tolerancia entre kiosco y marcación manual;
   comprobar protección ante presencia repetida. El navegador hace una pausa
   de seis segundos, pero el servidor alterna entrada/salida según el registro.
7. Periodicidad de nómina requerida y validación de cálculos laborales existentes.
8. Pruebas integradas SQL y recorridos reales de aceptación de usuarios.

Estos puntos no se presentan como reparaciones terminadas ni como funciones
validadas de extremo a extremo.
