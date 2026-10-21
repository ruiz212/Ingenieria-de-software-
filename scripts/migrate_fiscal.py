"""Migración aditiva DGI. Ejecutar con una conexión explícita y respaldo previo.

Uso: python scripts/migrate_fiscal.py --connection-env DB_CONNECTION_STRING
No borra ni renumera documentos existentes. Falla si hay numeración duplicada.
"""
import argparse
import os
from pathlib import Path
import pyodbc
from dotenv import load_dotenv

load_dotenv()


def _resolve_table(cursor, name, default_schema='dbo'):
    row = cursor.execute(
        "SELECT TOP 1 s.name + '.' + t.name FROM sys.tables t "
        "JOIN sys.schemas s ON t.schema_id = s.schema_id WHERE t.name = ?",
        name
    ).fetchone()
    if row:
        return row[0]
    has_schema = cursor.execute("SELECT 1 FROM sys.schemas WHERE name = ?", default_schema).fetchone()
    return f"{default_schema}.{name}" if has_schema else f"dbo.{name}"


def migrate(connection):
    cursor = connection.cursor()
    cfg_tbl = _resolve_table(cursor, 'ConfiguracionSistema', 'seguridad')
    cursor.execute(f'ALTER TABLE {cfg_tbl} ALTER COLUMN Valor NVARCHAR(MAX) NOT NULL')
    for table, schema, column, definition in [
        ('Facturas', 'ventas', 'EstadoFiscal', "VARCHAR(12) NOT NULL DEFAULT 'Emitida'"),
        ('Facturas', 'ventas', 'DocumentoJSON', 'NVARCHAR(MAX) NULL'),
        ('Facturas', 'ventas', 'AnuladaPor', 'INT NULL'),
        ('Facturas', 'ventas', 'FechaAnulacion', 'DATETIME NULL'),
        ('Facturas', 'ventas', 'MotivoAnulacion', 'NVARCHAR(300) NULL'),
        ('Facturas', 'ventas', 'ClaveSolicitud', 'VARCHAR(64) NULL'),
        ('Pagos', 'ventas', 'MonedaRegistro', "VARCHAR(6) NOT NULL DEFAULT 'Legacy'"),
        ('Pagos', 'ventas', 'TipoCambioAplicado', 'DECIMAL(12,6) NULL'),
        ('Productos', 'catalogo', 'TasaIVA', 'DECIMAL(5,2) NULL'),
        ('Productos', 'catalogo', 'MotivoExencion', 'NVARCHAR(200) NULL'),
        ('ComprasMateriaPrima', 'produccion', 'FacturaProveedor', 'NVARCHAR(50) NULL'),
        ('ComprasMateriaPrima', 'produccion', 'IVADocumentado', 'DECIMAL(18,2) NOT NULL DEFAULT 0'),
        ('PeriodosContables', 'contabilidad', 'CerradoPor', 'INT NULL'),
        ('PeriodosContables', 'contabilidad', 'CerradoEn', 'DATETIME NULL'),
        ('AsientosDiario', 'contabilidad', 'EmisorJSON', 'NVARCHAR(MAX) NULL'),
    ]:
        resolved = _resolve_table(cursor, table, schema)
        cursor.execute(f"IF COL_LENGTH('{resolved}', '{column}') IS NULL ALTER TABLE {resolved} ADD {column} {definition}")
    sec_tbl = _resolve_table(cursor, 'SecuenciasFiscales', 'ventas')
    bit_tbl = _resolve_table(cursor, 'BitacoraFiscal', 'fiscal')
    fac_tbl = _resolve_table(cursor, 'Facturas', 'ventas')
    det_fac_tbl = _resolve_table(cursor, 'DetalleFacturas', 'ventas')
    per_tbl = _resolve_table(cursor, 'PeriodosContables', 'contabilidad')
    asi_tbl = _resolve_table(cursor, 'AsientosDiario', 'contabilidad')
    det_asi_tbl = _resolve_table(cursor, 'DetalleAsientos', 'contabilidad')
    nom_tbl = _resolve_table(cursor, 'Nomina', 'rrhh')
    cursor.execute(f"""
        IF OBJECT_ID('{sec_tbl}', 'U') IS NULL
        CREATE TABLE {sec_tbl} (Serie VARCHAR(10) PRIMARY KEY, Ultimo BIGINT NOT NULL DEFAULT 0);
        IF NOT EXISTS (SELECT 1 FROM {sec_tbl} WHERE Serie='FAC')
        INSERT INTO {sec_tbl} (Serie, Ultimo)
        SELECT 'FAC', ISNULL(MAX(TRY_CONVERT(BIGINT, SUBSTRING(NumeroFactura, 5, 20))),0)
        FROM {fac_tbl} WHERE NumeroFactura LIKE 'FAC-%';
        IF OBJECT_ID('{bit_tbl}', 'U') IS NULL
        CREATE TABLE {bit_tbl} (
            ID BIGINT IDENTITY PRIMARY KEY, Fecha DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
            UsuarioID INT NULL, Accion NVARCHAR(50) NOT NULL,
            Entidad NVARCHAR(50) NOT NULL, EntidadID INT NULL,
            Detalle NVARCHAR(MAX) NOT NULL, IP VARCHAR(45) NULL);
    """)
    for name, resolved_table, columns, where in [
        ('UX_FiscalNumero', fac_tbl, 'NumeroFactura', ''),
        ('UX_FiscalSolicitud', fac_tbl, 'ClaveSolicitud', 'WHERE ClaveSolicitud IS NOT NULL'),
        ('UX_FiscalPeriodo', per_tbl, 'Anio, Mes', ''),
        ('UX_FiscalComprobante', asi_tbl, 'NumeroComprobante', 'WHERE NumeroComprobante IS NOT NULL'),
    ]:
        cursor.execute(f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='{name}') CREATE UNIQUE INDEX {name} ON {resolved_table} ({columns}) {where}")
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
        'tipo_cambio_usd': ('36.6243', 'Córdobas por dólar según el tipo de cambio oficial BCN; actualizar cuando corresponda'),
    }
    for key, (value, description) in defaults.items():
        cursor.execute(f"IF NOT EXISTS(SELECT 1 FROM {cfg_tbl} WHERE Clave=?) INSERT INTO {cfg_tbl}(Clave,Valor,Descripcion) VALUES(?,?,?)", key,key,value,description)
    nom_schema = nom_tbl.split('.')[0]
    cursor.execute(f"""
        IF OBJECT_ID('{nom_schema}.CK_Nomina_Estado','C') IS NOT NULL ALTER TABLE {nom_tbl} DROP CONSTRAINT CK_Nomina_Estado;
        IF OBJECT_ID('CK_Nomina_Estado','C') IS NOT NULL ALTER TABLE {nom_tbl} DROP CONSTRAINT CK_Nomina_Estado;
        ALTER TABLE {nom_tbl} WITH CHECK ADD CONSTRAINT CK_Nomina_Estado CHECK
        (Estado IN ('Borrador','Aprobada','Pagada','Anulada','Contabilizada'));
    """)
    fac_schema = fac_tbl.split('.')[0]
    bit_schema = bit_tbl.split('.')[0]
    det_fac_schema = det_fac_tbl.split('.')[0]
    det_asi_schema = det_asi_tbl.split('.')[0]
    # Impedir alteración del contenido de facturas que ya tienen instantánea fiscal.
    cursor.execute(f"""
    CREATE OR ALTER TRIGGER {fac_schema}.TR_FiscalFacturaInmutable ON {fac_tbl} AFTER UPDATE, DELETE AS
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
    cursor.execute(f"""
    CREATE OR ALTER TRIGGER {bit_schema}.TR_FiscalBitacoraInmutable ON {bit_tbl} INSTEAD OF UPDATE, DELETE AS
    BEGIN THROW 51003, 'La bitácora fiscal no permite edición ni borrado.', 1; END
    """)
    cursor.execute(f"""
    CREATE OR ALTER TRIGGER {det_fac_schema}.TR_FiscalDetalleInmutable ON {det_fac_tbl} AFTER UPDATE, DELETE AS
    BEGIN
      SET NOCOUNT ON;
      IF EXISTS(SELECT 1 FROM (SELECT FacturaID FROM inserted UNION SELECT FacturaID FROM deleted) d
                JOIN {fac_tbl} f ON f.ID=d.FacturaID WHERE f.DocumentoJSON IS NOT NULL)
        THROW 51004, 'No se puede alterar el detalle de una factura emitida.', 1;
    END
    """)
    cursor.execute(f"""
    CREATE OR ALTER TRIGGER {det_asi_schema}.TR_FiscalAsientoDetalleInmutable ON {det_asi_tbl} AFTER UPDATE, DELETE AS
    BEGIN
      SET NOCOUNT ON;
      IF EXISTS(SELECT 1 FROM deleted d JOIN {asi_tbl} a ON a.ID=d.AsientoID
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
