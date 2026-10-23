# Corte 5: estabilidad y trazabilidad Implementation Plan

> **For agentic workers:** Use executing-plans task by task. Each task needs a failing test, minimal implementation and passing verification.

**Goal:** Entregar búsqueda fiscal paginada, continuidad de sesión y borradores, perfiles y asistencia excepcional, y detalle contable comprensible.

**Architecture:** Endpoints Flask pequeños para consulta y ping; procedimientos SQL de solo lectura y escritura auditada; JavaScript modular para comportamiento progresivo. Migraciones idempotentes sobre el esquema existente.

**Tech Stack:** Python 3.12, Flask, SQL Server/T-SQL, Jinja, JavaScript.

**Spec:** `docs/superpowers/specs/2026-10-21-corte5-estabilidad-design.md`

## Global Constraints

- No modificar salarios ni escalas salariales.
- QA para migraciones y pruebas de escritura; no modificar la base ordinaria ni Azure.
- No SMTP real ni exponer datos personales en resultados.

## Review Focus

- Consulta de una página vacía: el total y los controles de paginación deben ser coherentes.
- Filtro que parece SQL/XSS: se parametriza en servidor y se inserta como texto en DOM.
- Pestaña sin actividad y polling de fondo: no prolongan la sesión.
- Marcaje manual repetido: no genera un segundo evento de excepción.
- Anticipo mixto o parcial: el asiento coincide con el dinero recibido por método y el arqueo toma el turno receptor.

### Task 1: Consulta DGI

**Files:** `app/admin/routes_dgi.py`, `app/services/dgi_repository.py`, `templates/admin/dgi/dashboard.html`, `static/js/dgi_invoices.js`, `database/03_stored_procedures.sql`, `database/01_esquemas_migracion.sql`, `tests/test_corte5_dgi.py`.

- [x] Escribir pruebas del filtro, período, tamaño, límite y actualización; observar fallo.
- [x] Añadir procedimiento paginado, índices y endpoint autorizado; verificar pruebas.
- [x] Añadir tabla y filtros accesibles con búsqueda diferida; comprobar navegador.

### Task 2: Sesión y borradores

**Files:** `app/auth/routes.py`, `app/__init__.py`, `config.py`, `templates/admin_base.html`, `static/js/session_guard.js`, `static/js/form_drafts.js`, formularios de RRHH/DGI/cotización, `tests/test_corte5_session.py`.

- [x] Escribir pruebas de ping, expiración y actividad; observar fallo.
- [x] Implementar vencimiento y renovación explícita de sesión.
- [x] Añadir aviso y borradores limitados por usuario/formulario; verificar teclado, recarga y guardado.

### Task 3: Puestos y asistencia de contingencia

**Files:** `app/admin/routes_hr.py`, `app/kiosco/routes.py`, `templates/admin/rrhh.html`, `database/01_esquemas_migracion.sql`, `database/03_stored_procedures.sql`, `tests/test_corte5_hr.py`.

- [x] Escribir pruebas de fecha por defecto, perfil y autorización/motivo de marcaje; observar fallo.
- [x] Añadir catálogo, vinculación opcional, rutas y transacción auditada.
- [x] Presentar ficha de puesto y acceso al marcaje excepcional; verificar rol e idempotencia.

### Task 4: Anticipos contables

**Files:** `app/services/contabilidad_service.py`, `templates/admin/libro_mayor.html`, `tests/test_corte5_accounting.py`.

- [x] Escribir prueba de asiento por anticipo y saldo con leyendas claras; observar fallo.
- [x] Ajustar descripción sin alterar importes o cuentas; verificar asiento y arqueo.

### Task 5: Validación integrada

- [x] Aplicar migración idempotente exclusivamente a QA y probar las rutas con roles reales.
- [x] Ejecutar pruebas dirigidas, navegador y suite completa con SMTP bloqueado.
- [x] Revisar diff y documentación, registrar límites operativos antes de entrega.
