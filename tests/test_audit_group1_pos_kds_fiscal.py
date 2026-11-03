"""Pruebas de remediación para Grupo 1 (POS, Arqueos, Encargos/KDS, Cotizaciones y Anulaciones Fiscales).

Cubre los hallazgos L01, L02, L03, L13, L15 y L28 tanto en rutas Flask como en procedimientos SQL Server.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from inspect import unwrap
import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pyodbc
import pytest
from flask import Flask
from flask_wtf.csrf import generate_csrf

from app import create_app
from app.models import User
from app.pos import routes as pos_routes
from app.admin import routes_pos, routes_fiscal
from app.monitor import routes as monitor_routes
from app.services.fiscal_service import calculate_sale
from app.services.contabilidad_service import ContabilidadService
from app.qa_safety import connect_qa


class SavepointRouteConn:
    """Envuelve una conexión pyodbc usando SAVE TRANSACTION para que ninguna prueba persista filas."""

    def __init__(self, connection):
        self.connection = connection
        self.cur = connection.cursor()
        self.cur.execute('SAVE TRANSACTION grp1_route')

    def cursor(self):
        return self.cur

    def commit(self):
        pass

    def rollback(self):
        self.cur.execute('ROLLBACK TRANSACTION grp1_route')

    def close(self):
        self.cur.close()


@pytest.fixture
def qa_sql():
    conn_str = os.environ.get('TEST_DB_CONNECTION_STRING')
    if not conn_str:
        pytest.skip('Se requiere TEST_DB_CONNECTION_STRING hacia PanaderiaQA_Prevalidacion_20261015')
    conn = connect_qa(pyodbc.connect, conn_str)
    cur = conn.cursor()
    marker = 'G1_' + uuid4().hex[:12].upper()
    role_id = cur.execute("SELECT ID FROM seguridad.Roles WHERE Nombre = 'Admin'").fetchone()[0]
    user_id = cur.execute(
        "INSERT INTO seguridad.Usuarios(NombreCompleto, Username, PasswordHash, RolID, Activo) "
        "OUTPUT INSERTED.ID VALUES(?, ?, 'synthetic-hash', ?, 1)",
        marker, marker, role_id,
    ).fetchone()[0]
    shift_id = cur.execute(
        "INSERT INTO ventas.TurnosCaja(UsuarioID, FechaApertura, Cerrado) OUTPUT INSERTED.ID VALUES(?, GETDATE(), 0)",
        user_id,
    ).fetchone()[0]
    cat_id = cur.execute("SELECT TOP 1 ID FROM catalogo.Categorias ORDER BY ID").fetchone()[0]
    prod_id = cur.execute(
        "INSERT INTO catalogo.Productos(Nombre, CategoriaID, PrecioBase, EsFicticio, PorcentajeDescuento, Activo, TasaIVA) "
        "OUTPUT INSERTED.ID VALUES(?, ?, 100.00, 0, 0, 1, 0)",
        f'Prod {marker}', cat_id,
    ).fetchone()[0]
    cur.execute("EXEC sys.sp_set_session_context @key=N'usuario_id', @value=?", user_id)
    try:
        yield conn, cur, user_id, shift_id, prod_id, marker
    finally:
        conn.rollback()
        conn.close()


def _make_pos_client(monkeypatch, conn, user_id, role='Admin'):
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-group1-secret'
    app.add_url_rule('/api/factura', view_func=unwrap(pos_routes.registrar_factura), methods=['POST'])
    app.add_url_rule('/admin/api/arqueo/etapa1-conteo', view_func=unwrap(routes_pos.arqueo_etapa1_conteo), methods=['POST'])
    app.add_url_rule('/api/seguimiento/<codigo>/estado', view_func=unwrap(monitor_routes.actualizar_estado), methods=['PUT'])
    actor = SimpleNamespace(id=user_id, rol_nombre=role, nombre_completo='Tester G1', es_invitado=False)
    monkeypatch.setattr(pos_routes, 'get_db_connection', lambda: SavepointRouteConn(conn))
    monkeypatch.setattr(routes_pos, 'get_db_connection', lambda: SavepointRouteConn(conn))
    monkeypatch.setattr(monitor_routes, 'get_db_connection', lambda: SavepointRouteConn(conn))
    monkeypatch.setattr(pos_routes, 'current_user', actor)
    monkeypatch.setattr(routes_pos, 'current_user', actor)
    monkeypatch.setattr(monitor_routes, 'current_user', actor)
    from app.services import smtp_alerts
    monkeypatch.setattr(smtp_alerts, 'notify_error', lambda *a, **k: False)
    return app.test_client()


# ============================================================================
# L01: Validación estricta de monto_recibido en POS (/api/factura)
# ============================================================================

def test_l01_encargo_rejects_monto_recibido_below_advance(qa_sql, monkeypatch):
    conn, cur, user_id, shift_id, prod_id, marker = qa_sql
    client = _make_pos_client(monkeypatch, conn, user_id)
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    # Escenario exacto L01: total C$100, adelanto C$50, monto_recibido=C$1
    payload = {
        'clave_solicitud': uuid4().hex,
        'carrito': [{'id': prod_id, 'cantidad': 1}],
        'es_encargo': True,
        'encargo_detalles': {
            'adelanto': 50,
            'saldo': 50,
            'metodo_adelanto': 'Efectivo',
            'monto_recibido': 1,
            'fecha_entrega': tomorrow,
            'nombre_cliente': 'Cliente L01',
            'telefono': '88887777',
        },
    }
    resp = client.post('/api/factura', json=payload)
    assert resp.status_code == 400, resp.json
    assert 'menor' in resp.json['error'].lower()
    assert cur.execute("SELECT COUNT(*) FROM ventas.Facturas WHERE ClaveSolicitud = ?", payload['clave_solicitud']).fetchone()[0] == 0

    # También en venta directa con monto_recibido=1 para total=100
    direct_payload = {
        'clave_solicitud': uuid4().hex,
        'carrito': [{'id': prod_id, 'cantidad': 1}],
        'es_encargo': False,
        'metodo_pago': 'Efectivo',
        'monto_recibido': 1,
    }
    resp_direct = client.post('/api/factura', json=direct_payload)
    assert resp_direct.status_code == 400, resp_direct.json
    assert 'menor' in resp_direct.json['error'].lower()

    # Con monto_recibido válido (C$100 para adelanto de C$50), registra pago neto C$50 y cambio C$50
    valid_payload = {
        **payload,
        'clave_solicitud': uuid4().hex,
        'encargo_detalles': {**payload['encargo_detalles'], 'monto_recibido': 100},
    }
    resp_ok = client.post('/api/factura', json=valid_payload)
    assert resp_ok.status_code == 200, resp_ok.json
    assert resp_ok.json['factura']['cambio'] == 50.0
    assert resp_ok.json['factura']['pagos'][0]['monto'] == 50.0


# ============================================================================
# L02: Congruencia de denominaciones y efectivo_contado en Arqueo Etapa 1
# ============================================================================

def test_l02_arqueo_rejects_incongruent_denominations_and_invalid_entries(qa_sql, monkeypatch):
    conn, cur, user_id, shift_id, prod_id, marker = qa_sql
    client = _make_pos_client(monkeypatch, conn, user_id)

    # Escenario exacto L02: efectivo_contado=0 con 5 billetes de C$500 (C$2,500)
    resp = client.post('/admin/api/arqueo/etapa1-conteo', json={
        'efectivo_contado': 0,
        'transferencias_contadas': 0,
        'dolares_contados': 0,
        'denominaciones': [{'tipo': 'NIO', 'denominacion': 500, 'cantidad': 5}],
    })
    assert resp.status_code == 400, resp.json
    assert 'incongruencia' in resp.json['error'].lower()
    assert cur.execute("SELECT COUNT(*) FROM ventas.ArqueoCaja WHERE TurnoID = ?", shift_id).fetchone()[0] == 0

    # Denominación inexistente (C$333)
    resp_bad_denom = client.post('/admin/api/arqueo/etapa1-conteo', json={
        'efectivo_contado': 333,
        'denominaciones': [{'tipo': 'NIO', 'denominacion': 333, 'cantidad': 1}],
    })
    assert resp_bad_denom.status_code == 400

    # Cantidad negativa o fraccionaria o moneda inválida
    for invalid_denom in (
        [{'tipo': 'NIO', 'denominacion': 500, 'cantidad': -1}],
        [{'tipo': 'NIO', 'denominacion': 500, 'cantidad': 1.5}],
        [{'tipo': 'EUR', 'denominacion': 500, 'cantidad': 1}],
    ):
        r = client.post('/admin/api/arqueo/etapa1-conteo', json={'denominaciones': invalid_denom})
        assert r.status_code == 400

    # Desglose congruente: 5 billetes de C$500 -> C$2,500
    resp_ok = client.post('/admin/api/arqueo/etapa1-conteo', json={
        'efectivo_contado': 2500,
        'transferencias_contadas': 0,
        'dolares_contados': 0,
        'denominaciones': [{'tipo': 'NIO', 'denominacion': 500, 'cantidad': 5}],
    })
    assert resp_ok.status_code == 200, resp_ok.json
    assert resp_ok.json['arqueo']['efectivo_contado'] == 2500.0


# ============================================================================
# L13: Consistencia de efectivo esperado del turno POS (gaveta vs Caja General)
# ============================================================================

def test_l13_shift_cash_summary_tracks_pos_drawer_and_subtracts_refunds(qa_sql, monkeypatch):
    conn, cur, user_id, shift_id, prod_id, marker = qa_sql
    client = _make_pos_client(monkeypatch, conn, user_id)

    # 1. Registrar venta en efectivo de C$100 en el turno
    sale_resp = client.post('/api/factura', json={
        'clave_solicitud': uuid4().hex,
        'carrito': [{'id': prod_id, 'cantidad': 1}],
        'es_encargo': False,
        'pagos_multiples': [{'metodo': 'Efectivo', 'monto': 100}],
    })
    assert sale_resp.status_code == 200, sale_resp.json
    factura_id = sale_resp.json['factura']['id']

    # 2. Registrar un egreso privado de oficina (Caja General) y verificar que NO altera la gaveta del turno POS
    cur.execute(
        "INSERT INTO contabilidad.EgresosPrivados(Concepto, Monto, UsuarioID, Fecha) VALUES('Gasto oficina QA', 40.00, ?, GETDATE())",
        user_id,
    )
    resumen = cur.execute("EXEC ventas.sp_ObtenerResumenTurnoCaja @TurnoID = ?", shift_id).fetchall()[0]
    while cur.nextset():
        pass
    assert Decimal(str(resumen.EfectivoCordobasSistema)) == Decimal('100.00')

    # 3. Registrar devolución por anulación en la misma gaveta del turno (C$-100) y verificar que el efectivo esperado baja a C$0
    cur.execute(
        "EXEC ventas.sp_InsertarPagoDevolucionAnulacion ?, 'Efectivo', -100.00, 'Devolución por anulación QA'",
        factura_id,
    )
    while cur.nextset():
        pass
    resumen_post = cur.execute("EXEC ventas.sp_ObtenerResumenTurnoCaja @TurnoID = ?", shift_id).fetchall()[0]
    while cur.nextset():
        pass
    assert Decimal(str(resumen_post.EfectivoCordobasSistema)) == Decimal('0.00')

    arqueo_resp = client.post('/admin/api/arqueo/etapa1-conteo', json={
        'efectivo_contado': 0,
        'transferencias_contadas': 0,
        'dolares_contados': 0,
    })
    assert arqueo_resp.status_code == 200, arqueo_resp.json
    assert arqueo_resp.json['arqueo']['efectivo_sistema'] == 0.0
    assert arqueo_resp.json['arqueo']['diferencia_efectivo'] == 0.0
    assert arqueo_resp.json['arqueo']['origen_efectivo_sistema'] == 'gaveta_turno_pos'
    assert arqueo_resp.json['arqueo']['egresos_caja_general_excluidos'] is True


# ============================================================================
# L03: Máquina de estados estricta en KDS / Encargos (sin retrocesos desde Entregado)
# ============================================================================

def test_l03_kds_rejects_backward_transitions_and_duplicate_balance_payments(qa_sql, monkeypatch):
    conn, cur, user_id, shift_id, prod_id, marker = qa_sql
    client = _make_pos_client(monkeypatch, conn, user_id)
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    # Crear encargo con total C$100 y adelanto C$50
    sale_resp = client.post('/api/factura', json={
        'clave_solicitud': uuid4().hex,
        'carrito': [{'id': prod_id, 'cantidad': 1}],
        'es_encargo': True,
        'encargo_detalles': {
            'adelanto': 50,
            'saldo': 50,
            'metodo_adelanto': 'Efectivo',
            'monto_recibido': 50,
            'fecha_entrega': tomorrow,
            'nombre_cliente': 'Cliente L03',
            'telefono': '88886666',
        },
    })
    assert sale_resp.status_code == 200, sale_resp.json
    codigo = sale_resp.json['factura']['codigo_seguimiento']
    factura_id = sale_resp.json['factura']['id']

    # Pendiente -> Entregado (cobra el saldo de C$50 una única vez)
    r_deliver = client.put(f'/api/seguimiento/{codigo}/estado', json={'estado': 'Entregado'})
    assert r_deliver.status_code == 200, r_deliver.json

    # Intentar regresar Entregado -> Pendiente, En Proceso o Listo debe rechazarse con 409
    for target_state in ('Pendiente', 'En Proceso', 'Listo'):
        r_back = client.put(f'/api/seguimiento/{codigo}/estado', json={'estado': target_state})
        assert r_back.status_code == 409, r_back.json

    # También a nivel de SP directo en SQL Server debe lanzar THROW 51034
    with pytest.raises(pyodbc.Error, match='51034'):
        cur.execute("EXEC produccion.sp_ActualizarEstadoEncargoCompare 'Pendiente', ?, 'Entregado'", codigo)

    # El estado sigue siendo Entregado y el total pagado es exactamente C$100 (sin duplicados)
    assert cur.execute("SELECT Estado FROM ventas.Encargos WHERE FacturaID = ?", factura_id).fetchone()[0] == 'Entregado'
    assert Decimal(str(cur.execute("SELECT SUM(Monto) FROM ventas.Pagos WHERE FacturaID = ?", factura_id).fetchone()[0])) == Decimal('100.00')

    # Intentar insertar otro pago de saldo vía SP cuando ya está pagado lanza THROW 51035
    with pytest.raises(pyodbc.Error, match='51035'):
        cur.execute(
            "EXEC ventas.sp_InsertarPagoSaldoEncargo ?, 'Efectivo', 50.00, 'Intento duplicado', ?, NULL, ?, ?",
            factura_id, datetime.now(), shift_id, user_id,
        )


# ============================================================================
# L15: Uso único de cotización al convertir a factura
# ============================================================================

def test_l15_quote_can_only_be_billed_once(qa_sql, monkeypatch):
    conn, cur, user_id, shift_id, prod_id, marker = qa_sql
    client = _make_pos_client(monkeypatch, conn, user_id)

    cot_id = cur.execute(
        "INSERT INTO crm.Cotizaciones(Especificaciones, FechaEntrega, TelefonoContacto, PrecioCotizado, Estado, NombreContacto) "
        "OUTPUT INSERTED.ID VALUES('Pastel L15', DATEADD(day, 2, GETDATE()), '88885555', 250.00, 'Aceptada', 'Cliente L15')"
    ).fetchone()[0]

    # 1. No permite duplicar la misma cotización en dos líneas del mismo carrito
    dup_cart_resp = client.post('/api/factura', json={
        'clave_solicitud': uuid4().hex,
        'carrito': [
            {'id': f'custom_{cot_id}', 'cantidad': 1},
            {'id': f'custom_{cot_id}', 'cantidad': 1},
        ],
        'pagos_multiples': [{'metodo': 'Efectivo', 'monto': 500}],
    })
    assert dup_cart_resp.status_code == 400, dup_cart_resp.json

    # 2. Primera conversión a factura tiene éxito y pasa la cotización a estado 'Facturada'
    first_resp = client.post('/api/factura', json={
        'clave_solicitud': uuid4().hex,
        'carrito': [{'id': f'custom_{cot_id}', 'cantidad': 1}],
        'pagos_multiples': [{'metodo': 'Efectivo', 'monto': 250}],
    })
    assert first_resp.status_code == 200, first_resp.json
    assert cur.execute("SELECT Estado FROM crm.Cotizaciones WHERE ID = ?", cot_id).fetchone()[0] == 'Facturada'

    # 3. Segunda conversión con la misma cotización es rechazada con HTTP 400/409
    second_resp = client.post('/api/factura', json={
        'clave_solicitud': uuid4().hex,
        'carrito': [{'id': f'custom_{cot_id}', 'cantidad': 1}],
        'pagos_multiples': [{'metodo': 'Efectivo', 'monto': 250}],
    })
    assert second_resp.status_code in (400, 409), second_resp.json


# ============================================================================
# L28: Marca temporal comercial de Nicaragua idéntica en factura anulada,
#      asiento original anulado y asiento de reversión
# ============================================================================

def test_l28_void_invoice_uses_identical_business_timestamp_across_invoice_and_journals(qa_sql, monkeypatch):
    conn, cur, user_id, shift_id, prod_id, marker = qa_sql
    pos_client = _make_pos_client(monkeypatch, conn, user_id)

    # Emitir factura con su asiento contable
    sale_resp = pos_client.post('/api/factura', json={
        'clave_solicitud': uuid4().hex,
        'carrito': [{'id': prod_id, 'cantidad': 1}],
        'pagos_multiples': [{'metodo': 'Efectivo', 'monto': 100}],
    })
    assert sale_resp.status_code == 200, sale_resp.json
    factura_id = sale_resp.json['factura']['id']
    asiento_original_id = sale_resp.json['factura']['asiento_id']

    # Fijar business_now() a una marca temporal determinista para comprobar igualdad exacta
    fixed_void_time = datetime(2026, 10, 25, 15, 42, 19)
    monkeypatch.setattr(routes_fiscal, 'business_now', lambda: fixed_void_time)

    class Config:
        TESTING = True
        SECRET_KEY = 'l28-test-secret'
        WTF_CSRF_ENABLED = False

    app = create_app(Config)
    actor = User(user_id, marker, 'Admin L28', 1, 'Admin')
    monkeypatch.setattr(app.login_manager, '_user_callback', lambda _: actor)
    monkeypatch.setattr(routes_fiscal, 'get_db_connection', lambda: SavepointRouteConn(conn))
    from app.services import smtp_alerts
    monkeypatch.setattr(smtp_alerts, 'notify_error', lambda *a, **k: False)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = actor.get_id()
        sess['_fresh'] = True

    void_resp = client.post(
        f'/admin/fiscal/facturas/{factura_id}/anular',
        data={'motivo': 'Anulación de auditoría L28'},
    )
    assert void_resp.status_code == 302

    fecha_anulacion_factura = cur.execute(
        "SELECT FechaAnulacion FROM ventas.Facturas WHERE ID = ?", factura_id
    ).fetchone()[0]
    estado_orig, fecha_anulacion_asiento_orig = cur.execute(
        "SELECT Estado, FechaAnulacion FROM contabilidad.AsientosDiario WHERE ID = ?", asiento_original_id
    ).fetchone()
    fecha_asiento_reverso = cur.execute(
        "SELECT Fecha FROM contabilidad.AsientosDiario WHERE ReferenciaExterna = ?",
        f'REV-{asiento_original_id}',
    ).fetchone()[0]

    assert estado_orig == 'Anulado'
    assert fecha_anulacion_factura == fixed_void_time
    assert fecha_anulacion_asiento_orig == fixed_void_time
    assert fecha_asiento_reverso == fixed_void_time
