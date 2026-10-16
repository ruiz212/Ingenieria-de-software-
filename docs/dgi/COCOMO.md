# Ampliación de estimación por DGI

Este escenario conserva la medición de la entrega inicial 1.0. La versión 1.1
reorganiza y formatea plantillas y agrega el reloj comercial y nuevos flujos;
consulte [REVISION_FUNCIONAL.md](REVISION_FUNCIONAL.md). Ejecutar el contador sobre
la versión actual dará otras líneas físicas; ese cambio de formato no equivale
a una medición nueva de esfuerzo ni valida la línea base histórica.

## Línea base encontrada y límites

El documento `Proyecto Corte 2 UNIDAD II - Erick Mayorquin - Brajher's Cake V4.docx`
y la extracción del Corte 2 disponible en el directorio padre declaran **9040 líneas,
9.04 MLDC**. Usan fórmulas orgánica `3.2 × KLOC^1.05`, tiempo `2.5 × E^0.38`, y
semiacoplada `3.0 × KLOC^1.12`, tiempo `2.5 × E^0.35`, con USD 800 por persona-mes.
Son parámetros heredados del documento, no una calibración validada en esta entrega.

El origen no documenta cómo contó líneas, si incluyó HTML/JS/CSS ni qué versión
exacta del código midió. También hay diferencias aritméticas: sus 32.40 y 35.90
persona-mes no reproducen exactamente las potencias indicadas. Al reevaluar esas
fórmulas con 9.04 se obtienen **32.294** y **35.321** persona-mes, respectivamente.
No se sobrescriben ni presentan como confirmados los presupuestos anteriores.

## Medición reproducible del incremento

```powershell
python scripts/estimate_dgi.py
```

La medición registra **996 líneas físicas no vacías** en 12 archivos nuevos de
producción/migración: rutas, motor, repositorio, XLSX, migración, CSS, JS y cinco
plantillas. Incluye docstrings y marcado. Excluye pruebas, documentos, scripts de
demo y ejecución local, archivos de muestra y modificaciones pequeñas al menú,
registro del blueprint y enlaces. Los HTML/CSS contienen varias instrucciones por
línea; por ello **esta medida no equivale a SLOC ni a puntos de función**. El script
publica el desglose por archivo y permite actualizarlo si cambia el código.

## Sensibilidad con los parámetros heredados

Solo para mostrar el impacto matemático, si se tratara la medición física como
comparable a la histórica: `KLOC_escenario = 9.04 + 0.996 = 10.036`.
Esa comparabilidad es un **supuesto pendiente**, no un nuevo tamaño base aprobado.

| Escenario heredado | Esfuerzo base recalculado | Esfuerzo con incremento | Diferencia | Tiempo total por fórmula heredada |
|---|---:|---:|---:|---:|
| Orgánico del documento | 32.294 PM | 36.040 PM | +3.746 PM | 9.762 meses |
| Semiacoplado del documento | 35.321 PM | 39.707 PM | +4.386 PM | 9.069 meses |

Con los USD 800/PM históricos, los totales hipotéticos serían USD 28832.26 y
USD 31765.75. No son precios actuales ni costos incurridos. No se añade un
porcentaje de infraestructura ni productividad sin base. Deben revisarse tipo de
COCOMO, factores de esfuerzo y métrica común antes de aprobar un presupuesto.

## Desglose de planificación del incremento

Estimación de horas de trabajo humano para planificar una implementación similar
desde el estado previo, con conocimiento de Flask/SQL Server. No son horas
registradas de esta sesión ni se suman a los resultados COCOMO.

| Trabajo adicional | Rango HH propuesto | Dependencias |
|---|---:|---|
| Inspección, fuentes y alcance | 6–10 | Repositorio y requisitos accesibles |
| Modelo, diccionario y migraciones | 6–10 | Esquema fiscal/contable previo |
| Adaptadores, reglas y conciliación | 14–22 | Convenciones de anulaciones y mayor |
| Flujo, snapshot y auditoría | 10–16 | Usuarios, permisos y transacciones |
| Pantallas e integración del menú | 10–16 | Plantilla administrativa |
| Exportación interna y verificación | 6–10 | Estructura del diagnóstico |
| Pruebas unitarias, SQL y regresión | 12–20 | Base QA independiente |
| Manual, matrices y estimación | 6–10 | Implementación y resultados verificables |
| **Total de planificación** | **70–114** | No incluye esperas externas |

Fuera de este rango: investigación profesional del contribuyente, nueva plantilla
oficial, importador, notas de crédito/débito, adaptación multiempresa, puesta en
producción y revisión de nómina/IVA preexistentes. Esas fases requieren estimación
separada con insumos reales. La ampliación pertenece a Contabilidad/Finanzas y
Seguridad dentro de los ocho módulos ya documentados.
