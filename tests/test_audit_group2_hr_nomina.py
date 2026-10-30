"""Pruebas de remediación Grupo 2: RRHH, Nómina, Pago de Planilla, Vales, Asistencia y Biometría (L04, L05, L12, L17, L19)."""
from datetime import date, datetime, time
from decimal import Decimal
from inspect import unwrap
from types import SimpleNamespace
from uuid import uuid4
import json
import os
import re
from pathlib import Path

import numpy as np
import pyodbc
import pytest
from flask import Flask

from app import create_app
from app.db import as_db_role
from app.models import User
from app.qa_safety import connect_qa
from app.services.hr_calculations import (
    absent_dates,
    resolver_horario_y_clasificar_asistencia,
)


def _qa_conn():
    conn_str = os.environ.get('TEST_DB_CONNECTION_STRING')
    if not conn_str:
        pytest.skip('Requiere TEST_DB_CONNECTION_STRING apuntando a base QA.')
    return connect_qa(pyodbc.connect, conn_str)


# ==============================================================================
# 1. CSS & Plantillas sin estilos inline (rrhh.html y colilla_pago.html)
# ==============================================================================

def test_rrhh_and_colilla_templates_have_no_inline_styles():
    root = Path(__file__).resolve().parents[1]
    for rel in ('templates/admin/rrhh.html', 'templates/admin/colilla_pago.html'):
        text = (root / rel).read_text(encoding='utf-8')
        assert not re.search(r'<style\b|\sstyle=', text), f'Estilo inline detectado en {rel}'


# ==============================================================================
# 2. L04: Nómina — No descontar días futuros del mes en curso y bloquear meses futuros
# ==============================================================================

def test_l04_absent_dates_never_counts_days_after_as_of_date():
    # Mes de octubre 2026 calculado el 25/10/2026: los días 26-31 oct no deben ser ausencias
    asistencias = [
        date(2026, 10, d)
        for d in range(1, 26)
        if date(2026, 10, d).weekday() != 6
    ]
    ausencias = absent_dates(
        start=date(2026, 10, 1),
        end=date(2026, 10, 31),
        attended=asistencias,
        licenses=[],
        as_of_date=date(2026, 10, 25),
    )
    assert ausencias == set()

    # Si faltó sólo el sábado 24/10/2026, sólo debe contar 1 ausencia (y ninguna del 26 al 31)
    asistencias_sin_24 = [d for d in asistencias if d != date(2026, 10, 24)]
    ausencias_parcial = absent_dates(
        start=date(2026, 10, 1),
        end=date(2026, 10, 31),
        attended=asistencias_sin_24,
        licenses=[],
        as_of_date=date(2026, 10, 25),
    )
    assert ausencias_parcial == {date(2026, 10, 24)}
    assert all(d <= date(2026, 10, 25) for d in ausencias_parcial)


def test_l04_obtener_dias_ausentes_auto_clips_to_as_of_date(monkeypatch):
    from app.admin import routes_hr

    monkeypatch.setattr(routes_hr, 'business_now', lambda: datetime(2026, 10, 25, 10, 0, 0))

    class FakeCursor:
        def __init__(self):
            self.last_sql = ''
            # Empleado asistió todos los días hábiles del 1 al 25 de octubre
            self.attended = [
                date(2026, 10, d)
                for d in range(1, 26)
                if date(2026, 10, d).weekday() != 6
            ]

        def execute(self, sql, *args):
            self.last_sql = sql
            return self

        def fetchone(self):
            if 'FROM Empleados' in self.last_sql:
                return SimpleNamespace(FechaIngreso=date(2025, 1, 1), FechaEgreso=None)
            if 'COUNT(*) FROM Asistencia' in self.last_sql:
                return (len(self.attended),)
            raise AssertionError(f'SQL inesperado: {self.last_sql}')

        def fetchall(self):
            if 'FROM Asistencia' in self.last_sql:
                return [SimpleNamespace(Fecha=d) for d in self.attended]
            if 'FROM LicenciasEmpleados' in self.last_sql:
                return []
            raise AssertionError(f'SQL inesperado: {self.last_sql}')

    dias = routes_hr.obtener_dias_ausentes_auto(FakeCursor(), 1, '2026-10-01', '2026-10-31')
    assert dias == 0


