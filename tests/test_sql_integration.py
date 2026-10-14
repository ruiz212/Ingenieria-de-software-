"""Integración real SQL Server. Solo admite una BD cuyo nombre empiece PanaderiaQA_."""
import os
import uuid
from datetime import datetime
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import pytest
import pyodbc
from app import create_app
from config import Config
from app.models import User
from app.services.contabilidad_service import ContabilidadService, ContabilidadError
from app.services.fiscal_service import next_invoice
from scripts.migrate_fiscal import migrate


@pytest.fixture(scope='module')
def connection_string():
    value=os.getenv('TEST_DB_CONNECTION_STRING')
    if not value: pytest.skip('Defina TEST_DB_CONNECTION_STRING para una base de QA.')
    c=pyodbc.connect(value)
    assert c.cursor().execute('SELECT DB_NAME()').fetchone()[0].startswith('PanaderiaQA_')
    migrate(c);c.commit();c.close()
    return value


@pytest.fixture
def conn(connection_string):
    c=pyodbc.connect(connection_string)
    yield c
    c.rollback();c.close()


@pytest.fixture
def app(connection_string):
    class TestConfig(Config):
        TESTING=True
        SECRET_KEY='only-for-isolated-qa'
        SQL_SERVER_CONNECTION_STRING=connection_string
    app=create_app(TestConfig)
    app.login_manager._user_callback=lambda _:User(1,'qa','Administrador QA',1,'SuperAdmin')
    return app


@pytest.fixture
def client(app):
    client=app.test_client()
    with client.session_transaction() as session:
        session['_user_id']='emp_1';session['_fresh']=True
    return client


def token(client):
    import re
    page=client.get('/admin/fiscal')
    assert page.status_code==200
    return re.search(r'name="csrf-token" content="([^"]+)"',page.text).group(1)


def test_csrf_missing_rejected(client):
    response=client.post('/api/factura',json={})
    assert response.status_code==400 and 'sesión' in response.json['error']


def test_journal_reversal_nets_zero(conn):
    cursor=conn.cursor()
    before=ContabilidadService.obtener_saldo_cuenta(cursor,ContabilidadService.CAJA_GENERAL_CS)
    original=ContabilidadService.crear_asiento(cursor,'QA prueba de reversión',[(ContabilidadService.CAJA_GENERAL_CS,10,0),(ContabilidadService.VENTAS_PAN,0,10)],1)
    ContabilidadService.revertir_asiento(cursor,original['asiento_id'],1,'Prueba de reversión')
    after=ContabilidadService.obtener_saldo_cuenta(cursor,ContabilidadService.CAJA_GENERAL_CS)
    assert after==before
    with pytest.raises(ContabilidadError): ContabilidadService.revertir_asiento(cursor,original['asiento_id'],1,'Segundo intento')


def test_closed_period_rejects_posting(conn):
    cursor=conn.cursor()
    period=ContabilidadService._obtener_o_crear_periodo(cursor,1,2020)
    ContabilidadService.cerrar_periodo(cursor,period,1)
    with pytest.raises(ContabilidadError):
        ContabilidadService.crear_asiento(cursor,'QA cerrado',[(ContabilidadService.CAJA_GENERAL_CS,10,0),(ContabilidadService.VENTAS_PAN,0,10)],1,fecha=datetime(2020,1,5))


def test_balanza_includes_opening_balance(conn):
    cursor=conn.cursor()
    ContabilidadService.crear_asiento(cursor,'QA apertura',[(ContabilidadService.CAJA_GENERAL_CS,7,0),(ContabilidadService.VENTAS_PAN,0,7)],1,fecha=datetime(2019,1,5))
    rows=ContabilidadService.balanza_mensual(cursor,2,2019)
    caja=next(r for r in rows if r['Codigo']==ContabilidadService.CAJA_GENERAL_CS)
    assert caja['SaldoAnterior']==7 and caja['TotalDebe']==0 and caja['SaldoFinal']==7


def test_sequence_parallel_transactions(connection_string):
    def take(_):
        c=pyodbc.connect(connection_string)
        try:
            result=next_invoice(c.cursor());c.commit();return result
        finally:c.close()
    with ThreadPoolExecutor(max_workers=6) as pool:
        values=list(pool.map(take,range(12)))
    numbers=sorted(int(v.split('-')[1]) for v in values)
    assert len(set(values))==12 and numbers==list(range(numbers[0],numbers[0]+12))


