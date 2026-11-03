"""Suite de pruebas de remediación para el Grupo 4 de Auditoría:
Autenticación (L08, L09), Administración de Usuarios y Alertas SMTP (L23, L26),
Clientes/Fidelización (L16), Inventario/Compras (L10, L18, L20) y Producción (L21).
"""
from __future__ import annotations

import os
import re
import uuid
import pyodbc
import pyotp
import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.auth import routes as auth_routes
from app.models import User
from app.services import auth_challenges as challenges
from app.services import smtp_alerts as alerts


DEFAULT_QA_CONN = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost\\SQLDEV;"
    "DATABASE=PanaderiaQA_Prevalidacion_20261015;"
    "Trusted_Connection=yes;"
)


@pytest.fixture(scope="module")
def qa_conn_str() -> str:
    previous_qa_conn = os.environ.get("TEST_DB_CONNECTION_STRING")
    conn_str = previous_qa_conn or DEFAULT_QA_CONN
    os.environ["TEST_DB_CONNECTION_STRING"] = conn_str
    conn = pyodbc.connect(conn_str)
    try:
        db_name = conn.cursor().execute("SELECT DB_NAME()").fetchone()[0]
        assert db_name.startswith("PanaderiaQA_"), f"Base de datos insegura para QA: {db_name}"
    finally:
        conn.close()
    try:
        yield conn_str
    finally:
        if previous_qa_conn is None:
            os.environ.pop("TEST_DB_CONNECTION_STRING", None)
        else:
            os.environ["TEST_DB_CONNECTION_STRING"] = previous_qa_conn


@pytest.fixture()
def app_instance(qa_conn_str):
    app = create_app()
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SECRET_KEY="group4-qa-secret-key",
        SQL_SERVER_CONNECTION_STRING=qa_conn_str,
        SMTP_ENABLED=True,
        SMTP_ASYNC=False,
        SMTP_HOST="smtp.qa.local",
        SMTP_PORT=587,
        SMTP_USE_TLS=True,
        SMTP_USER="alertas@qa.local",
        SMTP_PASSWORD="qa-password",
        SMTP_FROM_EMAIL="alertas@qa.local",
        SMTP_ALERT_RECIPIENTS="global@qa.local",
        SMTP_RATE_LIMIT_SECONDS=300,
    )
    auth_routes._FALLBACK_LOGIN_LOCKS.clear()
    return app


@pytest.fixture()
def raw_conn(qa_conn_str):
    conn = pyodbc.connect(qa_conn_str)
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()


def _make_authenticated_client(app_instance, user_id: int = 1, username: str = "superadmin_qa", rol: str = "SuperAdmin"):
    app_instance.login_manager._user_callback = lambda _: User(user_id, username, f"Usuario {username}", 1, rol)
    client = app_instance.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = f"emp_{user_id}"
        sess["_fresh"] = True
    return client


