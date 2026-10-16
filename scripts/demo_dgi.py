"""Demostración sintética integrada. Rechaza bases cuyo nombre no empiece PanaderiaQA_.

python scripts/demo_dgi.py --connection-env TEST_DB_CONNECTION_STRING --mes 2030-10
python scripts/demo_dgi.py --connection-env TEST_DB_CONNECTION_STRING --corregir-periodo ID
"""
import argparse
import json
import os
import secrets
import sys
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pyodbc
from dotenv import load_dotenv

from app.services import dgi_repository as repo
from app.services.contabilidad_service import ContabilidadService as Accounting
from app.services.dgi_engine import analyze, json_dump, monthly_period
from scripts.migrate_dgi import migrate


def require_qa(connection):
    name = connection.cursor().execute('SELECT DB_NAME()').fetchone()[0]
    if not name.startswith('PanaderiaQA_'):
        raise ValueError('Solo se admiten bases aisladas PanaderiaQA_. No se insertaron datos.')


def create_demo_user(connection):
    """Cuenta independiente y aleatoria, exclusivamente en QA; no altera usuarios previos."""
    require_qa(connection)
    from werkzeug.security import generate_password_hash
    cursor = connection.cursor()
    role = cursor.execute("SELECT ID FROM Roles WHERE Nombre='SuperAdmin'").fetchone()
    if not role:
        raise ValueError('Falta el rol SuperAdmin del sistema existente.')
    username, password = 'dgi_demo_' + uuid.uuid4().hex[:6], secrets.token_urlsafe(18)
    user_id = cursor.execute('''INSERT INTO Usuarios(NombreCompleto,Username,PasswordHash,RolID)
        OUTPUT INSERTED.ID VALUES(?,?,?,?)''', 'Revisor DGI SINTÉTICO QA', username,
        generate_password_hash(password), role[0]).fetchone()[0]
    repo.audit(cursor, user_id, 'DGI_CUENTA_DEMO', 'Usuarios', user_id, {'solo_qa': True})
    return dict(id=user_id, usuario=username, clave=password)


