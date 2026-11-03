# -*- coding: utf-8 -*-
"""
Pruebas integrales de Planilla en 3 Partes, DetalleNomina, Gestión y Recomendación de Vacaciones,
Préstamos, Cobros por Pérdidas y Asistencia.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
import os
from types import SimpleNamespace
from uuid import uuid4

import pyodbc
import pytest
from flask import Flask

from app import create_app
from app.models import User
from app.qa_safety import connect_qa
from app.services.payroll_engine import (
    calcular_planilla_completa,
    calcular_saldo_vacaciones_empleado,
    generar_plan_recomendado_vacaciones,
    calcular_ir_metodo_acumulado,
    calcular_tasa_provision_indemnizacion,
)


def _qa_conn():
    conn_str = os.environ.get('TEST_DB_CONNECTION_STRING')
    if not conn_str:
        pytest.skip('Requiere TEST_DB_CONNECTION_STRING apuntando a base QA.')
    return connect_qa(pyodbc.connect, conn_str)


# ==============================================================================
# 1. Pruebas Unitarias del Motor de Nómina en 3 Partes
# ==============================================================================

def test_motor_nomina_3_partes_calculos_y_balance():
    res = calcular_planilla_completa(
        salario_base=15000.0,
        dias_ausentes=0,
        horas_extras=10,
        sueldo_extraordinario=1000.0,
        incentivos=1500.0,
        riesgo_laboral=225.0,  # 1.5% de 15,000
        viaticos=1200.0,
        depreciacion_vehiculo=800.0,
        tasa_inss_laboral=7.0,
        embargo_salarial=500.0,
        deduccion_prestamos=1000.0,
        vales_adelanto=600.0,
        cobros_perdidas=300.0,
        tasa_inss_patronal=21.5,
        tasa_inatec=2.0,
        anios_antiguedad=2.5,
        dias_esperados=30,
        dias_asistidos=28,
        dias_tardanzas=2,
        horas_totales_trabajadas=224,
    )

    # Parte 1: Ingresos
    assert res.sueldo_ordinario == Decimal('15000.00')
    assert res.monto_horas_extras == Decimal('1250.00')  # 10 * (15000/30/8) * 2 = 1250
    assert res.incentivos == Decimal('1500.00')
    assert res.sueldo_extraordinario == Decimal('1000.00')
    assert res.riesgo_laboral == Decimal('225.00')
    assert res.viaticos == Decimal('1200.00')
    assert res.depreciacion_vehiculo == Decimal('800.00')
    assert res.total_ingresos_no_salariales == Decimal('2000.00')
    assert res.total_ingresos_salariales == Decimal('18975.00')
    assert res.total_ingresos == Decimal('20975.00')

    # Parte 2: Deducciones
    assert res.inss_laboral == Decimal('1328.25')  # 7% de 18,975.00
    assert res.embargo_salarial == Decimal('500.00')
    assert res.deduccion_prestamos == Decimal('1000.00')
    assert res.vales_adelanto == Decimal('600.00')
    assert res.cobros_perdidas == Decimal('300.00')
    assert res.salario_neto == res.total_ingresos - res.total_deducciones

    # Parte 3: Patronales
    assert res.inss_patronal == Decimal('4079.63')
    assert res.inatec == round(Decimal('18975.00') * Decimal('0.02'), 2)
    assert res.provision_vacaciones == round(Decimal('18975.00') * Decimal('2.5') / Decimal('30'), 2)
    assert res.provision_aguinaldo == round(Decimal('18975.00') / Decimal('12'), 2)
    # Antigüedad 2.5 años -> 8.333%
    assert res.provision_indemnizacion in (Decimal('1581.24'), Decimal('1581.25'))
    assert res.costo_total_empresa == res.total_ingresos + res.total_patronal

    # Métricas de asistencia
    assert res.promedio_asistencia_pct == Decimal('93.33')
    assert res.promedio_puntualidad_pct == Decimal('92.86')

    # Listas estructuradas
    assert len(res.ingresos) >= 7
    assert len(res.deducciones) >= 6
    assert len(res.patronales) == 5


def test_motor_vacaciones_saldos_y_semaforo():
    hoy = date(2026, 10, 25)
    
    # Empleado nuevo (2 meses trabajados): ~5 días ganados, 0 tomados -> Verde (<15)
    saldo_verde = calcular_saldo_vacaciones_empleado(date(2026, 8, 25), dias_gozados=0, as_of=hoy)
    assert round(saldo_verde['dias_devengados'], 1) == 5.0
    assert round(saldo_verde['dias_disponibles'], 1) == 5.0
    assert saldo_verde['alerta_semaforo'] == 'Verde'
    assert not saldo_verde['acumulacion_excesiva']

    # Empleado con 8 meses trabajados (20 días ganados, 0 tomados) -> Amarillo (15-29)
    saldo_amarillo = calcular_saldo_vacaciones_empleado(date(2026, 2, 25), dias_gozados=0, as_of=hoy)
    assert round(saldo_amarillo['dias_disponibles'], 0) == 20.0
    assert saldo_amarillo['alerta_semaforo'] == 'Amarillo'

    # Empleado con 15 meses trabajados (37.5 días ganados, 5 tomados = 32.5 disp) -> Rojo (>=30)
    saldo_rojo = calcular_saldo_vacaciones_empleado(date(2025, 7, 25), dias_gozados=5, as_of=hoy)
    assert round(saldo_rojo['dias_disponibles'], 0) >= 30.0
    assert saldo_rojo['alerta_semaforo'] == 'Rojo'
    assert saldo_rojo['acumulacion_excesiva']


def test_recomendador_vacaciones_rotativo_prioridades_y_bloqueos():
    empleados = [
        {'empleado_id': 1, 'nombre': 'Panadero 1', 'cargo': 'Panadero', 'dias_disponibles': 35.0, 'semaforo': 'rojo'},
        {'empleado_id': 2, 'nombre': 'Panadero 2', 'cargo': 'Panadero', 'dias_disponibles': 22.0, 'semaforo': 'amarillo'},
        {'empleado_id': 3, 'nombre': 'Cajera 1', 'cargo': 'Cajera', 'dias_disponibles': 30.0, 'semaforo': 'rojo'},
    ]
    inicio = date(2026, 11, 1)
    propuestas = generar_plan_recomendado_vacaciones(empleados, inicio, bloques_dias=15, max_por_cargo=1, meses_proyeccion=3)

    assert len(propuestas) >= 2
    # El Panadero 1 (Rojo) debe programarse antes que el Panadero 2
    prop_p1 = next(p for p in propuestas if p['empleado_id'] == 1)
    prop_p2 = next((p for p in propuestas if p['empleado_id'] == 2), None)
    if prop_p2:
        assert prop_p1['fecha_inicio'] < prop_p2['fecha_inicio']

    # Ninguna propuesta debe solapar con temporada alta navideña (15 al 31 de diciembre)
    for p in propuestas:
        p_ini = date.fromisoformat(p['fecha_inicio'])
        p_fin = date.fromisoformat(p['fecha_fin'])
        navidad_ini = date(2026, 12, 15)
        navidad_fin = date(2026, 12, 31)
        solapa = (p_ini <= navidad_fin and p_fin >= navidad_ini)
        assert not solapa, f"La propuesta para {p.get('nombre') or p.get('nombre_completo')} solapa con temporada alta navideña"


# ==============================================================================
# 2. Pruebas de Renderizado de Colilla de Pago en 3 Partes
# ==============================================================================

def test_render_colilla_pago_con_3_partes_y_asistencia():
    app = Flask(__name__, template_folder=r'c:\Ingenieria de software\panaderia_amada\templates')
    app.config['SECRET_KEY'] = 'test-secret'

    def fake_css_url(bundle):
        return f"/static/css/dist/{bundle}.css"

    app.jinja_env.globals['css_url'] = fake_css_url
    app.jinja_env.globals['csrf_token'] = lambda: 'test-token'

    nomina = SimpleNamespace(
        ID=101,
        NombreCompleto='Carlos Panadero',
        Cedula='001-010190-0001A',
        Cargo='Panadero Maestro',
        NumeroINSS='6543210-9',
        PeriodoInicio=date(2026, 10, 1),
        PeriodoFin=date(2026, 10, 31),
        Estado='Contabilizada',
        SalarioBruto=Decimal('15000.00'),
        HorasExtras=10,
        MontoHorasExtras=Decimal('1250.00'),
        OtrosIngresos=Decimal('1000.00'),
        TotalDevengado=Decimal('17250.00'),
        INSSLaboral=Decimal('1207.50'),
        IRMensual=Decimal('250.00'),
        PensionAlimenticia=Decimal('0.00'),
        ValesDescontados=Decimal('0.00'),
        TotalDeducciones=Decimal('1457.50'),
        SalarioNeto=Decimal('15792.50'),
        INSSPatronal=Decimal('3708.75'),
        INATEC=Decimal('345.00'),
        PromedioAsistencia=Decimal('96.7'),
        PromedioPuntualidad=Decimal('100.0'),
        CostoTotalEmpresa=Decimal('23500.00'),
    )

    detalles = [
        (1, 101, 'Sueldo Base Efectivo', 'Ingreso', Decimal('15000.00'), 'Salario ordinario'),
        (2, 101, 'Horas Extras (10h)', 'Ingreso', Decimal('1250.00'), 'Horas extras'),
        (3, 101, 'Viaticos', 'Ingreso', Decimal('1000.00'), 'No salarial'),
        (4, 101, 'INSS Laboral (7%)', 'Deduccion', Decimal('1207.50'), 'Aporte laboral'),
        (5, 101, 'IR Laboral Ley 822', 'Deduccion', Decimal('250.00'), 'Retencion'),
        (6, 101, 'INSS Patronal (21.5%)', 'Patronal', Decimal('3708.75'), 'Aporte patronal'),
        (7, 101, 'Provision Vacaciones', 'Patronal', Decimal('1437.50'), '2.5 d/mes'),
    ]

    with app.test_request_context():
        from flask import render_template
        html = render_template(
            'admin/colilla_pago.html',
            nomina=nomina,
            datetime=datetime,
            aguinaldo_detalles=None,
            detalles=detalles,
        )

        assert 'Parte 1: Ingresos' in html
        assert 'Parte 2: Deducciones' in html
        assert 'Parte 3: Cargos y Provisiones Patronales' in html or 'Parte 3: Cargas y Provisiones Patronales' in html
        assert 'Promedio Asistencia' in html
        assert '96.7%' in html
        assert 'Provision Vacaciones' in html
        assert 'Costo Total Empresa' in html
        # Comprobar que no hay estilos inline
        assert 'style=' not in html
        assert '<style>' not in html


# ==============================================================================
# 3. Pruebas de Integración con Base de Datos QA
# ==============================================================================

def test_integracion_nomina_3_partes_detalles_asiento_y_prestamo(monkeypatch):
    from app.admin import routes_hr

    monkeypatch.setattr(routes_hr, 'business_now', lambda: datetime(2026, 10, 25, 14, 0, 0))
    conn = _qa_conn()
    cursor = conn.cursor()
    marker = uuid4().hex[:8]

    try:
        # 1. Crear usuario y empleado
        cursor.execute(
            """
            INSERT INTO seguridad.Usuarios (NombreCompleto, Username, PasswordHash, RolID, Activo)
            OUTPUT INSERTED.ID VALUES (?, ?, 'hash', 1, 1)
            """,
            f'QA User 3Partes {marker}', f'usr_3p_{marker}'
        )
        user_id = cursor.fetchone()[0]

        cursor.execute(
            'EXEC rrhh.sp_GuardarPerfilPuesto ?,?,?,?,?,?',
            f'QA Cargo 3P {marker}', 'Perfil', 'Obligaciones', 'Competencias', 1, '127.0.0.1'
        )

        cursor.execute(
            """
            INSERT INTO rrhh.Empleados (
                UsuarioID, NombreCompleto, Cedula, Cargo, FechaIngreso,
                TipoContrato, TipoJornada, SalarioBase, FormaPago, EstadoEmpleado, ConsentimientoDatos
            )
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, '2025-01-01', 'Indefinido', 'Diurna', 12000.00, 'Mensual', 'Activo', 1)
            """,
            user_id, f'QA Emp 3P {marker}', f'3P-{marker}', f'QA Cargo 3P {marker}'
        )
        emp_id = cursor.fetchone()[0]

        # 2. Registrar préstamo activo para el empleado
        cursor.execute(
            """
            INSERT INTO rrhh.PrestamosEmpleados (EmpleadoID, MontoTotal, CuotaMensual, SaldoPendiente, Motivo, FechaInicio, Estado, CreadoPor)
            OUTPUT INSERTED.ID
            VALUES (?, 3000.00, 500.00, 3000.00, 'Préstamo personal QA', '2026-09-01', 'Activo', ?)
            """,
            emp_id, user_id
        )
        prestamo_id = cursor.fetchone()[0]

        # 3. Registrar cobro por pérdida pendiente
        cursor.execute(
            """
            INSERT INTO rrhh.CobrosPerdidasEmpleados (EmpleadoID, Descripcion, MontoTotal, SaldoPendiente, NumeroDocumento, FechaIncidente, Estado, CreadoPor)
            OUTPUT INSERTED.ID
            VALUES (?, 'Rotura de bandeja QA', 400.00, 400.00, 'DOC-001', '2026-09-15', 'Pendiente', ?)
            """,
            emp_id, user_id
        )
        cobro_id = cursor.fetchone()[0]

        conn.commit()

        # 4. Calcular nómina mensual con ingresos adicionales (Incentivos, Viáticos, Horas Extras)
        app = create_app()
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False

        admin_user = User(
            id=user_id,
            username=f'usr_3p_{marker}',
            nombre_completo=f'QA User 3Partes {marker}',
            rol_id=1,
            rol_nombre='SuperAdmin',
        )

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(user_id)
            monkeypatch.setattr('flask_login.utils._get_user', lambda: admin_user)

            # Verificar precarga automatica de datos de nomina individual
            resp_precarga = client.get(f'/admin/api/rrhh/nomina/precargar_datos?empleado_id={emp_id}&periodo_inicio=2026-09-01&periodo_fin=2026-09-30')
            assert resp_precarga.status_code == 200
            data_auto = resp_precarga.get_json()['automaticos']
            assert data_auto['deduccion_prestamos'] == 500.0
            assert data_auto['cobros_perdidas'] == 400.0

            payload = {
                'empleado_id': emp_id,
                'periodo_inicio': '2026-09-01',
                'periodo_fin': '2026-09-30',
                'horas_extras': 8,
                'incentivos': 500.0,
                'viaticos': 300.0,
                'depreciacion_vehiculo': 200.0,
                'dias_ausentes': 0,
            }

            resp = client.post('/admin/api/rrhh/nomina/calcular', json=payload)
            assert resp.status_code == 200, resp.get_json()
            data = resp.get_json()['nomina']
            nomina_id = data['id']

            # Verificar que se aplicó el abono al préstamo
            cursor.execute('SELECT SaldoPendiente FROM rrhh.PrestamosEmpleados WHERE ID = ?', prestamo_id)
            nuevo_saldo_prestamo = float(cursor.fetchone()[0])
            assert nuevo_saldo_prestamo == 2500.00  # 3000 - 500 cuota

            # Verificar que se aplicó el cobro por pérdida
            cursor.execute('SELECT SaldoPendiente FROM rrhh.CobrosPerdidasEmpleados WHERE ID = ?', cobro_id)
            nuevo_saldo_perdida = float(cursor.fetchone()[0])
            assert nuevo_saldo_perdida < 400.00

            # Verificar DetalleNomina
            cursor.execute('SELECT Concepto, Tipo, Monto FROM rrhh.DetalleNomina WHERE NominaID = ?', nomina_id)
            detalles = cursor.fetchall()
            assert len(detalles) >= 10
            tipos = {d[1] for d in detalles}
            assert 'Ingreso' in tipos
            assert 'Deduccion' in tipos
            assert 'Patronal' in tipos

            # Verificar asiento contable en partida doble exacta
            cursor.execute(
                """
                SELECT SUM(d.Debe), SUM(d.Haber)
                FROM contabilidad.DetalleAsientos d
                JOIN contabilidad.AsientosDiario a ON a.ID = d.AsientoID
                WHERE a.ReferenciaExterna = ?
                """,
                f'NOM-{nomina_id}'
            )
            asiento_row = cursor.fetchone()
            sum_debe = float(asiento_row[0])
            sum_haber = float(asiento_row[1])
            assert sum_debe > 0
            assert round(sum_debe, 2) == round(sum_haber, 2), f"Descuadre: Debe {sum_debe} != Haber {sum_haber}"

            # Verificar endpoint de saldos de vacaciones
            resp_vac = client.get('/admin/api/rrhh/vacaciones/saldos')
            assert resp_vac.status_code == 200
            saldos = resp_vac.get_json()['saldos']
            emp_saldo = next((s for s in saldos if s['empleado_id'] == emp_id), None)
            assert emp_saldo is not None
            assert emp_saldo['alerta_semaforo'] in ('Verde', 'Amarillo', 'Rojo')
            assert emp_saldo['dias_devengados'] > 0

            # Verificar endpoint de recomendar vacaciones
            resp_rec = client.post('/admin/api/rrhh/vacaciones/recomendar', json={'meses': 6, 'guardar': True})
            assert resp_rec.status_code == 200
            propuestas = resp_rec.get_json()['propuestas']
            assert len(propuestas) > 0
            prop_id = propuestas[0]['id']

            # Verificar aprobación de propuesta de vacaciones
            resp_aprob = client.post(f'/admin/api/rrhh/vacaciones/aprobar/{prop_id}')
            assert resp_aprob.status_code == 200
            cursor.execute('SELECT Estado FROM rrhh.PropuestasVacaciones WHERE ID = ?', prop_id)
            assert cursor.fetchone()[0] == 'Aprobada'
            cursor.execute('SELECT TOP 1 ID FROM rrhh.LicenciasEmpleados WHERE TipoLicencia = ? ORDER BY ID DESC', 'Vacaciones')
            assert cursor.fetchone() is not None

    finally:
        conn.close()