# ============================================================================
# L08: Bloqueo de login normalizando identificador (trim/lowercase/teléfono)
# ============================================================================
def test_l08_login_lockout_normalizes_username_and_phone_variants(app_instance, raw_conn):
    cursor = raw_conn.cursor()
    suffix = uuid.uuid4().hex[:6]
    username = f"qa_l08_{suffix}"
    phone_digits = f"8{int(suffix, 16) % 10000000:07d}"
    pw_hash = generate_password_hash("CorrectPass#2026!")

    rol_id = cursor.execute("SELECT TOP 1 ID FROM seguridad.Roles WHERE Nombre = 'Estandar'").fetchone()[0]
    user_id = cursor.execute(
        "INSERT INTO seguridad.Usuarios (NombreCompleto, Username, PasswordHash, RolID, Activo, TOTPEnabled) "
        "OUTPUT INSERTED.ID VALUES (?, ?, ?, ?, 1, 0)",
        (f"Usuario L08 {suffix}", username, pw_hash, rol_id),
    ).fetchone()[0]
    cliente_id = cursor.execute(
        "INSERT INTO crm.Clientes (Nombre, Apellidos, Telefono, PasswordHash, EsInvitado, NivelConfianzaID) "
        "OUTPUT INSERTED.ID VALUES (?, 'QA', ?, ?, 0, 1)",
        (f"Cliente L08 {suffix}", phone_digits, pw_hash),
    ).fetchone()[0]
    raw_conn.commit()

    client = app_instance.test_client()
    try:
        # 1. Variantes de mayúsculas y espacios para empleado acumulan en la misma cuenta
        variants_user = [
            f"  {username.upper()}  ",
            f"\t{username.capitalize()} ",
            username.upper(),
            f" {username} ",
            f"   {username.upper()}",
        ]
        for v in variants_user:
            resp = client.post("/login", data={"identificador": v, "password": "WrongPassword!"}, follow_redirects=True)
            assert resp.status_code in (200, 429)

        # El 6to intento con contraseña correcta debe ser bloqueado (HTTP 429)
        resp_locked = client.post(
            "/login",
            data={"identificador": username, "password": "CorrectPass#2026!"},
            follow_redirects=True,
        )
        assert resp_locked.status_code == 429 or "bloqueada" in resp_locked.text.lower()

        # 2. Variantes de formato telefónico (+505, guiones, espacios, 505) acumulan en el mismo cliente
        phone_variants = [
            f"+505 {phone_digits[:4]}-{phone_digits[4:]}",
            f"{phone_digits[:4]}-{phone_digits[4:]}",
            f"505{phone_digits}",
            f"  +505-{phone_digits[:4]} {phone_digits[4:]}  ",
            phone_digits,
        ]
        for pv in phone_variants:
            resp = client.post("/login", data={"identificador": pv, "password": "WrongPassword!"}, follow_redirects=True)
            assert resp.status_code in (200, 429)

        resp_phone_locked = client.post(
            "/login",
            data={"identificador": phone_digits, "password": "CorrectPass#2026!"},
            follow_redirects=True,
        )
        assert resp_phone_locked.status_code == 429 or "bloqueada" in resp_phone_locked.text.lower()
    finally:
        auth_routes._FALLBACK_LOGIN_LOCKS.clear()
        cursor.execute(
            "DELETE FROM seguridad.BloqueosCuenta WHERE Identificador IN (?, ?, ?)",
            (username, phone_digits, f"+505{phone_digits}"),
        )
        cursor.execute("DELETE FROM crm.Clientes WHERE ID = ?", (cliente_id,))
        cursor.execute("DELETE FROM seguridad.Usuarios WHERE ID = ?", (user_id,))
        raw_conn.commit()


