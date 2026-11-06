# DGI y tiempos de carga — 06-11-2026

## Causas comprobadas del error 500

1. El código pedía dos procedimientos `_Lectura` que no estaban definidos en los
   scripts SQL ni instalados en Azure. El fallback SELECT directo era rechazado
   por el rol de aplicación con error 229. Se reutilizan los procedimientos
   publicados de período y revisión, sin ampliar permisos ni aplicar migraciones.
2. Hay revisiones históricas con un JSON anterior que no tiene `bloqueantes`.
   La pantalla intentaba leerlo incondicionalmente y fallaba con `KeyError`.
   Ahora se conservan los registros y se presentan como pendientes de revalidar.
   El detalle histórico ofrece la operación existente de revalidación, sin
   aprobar ni exportar resultados que no se pueden interpretar.

La reutilización de una revisión vigente comprueba además que su resultado y
snapshot sean legibles. Si el usuario revalida un resultado ilegible, el flujo
normal crea una nueva versión y conserva el anterior.

## Rendimiento

- Las revisiones de motor anterior, obsoletas o de resultado ilegible ya no
  provocan una lectura completa de facturas, detalles, compras y asientos para
  confirmar algo que ya se conoce: necesitan revalidación.
- Las pantallas de consulta usan READ COMMITTED y autocommit para liberar los
  bloqueos de cada sentencia. Azure tiene READ_COMMITTED_SNAPSHOT habilitado.
  Se verificó `@@TRANCOUNT=0` tras leer un período con el rol de aplicación.
- Aprobar, analizar, exportar y otras mutaciones siguen usando la transacción
  SERIALIZABLE existente y vuelven a verificar las fuentes. La vigencia que
  muestra el dashboard es informativa, no una autorización para exportar.
- Los cursores se cierran antes de restablecer opciones ODBC y devolver la
  conexión al pool, incluso si la pantalla o la consulta falla.

## CSS y navegador

En Edge real sobre el login publicado: carga inicial 1,63 s y siguiente carga
0,22 s en la misma sesión. El CSS principal se transfirió gzip, 19.429 bytes,
en unos 131 ms; en la siguiente navegación los estilos y scripts se sirvieron
desde caché, con transferencia cero. Son dos muestras, no un benchmark ni una
medición de todas las pantallas, redes o equipos.

Se revisaron paquetes, orden de estilos, tamaños, fuentes y scripts principales.
Los 46 paquetes CSS están vigentes; POS y tienda cargan una sola versión del
script POS. No se comprobó que CSS fuera el cuello de botella principal en la
navegación medida. Se mantienen estilos, orden de cascada y compresión existentes.

Las consultas DGI actuales pueden necesitar recuperar los documentos del mes para
comprobar la huella. Desde la máquina local, ese detalle tarda varios segundos
por la transferencia SQL; esos tiempos no representan el tiempo HTTP del servidor
Azure. No se eliminó la comprobación de integridad para acelerar una pantalla.

## Verificación

- Suite local: 475 pruebas aprobadas, 168 omitidas por integraciones/QA.
- Regresiones reproducidas antes del arreglo: permiso SQL, JSON histórico,
  transacción larga en lectura, resultados ODBC pendientes y revalidación de un
  resultado ilegible. Pruebas de vigencia detectan invertir la comparación de huellas.
- Consultas nativas de solo lectura con el rol SQL: dashboard, detalle histórico,
  detalle actual y búsqueda paginada completan correctamente. No se abrieron
  conexiones adicionales ni se persistieron alertas durante esas comprobaciones.
- Edge con datos sintéticos: dashboard y detalle histórico a 1440 y 390 px,
  sin errores JavaScript ni desbordamiento horizontal. Detector de UI: sin hallazgos.
- Sin migraciones, cambios de permisos, escrituras fiscales, aprobaciones ni
  envíos reales durante la validación. La revalidación con escritura se probó
  únicamente contra dobles de la frontera SQL, no contra registros operativos.

La entrega y sus resultados remotos se verifican por CI y el workflow de `main`.
