import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pyodbc
from config import Config

def run_migration():
    print("Conectando a SQL Server para migración de escala_salarial...")
    conn_str = Config.SQL_SERVER_CONNECTION_STRING
    conn = pyodbc.connect(conn_str, autocommit=True)
    cursor = conn.cursor()

    try:
        # 1. Crear tabla rrhh.escala_salarial si no existe
        cursor.execute("""
        IF OBJECT_ID('rrhh.escala_salarial', 'U') IS NULL
        BEGIN
            CREATE TABLE [rrhh].[escala_salarial] (
                [id] INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                [nivel] VARCHAR(10) NOT NULL,
                [cargo] VARCHAR(100) NOT NULL,
                [limite_inferior] INT NULL,
                [limite_superior] INT NOT NULL,
                [salario_base] DECIMAL(12,2) NOT NULL
            );
            PRINT 'Tabla rrhh.escala_salarial creada exitosamente.';
        END
        ELSE
        BEGIN
            PRINT 'Tabla rrhh.escala_salarial ya existe.';
        END
        """)

        # 2. Crear sinónimo en dbo si no existe
        cursor.execute("""
        IF OBJECT_ID('dbo.escala_salarial') IS NULL
        BEGIN
            CREATE SYNONYM [dbo].[escala_salarial] FOR [rrhh].[escala_salarial];
            PRINT 'Sinónimo dbo.escala_salarial creado.';
        END
        """)

        # 3. Permisos para roles de seguridad
        cursor.execute("""
        IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'db_rol_gerencia')
            GRANT SELECT ON [rrhh].[escala_salarial] TO [db_rol_gerencia];
        IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'db_rol_superadmin')
            GRANT SELECT ON [rrhh].[escala_salarial] TO [db_rol_superadmin];
        """)

        # 4. Insertar datos de la tabla salarial de Excel
        datos_escala = [
            ('I', 'Limpieza', None, 100, 6519.58),
            ('II', 'Panadero Aprendiz', 101, 126, 8572.96),
            ('III', 'Cajero/Depedienta', 127, 159, 10626.34),
            ('III', 'Cajero', 127, 159, 10626.34),
            ('IV', 'Cocinero', 160, 200, 12679.72),
            ('IV', 'Cocina', 160, 200, 12679.72),
            ('V', 'Panadero Junior', 201, 252, 14733.10),
            ('VI', 'Jefe de Inventario', 253, 317, 16786.48),
            ('VII', 'Panadero Senior', 318, 400, 18839.86),
            ('VIII', 'Contador', 401, 504, 20893.24),
            ('IX', 'Maestro Panadero', 505, 635, 22946.62),
            ('X', 'Gerente General', 636, 800, 25000.00),
            ('X', 'Gerente', 636, 800, 25000.00),
            ('VIII', 'Ingeniero electronico', 401, 504, 20893.24),
            ('II', 'Panadero', 101, 126, 8572.96)
        ]

        for nivel, cargo, li, ls, sal in datos_escala:
            cursor.execute("""
            IF NOT EXISTS (SELECT 1 FROM [rrhh].[escala_salarial] WHERE LOWER(cargo) = LOWER(?))
            BEGIN
                INSERT INTO [rrhh].[escala_salarial] (nivel, cargo, limite_inferior, limite_superior, salario_base)
                VALUES (?, ?, ?, ?, ?);
            END
            ELSE
            BEGIN
                UPDATE [rrhh].[escala_salarial]
                SET nivel = ?, limite_inferior = ?, limite_superior = ?, salario_base = ?
                WHERE LOWER(cargo) = LOWER(?);
            END
            """, cargo, nivel, cargo, li, ls, sal, nivel, li, ls, sal, cargo)

        print("Datos de escala_salarial insertados/actualizados.")

        # 5. Stored Procedures para consulta
        cursor.execute("""
        CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerEscalaSalarialPorCargo]
            @Cargo NVARCHAR(100)
        AS
        BEGIN
            SET NOCOUNT ON;
            DECLARE @CargoClean NVARCHAR(100) = LTRIM(RTRIM(@Cargo));

            -- 1. Coincidencia exacta
            IF EXISTS (SELECT 1 FROM [rrhh].[escala_salarial] WHERE LOWER(cargo) = LOWER(@CargoClean))
            BEGIN
                SELECT id, nivel, cargo, limite_inferior, limite_superior, salario_base
                FROM [rrhh].[escala_salarial]
                WHERE LOWER(cargo) = LOWER(@CargoClean);
                RETURN;
            END

            -- 2. Mapeos o prefijo
            IF LOWER(@CargoClean) = 'cajero' OR LOWER(@CargoClean) LIKE 'cajero%'
            BEGIN
                SELECT TOP 1 id, nivel, cargo, limite_inferior, limite_superior, salario_base
                FROM [rrhh].[escala_salarial]
                WHERE LOWER(cargo) IN ('cajero', 'cajero/depedienta');
                RETURN;
            END

            IF LOWER(@CargoClean) = 'cocina' OR LOWER(@CargoClean) LIKE 'coci%'
            BEGIN
                SELECT TOP 1 id, nivel, cargo, limite_inferior, limite_superior, salario_base
                FROM [rrhh].[escala_salarial]
                WHERE LOWER(cargo) IN ('cocina', 'cocinero');
                RETURN;
            END

            IF LOWER(@CargoClean) = 'gerente' OR LOWER(@CargoClean) LIKE 'gerente%'
            BEGIN
                SELECT TOP 1 id, nivel, cargo, limite_inferior, limite_superior, salario_base
                FROM [rrhh].[escala_salarial]
                WHERE LOWER(cargo) IN ('gerente', 'gerente general');
                RETURN;
            END

            -- 3. LIKE genérico
            SELECT TOP 1 id, nivel, cargo, limite_inferior, limite_superior, salario_base
            FROM [rrhh].[escala_salarial]
            WHERE LOWER(cargo) LIKE '%' + LOWER(@CargoClean) + '%'
               OR LOWER(@CargoClean) LIKE '%' + LOWER(cargo) + '%'
            ORDER BY id ASC;
        END
        """)

        cursor.execute("""
        CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarEscalaSalarial]
        AS
        BEGIN
            SET NOCOUNT ON;
            SELECT id, nivel, cargo, limite_inferior, limite_superior, salario_base
            FROM [rrhh].[escala_salarial]
            ORDER BY id ASC;
        END
        """)

        # Permisos sobre SPs
        cursor.execute("""
        IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'db_rol_gerencia')
        BEGIN
            GRANT EXECUTE ON OBJECT::[rrhh].[sp_ObtenerEscalaSalarialPorCargo] TO [db_rol_gerencia];
            GRANT EXECUTE ON OBJECT::[rrhh].[sp_ListarEscalaSalarial] TO [db_rol_gerencia];
        END
        IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'db_rol_superadmin')
        BEGIN
            GRANT EXECUTE ON OBJECT::[rrhh].[sp_ObtenerEscalaSalarialPorCargo] TO [db_rol_superadmin];
            GRANT EXECUTE ON OBJECT::[rrhh].[sp_ListarEscalaSalarial] TO [db_rol_superadmin];
        END
        """)

        # 6. Asegurar que las subcategorías de panadero existan en rrhh.PerfilesPuesto
        subcategorias_panadero = [
            ('Panadero Aprendiz', 'Colaborador en etapa de aprendizaje y apoyo en procesos de amasado y horneado.'),
            ('Panadero Junior', 'Elaboración básica de panes y masas con supervisión regular.'),
            ('Panadero Senior', 'Elaboración experta de repostería y panadería compleja, control de tiempos de fermentación.'),
            ('Maestro Panadero', 'Jefe de producción de panadería, desarrollo de recetas maestras y estándares de calidad.')
        ]

        for sub_cargo, desc in subcategorias_panadero:
            cursor.execute("""
            IF NOT EXISTS (SELECT 1 FROM [rrhh].[PerfilesPuesto] WHERE Cargo = ?)
            BEGIN
                INSERT INTO [rrhh].[PerfilesPuesto] (Cargo, PerfilPuesto, Obligaciones, RequisitosCompetencias)
                VALUES (?, ?, 'Cumplimiento de estándares de calidad e inocuidad en panadería.', 'Competencias técnicas de panadería y repostería.');
            END
            """, sub_cargo, sub_cargo, desc)

        # 7. Actualizar rrhh.sp_ObtenerPerfilPuestoPorCargo para que valide contra PerfilesPuesto o escala_salarial
        cursor.execute("""
        CREATE OR ALTER PROCEDURE [rrhh].[sp_ObtenerPerfilPuestoPorCargo]
            @Cargo NVARCHAR(100)
        AS
        BEGIN
            SET NOCOUNT ON;
            IF EXISTS (SELECT 1 FROM [rrhh].[PerfilesPuesto] WHERE Cargo = @Cargo)
                SELECT Cargo FROM [rrhh].[PerfilesPuesto] WHERE Cargo = @Cargo;
            ELSE IF EXISTS (SELECT 1 FROM [rrhh].[escala_salarial] WHERE cargo = @Cargo)
                SELECT cargo AS Cargo FROM [rrhh].[escala_salarial] WHERE cargo = @Cargo;
            ELSE
                SELECT TOP 1 cargo AS Cargo FROM [rrhh].[escala_salarial] WHERE LOWER(cargo) LIKE '%' + LOWER(@Cargo) + '%';
        END
        """)

        print("Migración de escala salarial finalizada con éxito.")
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
