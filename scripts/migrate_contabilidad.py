import pyodbc
import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from config import Config

def migrate():
    conn_str = Config.SQL_SERVER_CONNECTION_STRING
    print(f"Conectando a {conn_str}...")
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        sql = """
        -- 1. Catálogo de Cuentas
        IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[CatalogoCuentas]') AND type in (N'U'))
        BEGIN
            CREATE TABLE CatalogoCuentas (
                ID INT PRIMARY KEY IDENTITY(1,1),
                Codigo VARCHAR(20) NOT NULL UNIQUE,
                Nombre VARCHAR(100) NOT NULL,
                Clase VARCHAR(20) NOT NULL,
                Grupo VARCHAR(50) NOT NULL,
                Naturaleza VARCHAR(10) NOT NULL,
                Activa BIT NOT NULL DEFAULT 1,
                CONSTRAINT CK_Cuenta_Naturaleza CHECK (Naturaleza IN ('Deudora', 'Acreedora')),
                CONSTRAINT CK_Cuenta_Clase CHECK (Clase IN ('Activo', 'Pasivo', 'Capital', 'Ingreso', 'Costo', 'Gasto'))
            );
        END;

        -- 2. Periodos Contables
        IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[PeriodosContables]') AND type in (N'U'))
        BEGIN
            CREATE TABLE PeriodosContables (
                ID INT PRIMARY KEY IDENTITY(1,1),
                Mes INT NOT NULL,
                Anio INT NOT NULL,
                Estado VARCHAR(20) NOT NULL DEFAULT 'Abierto',
                FechaApertura DATETIME NOT NULL DEFAULT GETDATE(),
                FechaCierre DATETIME NULL,
                CerradoPor INT NULL,
                CONSTRAINT UQ_Periodo UNIQUE (Mes, Anio),
                CONSTRAINT CK_Periodo_Estado CHECK (Estado IN ('Abierto', 'Cerrado')),
                CONSTRAINT CK_Periodo_Mes CHECK (Mes BETWEEN 1 AND 12)
            );
        END;

        -- 3. Asientos de Diario (Cabecera)
        IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[AsientosDiario]') AND type in (N'U'))
        BEGIN
            CREATE TABLE AsientosDiario (
                ID INT PRIMARY KEY IDENTITY(1,1),
                PeriodoID INT NOT NULL,
                Fecha DATETIME NOT NULL DEFAULT GETDATE(),
                Descripcion VARCHAR(255) NOT NULL,
                ReferenciaExterna VARCHAR(50) NULL,
                TipoDocumento VARCHAR(50) NOT NULL,
                Estado VARCHAR(20) NOT NULL DEFAULT 'Contabilizado',
                UsuarioID INT NOT NULL,
                FechaCreacion DATETIME NOT NULL DEFAULT GETDATE(),
                CONSTRAINT FK_Asiento_Periodo FOREIGN KEY (PeriodoID) REFERENCES PeriodosContables(ID),
                CONSTRAINT CK_Asiento_Estado CHECK (Estado IN ('Borrador', 'Contabilizado', 'Anulado'))
            );
        END;

        -- 4. Detalle de Asientos (Partidas)
        IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[DetalleAsientos]') AND type in (N'U'))
        BEGIN
            CREATE TABLE DetalleAsientos (
                ID BIGINT PRIMARY KEY IDENTITY(1,1),
                AsientoID INT NOT NULL,
                CuentaID INT NOT NULL,
                Debe DECIMAL(18, 4) NOT NULL DEFAULT 0.0000,
                Haber DECIMAL(18, 4) NOT NULL DEFAULT 0.0000,
                CONSTRAINT FK_Detalle_Asiento FOREIGN KEY (AsientoID) REFERENCES AsientosDiario(ID),
                CONSTRAINT FK_Detalle_Cuenta FOREIGN KEY (CuentaID) REFERENCES CatalogoCuentas(ID),
                CONSTRAINT CK_Detalle_Montos CHECK (Debe >= 0 AND Haber >= 0 AND (Debe > 0 OR Haber > 0))
            );
        END;
        """
        cursor.execute(sql)
        
        # Insertar algunos datos iniciales de prueba para el balance general si las tablas acaban de crearse
        cursor.execute("SELECT COUNT(*) FROM CatalogoCuentas")
        count = cursor.fetchone()[0]
        if count == 0:
            print("Insertando cuentas base...")
            cursor.execute("INSERT INTO CatalogoCuentas (Codigo, Nombre, Clase, Grupo, Naturaleza) VALUES ('1101', 'Caja General', 'Activo', 'Activo Circulante', 'Deudora')")
            cursor.execute("INSERT INTO CatalogoCuentas (Codigo, Nombre, Clase, Grupo, Naturaleza) VALUES ('1102', 'Cuentas por Cobrar', 'Activo', 'Activo Circulante', 'Deudora')")
            cursor.execute("INSERT INTO CatalogoCuentas (Codigo, Nombre, Clase, Grupo, Naturaleza) VALUES ('1103', 'Bancos', 'Activo', 'Activo Circulante', 'Deudora')")
            cursor.execute("INSERT INTO CatalogoCuentas (Codigo, Nombre, Clase, Grupo, Naturaleza) VALUES ('2101', 'Cuentas por Pagar', 'Pasivo', 'Pasivo Circulante', 'Acreedora')")
            cursor.execute("INSERT INTO CatalogoCuentas (Codigo, Nombre, Clase, Grupo, Naturaleza) VALUES ('2102', 'IVA por Pagar', 'Pasivo', 'Pasivo Circulante', 'Acreedora')")
            cursor.execute("INSERT INTO CatalogoCuentas (Codigo, Nombre, Clase, Grupo, Naturaleza) VALUES ('3101', 'Capital Social', 'Capital', 'Capital Contable', 'Acreedora')")
            cursor.execute("INSERT INTO CatalogoCuentas (Codigo, Nombre, Clase, Grupo, Naturaleza) VALUES ('4101', 'Ingresos por Ventas', 'Ingreso', 'Ingresos Operativos', 'Acreedora')")
            cursor.execute("INSERT INTO CatalogoCuentas (Codigo, Nombre, Clase, Grupo, Naturaleza) VALUES ('5101', 'Costo de Ventas', 'Costo', 'Costos Operativos', 'Deudora')")
            
            # Crear un periodo y asiento de prueba
            cursor.execute("INSERT INTO PeriodosContables (Mes, Anio) VALUES (9, 2026)")
            periodo_id = cursor.execute("SELECT SCOPE_IDENTITY()").fetchone()[0]
            
            cursor.execute("INSERT INTO AsientosDiario (PeriodoID, Descripcion, TipoDocumento, UsuarioID) VALUES (?, 'Aporte Inicial', 'Capital', 1)", (periodo_id,))
            asiento_id = cursor.execute("SELECT SCOPE_IDENTITY()").fetchone()[0]
            
            cursor.execute("INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber) VALUES (?, (SELECT ID FROM CatalogoCuentas WHERE Codigo='1101'), 50000, 0)", (asiento_id,))
            cursor.execute("INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber) VALUES (?, (SELECT ID FROM CatalogoCuentas WHERE Codigo='3101'), 0, 50000)", (asiento_id,))
        else:
            # Check for Bancos and IVA accounts in case they don't exist
            cursor.execute("SELECT COUNT(*) FROM CatalogoCuentas WHERE Codigo = '1103'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO CatalogoCuentas (Codigo, Nombre, Clase, Grupo, Naturaleza) VALUES ('1103', 'Bancos', 'Activo', 'Activo Circulante', 'Deudora')")
            
            cursor.execute("SELECT COUNT(*) FROM CatalogoCuentas WHERE Codigo = '2102'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO CatalogoCuentas (Codigo, Nombre, Clase, Grupo, Naturaleza) VALUES ('2102', 'IVA por Pagar', 'Pasivo', 'Pasivo Circulante', 'Acreedora')")

        conn.commit()
        print("Migración a base de datos en la nube completada exitosamente.")
    except Exception as e:
        print(f"Error durante la migración: {e}")

if __name__ == "__main__":
    migrate()
