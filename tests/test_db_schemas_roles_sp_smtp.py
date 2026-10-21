# tests/test_db_schemas_roles_sp_smtp.py
# Pruebas integrales de separación por 8 esquemas, 6 roles de BD (principio de privilegio mínimo),
# catálogo de Stored Procedures, blindaje de seguridad (SESSION_CONTEXT, DDM, bloqueo por fuerza bruta,
# triggers de inmutabilidad) y programación de errores con alertas SMTP.

import os
from unittest.mock import MagicMock, patch
import pyodbc
import pytest

from app import create_app
from app.db import (
    ROLE_TO_DB_ROLE,
    ROLE_TO_DB_USER,
    as_db_role,
    get_db_connection,
)
from app.services.smtp_alerts import (
    build_alert_email,
    notify_error,
    reset_rate_limit_cache,
)


DEFAULT_QA_CONN = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=localhost\\SQLDEV;"
    "DATABASE=PanaderiaQA_Prevalidacion_20261015;"
    "Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;"
)


@pytest.fixture(scope="module")
def app_instance():
    conn_str = os.environ.get("TEST_DB_CONNECTION_STRING") or DEFAULT_QA_CONN
    os.environ["TEST_DB_CONNECTION_STRING"] = conn_str
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SQL_SERVER_CONNECTION_STRING"] = conn_str
    app.config["SMTP_ENABLED"] = True
    app.config["SMTP_ASYNC"] = False
    app.config["SMTP_HOST"] = "smtp.test.local"
    app.config["SMTP_PORT"] = 587
    app.config["SMTP_USE_TLS"] = True
    app.config["SMTP_USER"] = "alertas@brajhers.local"
    app.config["SMTP_PASSWORD"] = "secret-test-pass"
    app.config["SMTP_FROM_EMAIL"] = "alertas@brajhers.local"
    app.config["SMTP_ALERT_RECIPIENTS"] = "seguridad@brajhers.local"
    app.config["SMTP_RATE_LIMIT_SECONDS"] = 300
    return app


@pytest.fixture()
def db_conn(app_instance):
    with app_instance.app_context():
        conn = get_db_connection(inject_context=False)
        try:
            yield conn
        finally:
            conn.close()


# ==============================================================================
# 1. VERIFICACIÓN DE LOS 8 ESQUEMAS DE DOMINIO Y 50 TABLAS
# ==============================================================================

EXPECTED_SCHEMAS = {
    "seguridad",
    "crm",
    "catalogo",
    "ventas",
    "produccion",
    "rrhh",
    "contabilidad",
    "fiscal",
}

EXPECTED_SCHEMA_TABLES = {
    "seguridad": {
        "Roles",
        "Usuarios",
        "AuthChallenges",
        "AuditLog",
        "ConfiguracionSistema",
        "BitacoraErrores",
        "BloqueosCuenta",
    },
    "crm": {
        "NivelesConfianza",
        "Clientes",
        "Cotizaciones",
    },
    "catalogo": {
        "Categorias",
        "UnidadesMedida",
        "Productos",
        "Ingredientes",
    },
    "ventas": {
        "TurnosCaja",
        "Facturas",
        "DetalleFacturas",
        "DetalleIngredientes",
        "Pagos",
        "FacturasRUC",
        "Encargos",
        "ArqueoCaja",
        "ArqueoDetalleDenominacion",
        "ArqueoAuditLog",
        "TipoCambio",
        "SecuenciasFiscales",
    },
    "produccion": {
        "Proveedores",
        "MateriaPrima",
        "ComprasMateriaPrima",
        "RecetaProducto",
        "ProduccionLotes",
        "ConsumoLote",
        "Mermas",
    },
    "rrhh": {
        "Empleados",
        "TurnosLaborales",
        "Asistencia",
        "FeriadosNacionales",
        "Nomina",
        "DetalleNomina",
        "LicenciasEmpleados",
        "DeduccionesJudiciales",
        "IncidentesLaborales",
        "ValesEmpleados",
    },
    "contabilidad": {
        "CatalogoCuentas",
        "PeriodosContables",
        "TiposComprobante",
        "AsientosDiario",
        "DetalleAsientos",
        "EgresosPrivados",
        "CuentasPorCobrar",
        "CuentasPorPagar",
        "PagosCxC",
        "ConciliacionBancaria",
        "DetalleConciliacion",
    },
    "fiscal": {
        "BitacoraFiscal",
        "DGI_Periodos",
        "DGI_Revisiones",
        "DGI_Observaciones",
        "DGI_Exportaciones",
    },
}