# ============================================================================
# L09: TOTP no limpia fallos de contraseña antes de completar 2FA y bloquea
#      acumulando fallos TOTP por cuenta aunque se regenere el challenge
# ============================================================================
def test_l09_totp_preserves_login_failures_and_accumulates_across_regenerated_challenges(app_instance, raw_conn):
    cursor = raw_conn.cursor()
    suffix = uuid.uuid4().hex[:6]
    username = f"qa_l09_{suffix}"
    correct_pw = "CorrectTotpPass#2026!"
    pw_hash = generate_password_hash(correct_pw)
    totp_secret = pyotp.random_base32()

    rol_id = cursor.execute("SELECT TOP 1 ID FROM seguridad.Roles WHERE Nombre = 'Admin'").fetchone()[0]
    user_id = cursor.execute(
        "INSERT INTO seguridad.Usuarios (NombreCompleto, Username, PasswordHash, RolID, Activo, TOTPEnabled, TOTPSecret) "
        "OUTPUT INSERTED.ID VALUES (?, ?, ?, ?, 1, 1, ?)",
        (f"Admin TOTP {suffix}", username, pw_hash, rol_id, totp_secret),
    ).fetchone()[0]
    raw_conn.commit()

    client = app_instance.test_client()
    try:
        # 4 intentos fallidos de contraseña
        for _ in range(4):
            client.post("/login", data={"identificador": username, "password": "BadPassword!"}, follow_redirects=False)

        # Contraseña correcta -> redirige a /login/totp PERO NO debe limpiar los 4 fallos previos de login
        r_step1 = client.post("/login", data={"identificador": username, "password": correct_pw}, follow_redirects=False)
        assert r_step1.status_code == 302
        assert "/login/totp" in r_step1.headers["Location"]

        row_lock = cursor.execute(
            "SELECT IntentosFallidos FROM seguridad.BloqueosCuenta WHERE Identificador = ?",
            (username,),
        ).fetchone()
        assert row_lock is not None and int(row_lock[0]) == 4, (
            "La validación de contraseña no debe limpiar BloqueosCuenta antes de superar TOTP"
        )

        # Fallamos 2 veces en el primer challenge TOTP, luego regeneramos un 2do challenge
        # y fallamos 3 veces más -> al llegar a 5 fallos acumulados en la cuenta, queda bloqueado.
        for _ in range(2):
            client.post("/login/totp", data={"totp_code": "000000"}, follow_redirects=True)

        # Regenerar challenge volviendo a hacer POST /login con contraseña correcta
        r_regen = client.post("/login", data={"identificador": username, "password": correct_pw}, follow_redirects=False)
        assert r_regen.status_code == 302
        assert "/login/totp" in r_regen.headers["Location"]

        for _ in range(3):
            client.post("/login/totp", data={"totp_code": "000000"}, follow_redirects=True)

        # Ya acumula 5 fallos TOTP para la cuenta: intentar regenerar otro challenge con contraseña correcta debe bloquearse
        r_blocked_regen = client.post(
            "/login",
            data={"identificador": username, "password": correct_pw},
            follow_redirects=True,
        )
        assert r_blocked_regen.status_code == 429 or "bloqueada" in r_blocked_regen.text.lower()

        with app_instance.app_context():
            with pytest.raises(challenges.TOTPLocked):
                challenges.create("totp", str(user_id))

        # Al limpiar los fallos TOTP y completar 2FA con código válido, los fallos de login sí se limpian
        with app_instance.app_context():
            challenges.clear_totp_failures(str(user_id))

        valid_code = pyotp.TOTP(totp_secret).now()
        r_ok_step1 = client.post("/login", data={"identificador": username, "password": correct_pw}, follow_redirects=False)
        assert r_ok_step1.status_code == 302
        r_ok_step2 = client.post("/login/totp", data={"totp_code": valid_code}, follow_redirects=False)
        assert r_ok_step2.status_code == 302

        row_after = cursor.execute(
            "SELECT IntentosFallidos FROM seguridad.BloqueosCuenta WHERE Identificador = ?",
            (username,),
        ).fetchone()
        assert row_after is None or int(row_after[0]) == 0, (
            "Tras completar TOTP exitosamente deben limpiarse los intentos fallidos previos"
        )
    finally:
        auth_routes._FALLBACK_LOGIN_LOCKS.clear()
        cursor.execute("DELETE FROM seguridad.BloqueosCuenta WHERE Identificador = ?", (username,))
        cursor.execute("DELETE FROM seguridad.AuthChallenges WHERE Subject = ?", (str(user_id),))
        cursor.execute("DELETE FROM seguridad.Usuarios WHERE ID = ?", (user_id,))
        raw_conn.commit()


# ============================================================================
# L23: Protección atómica del último SuperAdmin activo
# ============================================================================
def test_l23_cannot_deactivate_or_demote_last_active_superadmin(app_instance, raw_conn):
    cursor = raw_conn.cursor()
    superadmin_role_id = cursor.execute("SELECT ID FROM seguridad.Roles WHERE Nombre = 'SuperAdmin'").fetchone()[0]
    admin_role_id = cursor.execute("SELECT ID FROM seguridad.Roles WHERE Nombre = 'Admin'").fetchone()[0]

    original_active_ids = [
        r[0]
        for r in cursor.execute(
            "SELECT ID FROM seguridad.Usuarios WHERE RolID = ? AND Activo = 1 ORDER BY ID",
            (superadmin_role_id,),
        ).fetchall()
    ]
    assert len(original_active_ids) >= 1
    sole_superadmin_id = original_active_ids[0]
    other_ids = original_active_ids[1:]

    try:
        for oid in other_ids:
            cursor.execute("UPDATE seguridad.Usuarios SET Activo = 0 WHERE ID = ?", (oid,))
        raw_conn.commit()

        client = _make_authenticated_client(app_instance, user_id=999999, username="sesion_sa", rol="SuperAdmin")

        # 1. Intentar cambiar el rol del último SuperAdmin activo vía endpoint
        resp_role = client.post(
            f"/admin/api/usuarios/{sole_superadmin_id}/rol",
            json={"rol_id": admin_role_id},
        )
        assert resp_role.status_code == 400
        assert "No se puede desactivar ni cambiar el rol del último SuperAdmin activo del sistema" in resp_role.json["error"]

        # 2. Intentar desactivar al último SuperAdmin activo vía endpoint
        resp_toggle = client.post(f"/admin/api/usuarios/{sole_superadmin_id}/toggle")
        assert resp_toggle.status_code == 400
        assert "No se puede desactivar ni cambiar el rol del último SuperAdmin activo del sistema" in resp_toggle.json["error"]

        # 3. Verificar también la protección directa en los Stored Procedures
        with pytest.raises(pyodbc.Error) as exc_sp_role:
            cursor.execute("EXEC seguridad.sp_ActualizarRolUsuario @P1 = ?, @P2 = ?", (sole_superadmin_id, admin_role_id))
        assert "último SuperAdmin" in str(exc_sp_role.value)
        raw_conn.rollback()

        with pytest.raises(pyodbc.Error) as exc_sp_toggle:
            cursor.execute("EXEC seguridad.sp_ToggleActivoUsuario @P1 = ?", (sole_superadmin_id,))
        assert "último SuperAdmin" in str(exc_sp_toggle.value)
        raw_conn.rollback()

        row = cursor.execute(
            "SELECT RolID, Activo FROM seguridad.Usuarios WHERE ID = ?",
            (sole_superadmin_id,),
        ).fetchone()
        assert row.RolID == superadmin_role_id and bool(row.Activo) is True
    finally:
        for oid in other_ids:
            cursor.execute("UPDATE seguridad.Usuarios SET Activo = 1 WHERE ID = ?", (oid,))
        raw_conn.commit()


