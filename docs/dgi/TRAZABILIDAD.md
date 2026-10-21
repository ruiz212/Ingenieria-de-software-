# Requisitos, casos de uso y pruebas DGI

Anexo incremental de los ocho módulos existentes: DGI amplía Contabilidad y
Finanzas, con controles de Seguridad. No se sustituye el alcance anterior.
Fuente de intención docente: transcripción depurada aportada por el usuario,
`Analisis_Modulo_DGI_Transcripcion.md`; no se afirma una nueva transcripción del audio.
Las decisiones técnicas siguientes son propuestas de ingeniería, no citas del profesor.

Refinamiento 1.1 autorizado por el usuario: el perfil pendiente se trata como
configuración, no como error contable del análisis interno; Admin puede validar
y exportar el informe interno. Diagnóstico sin aprobación disponible con errores.
El detalle y las nuevas pruebas figuran en [REVISION_FUNCIONAL.md](REVISION_FUNCIONAL.md).

| Necesidad docente / requisito | Implementación | Evidencia automatizada |
|---|---|---|
| Incluir DGI; RF-01 perfil | Configuración compartida, responsable, régimen, obligaciones, vigencia | `test_missing_profile_is_configuration_not_a_data_error`, `test_profile_must_cover_full_period`, `test_changed_profile_invalidates_before_approval` |
| Recopilar movimientos; RF-02 períodos | Mes seleccionado, preparación abierta/cerrada | `test_leap_month_and_invalid_month`, `test_period_close_requires_approval_and_reopen_preserves_data` |
| RF-03 ventas | Emisión/anulación, detalles, inclusión y enlaces actuales | `test_out_of_period_sale_is_excluded`, `test_same_period_void_and_reversal_cancel_without_double_counting` |
| RF-04 compras | Líneas de materia prima, soporte e IVA documentado | `test_missing_number_and_purchase_support`, `test_purchase_lines_of_different_materials_are_not_duplicate` |
| Evaluar antes de subir; RF-05/06 | Reglas internas, severidad, acción, origen y observaciones | `test_duplicate_invoice_references_source`, `test_arithmetic_and_details_are_separate_findings`, `test_comment_records_actor_and_cannot_override_blocker` |
| Explicar aproximación; RF-07 | Totales reproducibles, diferencia y fórmulas sin obligación inventada | `test_difference_is_10000_without_inventing_tax`, `test_reconciliation_compares_base_excluding_recorded_tax` |
| Corregir antes de presentar; RF-08 | Revisión humana, aprobación y detección de fuentes modificadas | `test_human_review_required_even_when_reconciled`, `test_changed_source_invalidates_approval_and_old_download` |
| Producir Excel; RF-09 | Seis hojas internas, rótulo no oficial, datos tipados y texto seguro | `test_xlsx_is_readable_typed_and_has_no_formula_injection`, `test_correction_revalidates_keeps_history_and_exports_readable_excel` |
| RF-10 auditoría | Eventos, actores, versiones, SHA-256 de fuentes y archivo | Mismo flujo SQL de corrección/exportación y prueba de caducidad |
| RF-11 oficial condicionado | Bloqueo del servidor sin plantilla/guía vigentes | `test_official_export_remains_blocked_in_server` |
| RF-13 historial | Versiones, nota humana, comentarios, archivo exacto y eventos | Flujo SQL de corrección y exportación; idempotencia concurrente |
| RF-14 brechas | Históricos, soporte ausente, conciliación, falta de RUC de proveedores | Casos unitarios y diagnóstico trazable, sin sanciones automáticas |
| Actualizar COCOMO; RF-15 | Medición de archivos, escenario histórico y tareas incrementales | `scripts/estimate_dgi.py`, `COCOMO.md` |

## Casos de uso implementados

1. **CU-DGI-01 Configurar perfil:** Admin guarda datos y vigencia; se comparten los
   datos del emisor. Una revisión anterior deberá comprobar nuevamente su huella.
2. **CU-DGI-02 Analizar período:** selecciona mes y propósito; se obtiene snapshot,
   diagnóstico, fuentes e historial. Sin cambios, conserva la misma versión.
3. **CU-DGI-03 Revisar hallazgos:** filtra regla/severidad, abre origen, registra
   observación y corrige por el módulo propietario. Comentarios no anulan bloqueos.
4. **CU-DGI-04 Aprobar internamente:** Admin/SuperAdmin necesita nota de revisión, cero errores de datos y
   fuentes vigentes. Un cambio caduca la aprobación y exige nueva versión.
5. **CU-DGI-05 Exportar:** genera XLSX interno, conserva archivo y huella y registra
   descargas. Un archivo histórico conserva su evidencia pero no puede descargarse
   desde una revisión obsoleta como si tuviera aprobación vigente.
6. **CU-DGI-06 Cerrar preparación:** Admin/SuperAdmin verifica las últimas revisiones;
   cierre independiente de la contabilidad; reapertura conserva las versiones.

## Requisitos no funcionales

- Montos Decimal, precisión de origen y cálculo determinista.
- Lectura consistente y revalidación en servidor antes de usar aprobación.
- Autenticación, permisos, CSRF, parámetros SQL y descargas sin caché pública.
- Datos sintéticos para pruebas; sin escrituras de negocio desde diagnóstico.
- Pantallas accesibles por teclado, diseño móvil y tablas desplazables.
- Migración aditiva idempotente y reversión condicionada a ausencia de datos.

## Próximos incrementos y exclusiones

RF-12 importación para conciliación y RF-16 adaptadores de otras obligaciones no
se implementan. Requieren diseño de validación de cargas, reglas y fuentes.
No se implementan tasas tributarias ni clasificación legal oficial de operaciones.
Historial no incluye una vista automática de diferencias campo a campo entre
snapshots; ambas versiones se pueden consultar y comparar.
El cierre no implementa notas de crédito/débito ni ajustes de facturas cerradas;
esas brechas comerciales preexistentes se muestran y documentan.