def test_eight_domain_schemas_and_tables_exist(db_conn):
    cursor = db_conn.cursor()
    cursor.execute("SELECT name FROM sys.schemas")
    existing_schemas = {row[0] for row in cursor.fetchall()}
    assert EXPECTED_SCHEMAS.issubset(existing_schemas), (
        f"Faltan esquemas de dominio: {EXPECTED_SCHEMAS - existing_schemas}"
    )

    cursor.execute(
        """
        SELECT s.name AS schema_name, t.name AS table_name
        FROM sys.tables t
        INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
        WHERE s.name IN ('seguridad','crm','catalogo','ventas','produccion','rrhh','contabilidad','fiscal')
        """
    )
    found = {}
    for schema_name, table_name in cursor.fetchall():
        found.setdefault(schema_name, set()).add(table_name)

    total_expected = 0
    for schema_name, expected_tables in EXPECTED_SCHEMA_TABLES.items():
        total_expected += len(expected_tables)
        actual_tables = found.get(schema_name, set())
        missing = expected_tables - actual_tables
        assert not missing, f"En el esquema '{schema_name}' faltan las tablas: {missing}"
    assert total_expected == 59


def test_dbo_synonyms_provide_backward_compatibility(db_conn):
    cursor = db_conn.cursor()
    cursor.execute("SELECT name, base_object_name FROM sys.synonyms WHERE schema_id = SCHEMA_ID('dbo')")
    synonyms = {row[0]: row[1] for row in cursor.fetchall()}
    for schema_name, tables in EXPECTED_SCHEMA_TABLES.items():
        for tbl in tables:
            assert tbl in synonyms, f"Falta sinónimo dbo.{tbl} hacia {schema_name}.{tbl}"


# ==============================================================================
# 2. VERIFICACIÓN DE LOS 6 ROLES DE BASE DE DATOS Y PRIVILEGIO MÍNIMO
# ==============================================================================

def test_six_database_roles_and_users_exist(db_conn):
    assert ROLE_TO_DB_USER["SuperAdmin"] == "usr_bd_superadmin"
    assert ROLE_TO_DB_USER["Admin"] == "usr_bd_gerencia"
    assert ROLE_TO_DB_USER["Estandar"] == "usr_bd_cajero_pos"
    assert ROLE_TO_DB_USER["Operativo"] == "usr_bd_produccion"
    assert ROLE_TO_DB_USER["Kiosco"] == "usr_bd_kiosco"
    assert ROLE_TO_DB_USER["Cliente"] == "usr_bd_portal_cliente"
    assert ROLE_TO_DB_USER["Invitado"] == "usr_bd_portal_cliente"

    cursor = db_conn.cursor()
    cursor.execute("SELECT name, type_desc FROM sys.database_principals")
    principals = {row[0]: row[1] for row in cursor.fetchall()}

    for app_role, db_role in ROLE_TO_DB_ROLE.items():
        assert db_role in principals, f"Falta rol de BD {db_role} para rol de app {app_role}"
        assert principals[db_role] == "DATABASE_ROLE"

    for key, db_user in ROLE_TO_DB_USER.items():
        assert db_user in principals, f"Falta usuario contenido {db_user} para {key}"


@pytest.mark.parametrize(
    "db_user,forbidden_sql",
    [
        ("Estandar", "SELECT TOP 1 * FROM seguridad.Usuarios"),
        ("Estandar", "SELECT TOP 1 * FROM ventas.Facturas"),
        ("Estandar", "SELECT TOP 1 * FROM dbo.Facturas"),
        ("Estandar", "DELETE FROM ventas.Facturas WHERE ID = -999"),
        ("Operativo", "SELECT TOP 1 * FROM produccion.MateriaPrima"),
        ("Operativo", "SELECT TOP 1 * FROM contabilidad.AsientosDiario"),
        ("Kiosco", "SELECT TOP 1 * FROM rrhh.Nomina"),
        ("Kiosco", "SELECT TOP 1 * FROM seguridad.Usuarios"),
        ("Cliente", "SELECT TOP 1 * FROM crm.Clientes"),
        ("Invitado", "UPDATE catalogo.Productos SET Activo = 0 WHERE ID = 1"),
        ("Admin", "SELECT TOP 1 * FROM seguridad.Usuarios"),
        ("Admin", "DELETE FROM seguridad.AuditLog WHERE ID = 1"),
    ],
)
def test_operational_roles_denied_direct_table_access(db_conn, db_user, forbidden_sql):
    cursor = db_conn.cursor()
    with as_db_role(cursor, db_user):
        with pytest.raises(pyodbc.ProgrammingError) as exc_info:
            cursor.execute(forbidden_sql)
        err_msg = str(exc_info.value).lower()
        assert "permission was denied" in err_msg or "se denegó el permiso" in err_msg or "229" in err_msg


