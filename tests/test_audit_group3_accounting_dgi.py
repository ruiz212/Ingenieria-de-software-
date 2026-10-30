"""
Suite de pruebas de remediación de auditoría — Grupo 3:
Contabilidad, Balance General, Cierre Mensual, Motor/Repositorio DGI, Pronóstico Lineal y Contrato CSRF.
Cubre los hallazgos: L06, L07, L11, L14, L22, L24, L25, L27 y CSRF HTTP 400.
"""
import copy
import os
import pathlib
import re
import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal

import pyodbc
import pytest

from app import create_app
from app.admin.routes_dashboard import business_today, calcular_pronostico_ventas
from app.models import User
from app.services import dgi_repository as repo
from app.services.contabilidad_service import ContabilidadError, ContabilidadService
from app.services.dgi_engine import analyze
from config import Config


@pytest.fixture(scope='module')
def qa_string():
    value = os.environ.get('TEST_DB_CONNECTION_STRING')
    if not value:
        pytest.skip('Defina TEST_DB_CONNECTION_STRING para una base PanaderiaQA_ aislada.')
    return value


@pytest.fixture
def app(qa_string):
    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = 'group3-audit-qa-secret'
        SQL_SERVER_CONNECTION_STRING = qa_string

    application = create_app(TestConfig)
    application.login_manager._user_callback = lambda _: User(1, 'qa', 'Auditor QA', 1, 'SuperAdmin')
    return application


@pytest.fixture
def base_dgi_snapshot():
    return dict(
        desde='2026-10-01',
        hasta='2026-10-31',
        obligacion='Diagnóstico interno',
        perfil=dict(
            fiscal_razon_social='Panadería Brajhers QA',
            fiscal_ruc='J0310000000000',
            fiscal_regimen='General',
            dgi_responsable='Auditor QA',
            dgi_obligaciones='IVA mensual',
            dgi_vigente_desde='2026-01-01',
            dgi_vigente_hasta='',
        ),
        ventas=[
            dict(
                id=101,
                numero='FAC-000101',
                fecha='2026-10-10T10:00:00',
                estado='Emitida',
                anulada_en=None,
                base='1000.00',
                iva='150.00',
                total='1150.00',
                documento=True,
                asiento_id=501,
                detalles=[dict(subtotal='1000.00', cantidad=1, precio='1000.00')],
            )
        ],
        compras=[
            dict(
                id=1,
                numero='FC-001',
                fecha='2026-10-10T10:00:00',
                proveedor_id=1,
                proveedor='Harinas de Nicaragua',
                materia_id=1,
                cantidad='2',
                total='500.00',
                iva='0.00',
            )
        ],
        asientos=[
            dict(
                id=501,
                numero='FV-000501',
                fecha='2026-10-10T10:00:00',
                estado='Contabilizado',
                referencia='FAC-000101',
                tipo_documento='FacturaVenta',
                detalles=[
                    dict(cuenta='1.1.01.001', nombre='Caja General', clase='Activo', debe='1150.00', haber='0.00'),
                    dict(cuenta='4.1.01.001', nombre='Ventas de Panadería', clase='Ingreso', debe='0.00', haber='1000.00'),
                    dict(cuenta='2.1.02.001', nombre='IVA Débito Fiscal', clase='Pasivo', debe='0.00', haber='150.00'),
                ],
            )
        ],
    )


class _AttrRow:
    def __init__(self, columns, values):
        self._values = tuple(values)
        self._map = {col: val for col, val in zip(columns, values)}

    def __getitem__(self, idx):
        if isinstance(idx, str):
            return self._map[idx]
        return self._values[idx]

    def __len__(self):
        return len(self._values)

    def __getattr__(self, name):
        if name in self._map:
            return self._map[name]
        raise AttributeError(name)


