"""Contrato de persistencia y límite de acceso del módulo de mercadotecnia."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from app.services import marketing_repository as repo


ROOT = Path(__file__).resolve().parents[1]


class Cursor:
    def __init__(self, rows=None, one=None):
        self.rows = rows or []
        self.one = one

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.one


def test_training_reads_bounded_issued_sales_and_saves_anonymous_snapshot(monkeypatch):
    calls = []
    monkeypatch.setattr(repo, 'execute_sp', lambda cursor, name, params=(): calls.append((name, params)))
    cursor = Cursor([SimpleNamespace(FacturaID=10, ProductoID=4, Cantidad=2,
                                     Subtotal=60, FechaHora=datetime(2026, 10, 25, 10))])

    model = repo.train_and_save(cursor, datetime(2026, 10, 26, 10))

    assert [name for name, _ in calls] == [
        'crm.sp_DatosEntrenamientoMercadotecnia', 'crm.sp_GuardarModeloMercadotecnia']
    assert model['source_rows'] == 1
    assert 'customer' not in calls[1][1][0].lower()
    assert 'revenue' not in calls[1][1][1].lower()
    assert 'invoice_count' not in calls[1][1][1].lower()


def test_sql_migration_limits_public_role_to_snapshot_and_own_history():
    sql = (ROOT / 'database' / '05_mercadotecnia.sql').read_text(encoding='utf-8')
    assert "f.EstadoFiscal = 'Emitida'" in sql
    assert 'TOP (30000)' in sql
    assert "SESSION_CONTEXT(N'usuario_id')" in sql
    assert "SESSION_CONTEXT(N'rol')" in sql
    assert 'GRANT EXECUTE ON OBJECT::[crm].[sp_LeerModeloPublicoMercadotecnia] TO [db_rol_portal_cliente]' in sql
    assert 'GRANT EXECUTE ON OBJECT::[crm].[sp_LeerModeloMercadotecnia] TO [db_rol_portal_cliente]' not in sql
    assert 'GRANT EXECUTE ON OBJECT::[crm].[sp_HistorialPersonalMercadotecnia] TO [db_rol_portal_cliente]' in sql
    assert 'GRANT EXECUTE ON OBJECT::[crm].[sp_GuardarModeloMercadotecnia] TO [db_rol_portal_cliente]' not in sql
    assert 'GRANT EXECUTE ON OBJECT::[crm].[sp_DatosEntrenamientoMercadotecnia] TO [db_rol_portal_cliente]' not in sql
    assert 'DENY EXECUTE ON OBJECT::[crm].[sp_LeerModeloMercadotecnia] TO [db_rol_cajero_pos]' in sql


def test_guest_never_uses_shared_customer_history(monkeypatch):
    monkeypatch.setattr(repo, 'load_model', lambda cursor, **kwargs: {'products': {'4': {'score': 2}}, 'pairs': {}})
    monkeypatch.setattr(repo, 'customer_history', lambda cursor: (_ for _ in ()).throw(AssertionError('historial compartido')))
    guest = SimpleNamespace(is_authenticated=True, rol_nombre='Invitado', id=1, es_invitado=True)
    products = [dict(id=4, nombre='Bolillo', activo=True, es_ficticio=False, descuento=0)]

    result = repo.store_recommendations(Cursor(), products, guest)

    assert result[0]['id'] == 4


def test_store_uses_catalog_fallback_when_model_is_not_migrated(monkeypatch):
    import pyodbc
    monkeypatch.setattr(repo, 'load_model', lambda cursor, **kwargs: (_ for _ in ()).throw(pyodbc.Error('no existe')))
    guest = SimpleNamespace(is_authenticated=False)
    products = [dict(id=4, nombre='Bolillo', activo=True, es_ficticio=False, descuento=10)]

    result = repo.store_recommendations(Cursor(), products, guest)

    assert result[0]['id'] == 4
    assert result[0]['motivo'] == 'Promoción vigente'