def test_invoice_retry_void_and_print(client,conn):
    cursor=conn.cursor()
    row=cursor.execute('SELECT TOP 1 ID,PrecioBase FROM Productos WHERE Activo=1 AND EsFicticio=0 AND PrecioBase>0').fetchone()
    csrf=token(client)
    body={'clave_solicitud':uuid.uuid4().hex,'carrito':[{'id':row[0],'cantidad':2,'precio':0.01}],
          'total':0.02,'subtotal':0.02,'iva':0,'pagos_multiples':[{'metodo':'Efectivo','monto':float(row[1])*2}]}
    result=client.post('/api/factura',json=body,headers={'X-CSRFToken':csrf})
    assert result.status_code==200,result.json
    document=result.json['factura']
    assert document['total']==float(row[1])*2
    again=client.post('/api/factura',json=body,headers={'X-CSRFToken':csrf})
    assert again.json['factura']['id']==document['id']
    changed={**body,'total':999}
    assert client.post('/api/factura',json=changed,headers={'X-CSRFToken':csrf}).status_code==409
    print_result=client.get(document['url_impresion'])
    assert print_result.status_code==200 and 'ORIGINAL' in print_result.text and 'COPIA' in print_result.text
    void=client.post(f"/admin/fiscal/facturas/{document['id']}/anular",data={'motivo':'Prueba de anulación QA','csrf_token':csrf})
    assert void.status_code==302
    assert 'ANULADO' in client.get(document['url_impresion']).text
    assert cursor.execute('SELECT SUM(Monto) FROM Pagos WHERE FacturaID=?',document['id']).fetchone()[0]==0


def test_rejected_sale_rolls_back_without_number(client,conn):
    csrf=token(client)
    before=conn.cursor().execute("SELECT Ultimo FROM SecuenciasFiscales WHERE Serie='FAC'").fetchone()[0]
    result=client.post('/api/factura',json={'clave_solicitud':uuid.uuid4().hex,
        'carrito':[{'id':999999999,'cantidad':1}], 'pagos_multiples':[{'metodo':'Efectivo','monto':20}]},headers={'X-CSRFToken':csrf})
    assert result.status_code==400
    assert conn.cursor().execute("SELECT Ultimo FROM SecuenciasFiscales WHERE Serie='FAC'").fetchone()[0]==before


def test_usd_uses_server_exchange_rate(client,conn):
    csrf=token(client)
    row=conn.cursor().execute('SELECT TOP 1 ID,PrecioBase FROM Productos WHERE Activo=1 AND EsFicticio=0 AND PrecioBase>0 AND PrecioBase<100 ORDER BY ID').fetchone()
    response=client.post('/api/factura',json={'clave_solicitud':uuid.uuid4().hex,
        'carrito':[{'id':row.ID,'cantidad':1}],
        'pagos_multiples':[{'metodo':'Efectivo USD','monto':100,'monto_cordobas':1}]},headers={'X-CSRFToken':csrf})
    assert response.status_code==200,response.json
    doc=response.json['factura']
    assert amount_for_test(doc['cambio']) == amount_for_test(100*Decimal(doc['tipo_cambio'])-row.PrecioBase)
    payment=conn.cursor().execute('SELECT Monto,MonedaRegistro,TipoCambioAplicado FROM Pagos WHERE FacturaID=?',doc['id']).fetchone()
    assert payment.Monto==row.PrecioBase and payment.MonedaRegistro=='NIO'
    journal=client.get(f"/admin/fiscal/asientos/{doc['asiento_id']}/imprimir")
    assert journal.status_code==200 and 'ORIGINAL' in journal.text and 'COPIA' in journal.text


def amount_for_test(value):
    return Decimal(str(value)).quantize(Decimal('.01'))


def test_issued_details_and_audit_immutable(conn):
    cursor=conn.cursor()
    row=cursor.execute('SELECT TOP 1 d.ID FROM DetalleFacturas d JOIN Facturas f ON f.ID=d.FacturaID WHERE f.DocumentoJSON IS NOT NULL').fetchone()
    assert row
    with pytest.raises(pyodbc.Error):
        cursor.execute('UPDATE DetalleFacturas SET Cantidad=Cantidad+1 WHERE ID=?',row.ID)
    conn.rollback()
    with pytest.raises(pyodbc.Error):
        cursor.execute('DELETE FROM BitacoraFiscal WHERE ID=(SELECT MIN(ID) FROM BitacoraFiscal)')


