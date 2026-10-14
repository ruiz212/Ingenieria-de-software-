"""Migración aditiva DGI. Ejecutar con una conexión explícita y respaldo previo.

Uso: python scripts/migrate_fiscal.py --connection-env DB_CONNECTION_STRING
No borra ni renumera documentos existentes. Falla si hay numeración duplicada.
"""
import argparse
import os
from pathlib import Path
import pyodbc


def migrate(connection):
    cursor = connection.cursor()
    cursor.execute('ALTER TABLE ConfiguracionSistema ALTER COLUMN Valor NVARCHAR(MAX) NOT NULL')
    for table, column, definition in [
        ('Facturas', 'EstadoFiscal', "VARCHAR(12) NOT NULL DEFAULT 'Emitida'"),
        ('Facturas', 'DocumentoJSON', 'NVARCHAR(MAX) NULL'),
        ('Facturas', 'AnuladaPor', 'INT NULL'),
        ('Facturas', 'FechaAnulacion', 'DATETIME NULL'),
        ('Facturas', 'MotivoAnulacion', 'NVARCHAR(300) NULL'),
        ('Facturas', 'ClaveSolicitud', 'VARCHAR(64) NULL'),
        ('Pagos', 'MonedaRegistro', "VARCHAR(6) NOT NULL DEFAULT 'Legacy'"),
        ('Pagos', 'TipoCambioAplicado', 'DECIMAL(12,6) NULL'),
        ('Productos', 'TasaIVA', 'DECIMAL(5,2) NULL'),
        ('Productos', 'MotivoExencion', 'NVARCHAR(200) NULL'),
        ('ComprasMateriaPrima', 'FacturaProveedor', 'NVARCHAR(50) NULL'),
        ('ComprasMateriaPrima', 'IVADocumentado', 'DECIMAL(18,2) NOT NULL DEFAULT 0'),
        ('PeriodosContables', 'CerradoPor', 'INT NULL'),
        ('PeriodosContables', 'CerradoEn', 'DATETIME NULL'),
        ('AsientosDiario', 'EmisorJSON', 'NVARCHAR(MAX) NULL'),
    ]:
        cursor.execute(f"IF COL_LENGTH('{table}', '{column}') IS NULL ALTER TABLE {table} ADD {column} {definition}")
    cursor.execute("""
        IF OBJECT_ID('SecuenciasFiscales') IS NULL
        CREATE TABLE SecuenciasFiscales (Serie VARCHAR(10) PRIMARY KEY, Ultimo BIGINT NOT NULL DEFAULT 0);
        IF NOT EXISTS (SELECT 1 FROM SecuenciasFiscales WHERE Serie='FAC')
        INSERT INTO SecuenciasFiscales (Serie, Ultimo)
        SELECT 'FAC', ISNULL(MAX(TRY_CONVERT(BIGINT, SUBSTRING(NumeroFactura, 5, 20))),0)
        FROM Facturas WHERE NumeroFactura LIKE 'FAC-%';
        IF OBJECT_ID('BitacoraFiscal') IS NULL
        CREATE TABLE BitacoraFiscal (
            ID BIGINT IDENTITY PRIMARY KEY, Fecha DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
            UsuarioID INT NULL, Accion NVARCHAR(50) NOT NULL,
            Entidad NVARCHAR(50) NOT NULL, EntidadID INT NULL,
            Detalle NVARCHAR(MAX) NOT NULL, IP VARCHAR(45) NULL);
    """)
    for name, table, columns, where in [
        ('UX_FiscalNumero', 'Facturas', 'NumeroFactura', ''),
        ('UX_FiscalSolicitud', 'Facturas', 'ClaveSolicitud', 'WHERE ClaveSolicitud IS NOT NULL'),
        ('UX_FiscalPeriodo', 'PeriodosContables', 'Anio, Mes', ''),
        ('UX_FiscalComprobante', 'AsientosDiario', 'NumeroComprobante', 'WHERE NumeroComprobante IS NOT NULL'),
    ]:
        cursor.execute(f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='{name}') CREATE UNIQUE INDEX {name} ON {table} ({columns}) {where}")
    defaults = {
        'fiscal_regimen': ('Pendiente', 'Pendiente, Cuota fija o General; confirmar con la inscripción DGI'),
        'fiscal_razon_social': ('', 'Razón social del emisor'),
        'fiscal_ruc': ('', 'RUC del emisor según inscripción'),
        'fiscal_direccion': ('', 'Dirección del establecimiento'),
        'fiscal_telefono': ('', 'Teléfono del emisor'),
        'fiscal_correo': ('', 'Correo del emisor'),
        'fiscal_autorizacion': ('', 'Referencia de autorización real DGI; no constituye validación automática'),
        'fiscal_sucursal': ('Casa matriz', 'Establecimiento emisor; esta instalación usa una sola serie'),
        'fiscal_serie': ('FAC', 'Serie fija para esta instalación; no editar con ventas existentes'),
    }
    for key, (value, description) in defaults.items():
        cursor.execute("IF NOT EXISTS(SELECT 1 FROM ConfiguracionSistema WHERE Clave=?) INSERT INTO ConfiguracionSistema(Clave,Valor,Descripcion) VALUES(?,?,?)", key,key,value,description)
    cursor.execute("""
        IF OBJECT_ID('CK_Nomina_Estado','C') IS NOT NULL ALTER TABLE Nomina DROP CONSTRAINT CK_Nomina_Estado;
        ALTER TABLE Nomina WITH CHECK ADD CONSTRAINT CK_Nomina_Estado CHECK
        (Estado IN ('Borrador','Aprobada','Pagada','Anulada','Contabilizada'));
    """)
    # Impedir alteración del contenido de facturas que ya tienen instantánea fiscal.
    cursor.execute("""
    CREATE OR ALTER TRIGGER TR_FiscalFacturaInmutable ON Facturas AFTER UPDATE, DELETE AS
    BEGIN
      SET NOCOUNT ON;
      IF EXISTS(SELECT 1 FROM deleted d LEFT JOIN inserted i ON i.ID=d.ID WHERE i.ID IS NULL)
        THROW 51001, 'Las facturas se anulan, no se eliminan.', 1;
      IF EXISTS(SELECT 1 FROM deleted d JOIN inserted i ON i.ID=d.ID
        WHERE d.NumeroFactura<>i.NumeroFactura OR d.Total<>i.Total OR d.Subtotal<>i.Subtotal OR d.IVA<>i.IVA
        OR (d.DocumentoJSON IS NOT NULL AND (i.DocumentoJSON IS NULL OR d.DocumentoJSON<>i.DocumentoJSON)))
        THROW 51002, 'No se puede alterar una factura emitida.', 1;
    END
    """)
    cursor.execute("""
    CREATE OR ALTER TRIGGER TR_FiscalBitacoraInmutable ON BitacoraFiscal INSTEAD OF UPDATE, DELETE AS
    BEGIN THROW 51003, 'La bitácora fiscal no permite edición ni borrado.', 1; END
    """)
    cursor.execute("""
    CREATE OR ALTER TRIGGER TR_FiscalDetalleInmutable ON DetalleFacturas AFTER UPDATE, DELETE AS
    BEGIN
      SET NOCOUNT ON;
      IF EXISTS(SELECT 1 FROM (SELECT FacturaID FROM inserted UNION SELECT FacturaID FROM deleted) d
                JOIN Facturas f ON f.ID=d.FacturaID WHERE f.DocumentoJSON IS NOT NULL)
        THROW 51004, 'No se puede alterar el detalle de una factura emitida.', 1;
    END
    """)
    cursor.execute("""
    CREATE OR ALTER TRIGGER TR_FiscalAsientoDetalleInmutable ON DetalleAsientos AFTER UPDATE, DELETE AS
    BEGIN
      SET NOCOUNT ON;
      IF EXISTS(SELECT 1 FROM deleted d JOIN AsientosDiario a ON a.ID=d.AsientoID
                WHERE a.Estado IN ('Contabilizado','Anulado'))
        THROW 51005, 'Corrija el asiento mediante reversión, no editando sus líneas.', 1;
    END
    """)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-env', required=True)
    args = parser.parse_args()
    conn = pyodbc.connect(os.environ[args.connection_env])
    try:
        migrate(conn)
        conn.commit()
        print('Migración fiscal completada sin eliminar registros.')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