# ============================================================================
# L26: Alertas SMTP en cola respetan destinatario individual aunque no haya
#      destinatarios globales configurados
# ============================================================================
def test_l26_smtp_outbox_delivers_row_specific_recipient_without_global_recipients(qa_conn_str, monkeypatch, raw_conn):
    alerts.reset_rate_limit_cache()
    sent_messages = []

    def fake_send(msg, smtp_cfg):
        sent_messages.append({"to": msg["To"], "subject": msg["Subject"], "recipients": list(smtp_cfg.get("recipients") or [])})
        return True

    monkeypatch.setattr(alerts, "send_smtp_message", fake_send)

    cursor = raw_conn.cursor()
    existing_outbox_ids = {
        r[0]
        for r in cursor.execute("SELECT ErrorID FROM seguridad.AlertasSMTPOutbox").fetchall()
    }
    prev_pending = [
        r[0]
        for r in cursor.execute(
            "SELECT ErrorID FROM seguridad.AlertasSMTPOutbox WHERE Estado IN ('Pending', 'Sending')"
        ).fetchall()
    ]
    for pid in prev_pending:
        cursor.execute("UPDATE seguridad.AlertasSMTPOutbox SET Estado = 'Suppressed' WHERE ErrorID = ?", (pid,))
    raw_conn.commit()

    marker = f"QA_L26_{uuid.uuid4().hex[:8]}"
    error_id = None
    try:
        cfg_no_global = {
            "enabled": True,
            "host": "smtp.qa.local",
            "port": 587,
            "use_tls": True,
            "use_ssl": False,
            "user": "",
            "password": "",
            "from_email": "alertas@qa.local",
            "recipients": [],
            "rate_limit_seconds": 300,
            "async": True,
            "connection_string": qa_conn_str,
            "testing": True,
        }

        payload = {
            "origen": "SEGURIDAD_AUTH",
            "severidad": "CRITICAL",
            "numero_error": 50099,
            "procedimiento": f"seguridad.{marker}",
            "esquema_origen": "seguridad",
            "mensaje_error": f"Alerta dirigida {marker}",
            "override_recipients": ["auditor.especifico@panaderia.local"],
            "force_send": True,
        }
        error_id = alerts.record_error_in_db(payload, cfg_no_global)
        assert error_id is not None
        assert alerts._enqueue_error(error_id, cfg_no_global, payload) is True

        stats = alerts.retry_pending_alerts(max_batch=5, smtp_cfg=cfg_no_global)
        assert stats["attempted"] >= 1
        assert stats["delivered"] == 1
        assert len(sent_messages) == 1
        assert sent_messages[0]["to"] == "auditor.especifico@panaderia.local"
        assert sent_messages[0]["recipients"] == ["auditor.especifico@panaderia.local"]

        notified = cursor.execute(
            "SELECT NotificadoSMTP FROM seguridad.BitacoraErrores WHERE ID = ?",
            (error_id,),
        ).fetchone()[0]
        assert notified == 1
    finally:
        current_outbox_ids = [
            r[0]
            for r in cursor.execute("SELECT ErrorID FROM seguridad.AlertasSMTPOutbox").fetchall()
            if r[0] not in existing_outbox_ids
        ]
        for new_oid in current_outbox_ids:
            cursor.execute("DELETE FROM seguridad.AlertasSMTPOutbox WHERE ErrorID = ?", (new_oid,))
        for pid in prev_pending:
            cursor.execute("UPDATE seguridad.AlertasSMTPOutbox SET Estado = 'Pending' WHERE ErrorID = ?", (pid,))
        raw_conn.commit()