def test_l04_blocks_future_month_in_individual_and_batch_payroll(monkeypatch):
    from app.admin import routes_hr

    monkeypatch.setattr(routes_hr, 'business_now', lambda: datetime(2026, 10, 25, 12, 0, 0))
    conn = _qa_conn()
    cursor = conn.cursor()
    marker = uuid4().hex[:10]
    try:
        cursor.execute(
            'EXEC rrhh.sp_GuardarPerfilPuesto ?,?,?,?,?,?',
            f'QA Cargo L04 {marker}', 'Perfil', 'Obligaciones', 'Competencias', 1, '127.0.0.1',
        )
        cursor.execute(
            'EXEC rrhh.sp_CrearEmpleado ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?',
            f'QA Emp L04 {marker}', f'L04-{marker}', None, None, None, None,
            None, None, f'QA Cargo L04 {marker}', date(2026, 1, 1), 'Indefinido',
            None, 'Diurna', 15000, 'Mensual', 1, None, None, None, None,
        )
        emp_id = cursor.fetchone()[0]

        class BorrowedConn:
            def cursor(self): return conn.cursor()
            def commit(self): pass
            def rollback(self): pass
            def close(self): pass

        monkeypatch.setattr(routes_hr, 'get_db_connection', BorrowedConn)
        monkeypatch.setattr(routes_hr, 'current_user', SimpleNamespace(id=1, rol_nombre='Admin'))

        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY='qa-l04')
        app.add_url_rule('/ind', view_func=unwrap(routes_hr.calcular_nomina), methods=['POST'])
        app.add_url_rule('/batch', view_func=unwrap(routes_hr.calcular_nomina_batch), methods=['POST'])
        client = app.test_client()

        with as_db_role(cursor, 'Admin'):
            res_ind = client.post('/ind', json={
                'empleado_id': emp_id,
                'periodo_inicio': '2026-11-01',
                'periodo_fin': '2026-11-30',
            })
            assert res_ind.status_code == 400
            assert 'futuro' in res_ind.get_json()['error'].lower()

            res_batch = client.post('/batch', json={
                'periodo_inicio': '2026-11-01',
                'periodo_fin': '2026-11-30',
            })
            assert res_batch.status_code == 400
            assert 'futuro' in res_batch.get_json()['error'].lower()

        count_nom = cursor.execute(
            "SELECT COUNT(*) FROM rrhh.Nomina WHERE EmpleadoID = ? AND PeriodoInicio = '2026-11-01'",
            emp_id,
        ).fetchone()[0]
        assert count_nom == 0
    finally:
        conn.rollback()
        conn.close()


# ==============================================================================
# 3. L05: Separación Contabilizada vs Pagada, colilla veraz y desembolso con control de fondos
# ==============================================================================

def test_l05_colilla_distinguishes_contabilizada_vs_pagada():
    class Config:
        TESTING = True
        SECRET_KEY = 'l05-colilla'
        WTF_CSRF_ENABLED = False
        SQL_SERVER_CONNECTION_STRING = ''

    app = create_app(Config)
    base_nomina = dict(
        ID=77,
        NombreCompleto='María López',
        Cedula='001-010190-0001A',
        Cargo='Panadera',
        NumeroINSS='1234567',
        PeriodoInicio=date(2026, 9, 1),
        PeriodoFin=date(2026, 9, 30),
        SalarioBruto=Decimal('12000.00'),
        HorasExtras=Decimal('0.00'),
        MontoHorasExtras=Decimal('0.00'),
        OtrosIngresos=Decimal('0.00'),
        TotalDevengado=Decimal('12000.00'),
        INSSLaboral=Decimal('840.00'),
        IRMensual=Decimal('174.00'),
        PensionAlimenticia=Decimal('0.00'),
        ValesDescontados=Decimal('0.00'),
        TotalDeducciones=Decimal('1014.00'),
        SalarioNeto=Decimal('10986.00'),
    )

    with app.test_request_context():
        from flask import render_template
        html_contabilizada = render_template(
            'admin/colilla_pago.html',
            nomina=SimpleNamespace(**base_nomina, Estado='Contabilizada'),
            datetime=datetime,
            aguinaldo_detalles=None,
        )
        assert 'COMPROBANTE DE LIQUIDACIÓN DE NÓMINA (CONTABILIZADA — PENDIENTE DE DESEMBOLSO)' in html_contabilizada
        assert 'RECIBO OFICIAL DE PAGO DE NÓMINA — OBLIGACIÓN CANCELADA' not in html_contabilizada

        html_pagada = render_template(
            'admin/colilla_pago.html',
            nomina=SimpleNamespace(**base_nomina, Estado='Pagada'),
            datetime=datetime,
            aguinaldo_detalles=None,
        )
        assert 'RECIBO OFICIAL DE PAGO DE NÓMINA — OBLIGACIÓN CANCELADA' in html_pagada
        assert 'COMPROBANTE DE LIQUIDACIÓN DE NÓMINA (CONTABILIZADA — PENDIENTE DE DESEMBOLSO)' not in html_pagada