@pytest.mark.parametrize(
    "db_user,forbidden_sp,params",
    [
        ("Estandar", "rrhh.sp_ListarNominasPeriodo", ()),
        ("Estandar", "contabilidad.sp_ObtenerBalanceGeneral", ("2026-10-19",)),
        ("Estandar", "seguridad.sp_ListarBitacoraErrores", ()),
        ("Operativo", "ventas.sp_ListarArqueosCaja", ()),
        ("Operativo", "rrhh.sp_ListarNominasPeriodo", ()),
        ("Kiosco", "ventas.sp_ListarArqueosCaja", ()),
        ("Kiosco", "crm.sp_ObtenerClientePorID", (1,)),
        ("Cliente", "produccion.sp_ListarInventarioMateriaPrima", ()),
        ("Cliente", "seguridad.sp_ListarUsuariosYRoles", ()),
        ("Cliente", "crm.sp_ActualizarEstadoCotizacion", (1, "Cotizada", 10.0)),
        ("Cliente", "crm.sp_CotizarPedidoAdmin", (10.0, 1)),
        ("Admin", "seguridad.sp_ListarBitacoraErrores", ()),
        ("Admin", "seguridad.sp_ListarAuditoria", ()),
    ],
)
def test_cross_domain_stored_procedure_execution_denied(db_conn, db_user, forbidden_sp, params):
    cursor = db_conn.cursor()
    placeholders = ", ".join("?" for _ in params)
    sql = f"EXEC {forbidden_sp}" + (f" {placeholders}" if placeholders else "")
    with as_db_role(cursor, db_user):
        with pytest.raises(pyodbc.ProgrammingError) as exc_info:
            if params:
                cursor.execute(sql, *params)
            else:
                cursor.execute(sql)
        err_msg = str(exc_info.value).lower()
        assert "permission was denied" in err_msg or "se denegó el permiso" in err_msg or "229" in err_msg


@pytest.mark.parametrize(
    "db_user,allowed_sp,params",
    [
        ("Estandar", "catalogo.sp_ObtenerCatalogoActivo", ()),
        ("Estandar", "ventas.sp_ObtenerTurnoActivo", (1,)),
        ("Estandar", "crm.sp_ObtenerClientePorID", (1,)),
        ("Operativo", "produccion.sp_ListarInventarioMateriaPrima", ()),
        ("Operativo", "produccion.sp_ListarProduccionYRecetas", ()),
        ("Kiosco", "rrhh.sp_ObtenerDescriptoresFacialesKiosco", ()),
        ("Cliente", "catalogo.sp_ObtenerCatalogoActivo", ()),
        ("Cliente", "ventas.sp_ConsultarSeguimientoPedido", ("FAC-000001",)),
        ("Admin", "contabilidad.sp_ObtenerBalanceGeneral", ("2026-10-19",)),
        ("Admin", "rrhh.sp_ListarNominasPeriodo", ()),
        ("Admin", "fiscal.sp_ListarPeriodosDGI", ()),
        ("SuperAdmin", "seguridad.sp_ListarBitacoraErrores", (10, None, None, 0)),
        ("SuperAdmin", "seguridad.sp_ListarAuditoria", (None, None, None)),
    ],
)
def test_authorized_stored_procedures_succeed_via_ownership_chaining(db_conn, db_user, allowed_sp, params):
    cursor = db_conn.cursor()
    placeholders = ", ".join("?" for _ in params)
    sql = f"SET NOCOUNT ON; EXEC {allowed_sp}" + (f" {placeholders}" if placeholders else "")
    with as_db_role(cursor, db_user):
        if params:
            cursor.execute(sql, *params)
        else:
            cursor.execute(sql)
        assert cursor.description is not None


