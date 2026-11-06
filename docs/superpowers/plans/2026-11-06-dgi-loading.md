# Reparación DGI y rendimiento de carga

**Objetivo:** eliminar el 500 de DGI y optimizar costes comprobados sin cambiar reglas fiscales ni el diseño.

**Evidencia inicial:** lectura de metadatos Azure y reproducción bajo `usr_bd_superadmin`, con conexión de solo lectura y alertas desactivadas: falta `sp_ObtenerPeriodoDGIPorID_Lectura`; su fallback SELECT directo termina con permiso denegado 229. Los procedimientos publicados de período/revisión sí existen. El CSS principal se entrega gzip, unos 19 KB; en navegador real la primera carga de login fue 1,63 s y la siguiente 0,22 s, con recursos desde caché. Son muestras, no un benchmark estadístico.

**Decisión:** reutilizar procedimientos ya publicados y autorizados; no conceder SELECT, aplicar migraciones ni desactivar roles. Revisar el trabajo SQL de las consultas DGI antes de tocar su presentación. Mantener orden de estilos y fuentes salvo evidencia de un coste significativo.

- [x] Reproducir el fallo mediante un cursor que admita los SP publicados y rechace SELECT directo; verificar que falla antes del arreglo.
- [x] Corregir lecturas de período/revisión, renderizar DGI contra Azure solo mediante consultas de lectura y registrar tiempos/consultas sin datos privados.
- [x] Medir y reducir trabajo redundante en DGI y recursos, con regresiones de resultados y verificación de navegador.
- [ ] Suite sin SQL operativo de escritura, CSS vigente, revisión, PR/CI Linux y entrega por `main`; confirmar arranque y acceso DGI de solo lectura.

Autorización: reparación y optimización solicitadas; continuidad de la entrega a GitHub/main autorizada previamente. No migraciones, cambios de permisos, escrituras fiscales ni envíos reales.

Validación local: 475 aprobadas, 168 omitidas; CSS vigente, navegador 390/1440 px
y rutas DGI probadas con Azure de solo lectura. Informe `docs/RENDIMIENTO_DGI_2026-11-06.md`.