def test_l05_disbursement_insufficient_funds_then_funded_payment_and_idempotency(monkeypatch):
    from app.admin import routes_hr
    from app.services.contabilidad_service import ContabilidadService

    monkeypatch.setattr(routes_hr, 'business_now', lambda: datetime(2026, 10, 25, 14, 0, 0))
    conn = _qa_conn()
    cursor = conn.cursor()
    marker = uuid4().hex[:10]
    try:
        cursor.execute(
            'EXEC rrhh.sp_GuardarPerfilPuesto ?,?,?,?,?,?',
            f'QA Cargo L05 {marker}', 'Perfil', 'Obligaciones', 'Competencias', 1, '127.0.0.1',
        )
        cursor.execute(
            'EXEC rrhh.sp_CrearEmpleado ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?',
            f'QA Emp L05 {marker}', f'L05-{marker}', None, None, None, None,
            None, None, f'QA Cargo L05 {marker}', date(2026, 1, 1), 'Indefinido',
            None, 'Diurna', 12000, 'Mensual', 1, None, None, None, None,
        )
        emp_id = cursor.fetchone()[0]

        class BorrowedConn:
            def cursor(self): return conn.cursor()
            def commit(self): pass
            def rollback(self): pass
            def close(self): pass

        monkeypatch.setattr(routes_hr, 'get_db_connection', BorrowedConn)
        monkeypatch.setattr(routes_hr, 'current_user', SimpleNamespace(id=1, rol_nombre='Admin'))

        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY='qa-l05')
        app.add_url_rule('/calc', view_func=unwrap(routes_hr.calcular_nomina), methods=['POST'])
        app.add_url_rule('/pagar/<int:nomina_id>', view_func=unwrap(routes_hr.pagar_nomina), methods=['POST'])
        client = app.test_client()

        with as_db_role(cursor, 'Admin'):
            res_calc = client.post('/calc', json={
                'empleado_id': emp_id,
                'periodo_inicio': '2026-09-01',
                'periodo_fin': '2026-09-30',
                'dias_ausentes': 0,
            })
            assert res_calc.status_code == 200, res_calc.get_json()
            nomina_id = res_calc.get_json()['nomina']['id']
            salario_neto = Decimal(str(res_calc.get_json()['nomina']['salario_neto']))

        # Verificar que inicialmente quedó en estado Contabilizada
        estado_inicial = cursor.execute(
            'SELECT Estado FROM rrhh.Nomina WHERE ID = ?', nomina_id
        ).fetchone()[0]
        assert estado_inicial == 'Contabilizada'

        # 1) Intento de pago sin fondos suficientes en Bancos MN (1.1.01.004)
        cursor.execute(
            "EXEC contabilidad.sp_ObtenerSaldoDisponibleCuentaBloqueo ?",
            ContabilidadService.BANCOS_MN,
        )
        saldo_bancos = Decimal(str(cursor.fetchone()[0]))
        if saldo_bancos >= salario_neto:
            # Drenar temporalmente el exceso en la transacción de prueba para simular saldo insuficiente
            exceso = (saldo_bancos - salario_neto) + Decimal('500.00')
            ContabilidadService.crear_asiento(
                cursor=cursor,
                descripcion='Ajuste prueba drenaje bancos L05',
                detalles=[
                    (ContabilidadService.CAPITAL_SOCIAL, exceso, Decimal('0.00'), 'Drenaje prueba'),
                    (ContabilidadService.BANCOS_MN, Decimal('0.00'), exceso, 'Drenaje prueba'),
                ],
                usuario_id=1,
                tipo_comprobante='AJ',
                referencia_externa=f'DREN-L05-{marker}',
                tipo_documento='Ajuste',
                fecha=datetime(2026, 9, 30, 12, 0, 0),
            )

        with as_db_role(cursor, 'Admin'):
            res_sin_fondos = client.post(
                f'/pagar/{nomina_id}',
                json={'metodo_pago': 'Transferencia'},
            )
            assert res_sin_fondos.status_code == 400
            assert 'fondos insuficientes' in res_sin_fondos.get_json()['error'].lower()

        # Verificar que la nómina se mantiene Contabilizada y sin asiento PAG-NOM
        estado_tras_rechazo = cursor.execute(
            'SELECT Estado FROM rrhh.Nomina WHERE ID = ?', nomina_id
        ).fetchone()[0]
        assert estado_tras_rechazo == 'Contabilizada'
        asiento_inexistente = cursor.execute(
            "SELECT COUNT(*) FROM contabilidad.AsientosDiario WHERE ReferenciaExterna = ? AND Estado = 'Contabilizado'",
            f'PAG-NOM-{nomina_id}',
        ).fetchone()[0]
        assert asiento_inexistente == 0

        # 2) Inyectar fondos suficientes en Bancos MN y ejecutar el desembolso
        fondeo = salario_neto + Decimal('2000.00')
        ContabilidadService.crear_asiento(
            cursor=cursor,
            descripcion='Fondeo Bancos MN para pago de planilla L05',
            detalles=[
                (ContabilidadService.BANCOS_MN, fondeo, Decimal('0.00'), 'Depósito para planilla'),
                (ContabilidadService.CAPITAL_SOCIAL, Decimal('0.00'), fondeo, 'Aporte prueba'),
            ],
            usuario_id=1,
            tipo_comprobante='IN',
            referencia_externa=f'FOND-L05-{marker}',
            tipo_documento='Deposito',
            fecha=datetime(2026, 9, 30, 15, 0, 0),
        )

        with as_db_role(cursor, 'Admin'):
            res_pago = client.post(
                f'/pagar/{nomina_id}',
                json={'metodo_pago': 'Transferencia'},
            )
            assert res_pago.status_code == 200, res_pago.get_json()
            datos_pago = res_pago.get_json()
            assert datos_pago['estado'] == 'Pagada'
            assert datos_pago['asiento_id'] is not None

        # Verificar transición a Pagada y débito a Sueldos por Pagar (2.1.02.001)
        estado_pagada = cursor.execute(
            'SELECT Estado FROM rrhh.Nomina WHERE ID = ?', nomina_id
        ).fetchone()[0]
        assert estado_pagada == 'Pagada'

        lineas_pago = cursor.execute(
            """
            SELECT c.Codigo, d.Debe, d.Haber
            FROM contabilidad.DetalleAsientos d
            JOIN contabilidad.AsientosDiario a ON a.ID = d.AsientoID
            JOIN contabilidad.CatalogoCuentas c ON c.ID = d.CuentaID
            WHERE a.ReferenciaExterna = ? AND a.Estado = 'Contabilizado'
            """,
            f'PAG-NOM-{nomina_id}',
        ).fetchall()
        mapa_lineas = {row.Codigo: (Decimal(str(row.Debe)), Decimal(str(row.Haber))) for row in lineas_pago}
        assert ContabilidadService.SUELDOS_POR_PAGAR in mapa_lineas
        assert mapa_lineas[ContabilidadService.SUELDOS_POR_PAGAR] == (salario_neto, Decimal('0.0000'))
        assert mapa_lineas[ContabilidadService.BANCOS_MN] == (Decimal('0.0000'), salario_neto)

        # 3) Idempotencia: intentar pagar por segunda vez debe devolver HTTP 409 sin duplicar asiento
        with as_db_role(cursor, 'Admin'):
            res_duplicado = client.post(
                f'/pagar/{nomina_id}',
                json={'metodo_pago': 'Transferencia'},
            )
            assert res_duplicado.status_code == 409

        total_asientos_pago = cursor.execute(
            "SELECT COUNT(*) FROM contabilidad.AsientosDiario WHERE ReferenciaExterna = ? AND Estado = 'Contabilizado'",
            f'PAG-NOM-{nomina_id}',
        ).fetchone()[0]
        assert total_asientos_pago == 1
    finally:
        conn.rollback()
        conn.close()