# ============================================================================
# L16: Unicidad y normalización de teléfono de clientes en edición y creación
# ============================================================================
def test_l16_customer_phone_normalized_and_rejects_duplicates_with_409(app_instance, raw_conn):
    cursor = raw_conn.cursor()
    suffix = uuid.uuid4().hex[:6]
    phone_a = f"8{int(suffix, 16) % 10000000:07d}"
    phone_b = f"7{int(suffix, 16) % 10000000:07d}"

    id_a = cursor.execute(
        "INSERT INTO crm.Clientes (Nombre, Apellidos, Telefono, NivelConfianzaID) OUTPUT INSERTED.ID VALUES (?, 'QA', ?, 1)",
        (f"Cliente A {suffix}", phone_a),
    ).fetchone()[0]
    id_b = cursor.execute(
        "INSERT INTO crm.Clientes (Nombre, Apellidos, Telefono, NivelConfianzaID) OUTPUT INSERTED.ID VALUES (?, 'QA', ?, 1)",
        (f"Cliente B {suffix}", phone_b),
    ).fetchone()[0]
    raw_conn.commit()

    client = _make_authenticated_client(app_instance)
    created_id = None
    try:
        # 1. Intentar editar Cliente B con el teléfono de Cliente A usando formato +505 y guiones -> debe dar 409
        formatted_phone_a = f"+505 {phone_a[:4]}-{phone_a[4:]}"
        resp_dup = client.put(
            f"/admin/api/fidelizacion/clientes/{id_b}",
            json={
                "nombre": f"Cliente B {suffix}",
                "apellidos": "QA",
                "telefono": formatted_phone_a,
                "nivel_id": 1,
            },
        )
        assert resp_dup.status_code == 409, resp_dup.json
        assert "pertenece a otro cliente" in resp_dup.json["error"].lower()

        # 2. Editar Cliente B con su propio teléfono en formato con guiones -> 200 y queda normalizado a 8 dígitos
        resp_self = client.put(
            f"/admin/api/fidelizacion/clientes/{id_b}",
            json={
                "nombre": f"Cliente B Editado {suffix}",
                "apellidos": "QA",
                "telefono": f"  +505 {phone_b[:4]}-{phone_b[4:]}  ",
                "nivel_id": 1,
            },
        )
        assert resp_self.status_code == 200, resp_self.json
        stored_phone_b = cursor.execute("SELECT Telefono FROM crm.Clientes WHERE ID = ?", (id_b,)).fetchone()[0]
        assert stored_phone_b == phone_b

        # 3. Intentar crear un nuevo cliente con el teléfono de Cliente A en formato 505xxxxxxxx -> 409
        resp_create_dup = client.post(
            "/admin/api/fidelizacion/clientes",
            json={"nombre": "Cliente Duplicado", "telefono": f"505-{phone_a[:4]}-{phone_a[4:]}"},
        )
        assert resp_create_dup.status_code == 409
    finally:
        if created_id:
            cursor.execute("DELETE FROM crm.Clientes WHERE ID = ?", (created_id,))
        cursor.execute("DELETE FROM crm.Clientes WHERE ID IN (?, ?)", (id_a, id_b))
        raw_conn.commit()