def test_staff_cannot_change_fiscal_settings(app):
    app.login_manager._user_callback=lambda _:User(1,'qa','Caja QA',2,'Estandar')
    client=app.test_client()
    with client.session_transaction() as session:
        session['_user_id']='emp_1';session['_fresh']=True
    assert client.get('/admin/fiscal').status_code in (302,403)
    import re
    csrf=re.search(r'name="csrf-token" content="([^"]+)"',client.get('/pos').text).group(1)
    assert client.post('/admin/fiscal/configuracion',data={'csrf_token':csrf,'regimen':'General'}).status_code in (302,403)
    result=client.post('/admin/api/usuarios',json={'nombre':'bad'},headers={'X-CSRFToken':csrf})
    assert result.status_code==403


@pytest.fixture
def employee(conn):
    cursor=conn.cursor()
    employee_id=cursor.execute("INSERT INTO Empleados(NombreCompleto,Cedula,Cargo,FechaIngreso,SalarioBase) OUTPUT INSERTED.ID VALUES(?,?,'Administracion','2020-01-01',12345.67)",'Empleado de prueba',uuid.uuid4().hex[:20]).fetchone()[0]
    conn.commit()
    yield employee_id
    cursor.execute("UPDATE Empleados SET EstadoEmpleado='Suspendido' WHERE ID=?",employee_id)
    conn.commit()


def test_invalid_monthly_payroll_does_not_write(client,conn,employee):
    csrf=token(client)
    before=conn.cursor().execute('SELECT COUNT(*) FROM Nomina').fetchone()[0]
    result=client.post('/admin/api/rrhh/nomina/calcular',json={'empleado_id':employee,'periodo_inicio':'2026-01-01','periodo_fin':'2026-01-15'},headers={'X-CSRFToken':csrf})
    assert result.status_code==400,result.json
    assert conn.cursor().execute('SELECT COUNT(*) FROM Nomina').fetchone()[0]==before


def test_payroll_cents_and_duplicate_period(client,conn,employee):
    csrf=token(client)
    body={'empleado_id':employee,'periodo_inicio':'2026-01-01','periodo_fin':'2026-01-31','dias_ausentes':0,'horas_extras':1.3}
    result=client.post('/admin/api/rrhh/nomina/calcular',json=body,headers={'X-CSRFToken':csrf})
    assert result.status_code==200,result.json
    cursor=conn.cursor()
    row=cursor.execute('SELECT ID,TotalDevengado,TotalDeducciones,SalarioNeto FROM Nomina WHERE EmpleadoID=?',employee).fetchone()
    assert row.TotalDevengado==row.TotalDeducciones+row.SalarioNeto
    sums=cursor.execute("SELECT SUM(d.Debe),SUM(d.Haber) FROM DetalleAsientos d JOIN AsientosDiario a ON a.ID=d.AsientoID WHERE a.ReferenciaExterna=?",f'NOM-{row.ID}').fetchone()
    assert sums[0] and sums[0]==sums[1]
    period=cursor.execute("SELECT p.Mes,p.Anio FROM AsientosDiario a JOIN PeriodosContables p ON p.ID=a.PeriodoID WHERE a.ReferenciaExterna=?",f'NOM-{row.ID}').fetchone()
    assert period.Mes==1 and period.Anio==2026
    duplicate=client.post('/admin/api/rrhh/nomina/calcular',json=body,headers={'X-CSRFToken':csrf})
    assert duplicate.status_code==400


def test_batch_payroll_posts_journal(client,conn,employee):
    csrf=token(client)
    result=client.post('/admin/api/rrhh/nomina/calcular_batch',json={'periodo_inicio':'2026-02-01','periodo_fin':'2026-02-28'},headers={'X-CSRFToken':csrf})
    assert result.status_code==200,result.json
    row=conn.cursor().execute("SELECT n.ID,a.ID FROM Nomina n LEFT JOIN AsientosDiario a ON a.ReferenciaExterna=CONCAT('NOM-',n.ID) WHERE n.EmpleadoID=?",employee).fetchone()
    assert row and row[1]