# ==============================================================================
# 4. L12: Vales en nómina — Filtro por fecha de período y tope sin salario neto negativo
# ==============================================================================

def test_l12_vales_filtered_by_period_date_and_capped_without_negative_net(monkeypatch):
    from app.admin import routes_hr

    monkeypatch.setattr(routes_hr, 'business_now', lambda: datetime(2026, 10, 25, 14, 0, 0))
    conn = _qa_conn()
    cursor = conn.cursor()
    marker = uuid4().hex[:8]
    try:
        # Crear un usuario exclusivo para asociar vales a este empleado
        cursor.execute(
            """
            INSERT INTO seguridad.Usuarios (NombreCompleto, Username, PasswordHash, RolID, Activo)
            OUTPUT INSERTED.ID
            VALUES (?, ?, 'hash', 3, 1)
            """,
            f'QA Usuario Vale {marker}',
            f'usr_vale_{marker}',
        )
        usuario_id = cursor.fetchone()[0]

        cursor.execute(
            'EXEC rrhh.sp_GuardarPerfilPuesto ?,?,?,?,?,?',
            f'QA Cargo L12 {marker}', 'Perfil', 'Obligaciones', 'Competencias', 1, '127.0.0.1',
        )
        # Salario base C$1,000.00 -> INSS 7% = C$70.00, IR = C$0.00 -> Neto disponible = C$930.00
        cursor.execute(
            """
            INSERT INTO rrhh.Empleados (
                UsuarioID, NombreCompleto, Cedula, Cargo, FechaIngreso,
                TipoContrato, TipoJornada, SalarioBase, FormaPago, EstadoEmpleado, ConsentimientoDatos
            )
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, '2026-01-01', 'Indefinido', 'Diurna', 1000.00, 'Mensual', 'Activo', 1)
            """,
            usuario_id,
            f'QA Emp L12 {marker}',
            f'L12-{marker}',
            f'QA Cargo L12 {marker}',
        )
        emp_id = cursor.fetchone()[0]

        # Vale 1: dentro de septiembre (10/09/2026) por C$400.00 -> cabe completo (quedan C$530.00 disponibles)
        cursor.execute(
            "EXEC contabilidad.sp_InsertarValeEmpleado ?, ?, ?",
            usuario_id, Decimal('400.00'), datetime(2026, 9, 10, 10, 0, 0),
        )
        vale_sep_1 = cursor.fetchone()[0]

        # Vale 2: dentro de septiembre (20/09/2026) por C$550.00 -> solo caben C$530.00, deben quedar C$20.00 pendientes
        cursor.execute(
            "EXEC contabilidad.sp_InsertarValeEmpleado ?, ?, ?",
            usuario_id, Decimal('550.00'), datetime(2026, 9, 20, 10, 0, 0),
        )
        vale_sep_2 = cursor.fetchone()[0]

        # Vale 3: posterior al período de septiembre (15/10/2026) por C$300.00 -> NO debe tocarse en septiembre
        cursor.execute(
            "EXEC contabilidad.sp_InsertarValeEmpleado ?, ?, ?",
            usuario_id, Decimal('300.00'), datetime(2026, 10, 15, 10, 0, 0),
        )
        vale_oct = cursor.fetchone()[0]

        class BorrowedConn:
            def cursor(self): return conn.cursor()
            def commit(self): pass
            def rollback(self): pass
            def close(self): pass

        monkeypatch.setattr(routes_hr, 'get_db_connection', BorrowedConn)
        monkeypatch.setattr(routes_hr, 'current_user', SimpleNamespace(id=1, rol_nombre='Admin'))

        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY='qa-l12')
        app.add_url_rule('/calc', view_func=unwrap(routes_hr.calcular_nomina), methods=['POST'])
        client = app.test_client()

        with as_db_role(cursor, 'Admin'):
            res = client.post('/calc', json={
                'empleado_id': emp_id,
                'periodo_inicio': '2026-09-01',
                'periodo_fin': '2026-09-30',
                'dias_ausentes': 0,
            })
            assert res.status_code == 200, res.get_json()
            nom_data = res.get_json()['nomina']
            assert Decimal(str(nom_data['vales_descontados'])) == Decimal('930.00')
            assert Decimal(str(nom_data['salario_neto'])) == Decimal('0.00')

        # Verificar estados de los 3 vales en base de datos
        v1 = cursor.execute('SELECT Monto, Descontado FROM rrhh.ValesEmpleados WHERE ID = ?', vale_sep_1).fetchone()
        v2 = cursor.execute('SELECT Monto, Descontado FROM rrhh.ValesEmpleados WHERE ID = ?', vale_sep_2).fetchone()
        v3 = cursor.execute('SELECT Monto, Descontado FROM rrhh.ValesEmpleados WHERE ID = ?', vale_oct).fetchone()

        assert bool(v1.Descontado) is True
        assert bool(v2.Descontado) is False and Decimal(str(v2.Monto)) == Decimal('20.00')
        assert bool(v3.Descontado) is False and Decimal(str(v3.Monto)) == Decimal('300.00')
    finally:
        conn.rollback()
        conn.close()