# ============================================================================
# L10 & L18: Idempotencia en compras de materia prima y validación de RUC/factura
#            para crédito fiscal de IVA
# ============================================================================
def test_l10_and_l18_purchase_idempotency_and_iva_supplier_ruc_validation(app_instance, raw_conn):
    cursor = raw_conn.cursor()
    suffix = uuid.uuid4().hex[:6]
    unit_id = cursor.execute("SELECT TOP 1 ID FROM catalogo.UnidadesMedida").fetchone()[0]
    mp_id = cursor.execute(
        "INSERT INTO produccion.MateriaPrima (Nombre, UnidadMedidaID, StockActual, StockMinimo) "
        "OUTPUT INSERTED.ID VALUES (?, ?, 10.0, 1.0)",
        (f"Harina L10_{suffix}", unit_id),
    ).fetchone()[0]
    prov_no_ruc_id = cursor.execute(
        "INSERT INTO produccion.Proveedores (Nombre, Telefono, Activo, RUC) OUTPUT INSERTED.ID VALUES (?, '88887777', 1, NULL)",
        (f"Proveedor Sin RUC {suffix}",),
    ).fetchone()[0]
    prov_with_ruc_id = cursor.execute(
        "INSERT INTO produccion.Proveedores (Nombre, Telefono, Activo, RUC) OUTPUT INSERTED.ID VALUES (?, '88886666', 1, 'J0310000123456')",
        (f"Proveedor Con RUC {suffix}",),
    ).fetchone()[0]

    orig_regimen_row = cursor.execute(
        "SELECT Valor FROM seguridad.ConfiguracionSistema WHERE Clave = 'fiscal_regimen'"
    ).fetchone()
    orig_regimen = orig_regimen_row[0] if orig_regimen_row else "CuotaFija"
    cursor.execute("UPDATE seguridad.ConfiguracionSistema SET Valor = 'General' WHERE Clave = 'fiscal_regimen'")
    raw_conn.commit()

    client = _make_authenticated_client(app_instance)
    try:
        # --- L18: Con IVA > 0 y proveedor sin RUC válido, debe rechazarse con HTTP 400 sin tocar stock ---
        resp_no_ruc = client.post(
            "/admin/api/inventario/compra",
            json={
                "materia_id": mp_id,
                "proveedor_id": prov_no_ruc_id,
                "cantidad": 5,
                "costo": 575,
                "iva_documentado": 75,
                "factura_proveedor": f"FAC-NORUC-{suffix}",
            },
        )
        assert resp_no_ruc.status_code == 400
        assert "ruc" in resp_no_ruc.json["error"].lower()
        stock_after_reject = float(
            cursor.execute("SELECT StockActual FROM produccion.MateriaPrima WHERE ID = ?", (mp_id,)).fetchone()[0]
        )
        assert stock_after_reject == 10.0

        # --- L18 + L10: Con proveedor con RUC válido y clave de idempotencia ---
        idem_key = f"IDEM-{suffix}"
        factura_ok = f"FAC-OK-{suffix}"
        payload_ok = {
            "materia_id": mp_id,
            "proveedor_id": prov_with_ruc_id,
            "cantidad": 5,
            "costo": 575,
            "iva_documentado": 75,
            "factura_proveedor": factura_ok,
            "idempotency_key": idem_key,
        }
        resp_1 = client.post("/admin/api/inventario/compra", json=payload_ok)
        assert resp_1.status_code == 200, resp_1.json
        compra_id = resp_1.json["id"]

        # Reintento exacto con la misma clave de idempotencia -> devuelve el mismo ID sin duplicar stock ni asientos
        resp_2 = client.post("/admin/api/inventario/compra", json=payload_ok)
        assert resp_2.status_code == 200, resp_2.json
        assert resp_2.json["id"] == compra_id
        assert resp_2.json.get("idempotent") is True

        stock_final = float(
            cursor.execute("SELECT StockActual FROM produccion.MateriaPrima WHERE ID = ?", (mp_id,)).fetchone()[0]
        )
        assert stock_final == 15.0, "El stock solo debe incrementarse una vez ante reintentos idempotentes"

        compras_count = cursor.execute(
            "SELECT COUNT(*) FROM produccion.ComprasMateriaPrima WHERE FacturaProveedor = ?",
            (factura_ok,),
        ).fetchone()[0]
        assert compras_count == 1

        asientos_count = cursor.execute(
            "SELECT COUNT(*) FROM contabilidad.AsientosDiario WHERE ReferenciaExterna = ?",
            (factura_ok,),
        ).fetchone()[0]
        assert asientos_count == 1

        # Reintento con la misma clave de idempotencia pero monto distinto -> debe rechazarse con HTTP 409
        resp_conflict = client.post(
            "/admin/api/inventario/compra",
            json={**payload_ok, "costo": 999},
        )
        assert resp_conflict.status_code == 409
    finally:
        cursor.execute("UPDATE seguridad.ConfiguracionSistema SET Valor = ? WHERE Clave = 'fiscal_regimen'", (orig_regimen,))
        raw_conn.commit()