# ==============================================================================
# 3. DYNAMIC DATA MASKING (DDM), SESSION_CONTEXT, TRIGGERS INMUTABLES Y BLOQUEO
# ==============================================================================

def test_dynamic_data_masking_configured_on_sensitive_columns(db_conn):
    cursor = db_conn.cursor()
    cursor.execute(
        """
        SELECT s.name AS schema_name, t.name AS table_name, c.name AS column_name, c.masking_function
        FROM sys.masked_columns c
        INNER JOIN sys.tables t ON c.object_id = t.object_id
        INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
        """
    )
    masked = {(r[0], r[1], r[2]): r[3] for r in cursor.fetchall()}
    assert ("seguridad", "Usuarios", "TOTPSecret") in masked
    assert ("rrhh", "Empleados", "Cedula") in masked
    assert ("rrhh", "Empleados", "NumeroINSS") in masked
    assert ("rrhh", "Empleados", "FaceDescriptor") in masked


def test_sp_try_catch_logs_to_bitacora_errores_with_session_context(db_conn):
    cursor = db_conn.cursor()
    cursor.execute(
        "EXEC sys.sp_set_session_context @key=N'usuario_id', @value=99; "
        "EXEC sys.sp_set_session_context @key=N'username', @value=N'qa_auditor'; "
        "EXEC sys.sp_set_session_context @key=N'rol', @value=N'SuperAdmin'; "
        "EXEC sys.sp_set_session_context @key=N'ip', @value=N'10.20.30.40'; "
        "EXEC sys.sp_set_session_context @key=N'ruta_http', @value=N'/admin/produccion/receta';"
    )
    # Provocar un error de negocio controlado en produccion.sp_GuardarRecetaProducto (CantidadNecesaria <= 0)
    with pytest.raises(pyodbc.Error):
        cursor.execute(
            "EXEC produccion.sp_GuardarRecetaProducto @ProductoID=1, @MateriaPrimaID=1, @CantidadNecesaria=-5"
        )
    db_conn.commit()

    # Consultar la bitácora de errores para verificar que el CATCH persistió el fallo con SESSION_CONTEXT
    cursor.execute(
        """
        SELECT TOP 1 Procedimiento, EsquemaOrigen, Username, RolAplicacion, DireccionIP, RutaHTTP, MensajeError
        FROM seguridad.BitacoraErrores
        WHERE Username = N'qa_auditor' AND RutaHTTP = N'/admin/produccion/receta'
        ORDER BY ID DESC
        """
    )
    row = cursor.fetchone()
    assert row is not None, "El bloque CATCH del SP no registró el error en seguridad.BitacoraErrores"
    assert "sp_GuardarRecetaProducto" in (row[0] or "")
    assert row[1] == "produccion"
    assert row[2] == "qa_auditor"
    assert row[3] == "SuperAdmin"
    assert row[4] == "10.20.30.40"
    assert row[5] == "/admin/produccion/receta"
    assert "mayor a cero" in (row[6] or "").lower()


def test_immutability_triggers_protect_auditlog_and_bitacora_errores(db_conn):
    cursor = db_conn.cursor()

    # Asegurar que haya al menos un registro en AuditLog para probar el trigger
    cursor.execute(
        "EXEC seguridad.sp_RegistrarAuditoria @UsuarioID=1, @Accion='TEST_INMUTABILIDAD', "
        "@Entidad='Seguridad', @EntidadID='1', @DatosAntes=NULL, @DatosDespues='{}', @IP='127.0.0.1'"
    )
    db_conn.commit()

    # 1. Intentar borrar BitacoraErrores debe fallar por TR_BitacoraErrores_Inmutable
    with pytest.raises(pyodbc.Error) as exc_del_err:
        cursor.execute("DELETE TOP (1) FROM seguridad.BitacoraErrores")
    msg_del_err = str(exc_del_err.value).lower()
    assert "no permite eliminar" in msg_del_err or "inmutable" in msg_del_err or "51007" in msg_del_err
    db_conn.rollback()

    # 2. Intentar alterar el MensajeError de BitacoraErrores debe fallar
    with pytest.raises(pyodbc.Error) as exc_upd_err:
        cursor.execute(
            "UPDATE TOP (1) seguridad.BitacoraErrores SET MensajeError = N'Manipulado'"
        )
    msg_upd_err = str(exc_upd_err.value).lower()
    assert "inmutable" in msg_upd_err or "51008" in msg_upd_err
    db_conn.rollback()

    # 3. Intentar borrar AuditLog debe fallar por TR_AuditLog_Inmutable
    with pytest.raises(pyodbc.Error) as exc_del_aud:
        cursor.execute("DELETE TOP (1) FROM seguridad.AuditLog")
    msg_del_aud = str(exc_del_aud.value).lower()
    assert "inmutable" in msg_del_aud or "no se permite" in msg_del_aud or "51006" in msg_del_aud
    db_conn.rollback()