# ==============================================================================
# 5. L17: Asistencia — Política única determinista entre Kiosco y Administración
# ==============================================================================

def test_l17_shared_attendance_policy_matches_between_kiosco_and_admin(monkeypatch):
    from app.kiosco import routes as kiosco_routes
    from app.admin import routes_hr

    # Empleado con HoraEntrada personalizada 09:00 mientras el turno general entra a las 06:00 (tolerancia 15 min)
    # Ingreso a las 09:10 -> debe ser 'A Tiempo' tanto en Kiosco como en Admin
    ahora_prueba = datetime(2026, 10, 25, 9, 10, 0)
    empleado_obj = SimpleNamespace(
        ID=42,
        NombreCompleto='Carlos Puntual',
        HoraEntrada=time(9, 0),
        HoraSalida=time(17, 0),
    )
    turno_obj = SimpleNamespace(
        ID=1,
        HoraEntrada=time(6, 0),
        ToleranciaMinutos=15,
    )

    res_directo = resolver_horario_y_clasificar_asistencia(empleado_obj, turno_obj, ahora_prueba)
    assert res_directo['estado'] == 'A Tiempo'
    assert res_directo['fuente_horario'] == 'empleado'

    # Si ingresa a las 09:20 (supera 09:00 + 15 min), ambos deben clasificar 'Llegada Tardia'
    res_tarde = resolver_horario_y_clasificar_asistencia(
        empleado_obj, turno_obj, datetime(2026, 10, 25, 9, 20, 0)
    )
    assert res_tarde['estado'] == 'Llegada Tardia'

    # Verificar que _procesar_marcaje (Kiosco) y kiosco_marcar (Admin) graban el mismo estado
    estados_kiosco = []
    estados_admin = []

    class FakeCursor:
        current = None
        def fetchone(self):
            return self.current

    class FakeConn:
        def cursor(self): return FakeCursor()
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass

    def fake_exec_kiosco(cursor, sp_name, params=(), **kwargs):
        if sp_name == 'rrhh.sp_ObtenerEmpleadoActivoPorIDBloqueo':
            cursor.current = empleado_obj
        elif sp_name == 'rrhh.sp_ObtenerTurnoLaboralActivoDefecto':
            cursor.current = turno_obj
        elif sp_name == 'rrhh.sp_ObtenerAsistenciaPorEmpleadoFechaBloqueo':
            cursor.current = None
        elif sp_name == 'rrhh.sp_InsertarEntradaAsistenciaKiosco':
            estados_kiosco.append(params[4])
        return cursor

    def fake_exec_admin(cursor, sp_name, params=(), **kwargs):
        if sp_name in ('rrhh.sp_ObtenerEmpleadoKioscoPorIDBloqueo', 'rrhh.sp_ObtenerEmpleadoKioscoPorCedulaBloqueo'):
            cursor.current = empleado_obj
        elif sp_name == 'rrhh.sp_ObtenerTurnoLaboralActivoDefecto':
            cursor.current = turno_obj
        elif sp_name == 'rrhh.sp_ObtenerAsistenciaPorEmpleadoFechaBloqueo':
            cursor.current = None
        elif sp_name == 'rrhh.sp_InsertarEntradaAsistenciaConUsuario':
            estados_admin.append(params[4])
        return cursor

    monkeypatch.setattr(kiosco_routes, 'business_now', lambda: ahora_prueba)
    monkeypatch.setattr(kiosco_routes, 'get_db_connection', FakeConn)
    monkeypatch.setattr(kiosco_routes, 'execute_sp', fake_exec_kiosco)

    monkeypatch.setattr(routes_hr, 'business_now', lambda: ahora_prueba)
    monkeypatch.setattr(routes_hr, 'get_db_connection', FakeConn)
    monkeypatch.setattr(routes_hr, 'execute_sp', fake_exec_admin)
    monkeypatch.setattr(routes_hr, 'current_user', SimpleNamespace(id=1, rol_nombre='Admin'))

    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.add_url_rule('/admin_marcar', view_func=unwrap(routes_hr.kiosco_marcar), methods=['POST'])
    with app.test_request_context('/kiosco'):
        resp_kiosco = kiosco_routes._procesar_marcaje(42, 'entrada')
        assert resp_kiosco.get_json()['estado'] == 'A Tiempo'

    resp_admin = app.test_client().post('/admin_marcar', json={'empleado_id': 42, 'tipo': 'entrada'})
    assert resp_admin.status_code == 200
    assert estados_kiosco == ['A Tiempo']
    assert estados_admin == ['A Tiempo']