# ============================================================================
# L20: Cambio de unidad de medida de MateriaPrima requiere conversión o bloqueo
# ============================================================================
def test_l20_unit_change_with_stock_or_recipes_requires_conversion_factor(app_instance, raw_conn):
    cursor = raw_conn.cursor()
    suffix = uuid.uuid4().hex[:6]
    units = [r[0] for r in cursor.execute("SELECT TOP 2 ID FROM catalogo.UnidadesMedida ORDER BY ID").fetchall()]
    assert len(units) == 2
    unit_kg, unit_g = units[0], units[1]

    mp_id = cursor.execute(
        "INSERT INTO produccion.MateriaPrima (Nombre, UnidadMedidaID, StockActual, StockMinimo, CostoUnitario) "
        "OUTPUT INSERTED.ID VALUES (?, ?, 5.0, 1.0, 100.0)",
        (f"Azucar L20_{suffix}", unit_kg),
    ).fetchone()[0]
    prod_id = cursor.execute(
        "SELECT TOP 1 ID FROM catalogo.Productos WHERE Activo = 1 AND ISNULL(EsFicticio, 0) = 0"
    ).fetchone()[0]
    receta_id = cursor.execute(
        "INSERT INTO produccion.RecetaProducto (ProductoID, MateriaPrimaID, CantidadNecesaria) "
        "OUTPUT INSERTED.ID VALUES (?, ?, 0.5)",
        (prod_id, mp_id),
    ).fetchone()[0]
    raw_conn.commit()

    client = _make_authenticated_client(app_instance)
    try:
        # 1. Intentar cambiar unidad sin factor_conversion cuando hay stock y receta -> HTTP 400
        resp_reject = client.put(
            f"/admin/api/inventario/materia_prima/{mp_id}",
            json={
                "nombre": f"Azucar L20_{suffix}",
                "unidad_id": unit_g,
                "stock_minimo": 1.0,
            },
        )
        assert resp_reject.status_code == 400
        assert "factor" in resp_reject.json["error"].lower() or "unidad de medida" in resp_reject.json["error"].lower()

        row_before = cursor.execute(
            "SELECT UnidadMedidaID, StockActual FROM produccion.MateriaPrima WHERE ID = ?",
            (mp_id,),
        ).fetchone()
        assert row_before.UnidadMedidaID == unit_kg
        assert float(row_before.StockActual) == 5.0

        # 2. Cambiar unidad proporcionando factor_conversion = 1000 (1 kg -> 1000 g) -> HTTP 200 y recalcula stock y receta
        resp_convert = client.put(
            f"/admin/api/inventario/materia_prima/{mp_id}",
            json={
                "nombre": f"Azucar L20_{suffix}",
                "unidad_id": unit_g,
                "stock_minimo": 1.0,
                "factor_conversion": 1000,
            },
        )
        assert resp_convert.status_code == 200, resp_convert.json

        row_after = cursor.execute(
            "SELECT UnidadMedidaID, StockActual, StockMinimo, CostoUnitario FROM produccion.MateriaPrima WHERE ID = ?",
            (mp_id,),
        ).fetchone()
        assert row_after.UnidadMedidaID == unit_g
        assert float(row_after.StockActual) == pytest.approx(5000.0)
        assert float(row_after.StockMinimo) == pytest.approx(1000.0)
        assert float(row_after.CostoUnitario) == pytest.approx(0.1)

        receta_after = float(
            cursor.execute("SELECT CantidadNecesaria FROM produccion.RecetaProducto WHERE ID = ?", (receta_id,)).fetchone()[0]
        )
        assert receta_after == pytest.approx(500.0)
    finally:
        cursor.execute("DELETE FROM produccion.RecetaProducto WHERE ID = ?", (receta_id,))
        cursor.execute("DELETE FROM produccion.MateriaPrima WHERE ID = ?", (mp_id,))
        raw_conn.commit()


