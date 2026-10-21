"""Two-session fiscal locking regression using one reusable, labeled QA fixture.

SQL Server forbids deleting even synthetic invoices. This test intentionally retains
QA_RACE_R3_20261020, annulled, with a closed shift, disabled user and no money or
journal. Reruns reuse its IDs; they never disable immutable-document triggers.
"""
import json
import os
from datetime import datetime
from pathlib import Path

import pyodbc
import pytest

from app.db import as_db_role
from app.qa_safety import connect_qa


MARKER='QA_RACE_R3_20261020'
CODE='QAR3OCT20'


def test_native_delivery_invoice_lock_serializes_fiscal_annulment():
    connection_string=os.environ.get('TEST_DB_CONNECTION_STRING')
    if not connection_string:
        pytest.skip('Explicit QA SQL Server connection required')
    first=connect_qa(pyodbc.connect,connection_string)
    second=connect_qa(pyodbc.connect,connection_string)
    fixture=None
    evidence={}
    try:
        cur=first.cursor()
        fixture=cur.execute('SELECT ID,UsuarioID,TurnoID,CodigoSeguimiento,Total FROM ventas.Facturas WHERE NumeroFactura=?',MARKER).fetchone()
        if fixture is None:
            role=cur.execute('SELECT TOP 1 ID FROM seguridad.Roles ORDER BY ID').fetchone()[0]
            user=cur.execute('INSERT INTO seguridad.Usuarios(NombreCompleto,Username,PasswordHash,RolID,Activo) OUTPUT INSERTED.ID VALUES(?,?,?,?,0)',MARKER,MARKER,'synthetic-disabled',role).fetchone()[0]
            shift=cur.execute('INSERT INTO ventas.TurnosCaja(UsuarioID,Cerrado) OUTPUT INSERTED.ID VALUES(?,0)',user).fetchone()[0]
            invoice=cur.execute("INSERT INTO ventas.Facturas(NumeroFactura,CodigoSeguimiento,UsuarioID,ClienteID,TurnoID,Subtotal,IVA,Total,EsEncargo,IncluyeRUC,EstadoFiscal) OUTPUT INSERTED.ID VALUES(?,?,?,1,?,0,0,0,1,0,'Emitida')",MARKER,CODE,user,shift).fetchone()[0]
            cur.execute("INSERT INTO ventas.Encargos(FacturaID,FechaEntrega,Estado) VALUES(?,GETDATE(),'Listo')",invoice)
            fixture=(invoice,user,shift,CODE,0)
        invoice,user,shift,code,total=fixture
        assert code == CODE and total == 0
        assert cur.execute('SELECT Username FROM seguridad.Usuarios WHERE ID=?',user).fetchone()[0] == MARKER
        cur.execute("UPDATE ventas.Facturas SET EstadoFiscal='Emitida' WHERE ID=? AND NumeroFactura=?",invoice,MARKER)
        cur.execute("UPDATE ventas.Encargos SET Estado='Listo' WHERE FacturaID=?",invoice)
        first.commit()
        evidence={'marker':MARKER,'invoice_id':invoice,'user_id':user,'shift_id':shift}
        with as_db_role(cur,'Operativo'):
            cur.execute('EXEC produccion.sp_ObtenerEncargoPorCodigoBloqueo ?',CODE)
            assert cur.fetchone().EstadoFiscal == 'Emitida'
        other=second.cursor()
        other.execute('SET LOCK_TIMEOUT 250')
        with as_db_role(other,'Admin'):
            with pytest.raises(pyodbc.Error,match='1222'):
                other.execute('EXEC ventas.sp_ObtenerFacturaParaAnularBloqueo ?',invoice).fetchone()
        second.rollback()
        evidence['annulment_blocked_while_delivery_holds_invoice']=True
        cur.execute('EXEC ventas.sp_MarcarFacturaAnulada ?,?,?,?',user,datetime.now(),'Owned QA concurrency fixture',invoice)
        first.commit()
        with as_db_role(other,'Operativo'):
            other.execute('EXEC produccion.sp_ObtenerEncargoPorCodigoBloqueo ?',CODE)
            assert other.fetchone().EstadoFiscal == 'Anulada'
            other.execute('EXEC produccion.sp_ActualizarEstadoEncargoCompare ?,?,?','Entregado',CODE,'Listo')
        assert other.execute('SELECT Estado FROM ventas.Encargos WHERE FacturaID=?',invoice).fetchone()[0] == 'Listo'
        evidence['delivery_after_annulment_rejected']=True
        second.rollback()
    finally:
        first.rollback()
        second.rollback()
        first.close()
        second.close()
        if fixture is not None:
            invoice,user,shift,code,total=fixture
            cleanup=connect_qa(pyodbc.connect,connection_string)
            try:
                cur=cleanup.cursor()
                cur.execute("UPDATE ventas.Facturas SET EstadoFiscal='Anulada' WHERE ID=? AND NumeroFactura=?",invoice,MARKER)
                cur.execute("UPDATE ventas.Encargos SET Estado='Entregado' WHERE FacturaID=?",invoice)
                cur.execute('UPDATE ventas.TurnosCaja SET Cerrado=1,FechaCierre=GETDATE() WHERE ID=? AND UsuarioID=?',shift,user)
                evidence['payments']=cur.execute('SELECT COUNT(*) FROM ventas.Pagos WHERE FacturaID=?',invoice).fetchone()[0]
                evidence['journal_entries']=cur.execute('SELECT COUNT(*) FROM contabilidad.AsientosDiario WHERE ReferenciaExterna=?',MARKER).fetchone()[0]
                assert evidence['payments'] == 0 and evidence['journal_entries'] == 0
                cleanup.commit()
                evidence['retained_fixture_state']='Anulada; closed shift; disabled user; delivered synthetic order'
            finally:
                cleanup.close()
        output=os.environ.get('CASH_RACE_EVIDENCE')
        if output:
            Path(output).write_text(json.dumps(evidence,indent=2),encoding='utf-8')