# ==============================================================================
# 6. L19: Biometría — Invalidación y recarga automática de caché por huella en BD
# ==============================================================================

def test_l19_face_service_reloads_cache_when_db_fingerprint_changes(monkeypatch):
    from app.services import face_service as fs_module
    servicio = fs_module.face_service

    vec_emp_1 = [0.1] * 128
    vec_emp_2 = [0.2] * 128

    estado_bd = {
        'huella': (1, 10, 11111),
        'filas': [SimpleNamespace(ID=10, FaceDescriptor=json.dumps(vec_emp_1))],
    }

    class FakeCursor:
        def __init__(self):
            self.mode = None

        def fetchone(self):
            if self.mode == 'huella':
                return estado_bd['huella']
            return None

        def fetchall(self):
            if self.mode == 'descriptores':
                return list(estado_bd['filas'])
            return []

    class FakeConn:
        def __init__(self):
            self._cur = FakeCursor()
        def cursor(self):
            return self._cur
        def close(self):
            pass

    def fake_execute_sp(cursor, sp_name, params=(), **kwargs):
        if sp_name == 'rrhh.sp_ObtenerHuellaDescriptoresFacialesKiosco':
            cursor.mode = 'huella'
        elif sp_name == 'rrhh.sp_ObtenerDescriptoresFacialesKiosco':
            cursor.mode = 'descriptores'
        return cursor

    monkeypatch.setattr(fs_module, 'get_db_connection', FakeConn)
    monkeypatch.setattr(fs_module, 'execute_sp', fake_execute_sp)

    # Forzar estado inicial limpio
    servicio._descriptor_cache.clear()
    servicio._cache_loaded = False
    servicio._cache_version = None

    # Primera sincronización: carga empleado 10
    recargado_1 = servicio.verificar_y_sincronizar_cache()
    assert recargado_1 is True
    assert servicio._cache_version == (1, 10, 11111)
    assert set(servicio._descriptor_cache.keys()) == {10}

    # Segunda verificación sin cambios en BD: no recarga
    recargado_2 = servicio.verificar_y_sincronizar_cache()
    assert recargado_2 is False

    # Simular que otro worker registró al empleado 25 en la BD
    estado_bd['huella'] = (2, 25, 22222)
    estado_bd['filas'].append(SimpleNamespace(ID=25, FaceDescriptor=json.dumps(vec_emp_2)))

    # Al invocar reconocer_rostro (o verificar_y_sincronizar_cache), detecta cambio de huella y recarga
    monkeypatch.setattr(servicio, 'decodificar_base64_a_numpy', lambda _b64: None)
    res = servicio.reconocer_rostro('data:image/jpeg;base64,invalida')
    assert res['status'] == 'error'
    assert servicio._cache_version == (2, 25, 22222)
    assert set(servicio._descriptor_cache.keys()) == {10, 25}
    assert np.allclose(servicio._descriptor_cache[25], np.array([vec_emp_2], dtype=np.float32))