# ============================================================================
# L21: Validación de producto elegible al registrar lote de producción
# ============================================================================
def test_l21_production_batch_rejects_inactive_fictitious_and_resale_products(app_instance, raw_conn):
    cursor = raw_conn.cursor()
    suffix = uuid.uuid4().hex[:6]

    unit_id = cursor.execute("SELECT TOP 1 ID FROM catalogo.UnidadesMedida").fetchone()[0]
    mp_id = cursor.execute(
        "INSERT INTO produccion.MateriaPrima (Nombre, UnidadMedidaID, StockActual, StockMinimo) "
        "OUTPUT INSERTED.ID VALUES (?, ?, 100.0, 5.0)",
        (f"Insumo L21_{suffix}", unit_id),
    ).fetchone()[0]

    cat_pan_id = cursor.execute("SELECT TOP 1 ID FROM catalogo.Categorias WHERE Nombre NOT IN ('Bebidas', 'Bebida', 'Reventa')").fetchone()[0]
    cat_bebidas_row = cursor.execute("SELECT TOP 1 ID FROM catalogo.Categorias WHERE Nombre = 'Bebidas'").fetchone()
    if cat_bebidas_row:
        cat_bebidas_id = cat_bebidas_row[0]
    else:
        cat_bebidas_id = cursor.execute(
            "INSERT INTO catalogo.Categorias (Nombre, Descripcion) OUTPUT INSERTED.ID VALUES ('Bebidas', 'Bebidas y reventa')"
        ).fetchone()[0]

    prod_inactive_id = cursor.execute(
        "INSERT INTO catalogo.Productos (CategoriaID, Nombre, PrecioBase, Activo, EsFicticio) "
        "OUTPUT INSERTED.ID VALUES (?, ?, 25.0, 0, 0)",
        (cat_pan_id, f"Pan Inactivo {suffix}"),
    ).fetchone()[0]
    prod_fict_id = cursor.execute(
        "INSERT INTO catalogo.Productos (CategoriaID, Nombre, PrecioBase, Activo, EsFicticio) "
        "OUTPUT INSERTED.ID VALUES (?, ?, 25.0, 1, 1)",
        (cat_pan_id, f"Servicio Ficticio {suffix}"),
    ).fetchone()[0]
    prod_bebida_id = cursor.execute(
        "INSERT INTO catalogo.Productos (CategoriaID, Nombre, PrecioBase, Activo, EsFicticio) "
        "OUTPUT INSERTED.ID VALUES (?, ?, 30.0, 1, 0)",
        (cat_bebidas_id, f"Gaseosa Reventa {suffix}"),
    ).fetchone()[0]

    for pid in (prod_inactive_id, prod_fict_id, prod_bebida_id):
        cursor.execute(
            "INSERT INTO produccion.RecetaProducto (ProductoID, MateriaPrimaID, CantidadNecesaria) VALUES (?, ?, 2.0)",
            (pid, mp_id),
        )
    raw_conn.commit()

    client = _make_authenticated_client(app_instance)
    try:
        for invalid_pid, label in [
            (prod_inactive_id, "inactivo"),
            (prod_fict_id, "ficticio"),
            (prod_bebida_id, "reventa/bebidas"),
        ]:
            resp = client.post(
                "/admin/api/produccion/lote",
                json={"producto_id": invalid_pid, "cantidad": 5},
            )
            assert resp.status_code == 400, f"Debió rechazar lote para producto {label}: {resp.json}"

        stock_mp = float(
            cursor.execute("SELECT StockActual FROM produccion.MateriaPrima WHERE ID = ?", (mp_id,)).fetchone()[0]
        )
        assert stock_mp == 100.0
    finally:
        cursor.execute(
            "DELETE FROM produccion.RecetaProducto WHERE ProductoID IN (?, ?, ?)",
            (prod_inactive_id, prod_fict_id, prod_bebida_id),
        )
        cursor.execute(
            "DELETE FROM catalogo.Productos WHERE ID IN (?, ?, ?)",
            (prod_inactive_id, prod_fict_id, prod_bebida_id),
        )
        cursor.execute("DELETE FROM produccion.MateriaPrima WHERE ID = ?", (mp_id,))
        raw_conn.commit()
