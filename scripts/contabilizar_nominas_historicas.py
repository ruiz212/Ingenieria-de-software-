"""
Script para contabilizar todas las nóminas históricas (2023-2026) en el Libro Diario
y registrar los comprobantes de pago correspondientes a empleados pagados de forma atómica y rápida.
"""
import sys
import os
import time
import pyodbc
from dotenv import dotenv_values


def main():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    vals = dotenv_values(env_path)
    conn_str = vals.get('DB_CONNECTION_STRING')
    if not conn_str:
        print("ERROR: DB_CONNECTION_STRING no encontrada en .env")
        sys.exit(1)

    print("Conectando a Azure SQL Database...")
    conn = pyodbc.connect(conn_str, timeout=30)
    cur = conn.cursor()

    tsql = """
    SET NOCOUNT ON;

    BEGIN TRANSACTION;

    BEGIN TRY
        -- 1. Abrir periodos cerrados temporalmente
        DECLARE @PeriodosCerrados TABLE (ID INT);
        INSERT INTO @PeriodosCerrados (ID)
        SELECT ID FROM PeriodosContables WHERE Estado = 'Cerrado';

        UPDATE PeriodosContables SET Estado = 'Abierto' WHERE Estado = 'Cerrado';

        -- 2. Variables para comprobantes
        DECLARE @UltimoCN INT;
        SELECT @UltimoCN = ISNULL(CorrelativoActual, 0) FROM TiposComprobante WHERE Codigo = 'NM';
        DECLARE @UltimoCE INT;
        SELECT @UltimoCE = ISNULL(CorrelativoActual, 0) FROM TiposComprobante WHERE Codigo = 'EG';

        -- 3. Cursor sobre nominas pendientes
        DECLARE @NomID INT, @EmpID INT, @Nombre NVARCHAR(200), @Cargo NVARCHAR(100),
                @PFin DATE, @Bruto DECIMAL(18,2), @Devengado DECIMAL(18,2),
                @INSSLab DECIMAL(18,2), @IR DECIMAL(18,2), @INSSPat DECIMAL(18,2),
                @INATEC DECIMAL(18,2), @Vac DECIMAL(18,2), @Aguin DECIMAL(18,2),
                @Indem DECIMAL(18,2), @Neto DECIMAL(18,2), @Vales DECIMAL(18,2),
                @Pension DECIMAL(18,2), @Prestamo DECIMAL(18,2), @Perdida DECIMAL(18,2);

        DECLARE curNom CURSOR LOCAL FAST_FORWARD FOR
        SELECT n.ID, n.EmpleadoID, e.NombreCompleto, ISNULL(e.Cargo, 'Admin'), n.PeriodoFin,
               ROUND(n.SalarioBruto, 2), ROUND(n.TotalDevengado, 2),
               ROUND(ISNULL(n.INSSLaboral, 0), 2), ROUND(ISNULL(n.IRMensual, 0), 2),
               ROUND(ISNULL(n.INSSPatronal, 0), 2), ROUND(ISNULL(n.INATEC, 0), 2),
               ROUND(ISNULL(n.ProvisionVacaciones, 0), 2), ROUND(ISNULL(n.ProvisionAguinaldo, 0), 2),
               ROUND(ISNULL(n.ProvisionIndemnizacion, 0), 2), ROUND(ISNULL(n.SalarioNeto, 0), 2),
               ROUND(ISNULL(n.ValesDescontados, 0), 2), ROUND(ISNULL(n.PensionAlimenticia, 0), 2),
               ROUND(ISNULL(n.PrestamosDescontados, 0), 2), ROUND(ISNULL(n.CobrosPerdidas, 0), 2)
        FROM Nomina n
        JOIN Empleados e ON e.ID = n.EmpleadoID
        WHERE n.Estado = 'Pagada'
          AND NOT EXISTS (
              SELECT 1 FROM AsientosDiario a WHERE a.ReferenciaExterna = 'NOM-' + CAST(n.ID AS VARCHAR)
          )
        ORDER BY n.PeriodoFin ASC, n.ID ASC;

        OPEN curNom;
        FETCH NEXT FROM curNom INTO @NomID, @EmpID, @Nombre, @Cargo, @PFin,
                                    @Bruto, @Devengado, @INSSLab, @IR, @INSSPat,
                                    @INATEC, @Vac, @Aguin, @Indem, @Neto,
                                    @Vales, @Pension, @Prestamo, @Perdida;

        DECLARE @TotalProcesados INT = 0;
        DECLARE @CtaSueldoID INT, @CtaINSSPatID INT, @CtaINATECID INT, @CtaProvID INT;
        DECLARE @PeriodoID INT, @AsientoID INT, @AsientoPagoID INT;
        DECLARE @NumCompNM VARCHAR(20), @NumCompEG VARCHAR(20);
        DECLARE @CargoLower NVARCHAR(100);

        WHILE @@FETCH_STATUS = 0
        BEGIN
            -- Periodo
            SELECT @PeriodoID = ID FROM PeriodosContables WHERE Mes = MONTH(@PFin) AND Anio = YEAR(@PFin);

            -- Determinar Cuentas de Gasto/Costo segun cargo
            SET @CargoLower = LOWER(@Cargo);
            IF @CargoLower LIKE '%panadero%' OR @CargoLower LIKE '%produccion%' OR @CargoLower LIKE '%hornero%'
            BEGIN
                SET @CtaSueldoID = 93;   -- MOD Panaderos
                SET @CtaINSSPatID = 94;  -- CIF
                SET @CtaINATECID = 94;   -- CIF
                SET @CtaProvID = 94;     -- CIF
            END
            ELSE IF @CargoLower LIKE '%vendedor%' OR @CargoLower LIKE '%dependient%' OR @CargoLower LIKE '%cajer%'
            BEGIN
                SET @CtaSueldoID = 117;  -- Sueldos Ventas
                SET @CtaINSSPatID = 118; -- INSS Pat Ventas
                SET @CtaINATECID = 119;  -- INATEC Ventas
                SET @CtaProvID = 104;    -- Provisiones Admin
            END
            ELSE
            BEGIN
                SET @CtaSueldoID = 100;  -- Sueldos Admin
                SET @CtaINSSPatID = 101; -- INSS Pat Admin
                SET @CtaINATECID = 102;  -- INATEC Admin
                SET @CtaProvID = 104;    -- Provisiones Admin
            END

            -- 1. Crear Asiento Devengo
            SET @UltimoCN = @UltimoCN + 1;
            SET @NumCompNM = 'CN-' + RIGHT('000000' + CAST(@UltimoCN AS VARCHAR), 6);

            INSERT INTO AsientosDiario (PeriodoID, Fecha, Descripcion, ReferenciaExterna, TipoDocumento, Estado, UsuarioID, FechaCreacion, TipoComprobanteID, NumeroComprobante)
            VALUES (@PeriodoID, @PFin, 'Nómina ' + @Nombre + ' — NOM-' + CAST(@NomID AS VARCHAR), 'NOM-' + CAST(@NomID AS VARCHAR), 'Nomina', 'Contabilizado', 1, GETDATE(), 7, @NumCompNM);
            SET @AsientoID = SCOPE_IDENTITY();

            -- Lineas de Debito
            INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
            VALUES (@AsientoID, @CtaSueldoID, @Devengado, 0, 'Sueldo ' + @Nombre);

            IF @INSSPat > 0
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, @CtaINSSPatID, @INSSPat, 0, 'INSS Patronal ' + @Nombre);

            IF @INATEC > 0
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, @CtaINATECID, @INATEC, 0, 'INATEC ' + @Nombre);

            IF @Vac > 0
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, @CtaProvID, @Vac, 0, 'Provisión Vacaciones ' + @Nombre);

            IF @Aguin > 0
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, 103, @Aguin, 0, 'Provisión Aguinaldo ' + @Nombre);

            IF @Indem > 0
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, 105, @Indem, 0, 'Provisión Indemnización ' + @Nombre);

            -- Lineas de Credito
            DECLARE @CreditoSueldoNeto DECIMAL(18,2) = @Neto;
            -- Reconciliar centavo de redondeo entre Debe y Haber
            DECLARE @TotalD DECIMAL(18,2) = @Devengado + @INSSPat + @INATEC + @Vac + @Aguin + @Indem;
            DECLARE @TotalH DECIMAL(18,2) = @Neto + @INSSLab + @IR + @INSSPat + @INATEC + @Vac + @Aguin + @Indem + @Vales + @Pension + @Prestamo + @Perdida;
            DECLARE @Diff DECIMAL(18,2) = @TotalD - @TotalH;
            IF ABS(@Diff) <= 0.05 AND @Diff <> 0
            BEGIN
                SET @CreditoSueldoNeto = @CreditoSueldoNeto + @Diff;
            END

            IF @CreditoSueldoNeto > 0
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, 49, 0, @CreditoSueldoNeto, 'Neto a pagar ' + @Nombre);

            IF @INSSLab > 0
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, 50, 0, @INSSLab, 'INSS Lab. ' + @Nombre);

            IF @IR > 0
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, 53, 0, @IR, 'IR Ret. ' + @Nombre);

            IF @INSSPat > 0
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, 51, 0, @INSSPat, 'INSS Pat. x pagar ' + @Nombre);

            IF @INATEC > 0
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, 52, 0, @INATEC, 'INATEC x pagar ' + @Nombre);

            IF @Vac > 0
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, 54, 0, @Vac, 'Provisión Vacaciones ' + @Nombre);

            IF @Aguin > 0
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, 55, 0, @Aguin, 'Provisión Aguinaldo ' + @Nombre);

            IF @Indem > 0
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, 56, 0, @Indem, 'Provisión Indemnización ' + @Nombre);

            IF @Vales > 0
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, 17, 0, @Vales, 'Descuento vales ' + @Nombre);

            IF @Pension > 0
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, 57, 0, @Pension, 'Pensión alim. ' + @Nombre);

            -- 2. Crear Asiento de Desembolso / Pago (EG)
            IF @Neto > 0
            BEGIN
                SET @UltimoCE = @UltimoCE + 1;
                SET @NumCompEG = 'CE-' + RIGHT('000000' + CAST(@UltimoCE AS VARCHAR), 6);

                INSERT INTO AsientosDiario (PeriodoID, Fecha, Descripcion, ReferenciaExterna, TipoDocumento, Estado, UsuarioID, FechaCreacion, TipoComprobanteID, NumeroComprobante)
                VALUES (@PeriodoID, @PFin, 'Pago de nómina #' + CAST(@NomID AS VARCHAR) + ' - ' + @Nombre + ' (Transferencia)', 'PAG-NOM-' + CAST(@NomID AS VARCHAR), 'PagoNomina', 'Contabilizado', 1, GETDATE(), 3, @NumCompEG);
                SET @AsientoPagoID = SCOPE_IDENTITY();

                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoPagoID, 49, @Neto, 0, 'Cancelación sueldos por pagar ' + @Nombre);

                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoPagoID, 3, 0, @Neto, 'Desembolso nómina #' + CAST(@NomID AS VARCHAR) + ' (Transferencia)');
            END

            SET @TotalProcesados = @TotalProcesados + 1;

            FETCH NEXT FROM curNom INTO @NomID, @EmpID, @Nombre, @Cargo, @PFin,
                                        @Bruto, @Devengado, @INSSLab, @IR, @INSSPat,
                                        @INATEC, @Vac, @Aguin, @Indem, @Neto,
                                        @Vales, @Pension, @Prestamo, @Perdida;
        END

        CLOSE curNom;
        DEALLOCATE curNom;

        -- Actualizar contadores de comprobantes
        UPDATE TiposComprobante SET CorrelativoActual = @UltimoCN WHERE Codigo = 'NM';
        UPDATE TiposComprobante SET CorrelativoActual = @UltimoCE WHERE Codigo = 'EG';

        -- Restaurar periodos cerrados
        UPDATE p
        SET p.Estado = 'Cerrado'
        FROM PeriodosContables p
        JOIN @PeriodosCerrados c ON p.ID = c.ID;

        COMMIT TRANSACTION;
        SELECT @TotalProcesados AS Procesados, @UltimoCN AS UltimoCN, @UltimoCE AS UltimoCE;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        IF CURSOR_STATUS('local', 'curNom') >= 0
        BEGIN
            CLOSE curNom;
            DEALLOCATE curNom;
        END;
        THROW;
    END CATCH;
    """

    print("Ejecutando migración contable de nóminas...")
    t0 = time.time()
    cur.execute(tsql)
    res = cur.fetchone()
    conn.commit()
    print(f"¡Migración completada en {time.time() - t0:.2f}s!")
    print(f"Nóminas procesadas: {res[0]}, Último CN: {res[1]}, Último CE: {res[2]}")
    conn.close()


if __name__ == '__main__':
    main()