def seed_case(connection, month, actor=1, reconciled=False):
    require_qa(connection)
    cursor = connection.cursor()
    start, end = monthly_period(month)
    if cursor.execute('SELECT TOP 1 ID FROM Facturas WHERE FechaHora>=? AND FechaHora<DATEADD(day,1,?)', start, end).fetchone():
        raise ValueError('El mes contiene facturas. Seleccione otro mes vacío para no mezclar demostraciones.')
    if cursor.execute('SELECT TOP 1 ID FROM AsientosDiario WHERE Fecha>=? AND Fecha<DATEADD(day,1,?)', start, end).fetchone():
        raise ValueError('El mes contiene asientos. Seleccione otro mes vacío.')
    data = dict(fiscal_razon_social='EMPRESA SINTÉTICA DEMO DGI', fiscal_ruc='DEMO-SIN-VALIDEZ',
                fiscal_regimen='Cuota fija', dgi_responsable='Responsable de demostración',
                dgi_obligaciones='Diagnóstico interno', dgi_vigente_desde='2000-01-01', dgi_vigente_hasta='')
    # La demo comparte perfil con POS; completar sus prerrequisitos solo con marcas ficticias.
    for key, value in [('fiscal_direccion', 'DOMICILIO SINTÉTICO QA'), ('fiscal_telefono', 'TELÉFONO SINTÉTICO QA'),
                       ('fiscal_autorizacion', 'DEMO SINTÉTICA SIN AUTORIZACIÓN REAL')]:
        cursor.execute("UPDATE ConfiguracionSistema SET Valor=? WHERE Clave=? AND Valor=''", value, key)
    repo.save_profile(cursor, data, actor)
    period_id = repo.create_period(cursor, month, actor)
    product = cursor.execute('SELECT TOP 1 ID FROM Productos ORDER BY ID').fetchone()
    supplier = cursor.execute('SELECT TOP 1 ID FROM Proveedores ORDER BY ID').fetchone()
    material = cursor.execute('SELECT TOP 1 ID FROM MateriaPrima ORDER BY ID').fetchone()
    if not product or not supplier or not material:
        raise ValueError('La base QA necesita al menos un producto, proveedor y materia prima de prueba.')
    tag = uuid.uuid4().hex[:6]
    invoice_ids = []
    stamp = datetime(start.year, start.month, 10, 10, 0)
    for index in range(1, 4):
        number = f'DEMO-DGI-{tag}-{index}'
        rid = cursor.execute('''INSERT INTO Facturas(NumeroFactura,CodigoSeguimiento,FechaHora,UsuarioID,Subtotal,IVA,Total)
            OUTPUT INSERTED.ID VALUES(?,?,?,?,40000,0,40000)''', number, uuid.uuid4().hex[:10], stamp, actor).fetchone()[0]
        cursor.execute('INSERT INTO DetalleFacturas(FacturaID,ProductoID,Cantidad,PrecioUnitario,Subtotal) VALUES(?,?,1,40000,40000)', rid, product[0])
        document = dict(id=rid, numero_factura=number, emisor=data, fecha=stamp.strftime('%d/%m/%Y'), hora='10:00:00',
            condicion='DEMO', aviso='COMPROBANTE SINTÉTICO DE DEMOSTRACIÓN. SIN VALIDEZ FISCAL.',
            subtotal=40000, iva=0, total=40000, ruc=None, encargo_detalles=None,
            productos=[dict(cantidad=1,nombre='Operación sintética DGI',precio_lista=40000,descuento=0,subtotal=40000,iva=0,
                            detalle_ingredientes={'ingredientes': []})])
        cursor.execute('UPDATE Facturas SET DocumentoJSON=? WHERE ID=?', json_dump(document), rid)
        invoice_ids.append(rid)
    entry = Accounting.crear_asiento(cursor, 'DEMO DGI: ingresos sintéticos del período',
        [(Accounting.CAJA_GENERAL_CS, 120000 if reconciled else 110000, 0),
         (Accounting.VENTAS_PAN, 0, 120000 if reconciled else 110000)], actor,
        referencia_externa=f'DEMO-DGI-{tag}', fecha=stamp)
    purchase_id = cursor.execute('''INSERT INTO ComprasMateriaPrima(MateriaPrimaID,ProveedorID,Cantidad,CostoTotal,Fecha,FacturaProveedor,IVADocumentado)
        OUTPUT INSERTED.ID VALUES(?,?,1,5000,?,?,0)''', material[0], supplier[0], stamp, f'DEMO-COMPRA-{tag}').fetchone()[0]
    revision_id = repo.create_review(cursor, period_id, 'Diagnóstico interno', actor)
    return dict(periodo_id=period_id, revision_id=revision_id, facturas=invoice_ids,
                compra_id=purchase_id, asiento_id=entry['asiento_id'], mes=month)


def correct_case(connection, period_id, actor=1):
    require_qa(connection)
    cursor = connection.cursor()
    period = repo.get_period(cursor, period_id)
    data = repo.snapshot(cursor, period, 'Diagnóstico interno')
    if len(data['ventas']) != 3 or any(not r['numero'].startswith('DEMO-DGI-') for r in data['ventas']):
        raise ValueError('El período no coincide con una demostración sintética de este script.')
    result = analyze(data)
    delta = Decimal(result['totales']['diferencia'])
    if delta == 0:
        return repo.create_review(cursor, period_id, 'Diagnóstico interno', actor)
    if delta != Decimal('10000'):
        raise ValueError('La diferencia no coincide con la demo de C$10000. Revise los datos.')
    Accounting.crear_asiento(cursor, 'DEMO DGI: ajuste sintético de conciliación',
        [(Accounting.CAJA_GENERAL_CS, 10000, 0), (Accounting.VENTAS_PAN, 0, 10000)], actor,
        referencia_externa=f'DEMO-CORRECCION-{period_id}',
        fecha=datetime(period['Desde'].year, period['Desde'].month, 11, 10))
    return repo.create_review(cursor, period_id, 'Diagnóstico interno', actor)


if __name__ == '__main__':
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-env', required=True)
    parser.add_argument('--mes', default='2030-10')
    parser.add_argument('--corregir-periodo', type=int)
    args = parser.parse_args()
    connection = pyodbc.connect(os.environ[args.connection_env])
    try:
        require_qa(connection)
        migrate(connection)
        result = {'revision_corregida': correct_case(connection, args.corregir_periodo)} if args.corregir_periodo else seed_case(connection, args.mes)
        connection.commit()
        print(json.dumps(result, ensure_ascii=False))
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
