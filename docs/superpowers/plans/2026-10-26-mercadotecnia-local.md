# Mercadotecnia local Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recomendar productos en la tienda y mostrar a gerencia tendencias y acciones justificadas con ventas reales.

**Architecture:** Un modelo Python determinista se entrena con filas agregadas de facturas emitidas y se persiste en SQL Server. La tienda pública solo lee la instantánea sin datos personales; la gerencia ejecuta el entrenamiento y ve un panel explicable.

**Tech Stack:** Flask, Jinja, Python estándar, SQL Server, CSS existente.

**Spec:** `docs/superpowers/specs/2026-10-26-mercadotecnia-local-design.md`

## Global Constraints

- Sin API de IA ni dependencias pesadas nuevas.
- Invitados no comparten perfil personal.
- Solo facturas emitidas alimentan el modelo.
- Ningún precio o descuento se cambia automáticamente.
- La tienda funciona sin modelo inicial o si la migración falta.

## Review Focus

- Facturas anuladas no deben entrenar el modelo.
- El portal no debe poder pedir historial de otro cliente.
- Productos inactivos o ficticios no deben recomendarse.
- Datos escasos no deben generar afirmaciones de crecimiento.
- La falta de tabla/modelo no debe romper la tienda.

---

### Task 1: Motor local

**Files:** Create `app/services/marketing_model.py`; test `tests/test_marketing_model.py`.

**Interfaces:** `train_model(rows, now)` produce un diccionario JSON serializable; `recommend_products(model, catalog, history, limit)` produce productos con motivos; `business_insights(model, catalog)` produce observaciones con evidencia.

- [x] Escribir pruebas de exclusiones, personalización, asociaciones y datos escasos; confirmar que fallan.
- [x] Implementar el modelo determinista y comprobar que pasan.

### Task 2: Persistencia y permisos

**Files:** Create `database/05_mercadotecnia.sql`, `app/services/marketing_repository.py`; modify `scripts/migrate_esquemas_roles_sp.py`, `database/00_init_database_completo.sql`, `database/esquema.sql`.

**Interfaces:** `load_model(cursor)`, `train_and_save(cursor, now)`, `customer_history(cursor)`; procedimientos SQL `crm.sp_LeerModeloMercadotecnia`, `crm.sp_DatosEntrenamientoMercadotecnia`, `crm.sp_GuardarModeloMercadotecnia`, `crm.sp_HistorialPersonalMercadotecnia`.

- [x] Escribir pruebas de contratos de SQL y repositorio; confirmar que fallan.
- [x] Añadir migración idempotente, permisos mínimos y repositorio; comprobar pruebas.

### Task 3: Tienda y panel

**Files:** Modify `app/pos/routes.py`, `app/admin/__init__.py`, `templates/tienda.html`, `templates/admin/sidebar.html`, `static/css/sources.json`; create `app/admin/routes_marketing.py`, `templates/admin/mercadotecnia.html`, CSS de tienda y panel.

- [x] Escribir pruebas de acceso, perfil de invitado y degradación cuando no hay modelo; confirmar que fallan.
- [x] Implementar rutas y pantallas; compilar CSS y comprobar pruebas.

### Task 4: Verificación

- [x] Ejecutar pruebas enfocadas, pruebas de rutas, navegador y `scripts/build_css.py --check`.
- [x] Inspeccionar cambios y registrar que la migración SQL requiere aplicación en cada base desplegada.

**Validación SQL:** `database/05_mercadotecnia.sql` se aplicó a `PanaderiaQA_Prevalidacion_20261015`. El entrenamiento, lectura pública, denegación del modelo completo al cajero y rutas HTTP públicas pasaron con esa base. **Pendiente de despliegue:** aplicar la misma migración a la base Azure autorizada; no había una cadena de conexión Azure disponible en este entorno.