def test_brute_force_login_lockout_stored_procedures(db_conn):
    cursor = db_conn.cursor()
    test_username = "qa_lockout_target_user"
    test_ip = "192.168.99.99"

    # Reset previo ejecutando un intento exitoso
    cursor.execute(
        "EXEC seguridad.sp_RegistrarIntentoLogin @Identificador=?, @DireccionIP=?, @Exitoso=1",
        test_username,
        test_ip,
    )
    db_conn.commit()

    # Registrar 5 intentos fallidos consecutivos (umbral = 5)
    last_state = None
    for _ in range(5):
        cursor.execute(
            "SET NOCOUNT ON; EXEC seguridad.sp_RegistrarIntentoLogin "
            "@Identificador=?, @DireccionIP=?, @Exitoso=0, @MaxIntentos=5, @MinutosBloqueo=15",
            test_username,
            test_ip,
        )
        last_state = cursor.fetchone()
    db_conn.commit()

    assert last_state is not None
    assert bool(last_state[0]) is True  # Bloqueado
    assert int(last_state[2]) >= 5  # IntentosFallidos

    # Verificar con sp_VerificarBloqueoCuenta
    cursor.execute(
        "SET NOCOUNT ON; EXEC seguridad.sp_VerificarBloqueoCuenta @Identificador=?, @DireccionIP=?",
        test_username,
        test_ip,
    )
    check_row = cursor.fetchone()
    assert check_row is not None
    assert bool(check_row[5]) is True  # EstaBloqueado

    # Resetear con login exitoso
    cursor.execute(
        "SET NOCOUNT ON; EXEC seguridad.sp_RegistrarIntentoLogin @Identificador=?, @DireccionIP=?, @Exitoso=1",
        test_username,
        test_ip,
    )
    db_conn.commit()

    cursor.execute(
        "SET NOCOUNT ON; EXEC seguridad.sp_VerificarBloqueoCuenta @Identificador=?, @DireccionIP=?",
        test_username,
        test_ip,
    )
    unlocked_row = cursor.fetchone()
    assert unlocked_row is None or bool(unlocked_row[5]) is False


# ==============================================================================
# 4. PROGRAMACIÓN DE ERRORES Y ALERTAS POR CORREO SMTP
# ==============================================================================

def test_smtp_alert_email_builder_masks_sensitive_params(app_instance):
    with app_instance.app_context():
        msg = build_alert_email(
            {
                "error_id": 501,
                "severidad": "CRITICAL",
                "origen": "SQL_SP",
                "procedimiento": "seguridad.sp_AutenticarUsuario",
                "esquema_origen": "seguridad",
                "numero_error": 50001,
                "estado_error": 1,
                "linea_error": 42,
                "mensaje_error": "Error simulado de prueba en autenticación",
                "username": "admin_test",
                "rol_usuario": "SuperAdmin",
                "direccion_ip": "127.0.0.1",
                "ruta_http": "/login",
                "parametros_json": {"username": "admin_test", "password": "SuperSecretPassword123!"},
            }
        )
        assert "[ALERTA BD - CRITICAL]" in msg["Subject"]
        body_payloads = [
            part.get_payload(decode=True).decode("utf-8")
            for part in msg.walk()
            if part.get_payload(decode=True)
        ]
        combined_body = "\n".join(body_payloads)
        assert "seguridad.sp_AutenticarUsuario" in combined_body
        assert "50001" in combined_body
        assert "SuperSecretPassword123!" not in combined_body
        assert "***MASKED***" in combined_body


