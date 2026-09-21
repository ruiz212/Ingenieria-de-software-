"""
Migración: Módulo de Arqueos de Caja v2
Agrega tablas y columnas para el flujo multi-etapa de arqueo.
"""
import pyodbc
from config import Config


def run_migration():
    """Ejecuta la migración para Arqueos de Caja v2."""
    conn = pyodbc.connect(Config.SQL_SERVER_CONNECTION_STRING, autocommit=True)
    cursor = conn.cursor()

    migrations = [
        # 1. Tabla de Detalle por Denominación
        """
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ArqueoDetalleDenominacion')
        CREATE TABLE ArqueoDetalleDenominacion (
            ID INT PRIMARY KEY IDENTITY(1,1),
            ArqueoID INT NOT NULL,
            TipoMoneda VARCHAR(10) NOT NULL,
            Denominacion DECIMAL(10,2) NOT NULL,
            Cantidad INT NOT NULL DEFAULT 0,
            Subtotal AS (Denominacion * Cantidad) PERSISTED,
            CONSTRAINT FK_ArqueoDenom_Arqueo FOREIGN KEY (ArqueoID) REFERENCES ArqueoCaja(ID)
        )
        """,

        # 2. Agregar columna VerificadoPorID si no existe
        """
        IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('ArqueoCaja') AND name = 'VerificadoPorID')
        ALTER TABLE ArqueoCaja ADD VerificadoPorID INT NULL
        """,

        # 3. FK para VerificadoPorID
        """
        IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_ArqueoCaja_Verificador')
        ALTER TABLE ArqueoCaja ADD CONSTRAINT FK_ArqueoCaja_Verificador
            FOREIGN KEY (VerificadoPorID) REFERENCES Usuarios(ID)
        """,

        # 4. Agregar FechaVerificacion
        """
        IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('ArqueoCaja') AND name = 'FechaVerificacion')
        ALTER TABLE ArqueoCaja ADD FechaVerificacion DATETIME NULL
        """,

        # 5. Agregar EstadoArqueo
        """
        IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('ArqueoCaja') AND name = 'EstadoArqueo')
        ALTER TABLE ArqueoCaja ADD EstadoArqueo VARCHAR(20) NOT NULL DEFAULT 'Pendiente'
        """,

        # 6. Check constraint para EstadoArqueo
        """
        IF NOT EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CK_ArqueoCaja_Estado')
        ALTER TABLE ArqueoCaja ADD CONSTRAINT CK_ArqueoCaja_Estado
            CHECK (EstadoArqueo IN ('Pendiente', 'Verificado', 'Cerrado'))
        """,

        # 7. Agregar NotasDiscrepancia
        """
        IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('ArqueoCaja') AND name = 'NotasDiscrepancia')
        ALTER TABLE ArqueoCaja ADD NotasDiscrepancia VARCHAR(1000) NULL
        """,

        # 8. Agregar RequiereJustificacion
        """
        IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('ArqueoCaja') AND name = 'RequiereJustificacion')
        ALTER TABLE ArqueoCaja ADD RequiereJustificacion BIT NOT NULL DEFAULT 0
        """,

        # 9. Tabla de Audit Log para Arqueos
        """
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ArqueoAuditLog')
        CREATE TABLE ArqueoAuditLog (
            ID INT PRIMARY KEY IDENTITY(1,1),
            ArqueoID INT NOT NULL,
            UsuarioID INT NOT NULL,
            Accion VARCHAR(50) NOT NULL,
            Detalle VARCHAR(500) NULL,
            FechaAccion DATETIME NOT NULL DEFAULT GETDATE(),
            DireccionIP VARCHAR(45) NULL,
            CONSTRAINT FK_ArqueoLog_Arqueo FOREIGN KEY (ArqueoID) REFERENCES ArqueoCaja(ID),
            CONSTRAINT FK_ArqueoLog_Usuario FOREIGN KEY (UsuarioID) REFERENCES Usuarios(ID)
        )
        """,

        # 10. Agregar configuración de umbral de discrepancia
        """
        IF NOT EXISTS (SELECT * FROM ConfiguracionSistema WHERE Clave = 'umbral_discrepancia_cordobas')
        INSERT INTO ConfiguracionSistema (Clave, Valor, Descripcion)
        VALUES ('umbral_discrepancia_cordobas', '50.00', 'Monto en córdobas a partir del cual una discrepancia en arqueo requiere justificación obligatoria')
        """,
    ]

    for i, sql in enumerate(migrations):
        try:
            cursor.execute(sql.strip())
            print(f"  [OK] Migracion {i + 1}/{len(migrations)} ejecutada correctamente")
        except Exception as e:
            print(f"  [ERROR] Migracion {i + 1}/{len(migrations)} fallo: {e}")

    conn.close()
    print("\n[OK] Migracion de Arqueos v2 completada.")


if __name__ == '__main__':
    run_migration()