class _SqlitePyodbcAdapter:
    """Adaptador liviano de sqlite3.Cursor con firma estilo pyodbc para fallback_sql."""
    __module__ = 'sqlite3.adapter'

    def __init__(self, conn):
        self._conn = conn
        self._cur = conn.cursor()
        self._buffer = None

    @property
    def description(self):
        return self._cur.description

    def execute(self, sql, *params):
        if len(params) == 1 and isinstance(params[0], (tuple, list)):
            bound = tuple(params[0])
        else:
            bound = tuple(params)
        bound = tuple(
            v.isoformat(sep=' ')
            if isinstance(v, datetime)
            else (v.isoformat() if isinstance(v, date) else (float(v) if isinstance(v, Decimal) else v))
            for v in bound
        )
        cleaned = sql.replace('SET NOCOUNT ON;', '').replace('WITH (UPDLOCK, HOLDLOCK)', '').replace('WITH(UPDLOCK,HOLDLOCK)', '')
        cleaned = cleaned.replace('ISNULL(', 'COALESCE(')
        self._buffer = None

        if 'UPDATE TiposComprobante' in cleaned and 'OUTPUT INSERTED.' in cleaned:
            codigo = bound[0]
            self._cur.execute("UPDATE TiposComprobante SET CorrelativoActual = CorrelativoActual + 1 WHERE Codigo = ?", (codigo,))
            self._cur.execute("SELECT ID, Prefijo, CorrelativoActual FROM TiposComprobante WHERE Codigo = ?", (codigo,))
            row = self._cur.fetchone()
            self._buffer = [_AttrRow(['ID', 'Prefijo', 'CorrelativoActual'], row)] if row else []
            return self

        if 'OUTPUT INSERTED.ID' in cleaned:
            cleaned_no_output = re.sub(r'\s+OUTPUT\s+INSERTED\.ID\s+', ' ', cleaned, flags=re.IGNORECASE)
            self._cur.execute(cleaned_no_output, bound)
            self._buffer = [_AttrRow(['ID'], (self._cur.lastrowid,))]
            return self

        self._cur.execute(cleaned, bound)
        if self._cur.description:
            cols = [c[0] for c in self._cur.description]
            self._buffer = [_AttrRow(cols, r) for r in self._cur.fetchall()]
        else:
            self._buffer = []
        return self

    def fetchone(self):
        if self._buffer is not None:
            return self._buffer.pop(0) if self._buffer else None
        return self._cur.fetchone()

    def fetchall(self):
        if self._buffer is not None:
            res = list(self._buffer)
            self._buffer = []
            return res
        return self._cur.fetchall()