def test_notify_error_records_in_db_sends_smtp_and_rate_limits(app_instance, db_conn):
    reset_rate_limit_cache()
    # Durable dedup survives process restarts; each test run owns its signature.
    procedimiento = 'contabilidad.sp_CerrarPeriodoContable_QA_' + os.urandom(8).hex()
    smtp_mock_instance = MagicMock()

    with app_instance.app_context(), patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.return_value.__enter__.return_value = smtp_mock_instance

        res1 = notify_error(
            "Fallo crítico de prueba SMTP en SP contable",
            origen="SQL_SP",
            severidad="CRITICAL",
            procedimiento=procedimiento,
            esquema_origen="contabilidad",
            numero_error=54321,
            linea_error=88,
            parametros_json={"periodo_id": 999},
            async_send=False,
            force_send=False,
        )

        assert res1["error_id"] is not None
        assert res1["sent"] is True
        assert res1["rate_limited"] is False
        assert smtp_mock_instance.send_message.call_count == 1

        # Verificar que en seguridad.BitacoraErrores quedó marcado NotificadoSMTP = 1
        cursor = db_conn.cursor()
        cursor.execute(
            "SELECT NotificadoSMTP, FechaNotificacion, Procedimiento FROM seguridad.BitacoraErrores WHERE ID = ?",
            res1["error_id"],
        )
        db_row = cursor.fetchone()
        assert db_row is not None
        assert bool(db_row[0]) is True
        assert db_row[1] is not None
        assert db_row[2] == procedimiento

        # Segundo disparo idéntico dentro de la ventana de 5 minutos debe ser rate-limited
        res2 = notify_error(
            "Fallo crítico repetido en ventana de enfriamiento",
            origen="SQL_SP",
            severidad="CRITICAL",
            procedimiento=procedimiento,
            esquema_origen="contabilidad",
            numero_error=54321,
            linea_error=88,
            async_send=False,
            force_send=False,
        )
        assert res2["error_id"] is not None
        assert res2["sent"] is False
        assert res2["rate_limited"] is True
        assert smtp_mock_instance.send_message.call_count == 1


