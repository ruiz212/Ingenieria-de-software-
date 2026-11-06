"""
Script de migración integral para generar la trazabilidad completa de Producción,
Compras de Materia Prima y Asientos Contables de Costo para los 3 años históricos (2023-2026).
"""
import sys
import os
import time
from datetime import datetime, date
from decimal import Decimal
import pyodbc
from dotenv import dotenv_values

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    vals = dotenv_values(env_path)
    conn_str = vals.get('DB_CONNECTION_STRING')
    if not conn_str:
        print("ERROR: DB_CONNECTION_STRING no encontrada en .env")
        sys.exit(1)

    print("Conectando a Azure SQL Database...")
    conn = pyodbc.connect(conn_str, timeout=45)
    cur = conn.cursor()

    tsql = """
    SET NOCOUNT ON;

    BEGIN TRANSACTION;

    BEGIN TRY
        -- 1. Abrir temporalmente periodos contables cerrados
        DECLARE @PeriodosCerrados TABLE (ID INT);
        INSERT INTO @PeriodosCerrados (ID)
        SELECT ID FROM PeriodosContables WHERE Estado = 'Cerrado';

        UPDATE PeriodosContables SET Estado = 'Abierto' WHERE Estado = 'Cerrado';

        -- 2. INSERTAR LOTES DE PRODUCCION HISTORICOS (DIARIOS POR PRODUCTO VENDIDO)
        -- Cada lote se produjo a las 05:00 AM del dia de la venta con un 5% de margen normal de produccion
        INSERT INTO produccion.ProduccionLotes (ProductoID, CantidadProducida, Fecha, CantidadEsperada)
        SELECT 
            df.ProductoID,
            CAST(CEILING(SUM(df.Cantidad) * 1.05) AS INT) AS CantidadProducida,
            DATEADD(hour, 5, CAST(CAST(f.FechaHora AS DATE) AS DATETIME)) AS Fecha,
            CAST(CEILING(SUM(df.Cantidad) * 1.05) AS INT) AS CantidadEsperada
        FROM ventas.Facturas f
        JOIN ventas.DetalleFacturas df ON df.FacturaID = f.ID
        WHERE EXISTS (SELECT 1 FROM produccion.RecetaProducto rp WHERE rp.ProductoID = df.ProductoID)
          AND f.FechaHora < '2026-10-31 23:59:59'
          AND NOT EXISTS (
              SELECT 1 FROM produccion.ProduccionLotes l2 
              WHERE l2.ProductoID = df.ProductoID 
                AND CAST(l2.Fecha AS DATE) = CAST(f.FechaHora AS DATE)
          )
        GROUP BY CAST(f.FechaHora AS DATE), df.ProductoID;

        DECLARE @TotalLotesCreados INT = @@ROWCOUNT;

        -- 3. INSERTAR CONSUMO DE MATERIA PRIMA POR LOTE (TRAZABILIDAD RECETA -> MATERIA PRIMA)
        INSERT INTO produccion.ConsumoLote (LoteID, MateriaPrimaID, CantidadUsada)
        SELECT 
            l.ID AS LoteID,
            rp.MateriaPrimaID,
            ROUND(l.CantidadProducida * rp.CantidadNecesaria, 2) AS CantidadUsada
        FROM produccion.ProduccionLotes l
        JOIN produccion.RecetaProducto rp ON rp.ProductoID = l.ProductoID
        WHERE NOT EXISTS (
            SELECT 1 FROM produccion.ConsumoLote cl WHERE cl.LoteID = l.ID AND cl.MateriaPrimaID = rp.MateriaPrimaID
        );

        DECLARE @TotalConsumosCreados INT = @@ROWCOUNT;

        -- 4. INSERTAR COMPRAS SEMANALES DE MATERIA PRIMA
        -- Agrupamos el consumo semanal por materia prima + 10% de margen operativo de seguridad
        -- Mapeamos proveedores certificados segun tipo de ingrediente:
        -- Harinas y Azucar: Agricorp (2)
        -- Premezclas: PriceSmart (1)
        -- Lacteos y Grasas: Eskimo (3) o Levapan (5) o Cargill (6)
        -- Quimicos, levaduras, esencias: Dicegsa (4) o Levapan (5)
        -- Cafe: Cafe Las Flores (13)
        -- Empaques: Mercado Oriental (8)

        DECLARE @ComprasPrevias INT;
        SELECT @ComprasPrevias = COUNT(*) FROM produccion.ComprasMateriaPrima;

        -- Tabla temporal de costos unitarios referenciales
        DECLARE @CostosReferenciales TABLE (MateriaPrimaID INT PRIMARY KEY, CostoUnitario DECIMAL(18,4), ProveedorID INT);
        INSERT INTO @CostosReferenciales (MateriaPrimaID, CostoUnitario, ProveedorID)
        VALUES 
            (1, 0.1228, 2),  (2, 0.0740, 2),  (3, 0.1318, 1),  (4, 0.0946, 1),
            (5, 0.1048, 5),  (6, 0.0456, 3),  (7, 0.1177, 3),  (8, 0.1069, 3),
            (9, 0.0771, 3),  (10, 0.1068, 3), (11, 0.0616, 3), (12, 0.0773, 3),
            (13, 0.1264, 6), (14, 0.0402, 5), (15, 0.1459, 5), (16, 0.1098, 6),
            (17, 0.1184, 2), (18, 0.1293, 2), (19, 0.0884, 2), (20, 0.0969, 4),
            (21, 0.1454, 4), (22, 0.0653, 4), (23, 0.0867, 5), (24, 0.0675, 5),
            (25, 0.0795, 5), (26, 0.0619, 4), (27, 0.0853, 4), (28, 0.0702, 5),
            (29, 0.1449, 4), (30, 0.0766, 4), (31, 0.0409, 5), (32, 0.0740, 5),
            (33, 0.0688, 3), (34, 0.0746, 5), (35, 0.1452, 5), (36, 0.0793, 6),
            (37, 0.1152, 5), (38, 0.0500, 8), (39, 0.2000, 8), (40, 0.2500, 8),
            (41, 0.3000, 8), (42, 0.1500, 8), (43, 0.1200, 8), (44, 0.0900, 2),
            (45, 0.0600, 12),(46, 0.0800, 12),(47, 0.0700, 12),(48, 0.0500, 12),
            (49, 0.1000, 13),(50, 0.1200, 13),(51, 0.0800, 13),(52, 0.0600, 12),
            (53, 0.0700, 12);

        -- Insertar compras semanales basadas en el consumo de la semana
        INSERT INTO produccion.ComprasMateriaPrima (
            MateriaPrimaID, ProveedorID, Cantidad, CostoTotal, Fecha, FacturaProveedor, IVADocumentado
        )
        SELECT 
            cl.MateriaPrimaID,
            ISNULL(cr.ProveedorID, 2) AS ProveedorID,
            ROUND(SUM(cl.CantidadUsada) * 1.15, 2) AS Cantidad,
            ROUND(SUM(cl.CantidadUsada) * 1.15 * ISNULL(cr.CostoUnitario, 0.08), 2) AS CostoTotal,
            DATEADD(hour, 7, CAST(MIN(CAST(l.Fecha AS DATE)) AS DATETIME)) AS Fecha,
            'FAC-' + CAST(ISNULL(cr.ProveedorID, 2) AS VARCHAR) + '-' + CONVERT(VARCHAR(8), MIN(CAST(l.Fecha AS DATE)), 112) AS FacturaProveedor,
            0.00 AS IVADocumentado
        FROM produccion.ConsumoLote cl
        JOIN produccion.ProduccionLotes l ON l.ID = cl.LoteID
        LEFT JOIN @CostosReferenciales cr ON cr.MateriaPrimaID = cl.MateriaPrimaID
        WHERE NOT EXISTS (
            SELECT 1 FROM produccion.ComprasMateriaPrima cmp
            WHERE cmp.MateriaPrimaID = cl.MateriaPrimaID
              AND CAST(cmp.Fecha AS DATE) = CAST(l.Fecha AS DATE)
        )
        GROUP BY 
            DATEPART(year, l.Fecha),
            DATEPART(week, l.Fecha),
            cl.MateriaPrimaID,
            cr.ProveedorID,
            cr.CostoUnitario;

        DECLARE @TotalComprasCreadas INT = (SELECT COUNT(*) FROM produccion.ComprasMateriaPrima) - @ComprasPrevias;

        -- 5. RECALCULAR STOCK ACTUAL DE MATERIA PRIMA
        -- StockActual = Total Comprado - Total Consumido
        UPDATE mp
        SET mp.StockActual = CASE 
            WHEN (ISNULL(c.TotalComprado, 0) - ISNULL(u.TotalConsumido, 0)) >= 0 
                THEN (ISNULL(c.TotalComprado, 0) - ISNULL(u.TotalConsumido, 0)) + ISNULL(mp.StockMinimo, 1000) * 1.5
            ELSE ISNULL(mp.StockMinimo, 1000) * 2.0
        END
        FROM produccion.MateriaPrima mp
        LEFT JOIN (
            SELECT MateriaPrimaID, SUM(Cantidad) AS TotalComprado
            FROM produccion.ComprasMateriaPrima
            GROUP BY MateriaPrimaID
        ) c ON c.MateriaPrimaID = mp.ID
        LEFT JOIN (
            SELECT MateriaPrimaID, SUM(CantidadUsada) AS TotalConsumido
            FROM produccion.ConsumoLote
            GROUP BY MateriaPrimaID
        ) u ON u.MateriaPrimaID = mp.ID;

        -- 6. GENERAR ASIENTOS CONTABLES DE COMPRA Y CONSUMO DE MATERIA PRIMA (36 MESES)
        -- Para cada mes entre 2023-11 y 2026-10:
        -- A) Asiento FC (Compra MP): Debe 1.1.03.001 (Inventario MP), Haber 1.1.01.004 (Bancos MN)
        -- B) Asiento DI (Consumo MP): Debe 5.1.01.001 (Costo MP Consumida), Haber 1.1.03.001 (Inventario MP)

        DECLARE @UltimoFC INT;
        SELECT @UltimoFC = ISNULL(CorrelativoActual, 0) FROM TiposComprobante WHERE Codigo = 'FC';
        DECLARE @UltimoDI INT;
        SELECT @UltimoDI = ISNULL(CorrelativoActual, 0) FROM TiposComprobante WHERE Codigo = 'DI';

        DECLARE @Anio INT, @Mes INT, @PeriodoID INT, @AsientoID INT;
        DECLARE @TotalCompradoMes DECIMAL(18,2), @TotalConsumidoMes DECIMAL(18,2);
        DECLARE @FechaFinMes DATE, @NumCompFC VARCHAR(20), @NumCompDI VARCHAR(20);
        DECLARE @RefCompra VARCHAR(50), @RefConsumo VARCHAR(50);
        DECLARE @AsientosComprasCreados INT = 0, @AsientosConsumosCreados INT = 0;

        DECLARE curMeses CURSOR LOCAL FAST_FORWARD FOR
        SELECT p.ID, p.Anio, p.Mes, EOMONTH(DATEFROMPARTS(p.Anio, p.Mes, 1)) AS FechaFin
        FROM PeriodosContables p
        WHERE (p.Anio < 2026 OR (p.Anio = 2026 AND p.Mes <= 10))
        ORDER BY p.Anio, p.Mes;

        OPEN curMeses;
        FETCH NEXT FROM curMeses INTO @PeriodoID, @Anio, @Mes, @FechaFinMes;

        WHILE @@FETCH_STATUS = 0
        BEGIN
            -- Total Compras del mes
            SELECT @TotalCompradoMes = ISNULL(SUM(CostoTotal), 0)
            FROM produccion.ComprasMateriaPrima
            WHERE YEAR(Fecha) = @Anio AND MONTH(Fecha) = @Mes;

            -- Total Consumos del mes
            SELECT @TotalConsumidoMes = ISNULL(SUM(cl.CantidadUsada * ISNULL(cr.CostoUnitario, 0.08)), 0)
            FROM produccion.ConsumoLote cl
            JOIN produccion.ProduccionLotes l ON l.ID = cl.LoteID
            LEFT JOIN @CostosReferenciales cr ON cr.MateriaPrimaID = cl.MateriaPrimaID
            WHERE YEAR(l.Fecha) = @Anio AND MONTH(l.Fecha) = @Mes;

            -- A) Asiento de Compra (FC)
            SET @RefCompra = 'COMPRA-MP-' + CAST(@Anio AS VARCHAR) + '-' + RIGHT('00' + CAST(@Mes AS VARCHAR), 2);
            IF @TotalCompradoMes > 0 AND NOT EXISTS (SELECT 1 FROM AsientosDiario WHERE ReferenciaExterna = @RefCompra)
            BEGIN
                SET @UltimoFC = @UltimoFC + 1;
                SET @NumCompFC = 'FC-' + RIGHT('000000' + CAST(@UltimoFC AS VARCHAR), 6);

                INSERT INTO AsientosDiario (
                    PeriodoID, Fecha, Descripcion, ReferenciaExterna, TipoDocumento,
                    Estado, UsuarioID, FechaCreacion, TipoComprobanteID, NumeroComprobante
                )
                VALUES (
                    @PeriodoID, @FechaFinMes,
                    'Compras de Materia Prima — ' + DATENAME(month, @FechaFinMes) + ' ' + CAST(@Anio AS VARCHAR),
                    @RefCompra, 'FacturaCompra', 'Contabilizado', 1, GETDATE(), 9, @NumCompFC
                );
                SET @AsientoID = SCOPE_IDENTITY();

                -- Debe: 1.1.03.001 (Inventario Materia Prima)
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, 21, @TotalCompradoMes, 0, 'Adquisición de materias primas e insumos');

                -- Haber: 1.1.01.004 (Bancos Moneda Nacional)
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, 3, 0, @TotalCompradoMes, 'Desembolso bancario compras materias primas');

                SET @AsientosComprasCreados = @AsientosComprasCreados + 1;
            END

            -- B) Asiento de Consumo / Costo de Materia Prima (DI)
            SET @RefConsumo = 'CONSUMO-MP-' + CAST(@Anio AS VARCHAR) + '-' + RIGHT('00' + CAST(@Mes AS VARCHAR), 2);
            IF @TotalConsumidoMes > 0 AND NOT EXISTS (SELECT 1 FROM AsientosDiario WHERE ReferenciaExterna = @RefConsumo)
            BEGIN
                SET @UltimoDI = @UltimoDI + 1;
                SET @NumCompDI = 'CD-' + RIGHT('000000' + CAST(@UltimoDI AS VARCHAR), 6);

                INSERT INTO AsientosDiario (
                    PeriodoID, Fecha, Descripcion, ReferenciaExterna, TipoDocumento,
                    Estado, UsuarioID, FechaCreacion, TipoComprobanteID, NumeroComprobante
                )
                VALUES (
                    @PeriodoID, @FechaFinMes,
                    'Consumo de Materia Prima en Producción — ' + DATENAME(month, @FechaFinMes) + ' ' + CAST(@Anio AS VARCHAR),
                    @RefConsumo, 'ConsumoProduccion', 'Contabilizado', 1, GETDATE(), 1, @NumCompDI
                );
                SET @AsientoID = SCOPE_IDENTITY();

                -- Debe: 5.1.01.001 (Costo Materia Prima Consumida)
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, 8, @TotalConsumidoMes, 0, 'Materia prima consumida en horneado y pastelería');

                -- Haber: 1.1.03.001 (Inventario Materia Prima)
                INSERT INTO DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                VALUES (@AsientoID, 21, 0, @TotalConsumidoMes, 'Descargo de inventario por consumo en lotes');

                SET @AsientosConsumosCreados = @AsientosConsumosCreados + 1;
            END

            FETCH NEXT FROM curMeses INTO @PeriodoID, @Anio, @Mes, @FechaFinMes;
        END

        CLOSE curMeses;
        DEALLOCATE curMeses;

        -- Actualizar correlativos
        UPDATE TiposComprobante SET CorrelativoActual = @UltimoFC WHERE Codigo = 'FC';
        UPDATE TiposComprobante SET CorrelativoActual = @UltimoDI WHERE Codigo = 'DI';

        -- 7. Restaurar periodos cerrados historicos
        UPDATE p
        SET p.Estado = 'Cerrado'
        FROM PeriodosContables p
        JOIN @PeriodosCerrados c ON p.ID = c.ID;

        COMMIT TRANSACTION;

        SELECT 
            @TotalLotesCreados AS LotesCreados,
            @TotalConsumosCreados AS ConsumosCreados,
            @TotalComprasCreadas AS ComprasCreadas,
            @AsientosComprasCreados AS AsientosCompras,
            @AsientosConsumosCreados AS AsientosConsumos;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        IF CURSOR_STATUS('local', 'curMeses') >= 0
        BEGIN
            CLOSE curMeses;
            DEALLOCATE curMeses;
        END;
        THROW;
    END CATCH;
    """

    print("Ejecutando migración histórica de Producción, Compras y Costos...")
    t0 = time.time()
    cur.execute(tsql)
    res = cur.fetchone()
    conn.commit()
    print(f"¡Migración completada exitosamente en {time.time() - t0:.2f}s!")
    print(f"Lotes de Producción creados: {res[0]}")
    print(f"Detalles de Consumo registrados: {res[1]}")
    print(f"Compras de Materia Prima registradas: {res[2]}")
    print(f"Asientos de Compra (FC) generados: {res[3]}")
    print(f"Asientos de Consumo (DI) generados: {res[4]}")
    conn.close()


if __name__ == '__main__':
    main()