@pytest.fixture
def inventory(conn):
    cursor=conn.cursor()
    unit=cursor.execute('SELECT TOP 1 ID FROM UnidadesMedida').fetchone()[0]
    materia=cursor.execute("INSERT INTO MateriaPrima(Nombre,UnidadMedidaID,StockActual,StockMinimo) OUTPUT INSERTED.ID VALUES('Insumo QA',?,10,0)",unit).fetchone()[0]
    provider=cursor.execute("INSERT INTO Proveedores(Nombre) OUTPUT INSERTED.ID VALUES('Proveedor QA')").fetchone()[0]
    product=cursor.execute('SELECT TOP 1 ID FROM Productos WHERE Activo=1').fetchone()[0]
    cursor.execute('INSERT INTO RecetaProducto(ProductoID,MateriaPrimaID,CantidadNecesaria) VALUES(?,?,1)',product,materia)
    conn.commit()
    return materia,provider,product


def test_purchase_preserves_stock_on_invalid_tax(client,conn,inventory):
    cursor=conn.cursor()
    materia=cursor.execute('SELECT ID,StockActual FROM MateriaPrima WHERE ID=?',inventory[0]).fetchone()
    csrf=token(client)
    body={'materia_id':materia.ID,'proveedor_id':inventory[1],'cantidad':2,'costo':100,'iva_documentado':15,'factura_proveedor':'QA-IVA'}
    response=client.post('/admin/api/inventario/compra',json=body,headers={'X-CSRFToken':csrf})
    assert response.status_code==400,response.json
    assert cursor.execute('SELECT StockActual FROM MateriaPrima WHERE ID=?',materia.ID).fetchone()[0]==materia.StockActual


def test_purchase_stock_and_journal_commit_together(client,conn,inventory):
    cursor=conn.cursor()
    materia=cursor.execute('SELECT ID,StockActual FROM MateriaPrima WHERE ID=?',inventory[0]).fetchone()
    csrf=token(client)
    reference='QA-'+uuid.uuid4().hex[:12]
    response=client.post('/admin/api/inventario/compra',json={'materia_id':materia.ID,'proveedor_id':inventory[1],'cantidad':2,'costo':100,'iva_documentado':0,'factura_proveedor':reference},headers={'X-CSRFToken':csrf})
    assert response.status_code==200,response.json
    assert cursor.execute('SELECT StockActual FROM MateriaPrima WHERE ID=?',materia.ID).fetchone()[0]==materia.StockActual+2
    sums=cursor.execute('SELECT SUM(d.Debe),SUM(d.Haber) FROM DetalleAsientos d JOIN AsientosDiario a ON a.ID=d.AsientoID WHERE a.ReferenciaExterna=?',reference).fetchone()
    assert sums[0]==100 and sums[1]==100


def test_production_insufficient_stock_atomic(client,conn,inventory):
    cursor=conn.cursor()
    product=inventory[2]
    before=list(cursor.execute('SELECT ID,StockActual FROM MateriaPrima ORDER BY ID'))
    count=cursor.execute('SELECT COUNT(*) FROM ProduccionLotes').fetchone()[0]
    response=client.post('/admin/api/produccion/lote',json={'producto_id':product,'cantidad':999999},headers={'X-CSRFToken':token(client)})
    assert response.status_code==400,response.json
    assert list(cursor.execute('SELECT ID,StockActual FROM MateriaPrima ORDER BY ID'))==before
    assert cursor.execute('SELECT COUNT(*) FROM ProduccionLotes').fetchone()[0]==count


def test_materia_prima_accepts_zero_minimum(client,conn):
    unit=conn.cursor().execute('SELECT TOP 1 ID FROM UnidadesMedida').fetchone()[0]
    result=client.post('/admin/api/inventario/materia_prima',json={'nombre':'QA '+uuid.uuid4().hex[:8],'unidad_id':unit,'stock_minimo':0},headers={'X-CSRFToken':token(client)})
    assert result.status_code==200,result.json


@pytest.mark.parametrize('path',['/admin/dashboard','/admin/catalogo','/admin/inventario','/admin/produccion','/admin/usuarios','/admin/configuracion','/admin/contabilidad','/admin/contabilidad/balance','/admin/contabilidad/estado-resultados','/admin/contabilidad/comprobacion','/admin/contabilidad/mayor','/admin/contabilidad/catalogo','/admin/fidelizacion','/admin/arqueos','/admin/rrhh','/admin/rrhh/asistencia','/admin/estadistica','/monitor','/pos','/kiosco/'])
def test_module_pages(client,path):
    response=client.get(path)
    assert response.status_code==200,(path,response.status_code)