def _sqlite_accounting_cursor():
    conn = sqlite3.connect(':memory:')
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE ConfiguracionSistema (Clave TEXT PRIMARY KEY, Valor TEXT);
        CREATE TABLE BitacoraFiscal (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Fecha TEXT, UsuarioID INT, Accion TEXT, Entidad TEXT, EntidadID INT,
            Detalle TEXT, IP TEXT
        );
        CREATE TABLE PeriodosContables (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Mes INT, Anio INT, Estado TEXT, CerradoPor INT, CerradoEn TEXT
        );
        CREATE TABLE TiposComprobante (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Codigo TEXT, Nombre TEXT, Prefijo TEXT, CorrelativoActual INT
        );
        INSERT INTO TiposComprobante (Codigo, Nombre, Prefijo, CorrelativoActual) VALUES
            ('DI', 'Diario', 'DI', 0),
            ('IN', 'Ingreso', 'IN', 0),
            ('EG', 'Egreso', 'EG', 0),
            ('FV', 'Factura Venta', 'FV', 0),
            ('FC', 'Factura Compra', 'FC', 0);
        CREATE TABLE CatalogoCuentas (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Codigo TEXT UNIQUE, Nombre TEXT, Clase TEXT, Grupo TEXT,
            Naturaleza TEXT, Nivel INT, EsTransaccional INT DEFAULT 1,
            Activa INT DEFAULT 1, OrdenVisualizacion INT DEFAULT 1,
            Descripcion TEXT, CuentaPadreID INT
        );
        INSERT INTO CatalogoCuentas (Codigo, Nombre, Clase, Grupo, Naturaleza, Nivel) VALUES
            ('1.1.01.001', 'Caja General Córdobas', 'Activo', 'Efectivo', 'Deudora', 4),
            ('1.1.01.004', 'Banco BAC Córdobas', 'Activo', 'Efectivo', 'Deudora', 4),
            ('1.1.02.003', 'Anticipos y Vales a Empleados', 'Activo', 'Cuentas por Cobrar', 'Deudora', 4),
            ('1.1.03.001', 'Inventario de Materia Prima', 'Activo', 'Inventarios', 'Deudora', 4),
            ('1.1.04.001', 'IVA Crédito Fiscal', 'Activo', 'Impuestos', 'Deudora', 4),
            ('2.1.01.001', 'Proveedores de Materia Prima', 'Pasivo', 'Cuentas por Pagar', 'Acreedora', 4),
            ('2.1.02.001', 'IVA por Pagar (Débito Fiscal)', 'Pasivo', 'Impuestos', 'Acreedora', 4),
            ('2.1.03.001', 'IVA Débito Fiscal', 'Pasivo', 'Impuestos', 'Acreedora', 4),
            ('3.1.01.001', 'Capital Social', 'Capital', 'Patrimonio', 'Acreedora', 4),
            ('4.1.01.001', 'Ventas de Panadería', 'Ingreso', 'Ingresos Operativos', 'Acreedora', 4),
            ('4.2.01.001', 'Otros Ingresos', 'Ingreso', 'Otros Ingresos', 'Acreedora', 4),
            ('5.1.01.001', 'Costo de Productos Vendidos', 'Costo', 'Costo de Ventas', 'Deudora', 4),
            ('6.1.02.008', 'Gastos Varios de Administración', 'Gasto', 'Gastos Administrativos', 'Deudora', 4),
            ('6.2.99.001', 'Otros Gastos Administrativos', 'Gasto', 'Gastos Administrativos', 'Deudora', 4);
        CREATE TABLE AsientosDiario (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Fecha TEXT, PeriodoID INT, Descripcion TEXT, ReferenciaExterna TEXT,
            TipoDocumento TEXT, Estado TEXT, UsuarioID INT, TipoComprobanteID INT,
            NumeroComprobante TEXT, IP TEXT, EmisorJSON TEXT
        );
        CREATE TABLE DetalleAsientos (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            AsientoID INT, CuentaID INT, Debe REAL, Haber REAL,
            Descripcion TEXT, DocumentoRelacionado TEXT
        );
        CREATE TABLE Facturas (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            NumeroFactura TEXT, FechaHora TEXT, Subtotal REAL, IVA REAL, Total REAL,
            EstadoFiscal TEXT, DocumentoJSON TEXT
        );
        CREATE TABLE ComprasMateriaPrima (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            FacturaProveedor TEXT, Fecha TEXT, CostoTotal REAL, IVADocumentado REAL
        );
        """
    )
    return _SqlitePyodbcAdapter(conn)


# ==============================================================================
# 1. L06 — Anulación inter-período con asiento de reversión conciliado
# ==============================================================================

def test_l06_cross_period_annulment_with_valid_reversal_does_not_block(base_dgi_snapshot):
    snapshot = copy.deepcopy(base_dgi_snapshot)
    snapshot['ventas'].append(
        dict(
            id=99,
            numero='FAC-000099',
            fecha='2026-09-25T14:00:00',
            estado='Anulada',
            anulada_en='2026-10-10T09:30:00',
            base='400.00',
            iva='60.00',
            total='460.00',
            documento=True,
            asiento_id=450,
            reversion_asiento_id=502,
            detalles=[dict(subtotal='400.00', cantidad=1, precio='400.00')],
        )
    )
    snapshot['asientos'].append(
        dict(
            id=502,
            numero='DI-000502',
            fecha='2026-10-10T09:30:00',
            estado='Contabilizado',
            referencia='REV-450',
            tipo_documento='Reversión',
            descripcion='REVERSIÓN de FV-000450 (FAC-000099)',
            detalles=[
                dict(cuenta='4.1.01.001', nombre='Ventas de Panadería', clase='Ingreso', debe='400.00', haber='0.00'),
                dict(cuenta='2.1.02.001', nombre='IVA Débito Fiscal', clase='Pasivo', debe='60.00', haber='0.00'),
                dict(cuenta='1.1.01.001', nombre='Caja General', clase='Activo', debe='0.00', haber='460.00'),
            ],
        )
    )

    result = analyze(snapshot)
    codigos_bloqueantes = {f['codigo'] for f in result['hallazgos'] if f['severidad'] == 'ERROR_BLOQUEANTE'}
    assert 'ANULACION' not in codigos_bloqueantes
    assert 'CONCILIACION' not in codigos_bloqueantes
    assert result['bloqueantes'] == 0
    assert Decimal(result['totales']['ventas_base']) == Decimal('1000.00')
    assert Decimal(result['totales']['ingresos_contables']) == Decimal('1000.00')
    assert Decimal(result['totales']['diferencia']) == Decimal('0.00')

    venta_99 = next(v for v in result['ventas'] if v['id'] == 99)
    assert venta_99['anulacion_periodo_anterior_conciliada'] is True
    assert any(
        f['codigo'] == 'FUERA_PERIODO' and f['origen_id'] == 99 and f['severidad'] == 'INFORMATIVO'
        for f in result['hallazgos']
    )


def test_l06_cross_period_annulment_without_reversal_still_blocks(base_dgi_snapshot):
    snapshot = copy.deepcopy(base_dgi_snapshot)
    snapshot['ventas'].append(
        dict(
            id=98,
            numero='FAC-000098',
            fecha='2026-09-25T14:00:00',
            estado='Anulada',
            anulada_en='2026-10-10T09:30:00',
            base='400.00',
            iva='60.00',
            total='460.00',
            documento=True,
            asiento_id=449,
            detalles=[dict(subtotal='400.00', cantidad=1, precio='400.00')],
        )
    )
    result = analyze(snapshot)
    assert any(
        f['codigo'] == 'ANULACION' and f['origen_id'] == 98 and f['severidad'] == 'ERROR_BLOQUEANTE'
        for f in result['hallazgos']
    )


# ==============================================================================
# 2. L07 — Conciliación DGI excluye "Otros Ingresos" y exige vínculo por factura
# ==============================================================================

def test_l07_alien_income_cannot_mask_invoice_without_journal_entry(base_dgi_snapshot):
    snapshot = copy.deepcopy(base_dgi_snapshot)
    snapshot['ventas'].append(
        dict(
            id=102,
            numero='FAC-000102',
            fecha='2026-10-12T11:00:00',
            estado='Emitida',
            anulada_en=None,
            base='500.00',
            iva='0.00',
            total='500.00',
            documento=True,
            asiento_id=None,
            detalles=[dict(subtotal='500.00', cantidad=1, precio='500.00')],
        )
    )
    snapshot['asientos'].append(
        dict(
            id=503,
            numero='DI-000503',
            fecha='2026-10-12T12:00:00',
            estado='Contabilizado',
            referencia='ING-AJUSTE-1',
            tipo_documento='Manual',
            descripcion='Otros ingresos financieros no ligados a facturación',
            detalles=[
                dict(cuenta='1.1.01.001', nombre='Caja General', clase='Activo', debe='500.00', haber='0.00'),
                dict(cuenta='4.2.01.001', nombre='Otros Ingresos', clase='Ingreso', debe='0.00', haber='500.00'),
            ],
        )
    )

    result = analyze(snapshot)
    assert Decimal(result['totales']['ventas_base']) == Decimal('1500.00')
    assert Decimal(result['totales']['ingresos_contables']) == Decimal('1000.00')
    assert Decimal(result['totales']['diferencia']) == Decimal('500.00')
    assert any(
        f['codigo'] == 'CONCILIACION' and f['severidad'] == 'ERROR_BLOQUEANTE'
        for f in result['hallazgos']
    )


# ==============================================================================
# 3. L11 — Verificación de frescura (source_hash) en GET /admin/dgi
# ==============================================================================

def test_l11_dgi_dashboard_flags_stale_review_when_source_changes(app, qa_string):
    conn = pyodbc.connect(qa_string)
    cur = conn.cursor()
    period_id = None
    asiento_id = None
    try:
        start_d = date(2029, 5, 1)
        cur.execute("DELETE FROM fiscal.DGI_Revisiones WHERE PeriodoID IN (SELECT ID FROM fiscal.DGI_Periodos WHERE Desde = ?)", (start_d,))
        cur.execute("DELETE FROM fiscal.DGI_Periodos WHERE Desde = ?", (start_d,))
        conn.commit()

        with app.app_context():
            with repo.transaction() as tcur:
                period_id = repo.create_period(tcur, '2029-05', 1)
                review_id = repo.create_review(tcur, period_id, 'IVA mensual', 1)
                period_obj = repo.get_period(tcur, period_id)
                rev_obj = repo.get_review(tcur, review_id)
                assert repo.is_review_fresh(tcur, rev_obj, period=period_obj) is True

            cur.execute("UPDATE fiscal.DGI_Periodos SET Estado = 'Cerrado' WHERE ID = ?", (period_id,))
            cur.execute("UPDATE fiscal.DGI_Revisiones SET Estado = 'APROBADO' WHERE ID = ?", (review_id,))
            asiento_res = ContabilidadService.crear_asiento(
                cursor=cur,
                descripcion='Asiento posterior a revisión DGI',
                detalles=[('1.1.01.001', 100.0, 0.0), ('4.1.01.001', 0.0, 100.0)],
                usuario_id=1,
                fecha=datetime(2029, 5, 15, 10, 0, 0),
            )
            asiento_id = (asiento_res.get('asiento_id') or asiento_res.get('id')) if isinstance(asiento_res, dict) else asiento_res
            conn.commit()

            with repo.transaction() as tcur:
                period_obj = repo.get_period(tcur, period_id)
                rev_obj = repo.get_review(tcur, review_id)
                assert repo.is_review_fresh(tcur, rev_obj, period=period_obj) is False

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = 'emp_1'
                sess['_fresh'] = True
            resp = client.get(f'/admin/dgi?periodo_id={period_id}&revision_id={review_id}')
            assert resp.status_code == 200
            html = resp.get_data(as_text=True)
            assert 'Requiere Revalidación' in html
    finally:
        if asiento_id:
            cur.execute("DISABLE TRIGGER ALL ON contabilidad.DetalleAsientos; DISABLE TRIGGER ALL ON contabilidad.AsientosDiario;")
            cur.execute("DELETE FROM contabilidad.DetalleAsientos WHERE AsientoID = ?", (asiento_id,))
            cur.execute("DELETE FROM contabilidad.AsientosDiario WHERE ID = ?", (asiento_id,))
            cur.execute("ENABLE TRIGGER ALL ON contabilidad.DetalleAsientos; ENABLE TRIGGER ALL ON contabilidad.AsientosDiario;")
        if period_id:
            cur.execute("DELETE FROM fiscal.DGI_Revisiones WHERE PeriodoID = ?", (period_id,))
            cur.execute("DELETE FROM fiscal.DGI_Periodos WHERE ID = ?", (period_id,))
        conn.commit()
        conn.close()


# ==============================================================================
# 4. L14 — Utilidad Neta Contable vs Flujo de Caja Operativo y cero inline styles
# ==============================================================================

def test_l14_accounting_net_income_vs_operating_cash_flow():
    cur = _sqlite_accounting_cursor()
    fecha_op = datetime(2026, 10, 15, 10, 0, 0)

    # 1) Venta con IVA: Total 1150 (Base 1000 + IVA 150) en efectivo
    ContabilidadService.contabilizar_venta(
        cursor=cur,
        usuario_id=1,
        numero_factura='FAC-L14-1',
        subtotal=1000.0,
        iva=150.0,
        total=1150.0,
        pagos=[{'metodo': 'Efectivo', 'monto': 1150.0}],
        fecha=fecha_op,
    )
    # 2) Compra de inventario MP al crédito por 600 (Activo 1.1.03.001 vs Pasivo 2.1.01.001)
    ContabilidadService.contabilizar_compra(
        cursor=cur,
        usuario_id=1,
        compra_id=10,
        monto_sin_iva=600.0,
        iva=0.0,
        monto_total=600.0,
        metodo_pago='Credito',
        referencia='COMP-L14-10',
        fecha=fecha_op,
    )
    # 3) Egreso operativo pagado en efectivo por 200 (Gasto 6.2.99.001 vs Caja 1.1.01.001)
    ContabilidadService.contabilizar_egreso(
        cursor=cur,
        usuario_id=1,
        concepto='Pago servicio limpieza',
        monto=200.0,
        metodo_pago='Efectivo',
        referencia='EGR-L14-1',
        fecha=fecha_op,
    )

    resumen = ContabilidadService.obtener_resumen_financiero_rango(
        cur, datetime(2026, 10, 1), datetime(2026, 11, 1)
    )
    assert resumen['ingresos_contables'] == 1000.00
    assert resumen['costos_contables'] == 0.00
    assert resumen['gastos_contables'] == 200.00
    assert resumen['utilidad_neta'] == 800.00
    assert resumen['entradas_efectivo'] == 1150.00
    assert resumen['salidas_efectivo'] == 200.00
    assert resumen['flujo_caja_operativo'] == 950.00

    tpl_text = pathlib.Path('templates/admin/contabilidad.html').read_text(encoding='utf-8')
    assert 'style=' not in tpl_text.lower()
    assert 'Utilidad Neta Contable' in tpl_text
    assert 'Flujo de Caja Operativo' in tpl_text


# ==============================================================================
# 5. L22 — Balance General: Utilidad del Ejercicio vs Resultados Acumulados
# ==============================================================================

def test_l22_balance_sheet_separates_prior_years_from_current_year(app, qa_string):
    conn = pyodbc.connect(qa_string)
    cur = conn.cursor()
    asiento_prev = None
    asiento_curr = None
    try:
        with app.app_context():
            asiento_prev = ContabilidadService.crear_asiento(
                cursor=cur,
                descripcion='Ingreso ejercicio anterior 2024',
                detalles=[('1.1.01.001', 5000.0, 0.0), ('4.1.01.001', 0.0, 5000.0)],
                usuario_id=1,
                fecha=datetime(2024, 12, 15, 10, 0, 0),
            )
            asiento_curr = ContabilidadService.crear_asiento(
                cursor=cur,
                descripcion='Ingreso ejercicio actual 2025',
                detalles=[('1.1.01.001', 3000.0, 0.0), ('4.1.01.001', 0.0, 3000.0)],
                usuario_id=1,
                fecha=datetime(2025, 6, 10, 10, 0, 0),
            )
            conn.commit()

            cur.execute("EXEC contabilidad.sp_ObtenerBalanceGeneralCorte ?", ('2025-06-30',))
            rows = cur.fetchall()
            ventas_row = next(r for r in rows if r.Codigo == '4.1.01.001')
            assert float(ventas_row.SaldoEjerciciosAnteriores) >= 5000.0
            assert float(ventas_row.SaldoEjercicioActual) == 3000.0

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = 'emp_1'
                sess['_fresh'] = True
            resp = client.get('/admin/contabilidad/balance?fecha_corte=2025-06-30')
            assert resp.status_code == 200
            html = resp.get_data(as_text=True)
            assert 'Resultados Acumulados de Ejercicios Anteriores' in html
            assert 'Utilidad (Pérdida) del Ejercicio en Curso' in html
            assert '3,000.00' in html
    finally:
        cur.execute("DISABLE TRIGGER ALL ON contabilidad.DetalleAsientos; DISABLE TRIGGER ALL ON contabilidad.AsientosDiario;")
        for aid in (asiento_prev, asiento_curr):
            if aid:
                aid_int = (aid.get('asiento_id') or aid.get('id')) if isinstance(aid, dict) else aid
                cur.execute("DELETE FROM contabilidad.DetalleAsientos WHERE AsientoID = ?", (aid_int,))
                cur.execute("DELETE FROM contabilidad.AsientosDiario WHERE ID = ?", (aid_int,))
        cur.execute("ENABLE TRIGGER ALL ON contabilidad.DetalleAsientos; ENABLE TRIGGER ALL ON contabilidad.AsientosDiario;")
        conn.commit()
        conn.close()


# ==============================================================================
# 6. L24 — Validación de fondos disponibles en egresos y vales
# ==============================================================================

def test_l24_egresos_and_vales_reject_insufficient_funds_and_invalid_account():
    cur = _sqlite_accounting_cursor()
    fecha_op = datetime(2026, 10, 15, 10, 0, 0)

    ContabilidadService.crear_asiento(
        cursor=cur,
        descripcion='Apertura de caja',
        detalles=[('1.1.01.001', 300.0, 0.0), ('3.1.01.001', 0.0, 300.0)],
        usuario_id=1,
        fecha=fecha_op,
    )

    with pytest.raises(ContabilidadError, match='Fondos insuficientes'):
        ContabilidadService.contabilizar_egreso(
            cursor=cur,
            usuario_id=1,
            concepto='Compra excesiva sin fondos',
            monto=500.0,
            metodo_pago='Efectivo',
            fecha=fecha_op,
        )

    with pytest.raises(ContabilidadError, match='Fondos insuficientes'):
        ContabilidadService.contabilizar_vale(
            cursor=cur,
            usuario_id=1,
            empleado_nombre='Juan Pérez',
            monto=350.0,
            metodo_pago='Efectivo',
            fecha=fecha_op,
        )

    with pytest.raises(ContabilidadError, match='efectivo o bancos'):
        ContabilidadService.contabilizar_egreso(
            cursor=cur,
            usuario_id=1,
            concepto='Cuenta inválida',
            monto=50.0,
            cuenta_pago='4.1.01.001',
            fecha=fecha_op,
        )

    asiento_id = ContabilidadService.contabilizar_egreso(
        cursor=cur,
        usuario_id=1,
        concepto='Pago agua potable',
        monto=120.0,
        metodo_pago='Efectivo',
        fecha=fecha_op,
    )
    assert asiento_id is not None
    assert float(ContabilidadService.obtener_saldo_disponible_cuenta(cur, '1.1.01.001')) == 180.0


# ==============================================================================
# 7. L25 — Regresión lineal rellena días con 0.0 y proyecta desde hoy_ni + 1
# ==============================================================================

def test_l25_sales_forecast_fills_calendar_gaps_and_projects_from_business_today():
    hoy = date(2026, 10, 20)
    historico = [
        {'Dia': date(2026, 10, 14), 'Total': 100.0},
        {'Dia': date(2026, 10, 16), 'Total': 200.0},
        {'Dia': date(2026, 10, 18), 'Total': 300.0},
    ]
    res = calcular_pronostico_ventas(historico, hoy=hoy)

    dias_hist = [d['dia'] for d in res['serie_diaria']]
    assert dias_hist == [
        '2026-10-14',
        '2026-10-15',
        '2026-10-16',
        '2026-10-17',
        '2026-10-18',
        '2026-10-19',
        '2026-10-20',
    ]
    totales_hist = [d['total'] for d in res['serie_diaria']]
    assert totales_hist == [100.0, 0.0, 200.0, 0.0, 300.0, 0.0, 0.0]

    assert res['prediccion_fechas_iso'] == [
        '2026-10-21',
        '2026-10-22',
        '2026-10-23',
        '2026-10-24',
        '2026-10-25',
        '2026-10-26',
        '2026-10-27',
    ]


# ==============================================================================
# 8. L27 — Cierre de período bloqueado cuando hay facturas o compras sin asiento
# ==============================================================================

def test_l27_period_close_requires_reconciled_invoices_and_purchases():
    cur = _sqlite_accounting_cursor()

    cur.execute("INSERT INTO PeriodosContables (ID, Mes, Anio, Estado) VALUES (1, 9, 2026, 'Abierto')")
    cur.execute(
        "INSERT INTO Facturas (ID, NumeroFactura, FechaHora, Subtotal, IVA, Total, EstadoFiscal) "
        "VALUES (50, 'FAC-000050', '2026-09-15 10:00:00', 200.0, 30.0, 230.0, 'Emitida')"
    )

    with pytest.raises(ContabilidadError, match='sin asiento contable conciliado'):
        ContabilidadService.cerrar_periodo(cur, 1, usuario_id=1)

    ContabilidadService.contabilizar_venta(
        cursor=cur,
        usuario_id=1,
        numero_factura='FAC-000050',
        subtotal=200.0,
        iva=30.0,
        total=230.0,
        pagos=[{'metodo': 'Efectivo', 'monto': 230.0}],
        fecha=datetime(2026, 9, 15, 10, 0, 0),
    )
    cur.execute(
        "INSERT INTO ComprasMateriaPrima (ID, FacturaProveedor, Fecha, CostoTotal, IVADocumentado) "
        "VALUES (70, 'FC-PROV-70', '2026-09-16 11:00:00', 500.0, 0.0)"
    )

    with pytest.raises(ContabilidadError, match='sin asiento contable conciliado'):
        ContabilidadService.cerrar_periodo(cur, 1, usuario_id=1)

    ContabilidadService.contabilizar_compra(
        cursor=cur,
        usuario_id=1,
        compra_id=70,
        monto_sin_iva=500.0,
        iva=0.0,
        monto_total=500.0,
        metodo_pago='Credito',
        referencia='FC-PROV-70',
        fecha=datetime(2026, 9, 16, 11, 0, 0),
    )
    ContabilidadService.cerrar_periodo(cur, 1, usuario_id=1)
    cur.execute("SELECT Estado FROM PeriodosContables WHERE ID = 1")
    assert cur.fetchone()[0] == 'Cerrado'


# ==============================================================================
# 9. Contrato CSRF HTTP 400 vs redirección en /login
# ==============================================================================

def test_csrf_error_returns_400_for_protected_routes_and_302_for_login(app):
    app.config['WTF_CSRF_ENABLED'] = True

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['_user_id'] = 'emp_1'
            sess['_fresh'] = True

        r_dgi = client.post('/admin/dgi/periodos', data={'mes': '2026-10'})
        assert r_dgi.status_code == 400

        r_egr = client.post('/admin/api/contabilidad/egresos', json={'concepto': 'Test', 'monto': 10})
        assert r_egr.status_code == 400

        r_login = client.post('/login', data={'username': 'admin', 'password': 'x'})
        assert r_login.status_code == 302