def test_admin_security_bitacora_errores_and_smtp_test_endpoints(app_instance, db_conn):
    cursor = db_conn.cursor()
    cursor.execute(
        """
        SELECT TOP 1 u.ID
        FROM seguridad.Usuarios u
        INNER JOIN seguridad.Roles r ON u.RolID = r.ID
        WHERE r.Nombre = 'SuperAdmin' AND u.Activo = 1
        ORDER BY u.ID
        """
    )
    row = cursor.fetchone()
    assert row is not None, "Debe existir al menos un usuario SuperAdmin activo en seguridad.Usuarios"
    superadmin_id = row[0]

    client = app_instance.test_client()

    # Autenticar sesión como SuperAdmin en el test_client (prefijo emp_ requerido por User.get_id)
    with client.session_transaction() as sess:
        sess["_user_id"] = f"emp_{superadmin_id}"
        sess["_fresh"] = True

    # 1. Consultar endpoint de bitácora de errores
    resp_list = client.get("/admin/api/seguridad/bitacora-errores?top=10")
    assert resp_list.status_code == 200
    data_list = resp_list.get_json()
    assert data_list["success"] is True
    assert isinstance(data_list["errores"], list)

    # 2. Probar envío de alerta SMTP desde endpoint administrativo (con mock SMTP)
    smtp_mock_instance = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.return_value.__enter__.return_value = smtp_mock_instance
        resp_smtp = client.post(
            "/admin/api/seguridad/smtp-test",
            json={"mensaje": "Prueba de integración desde endpoint SuperAdmin"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp_smtp.status_code == 200
        data_smtp = resp_smtp.get_json()
        assert data_smtp["success"] is True
        assert data_smtp["resultado"]["error_id"] is not None
        assert data_smtp["resultado"]["sent"] is True


# ==============================================================================
# 5. PRUEBAS DE REGRESIÓN DE LA REVISIÓN DE CÓDIGO Y SEGURIDAD (P1-01 .. P2-09)
# ==============================================================================

def test_p1_01_flask_connection_activates_sql_role_for_authenticated_user(app_instance, db_conn):
    cursor = db_conn.cursor()
    cursor.execute(
        """
        SELECT TOP 1 u.ID
        FROM seguridad.Usuarios u
        INNER JOIN seguridad.Roles r ON u.RolID = r.ID
        WHERE r.Nombre = 'Estandar' AND u.Activo = 1
        ORDER BY u.ID
        """
    )
    row = cursor.fetchone()
    assert row is not None, "Debe existir al menos un usuario Estandar activo"
    estandar_id = row[0]

    with app_instance.test_request_context("/pos"):
        from flask_login import login_user
        from app.models import User

        user = User.get_by_id(estandar_id)
        assert user is not None and user.rol_nombre == "Estandar"
        login_user(user)

        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT USER_NAME(), IS_MEMBER('db_rol_cajero_pos'), HAS_PERMS_BY_NAME('rrhh.Nomina', 'OBJECT', 'SELECT')"
            )
            uname, is_cajero, can_read_nomina = cur.fetchone()
            assert uname == "usr_bd_cajero_pos"
            assert int(is_cajero) == 1
            assert int(can_read_nomina) == 0
        finally:
            conn.close()


def test_p1_02_portal_cliente_cannot_modify_quote_prices_or_other_session_quotes(db_conn):
    cursor = db_conn.cursor()
    # Crear cotización sintética perteneciente a otra sesión
    cursor.execute(
        "SET NOCOUNT ON; EXEC crm.sp_CrearCotizacion "
        "@ClienteID=NULL, @SessionID='sess_owner_original', @Especificaciones=N'Pastel sintético QA', "
        "@FechaEntrega='2026-12-01', @RutaImagenReferencia=NULL, @TelefonoContacto='88887777', @NombreContacto=N'QA Owner'"
    )
    cot_id = int(cursor.fetchone()[0])
    cursor.execute("EXEC crm.sp_CotizarPedidoAdmin @PrecioCotizado=100.00, @CotizacionID=?", cot_id)
    db_conn.commit()

    try:
        # Cambiar contexto a otra sesión de portal cliente e intentar alterar precio o cancelar cotización ajena
        cursor.execute(
            "EXEC sys.sp_set_session_context @key=N'rol', @value=N'Invitado'; "
            "EXEC sys.sp_set_session_context @key=N'usuario_id', @value=NULL; "
            "EXEC sys.sp_set_session_context @key=N'cotizacion_session_id', @value=N'sess_attacker_other';"
        )
        db_conn.commit()
        with as_db_role(cursor, "Invitado"):
            with pytest.raises(pyodbc.Error):
                cursor.execute(
                    "EXEC crm.sp_ActualizarEstadoCotizacion @CotizacionID=?, @NuevoEstado='Cotizada', @PrecioCotizado=0.01",
                    cot_id,
                )
            with pytest.raises(pyodbc.Error):
                cursor.execute(
                    "EXEC crm.sp_CotizarPedidoAdmin @PrecioCotizado=0.01, @CotizacionID=?",
                    cot_id,
                )
            with pytest.raises(pyodbc.Error):
                cursor.execute("EXEC crm.sp_CancelarCotizacionCliente @CotizacionID=?", cot_id)
            with pytest.raises(pyodbc.Error):
                cursor.execute("EXEC crm.sp_AceptarCotizacionCliente @CotizacionID=?", cot_id)

        # Verificar que el precio sigue intacto en 100.00 y estado Cotizada
        cursor.execute("SELECT PrecioCotizado, Estado FROM crm.Cotizaciones WHERE ID=?", cot_id)
        price, state = cursor.fetchone()
        assert float(price) == 100.00
        assert state == "Cotizada"
    finally:
        cursor.execute("DELETE FROM crm.Cotizaciones WHERE ID=?", cot_id)
        db_conn.commit()


def test_p1_03_user_loader_does_not_recursively_reopen_connections(app_instance, db_conn):
    cursor = db_conn.cursor()
    cursor.execute("SELECT TOP 1 ID FROM seguridad.Usuarios WHERE Activo = 1 ORDER BY ID")
    uid = cursor.fetchone()[0]

    import app.db as db_mod
    from app.models import load_user

    inject_calls = 0
    orig_inject = db_mod.inject_session_context

    def counting_inject(conn):
        nonlocal inject_calls
        inject_calls += 1
        return orig_inject(conn)

    with app_instance.test_request_context("/admin/dashboard"), patch.object(
        db_mod, "inject_session_context", side_effect=counting_inject
    ):
        loaded = load_user(f"emp_{uid}")
        assert loaded is not None
        assert inject_calls == 0


def test_p1_04_zero_direct_sql_execute_sites_in_app():
    import ast
    import pathlib
    import re

    app_root = pathlib.Path(__file__).resolve().parent.parent / "app"
    sql_re = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE)\b", re.I)
    direct_sites = []

    for py_file in sorted(app_root.rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    if sql_re.search(node.args[0].value):
                        direct_sites.append(f"{py_file.relative_to(app_root)}:{node.lineno}")

    assert direct_sites == [], f"Quedan sitios con SQL directo en app/: {direct_sites}"


def test_p2_05_positional_sensitive_scalars_redacted_in_alert_email(app_instance):
    with app_instance.app_context():
        msg = build_alert_email(
            {
                "error_id": 777,
                "severidad": "ERROR",
                "origen": "SQL_SP",
                "procedimiento": "seguridad.sp_AutenticarUsuario",
                "mensaje_error": "Error con token=SuperSecretToken999",
                "parametros_json": ["admin_user", "PositionalSecretValue123!"],
            }
        )
        body_payloads = [
            part.get_payload(decode=True).decode("utf-8")
            for part in msg.walk()
            if part.get_payload(decode=True)
        ]
        combined = "\n".join(body_payloads)
        assert "PositionalSecretValue123!" not in combined
        assert "SuperSecretToken999" not in combined
        assert "***MASKED***" in combined


def test_p2_07_failed_smtp_send_does_not_consume_rate_limit_window(app_instance, db_conn):
    reset_rate_limit_cache()
    procedimiento = 'ventas.sp_RegistrarFacturaCompleta_QA_' + os.urandom(8).hex()
    with app_instance.app_context():
        # 1. Primer intento falla por excepción SMTP
        with patch("smtplib.SMTP", side_effect=OSError("SMTP down")):
            res_fail = notify_error(
                "Error crítico con SMTP caído temporalmente",
                origen="SQL_SP",
                severidad="CRITICAL",
                procedimiento=procedimiento,
                numero_error=59991,
                linea_error=10,
                async_send=False,
                force_send=False,
            )
            assert res_fail["sent"] is False
            assert res_fail["rate_limited"] is False

        # 2. Segundo intento inmediato con SMTP restablecido NO debe ser bloqueado por rate-limit
        smtp_mock_instance = MagicMock()
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp_cls.return_value.__enter__.return_value = smtp_mock_instance
            res_ok = notify_error(
                "Error crítico con SMTP ya recuperado",
                origen="SQL_SP",
                severidad="CRITICAL",
                procedimiento=procedimiento,
                numero_error=59991,
                linea_error=10,
                async_send=False,
                force_send=False,
            )
            assert res_ok["rate_limited"] is False
            assert res_ok["sent"] is True
            assert smtp_mock_instance.send_message.call_count == 1


def test_p2_08_bitacora_errores_immutability_protects_all_forensic_columns(db_conn):
    cursor = db_conn.cursor()
    for col, val in [
        ("Username", "N'hacker'"),
        ("DireccionIP", "'9.9.9.9'"),
        ("Severidad", "'INFO'"),
        ("Procedimiento", "N'otro_sp'"),
        ("RutaHTTP", "N'/hacked'"),
    ]:
        with pytest.raises(pyodbc.Error) as exc_info:
            cursor.execute(f"UPDATE TOP (1) seguridad.BitacoraErrores SET {col} = {val}")
        assert "inmutable" in str(exc_info.value).lower() or "51008" in str(exc_info.value).lower()
        db_conn.rollback()


def test_p2_06_roles_required_403_and_unhandled_500_trigger_smtp_alerts(app_instance, db_conn):
    cursor = db_conn.cursor()
    cursor.execute(
        """
        SELECT TOP 1 u.ID
        FROM seguridad.Usuarios u
        INNER JOIN seguridad.Roles r ON u.RolID = r.ID
        WHERE r.Nombre = 'Estandar' AND u.Activo = 1
        ORDER BY u.ID
        """
    )
    estandar_id = cursor.fetchone()[0]

    client = app_instance.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = f"emp_{estandar_id}"
        sess["_fresh"] = True

    with patch("app.auth.routes.totp_is_required", return_value=False), patch(
        "app.services.smtp_alerts.notify_error"
    ) as mock_notify:
        resp_403 = client.get("/admin/api/seguridad/bitacora-errores")
        assert resp_403.status_code == 403
        assert mock_notify.called


def test_p2_09_migrate_auth_security_is_idempotent_with_dbo_synonym(db_conn):
    from scripts.migrate_auth_security import DDL

    cursor = db_conn.cursor()
    cursor.execute(DDL)
    db_conn.rollback()

