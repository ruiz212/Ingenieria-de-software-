# Reparación de la revalidación — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Ejecutar con regresiones que fallen primero y verificar después.

**Goal:** corregir R1–R8 del informe autorizado por el usuario.

**Architecture:** conservar Flask, SQL Server y el código local corregido por el usuario. Aislar las decisiones de identidad, enlaces de referencia, movimientos de caja y despacho SMTP en límites explícitos. Usar SP de negocio y permisos mínimos; no abrir tablas a roles operativos.

**Tech Stack:** Python 3.12, Flask, pyodbc, SQL Server, JavaScript, pytest y Playwright/Edge.

**Spec:** `docs/REVALIDACION_CORRECCIONES_2026-10-19.md`, cuya reparación fue solicitada expresamente.

## Global Constraints

- Trabajar sobre el estado local actual, que contiene correcciones sin commit; no resetear, publicar ni desplegar.
- Las conexiones de prueba deben apuntar explícitamente a `PanaderiaQA_Prevalidacion_20261015`; bloquear SMTP real.
- La autorización previa para avanzar con criterio propio sigue vigente. El informe aporta causas y correcciones concretas; no requiere una nueva ronda de aprobación de diseño.
- Conservar evidencias anteriores; guardar las nuevas en `scratch/remediation_20261020/`.
- No aplicar migraciones ni permisos en la base habitual o Azure. Preparar migración revisable y verificarla en QA.

## Review Focus

- Fallo de EXECUTE AS o commit posterior: cerrar la conexión y devolver error, sin conexión privilegiada.
- Cotización con comillas, HTML, URLs externas/protocolos no autorizados: ningún script ni enlace inseguro.
- Factura anulada, entrega repetida, saldo entre turnos y turno cerrado: sin cobro doble ni atribución incorrecta.
- Rol Operativo: preservar la operación autorizada con dependencias mínimas, sin dar acceso fiscal general.
- SMTP concurrente, proceso reiniciado, error de envío y cola llena: reserva atómica, recuperación observable y límites.

## Tareas

### 1. Identidad SQL e IP de auditoría (R1, R6)
- [x] Añadir tests de activación SQL rechazada, fallo de commit y resolución de rol fallida.
- [x] Observar fallos, cerrar conexiones en errores y aplicar la identidad requerida sin fallback privilegiado.
- [x] Centralizar IP validada en `request.remote_addr`; sólo aceptar XFF mediante proxy configurado de confianza.
- [x] Verificar cabeceras arbitrarias, IP IPv4/IPv6 y ausencia de contexto.
Files: `app/db.py`, `app/__init__.py`, `config.py`, `app/services/request_context.py` si conviene, tests nuevos.

### 2. Referencias de imagen y visor de errores (R2, R8)
- [x] Añadir regresiones de payload de imagen, enlaces permitidos y contrato real de bitácora.
- [x] Validar referencias en el servidor y construir enlaces/filas con DOM seguro.
- [x] Verificar el JavaScript real en navegador y las respuestas API relevantes.
Files: `app/pos/routes.py`, `static/js/pos.js`, `templates/admin/configuracion.html`, helpers y tests propios.

### 3. Entregas, caja y permisos de Operativo (R3, R4, R5)
- [x] Reproducir entrega anulada, saldo cobrado en otro turno y dependencias contables del rol.
- [x] Rechazar anuladas atómicamente; registrar turno/usuario receptor del cobro y usarlo en arqueos.
- [x] Preparar migración idempotente para datos existentes sin reescribir el historial fiscal.
- [x] Encapsular dependencias fiscales necesarias en un SP limitado; conservar denegación fiscal general.
- [x] Probar rollback, reintento, turnos distintos y permisos SQL reales en QA.
Files: `app/monitor/routes.py`, `app/admin/routes_pos.py`, `app/services/contabilidad_service.py`, scripts/SQL de migración, tests de caja/entrega y propios.

### 4. Recuperación SMTP (R7)
- [x] Reproducir carrera entre envíos y fallos de transporte.
- [x] Añadir reserva atómica compartida y un consumidor de pendientes ejecutable, con lote y concurrencia limitados.
- [x] Sustituir hilo por aviso por despacho limitado; conservar mensajes pendientes si no se pueden procesar.
- [x] Probar envío simulado, caída, liberación de reserva y recuperación sin duplicación concurrente.
Files: `app/services/smtp_alerts.py`, script de consumo y SQL de outbox propio separado, tests propios. Coordinar SQL de integración con tarea 3.

### 5. Integración y revisión final
- [x] Revisar diffs de cada área y compatibilidad de firmas/permisos/migraciones.
- [x] Aplicar únicamente en QA las migraciones revisadas y ejecutar la suite completa con SMTP bloqueado.
- [x] Ejecutar regresiones SQL y navegador, validar CSS y dependencias.
- [x] Actualizar documentación con resultados reales y pasos de activación pendientes en el destino.

## Decisiones de ejecución

Se conserva el checkout actual para incluir las modificaciones y fuentes todavía sin seguimiento que se auditaron; un worktree desde HEAD las omitiría. Se guardará una copia de los archivos a tocar antes de editar. No se crearán commits automáticos del trabajo previo del usuario. Las subtareas independientes tienen archivos asignados para evitar colisiones.
