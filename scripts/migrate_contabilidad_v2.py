# scripts/migrate_contabilidad_v2.py
# ============================================================
# MIGRACIÓN CONTABLE V2 — Catálogo NIIF Profesional (87 cuentas)
# Evolución NO destructiva del esquema existente
# ============================================================
# USO: python scripts/migrate_contabilidad_v2.py
# PREREQUISITO: Tener las tablas V1 ya creadas (migrate_contabilidad.py)
# ============================================================

import pyodbc
import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from config import Config


def migrate():
    conn_str = Config.SQL_SERVER_CONNECTION_STRING
    print("=" * 60)
    print("MIGRACIÓN CONTABLE V2 — Catálogo NIIF Profesional")
    print("=" * 60)
    print(f"Conectando a la base de datos...")

    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        conn.autocommit = False  # Control manual de transacciones

        # ============================================================
        # PASO 1: Evolucionar tabla CatalogoCuentas (ADD COLUMNS)
        # ============================================================
        print("\n[1/8] Evolucionando CatalogoCuentas...")

        columnas_nuevas_catalogo = [
            ("Nivel", "TINYINT NOT NULL DEFAULT 4"),
            ("CuentaPadreID", "INT NULL"),
            ("EsTransaccional", "BIT NOT NULL DEFAULT 1"),
            ("Descripcion", "VARCHAR(255) NULL"),
            ("OrdenVisualizacion", "INT NOT NULL DEFAULT 0"),
        ]

        for col_name, col_def in columnas_nuevas_catalogo:
            cursor.execute(f"""
                IF NOT EXISTS (
                    SELECT 1 FROM sys.columns 
                    WHERE object_id = OBJECT_ID('CatalogoCuentas') AND name = '{col_name}'
                )
                ALTER TABLE CatalogoCuentas ADD {col_name} {col_def};
            """)

        # FK para CuentaPadreID (autoref)
        cursor.execute("""
            IF NOT EXISTS (
                SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Cuenta_Padre'
            )
            ALTER TABLE CatalogoCuentas ADD 
                CONSTRAINT FK_Cuenta_Padre FOREIGN KEY (CuentaPadreID) 
                REFERENCES CatalogoCuentas(ID);
        """)

        # Actualizar CHECK constraint de Clase para incluir 'Gasto'
        cursor.execute("""
            IF EXISTS (
                SELECT 1 FROM sys.check_constraints WHERE name = 'CK_Cuenta_Clase'
            )
            ALTER TABLE CatalogoCuentas DROP CONSTRAINT CK_Cuenta_Clase;
        """)
        cursor.execute("""
            ALTER TABLE CatalogoCuentas ADD 
                CONSTRAINT CK_Cuenta_Clase CHECK (Clase IN ('Activo', 'Pasivo', 'Capital', 'Ingreso', 'Costo', 'Gasto'));
        """)

        print("   ✅ CatalogoCuentas evolucionada con jerarquía")

        # ============================================================
        # PASO 2: Evolucionar tabla AsientosDiario
        # ============================================================
        print("[2/8] Evolucionando AsientosDiario...")

        columnas_nuevas_asientos = [
            ("TipoComprobanteID", "INT NULL"),
            ("NumeroComprobante", "VARCHAR(20) NULL"),
            ("IP", "VARCHAR(45) NULL"),
            ("AnuladoPor", "INT NULL"),
            ("FechaAnulacion", "DATETIME NULL"),
            ("MotivoAnulacion", "VARCHAR(255) NULL"),
        ]

        for col_name, col_def in columnas_nuevas_asientos:
            cursor.execute(f"""
                IF NOT EXISTS (
                    SELECT 1 FROM sys.columns 
                    WHERE object_id = OBJECT_ID('AsientosDiario') AND name = '{col_name}'
                )
                ALTER TABLE AsientosDiario ADD {col_name} {col_def};
            """)

        print("   ✅ AsientosDiario evolucionada con auditoría y reversión")

        # ============================================================
        # PASO 3: Evolucionar tabla DetalleAsientos
        # ============================================================
        print("[3/8] Evolucionando DetalleAsientos...")

        columnas_nuevas_detalle = [
            ("Descripcion", "VARCHAR(255) NULL"),
            ("DocumentoRelacionado", "VARCHAR(50) NULL"),
        ]

        for col_name, col_def in columnas_nuevas_detalle:
            cursor.execute(f"""
                IF NOT EXISTS (
                    SELECT 1 FROM sys.columns 
                    WHERE object_id = OBJECT_ID('DetalleAsientos') AND name = '{col_name}'
                )
                ALTER TABLE DetalleAsientos ADD {col_name} {col_def};
            """)

        print("   ✅ DetalleAsientos evolucionada con descripciones")

        # ============================================================
        # PASO 4: Evolucionar tabla PeriodosContables
        # ============================================================
        print("[4/8] Evolucionando PeriodosContables...")

        columnas_nuevas_periodos = [
            ("CierreUtilidad", "DECIMAL(18,4) NULL"),
            ("CierreReservaLegal", "DECIMAL(18,4) NULL"),
        ]

        for col_name, col_def in columnas_nuevas_periodos:
            cursor.execute(f"""
                IF NOT EXISTS (
                    SELECT 1 FROM sys.columns 
                    WHERE object_id = OBJECT_ID('PeriodosContables') AND name = '{col_name}'
                )
                ALTER TABLE PeriodosContables ADD {col_name} {col_def};
            """)

        print("   ✅ PeriodosContables evolucionada")

        # ============================================================
        # PASO 5: Crear nuevas tablas
        # ============================================================
        print("[5/8] Creando nuevas tablas...")

        # 5a. TiposComprobante
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'TiposComprobante') AND type = N'U')
            CREATE TABLE TiposComprobante (
                ID INT PRIMARY KEY IDENTITY(1,1),
                Codigo VARCHAR(5) NOT NULL UNIQUE,
                Nombre VARCHAR(50) NOT NULL,
                CorrelativoActual INT NOT NULL DEFAULT 0,
                Prefijo VARCHAR(10) NOT NULL,
                Activo BIT NOT NULL DEFAULT 1
            );
        """)

        # FK de AsientosDiario → TiposComprobante
        cursor.execute("""
            IF NOT EXISTS (
                SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Asiento_TipoComprobante'
            )
            AND EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('AsientosDiario') AND name = 'TipoComprobanteID')
            ALTER TABLE AsientosDiario ADD 
                CONSTRAINT FK_Asiento_TipoComprobante FOREIGN KEY (TipoComprobanteID) 
                REFERENCES TiposComprobante(ID);
        """)

        # 5b. CuentasPorCobrar
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'CuentasPorCobrar') AND type = N'U')
            CREATE TABLE CuentasPorCobrar (
                ID INT PRIMARY KEY IDENTITY(1,1),
                ClienteID INT NOT NULL,
                FacturaID INT NOT NULL,
                MontoOriginal DECIMAL(18,2) NOT NULL,
                MontoPagado DECIMAL(18,2) NOT NULL DEFAULT 0,
                SaldoPendiente AS (MontoOriginal - MontoPagado),
                FechaEmision DATETIME NOT NULL DEFAULT GETDATE(),
                FechaVencimiento DATETIME NOT NULL,
                Estado VARCHAR(20) NOT NULL DEFAULT 'Vigente',
                CONSTRAINT FK_CxC_Cliente FOREIGN KEY (ClienteID) REFERENCES Clientes(ID),
                CONSTRAINT FK_CxC_Factura FOREIGN KEY (FacturaID) REFERENCES Facturas(ID),
                CONSTRAINT CK_CxC_Estado CHECK (Estado IN ('Vigente','Vencida','Pagada','Incobrable'))
            );
        """)

        # 5c. CuentasPorPagar
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'CuentasPorPagar') AND type = N'U')
            CREATE TABLE CuentasPorPagar (
                ID INT PRIMARY KEY IDENTITY(1,1),
                ProveedorID INT NOT NULL,
                CompraID INT NULL,
                MontoOriginal DECIMAL(18,2) NOT NULL,
                MontoPagado DECIMAL(18,2) NOT NULL DEFAULT 0,
                SaldoPendiente AS (MontoOriginal - MontoPagado),
                FechaEmision DATETIME NOT NULL DEFAULT GETDATE(),
                FechaVencimiento DATETIME NOT NULL,
                Estado VARCHAR(20) NOT NULL DEFAULT 'Vigente',
                CONSTRAINT FK_CxP_Proveedor FOREIGN KEY (ProveedorID) REFERENCES Proveedores(ID),
                CONSTRAINT FK_CxP_Compra FOREIGN KEY (CompraID) REFERENCES ComprasMateriaPrima(ID),
                CONSTRAINT CK_CxP_Estado CHECK (Estado IN ('Vigente','Vencida','Pagada'))
            );
        """)

        # 5d. PagosCxC
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'PagosCxC') AND type = N'U')
            CREATE TABLE PagosCxC (
                ID INT PRIMARY KEY IDENTITY(1,1),
                CuentaPorCobrarID INT NOT NULL,
                AsientoID INT NOT NULL,
                MontoPagado DECIMAL(18,2) NOT NULL,
                FechaPago DATETIME NOT NULL DEFAULT GETDATE(),
                MetodoPago VARCHAR(20) NOT NULL,
                CONSTRAINT FK_PagoCxC_CxC FOREIGN KEY (CuentaPorCobrarID) REFERENCES CuentasPorCobrar(ID),
                CONSTRAINT FK_PagoCxC_Asiento FOREIGN KEY (AsientoID) REFERENCES AsientosDiario(ID)
            );
        """)

        # 5e. ConciliacionBancaria
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'ConciliacionBancaria') AND type = N'U')
            CREATE TABLE ConciliacionBancaria (
                ID INT PRIMARY KEY IDENTITY(1,1),
                PeriodoID INT NOT NULL,
                FechaConciliacion DATETIME NOT NULL DEFAULT GETDATE(),
                SaldoSegunBanco DECIMAL(18,2) NOT NULL,
                SaldoSegunLibros DECIMAL(18,2) NOT NULL,
                Diferencia AS (SaldoSegunBanco - SaldoSegunLibros),
                Estado VARCHAR(20) NOT NULL DEFAULT 'Borrador',
                RealizadoPor INT NOT NULL,
                CONSTRAINT FK_Conc_Periodo FOREIGN KEY (PeriodoID) REFERENCES PeriodosContables(ID),
                CONSTRAINT FK_Conc_Usuario FOREIGN KEY (RealizadoPor) REFERENCES Usuarios(ID),
                CONSTRAINT CK_Conc_Estado CHECK (Estado IN ('Borrador','Conciliado'))
            );
        """)

        # 5f. DetalleConciliacion
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'DetalleConciliacion') AND type = N'U')
            CREATE TABLE DetalleConciliacion (
                ID INT PRIMARY KEY IDENTITY(1,1),
                ConciliacionID INT NOT NULL,
                Tipo VARCHAR(30) NOT NULL,
                Descripcion VARCHAR(255) NOT NULL,
                Monto DECIMAL(18,2) NOT NULL,
                FechaDocumento DATE NULL,
                CONSTRAINT FK_DetConc_Conc FOREIGN KEY (ConciliacionID) REFERENCES ConciliacionBancaria(ID)
            );
        """)

        print("   ✅ 6 tablas nuevas creadas (TiposComprobante, CxC, CxP, PagosCxC, ConciliacionBancaria, DetalleConciliacion)")

        # ============================================================
        # PASO 6: Migrar códigos de cuentas existentes (8 cuentas)
        # ============================================================
        print("[6/8] Migrando códigos de cuentas existentes...")

        mapeo_cuentas = {
            '1101': ('1.1.01.001', 'Caja General (C$)',           'Activo',  'Activo Circulante',  'Deudora',   4),
            '1102': ('1.1.02.001', 'Clientes (CxC Comerciales)',  'Activo',  'Activo Circulante',  'Deudora',   4),
            '1103': ('1.1.01.004', 'Bancos Moneda Nacional',      'Activo',  'Activo Circulante',  'Deudora',   4),
            '2101': ('2.1.01.001', 'Proveedores Nacionales (CxP)','Pasivo',  'Pasivo Circulante',  'Acreedora', 4),
            '2102': ('2.1.03.001', 'IVA Débito Fiscal (15%)',     'Pasivo',  'Pasivo Circulante',  'Acreedora', 4),
            '3101': ('3.1.01.001', 'Aporte de Capital — Amada Calero', 'Capital', 'Capital Contable', 'Acreedora', 4),
            '4101': ('4.1.01.001', 'Ventas de Pan y Repostería',  'Ingreso', 'Ingresos Operativos','Acreedora', 4),
            '5101': ('5.1.01.001', 'Costo de Materia Prima Consumida', 'Costo', 'Costos Operativos', 'Deudora', 4),
        }

        migradas = 0
        for codigo_viejo, (codigo_nuevo, nombre_nuevo, clase, grupo, naturaleza, nivel) in mapeo_cuentas.items():
            cursor.execute("SELECT ID FROM CatalogoCuentas WHERE Codigo = ?", (codigo_viejo,))
            row = cursor.fetchone()
            if row:
                cursor.execute("""
                    UPDATE CatalogoCuentas SET 
                        Codigo = ?, Nombre = ?, Clase = ?, Grupo = ?, 
                        Naturaleza = ?, Nivel = ?, EsTransaccional = 1
                    WHERE ID = ?
                """, (codigo_nuevo, nombre_nuevo, clase, grupo, naturaleza, nivel, row[0]))
                migradas += 1
                print(f"   {codigo_viejo} → {codigo_nuevo} ({nombre_nuevo})")

        print(f"   ✅ {migradas} cuentas migradas al formato jerárquico")

        # ============================================================
        # PASO 7: Insertar catálogo completo de 87 cuentas
        # ============================================================
        print("[7/8] Insertando catálogo de cuentas NIIF (87 cuentas)...")

        # Definición completa del catálogo
        # (Codigo, Nombre, Clase, Grupo, Naturaleza, Nivel, EsTransaccional, Descripcion, Orden)
        catalogo_completo = [
            # ═══════ CLASE 1: ACTIVOS ═══════
            ('1',          'ACTIVOS',                              'Activo', 'Activos',              'Deudora',   1, 0, 'Clase principal de activos',                                   100),
            ('1.1',        'Activo Circulante',                    'Activo', 'Activo Circulante',     'Deudora',   2, 0, 'Activos convertibles en efectivo en menos de 12 meses',       110),
            ('1.1.01',     'Efectivo y Equivalentes de Efectivo',  'Activo', 'Activo Circulante',     'Deudora',   3, 0, 'Dinero disponible inmediatamente',                             111),
            # 1.1.01.001 Caja General C$ — ya migrada arriba
            ('1.1.01.002', 'Caja General (USD)',                   'Activo', 'Activo Circulante',     'Deudora',   4, 1, 'Efectivo en dólares americanos en caja',                      112),
            ('1.1.01.003', 'Caja Chica',                           'Activo', 'Activo Circulante',     'Deudora',   4, 1, 'Fondo fijo para gastos menores',                              113),
            # 1.1.01.004 Bancos MN — ya migrada arriba
            ('1.1.01.005', 'Bancos Moneda Extranjera',             'Activo', 'Activo Circulante',     'Deudora',   4, 1, 'Cuentas bancarias en USD',                                    115),
            
            ('1.1.02',     'Cuentas y Documentos por Cobrar',      'Activo', 'Activo Circulante',     'Deudora',   3, 0, 'Derechos de cobro a terceros',                                121),
            # 1.1.02.001 Clientes CxC — ya migrada arriba
            ('1.1.02.002', 'Encargos por Cobrar (Saldo Restante)', 'Activo', 'Activo Circulante',     'Deudora',   4, 1, 'Saldo pendiente de cobro en pasteles por encargo',            122),
            ('1.1.02.003', 'Anticipos a Empleados (Vales)',        'Activo', 'Activo Circulante',     'Deudora',   4, 1, 'Vales y anticipos de sueldo a descontar en nómina',           123),
            ('1.1.02.004', 'Anticipos a Proveedores',              'Activo', 'Activo Circulante',     'Deudora',   4, 1, 'Pagos anticipados a proveedores de materia prima',            124),
            ('1.1.02.005', 'Estimación para Cuentas Incobrables',  'Activo', 'Activo Circulante',     'Acreedora', 4, 1, 'Provisión NIIF para incobrables (contraactivo)',              125),
            
            ('1.1.03',     'Inventarios',                          'Activo', 'Activo Circulante',     'Deudora',   3, 0, 'Bienes para la producción y venta',                           131),
            ('1.1.03.001', 'Inventario de Materia Prima',          'Activo', 'Activo Circulante',     'Deudora',   4, 1, 'Harina, azúcar, huevos, manteca, etc.',                       132),
            ('1.1.03.002', 'Inventario de Productos en Proceso',   'Activo', 'Activo Circulante',     'Deudora',   4, 1, 'Pan y pasteles en proceso de elaboración',                    133),
            ('1.1.03.003', 'Inventario de Productos Terminados',   'Activo', 'Activo Circulante',     'Deudora',   4, 1, 'Pan y repostería listo para venta',                           134),
            ('1.1.03.004', 'Inventario de Suministros y Empaques', 'Activo', 'Activo Circulante',     'Deudora',   4, 1, 'Bolsas, cajas, papel, etc.',                                  135),
            
            ('1.1.04',     'Impuestos Pagados por Anticipado',     'Activo', 'Activo Circulante',     'Deudora',   3, 0, 'Créditos fiscales a favor',                                   141),
            ('1.1.04.001', 'IVA Crédito Fiscal (15%)',             'Activo', 'Activo Circulante',     'Deudora',   4, 1, 'IVA pagado en compras, acreditable contra IVA por pagar',     142),
            ('1.1.04.002', 'IR Pagado por Anticipado',             'Activo', 'Activo Circulante',     'Deudora',   4, 1, 'Pagos a cuenta del IR anual',                                 143),
            ('1.1.04.003', 'Retenciones en la Fuente a Favor',     'Activo', 'Activo Circulante',     'Deudora',   4, 1, 'Retenciones hechas al negocio por clientes grandes',          144),
            
            ('1.1.05',     'Gastos Pagados por Anticipado',        'Activo', 'Activo Circulante',     'Deudora',   3, 0, 'Pagos por servicios aún no devengados',                       151),
            ('1.1.05.001', 'Seguros Pagados por Anticipado',       'Activo', 'Activo Circulante',     'Deudora',   4, 1, 'Pólizas de seguro pagadas por adelantado',                    152),
            ('1.1.05.002', 'Alquileres Pagados por Anticipado',    'Activo', 'Activo Circulante',     'Deudora',   4, 1, 'Renta pagada por adelantado',                                 153),
            
            ('1.2',        'Activo No Circulante',                 'Activo', 'Activo No Circulante',  'Deudora',   2, 0, 'Activos de largo plazo',                                      160),
            ('1.2.01',     'Propiedad, Planta y Equipo',           'Activo', 'Activo No Circulante',  'Deudora',   3, 0, 'Activos fijos tangibles NIIF Sección 17',                     161),
            ('1.2.01.001', 'Mobiliario y Equipo de Panadería',     'Activo', 'Activo No Circulante',  'Deudora',   4, 1, 'Hornos, amasadoras, vitrinas, mesas de trabajo',             162),
            ('1.2.01.002', 'Equipo de Cómputo y POS',             'Activo', 'Activo No Circulante',  'Deudora',   4, 1, 'Computadoras, impresoras térmicas, tablets',                  163),
            ('1.2.01.003', 'Vehículos de Reparto',                 'Activo', 'Activo No Circulante',  'Deudora',   4, 1, 'Vehículos para entregas de pasteles',                         164),
            ('1.2.01.004', 'Mejoras al Local',                     'Activo', 'Activo No Circulante',  'Deudora',   4, 1, 'Remodelaciones y adecuaciones del local',                     165),
            
            ('1.2.02',     'Depreciación Acumulada',               'Activo', 'Activo No Circulante',  'Acreedora', 3, 0, 'Desgaste acumulado de activos fijos (contraactivo)',          171),
            ('1.2.02.001', 'Dep. Acum. Mobiliario y Equipo',       'Activo', 'Activo No Circulante',  'Acreedora', 4, 1, 'Depreciación acumulada de equipo de panadería',               172),
            ('1.2.02.002', 'Dep. Acum. Equipo de Cómputo',        'Activo', 'Activo No Circulante',  'Acreedora', 4, 1, 'Depreciación acumulada de equipo informático',                173),
            ('1.2.02.003', 'Dep. Acum. Vehículos',                 'Activo', 'Activo No Circulante',  'Acreedora', 4, 1, 'Depreciación acumulada de vehículos',                         174),
            ('1.2.02.004', 'Dep. Acum. Mejoras al Local',          'Activo', 'Activo No Circulante',  'Acreedora', 4, 1, 'Amortización de mejoras al local',                            175),
            
            # ═══════ CLASE 2: PASIVOS ═══════
            ('2',          'PASIVOS',                               'Pasivo', 'Pasivos',               'Acreedora', 1, 0, 'Clase principal de pasivos',                                  200),
            ('2.1',        'Pasivo Circulante',                     'Pasivo', 'Pasivo Circulante',     'Acreedora', 2, 0, 'Obligaciones a pagar en menos de 12 meses',                   210),
            ('2.1.01',     'Cuentas y Documentos por Pagar',        'Pasivo', 'Pasivo Circulante',     'Acreedora', 3, 0, 'Deudas con proveedores y terceros',                           211),
            # 2.1.01.001 Proveedores Nacionales — ya migrada arriba
            ('2.1.01.002', 'Proveedores Extranjeros (CxP)',         'Pasivo', 'Pasivo Circulante',     'Acreedora', 4, 1, 'Deudas con proveedores internacionales',                      212),
            ('2.1.01.003', 'Anticipos Recibidos de Clientes',       'Pasivo', 'Pasivo Circulante',     'Acreedora', 4, 1, 'Adelantos recibidos por encargos de pasteles',                213),
            
            ('2.1.02',     'Obligaciones Laborales',                'Pasivo', 'Pasivo Circulante',     'Acreedora', 3, 0, 'Deudas con empleados e instituciones laborales',               221),
            ('2.1.02.001', 'Sueldos y Salarios por Pagar',          'Pasivo', 'Pasivo Circulante',     'Acreedora', 4, 1, 'Nómina pendiente de pago',                                    222),
            ('2.1.02.002', 'INSS Laboral por Pagar (7%)',           'Pasivo', 'Pasivo Circulante',     'Acreedora', 4, 1, 'Retención INSS laboral por enterar',                          223),
            ('2.1.02.003', 'INSS Patronal por Pagar (21.5%)',      'Pasivo', 'Pasivo Circulante',     'Acreedora', 4, 1, 'Aporte patronal INSS por pagar',                              224),
            ('2.1.02.004', 'INATEC por Pagar (2%)',                 'Pasivo', 'Pasivo Circulante',     'Acreedora', 4, 1, 'Aporte INATEC por pagar',                                     225),
            ('2.1.02.005', 'IR Laboral Retenido por Pagar',         'Pasivo', 'Pasivo Circulante',     'Acreedora', 4, 1, 'IR retenido a empleados, pendiente de enterar a DGI',         226),
            ('2.1.02.006', 'Vacaciones por Pagar',                  'Pasivo', 'Pasivo Circulante',     'Acreedora', 4, 1, 'Provisión de vacaciones devengadas Art. 76 Ley 185',          227),
            ('2.1.02.007', 'Aguinaldo por Pagar',                   'Pasivo', 'Pasivo Circulante',     'Acreedora', 4, 1, 'Provisión de décimo tercer mes Art. 93 Ley 185',              228),
            ('2.1.02.008', 'Indemnización por Pagar',               'Pasivo', 'Pasivo Circulante',     'Acreedora', 4, 1, 'Provisión de indemnización por antigüedad Art. 45 Ley 185',   229),
            ('2.1.02.009', 'Pensiones Alimenticias por Pagar',      'Pasivo', 'Pasivo Circulante',     'Acreedora', 4, 1, 'Retenciones judiciales por pensión alimenticia Ley 870',      230),
            
            ('2.1.03',     'Impuestos por Pagar',                   'Pasivo', 'Pasivo Circulante',     'Acreedora', 3, 0, 'Obligaciones fiscales con DGI y Alcaldía',                    231),
            # 2.1.03.001 IVA Débito Fiscal — ya migrada arriba
            ('2.1.03.002', 'IR Anual por Pagar',                    'Pasivo', 'Pasivo Circulante',     'Acreedora', 4, 1, 'Impuesto sobre la renta anual Ley 822',                      232),
            ('2.1.03.003', 'Anticipo IR Mensual (1%)',              'Pasivo', 'Pasivo Circulante',     'Acreedora', 4, 1, 'Anticipo mensual sobre ingresos brutos',                     233),
            ('2.1.03.004', 'Impuesto Municipal por Pagar',          'Pasivo', 'Pasivo Circulante',     'Acreedora', 4, 1, 'IMI y tributos municipales',                                  234),
            ('2.1.03.005', 'Retenciones en la Fuente por Pagar (2%)', 'Pasivo', 'Pasivo Circulante',   'Acreedora', 4, 1, 'Retenciones IR a proveedores por pagar a DGI',               235),
            
            ('2.1.04',     'Otras Obligaciones a Corto Plazo',     'Pasivo', 'Pasivo Circulante',     'Acreedora', 3, 0, 'Otras deudas a corto plazo',                                  241),
            ('2.1.04.001', 'Préstamos Bancarios a Corto Plazo',    'Pasivo', 'Pasivo Circulante',     'Acreedora', 4, 1, 'Porción corriente de préstamos bancarios',                    242),
            ('2.1.04.002', 'Intereses por Pagar',                   'Pasivo', 'Pasivo Circulante',     'Acreedora', 4, 1, 'Intereses devengados no pagados',                             243),
            
            ('2.2',        'Pasivo No Circulante',                  'Pasivo', 'Pasivo No Circulante',  'Acreedora', 2, 0, 'Obligaciones a largo plazo',                                  250),
            ('2.2.01',     'Obligaciones a Largo Plazo',            'Pasivo', 'Pasivo No Circulante',  'Acreedora', 3, 0, 'Deudas a más de 12 meses',                                    251),
            ('2.2.01.001', 'Préstamos Bancarios a Largo Plazo',    'Pasivo', 'Pasivo No Circulante',  'Acreedora', 4, 1, 'Financiamiento bancario a largo plazo',                       252),
            
            # ═══════ CLASE 3: CAPITAL ═══════
            ('3',          'CAPITAL CONTABLE',                      'Capital', 'Capital Contable',     'Acreedora', 1, 0, 'Patrimonio de los propietarios',                               300),
            ('3.1',        'Capital Contribuido',                   'Capital', 'Capital Contable',     'Acreedora', 2, 0, 'Aportes de los propietarios',                                  310),
            ('3.1.01',     'Capital Social',                        'Capital', 'Capital Contable',     'Acreedora', 3, 0, 'Capital social del negocio',                                   311),
            # 3.1.01.001 Aporte de Capital — ya migrada arriba
            
            ('3.2',        'Capital Ganado',                        'Capital', 'Capital Contable',     'Acreedora', 2, 0, 'Resultados acumulados del negocio',                            320),
            ('3.2.01',     'Resultados',                            'Capital', 'Capital Contable',     'Acreedora', 3, 0, 'Utilidades y pérdidas',                                        321),
            ('3.2.01.001', 'Utilidades Retenidas (Acumuladas)',     'Capital', 'Capital Contable',     'Acreedora', 4, 1, 'Ganancias acumuladas de ejercicios anteriores',               322),
            ('3.2.01.002', 'Utilidad del Ejercicio',                'Capital', 'Capital Contable',     'Acreedora', 4, 1, 'Resultado positivo del periodo actual',                       323),
            ('3.2.01.003', 'Pérdida del Ejercicio',                 'Capital', 'Capital Contable',     'Deudora',   4, 1, 'Resultado negativo del periodo actual',                       324),
            ('3.2.02',     'Reservas',                              'Capital', 'Capital Contable',     'Acreedora', 3, 0, 'Reservas legales y voluntarias',                               331),
            ('3.2.02.001', 'Reserva Legal (10%)',                   'Capital', 'Capital Contable',     'Acreedora', 4, 1, 'Reserva legal obligatoria sobre utilidades',                  332),
            
            # ═══════ CLASE 4: INGRESOS ═══════
            ('4',          'INGRESOS',                              'Ingreso', 'Ingresos',             'Acreedora', 1, 0, 'Clase principal de ingresos',                                  400),
            ('4.1',        'Ingresos Operativos',                   'Ingreso', 'Ingresos Operativos',  'Acreedora', 2, 0, 'Ingresos del giro principal del negocio',                     410),
            ('4.1.01',     'Ventas',                                'Ingreso', 'Ingresos Operativos',  'Acreedora', 3, 0, 'Ingresos por venta de productos',                             411),
            # 4.1.01.001 Ventas de Pan y Repostería — ya migrada arriba
            ('4.1.01.002', 'Ventas de Pasteles y Encargos',         'Ingreso', 'Ingresos Operativos',  'Acreedora', 4, 1, 'Ventas de pasteles personalizados por encargo',               412),
            ('4.1.01.003', 'Ventas de Bebidas',                     'Ingreso', 'Ingresos Operativos',  'Acreedora', 4, 1, 'Ventas de café, gaseosas, jugos',                             413),
            ('4.1.01.004', 'Devoluciones y Descuentos sobre Ventas','Ingreso', 'Ingresos Operativos',  'Deudora',   4, 1, 'Contra-ingreso por devoluciones y descuentos',               414),
            
            ('4.2',        'Ingresos No Operativos',                'Ingreso', 'Ingresos No Operativos','Acreedora',2, 0, 'Ingresos fuera del giro normal',                              420),
            ('4.2.01',     'Otros Ingresos',                        'Ingreso', 'Ingresos No Operativos','Acreedora',3, 0, 'Ingresos extraordinarios y financieros',                      421),
            ('4.2.01.001', 'Ganancia por Diferencial Cambiario',    'Ingreso', 'Ingresos No Operativos','Acreedora',4, 1, 'Ganancia por fluctuación USD/NIO',                            422),
            ('4.2.01.002', 'Ingresos Financieros (Intereses)',      'Ingreso', 'Ingresos No Operativos','Acreedora',4, 1, 'Intereses ganados en cuentas bancarias',                      423),
            ('4.2.01.003', 'Otros Ingresos No Operativos',          'Ingreso', 'Ingresos No Operativos','Acreedora',4, 1, 'Ingresos varios no recurrentes',                              424),
            
            # ═══════ CLASE 5: COSTOS ═══════
            ('5',          'COSTOS',                                'Costo',  'Costos',                'Deudora',   1, 0, 'Clase principal de costos',                                    500),
            ('5.1',        'Costo de Ventas',                       'Costo',  'Costo de Ventas',       'Deudora',   2, 0, 'Costo de los bienes vendidos',                                510),
            ('5.1.01',     'Costos Directos de Producción',         'Costo',  'Costo de Ventas',       'Deudora',   3, 0, 'Costos directos de la producción panadera',                   511),
            # 5.1.01.001 Costo de Materia Prima Consumida — ya migrada arriba
            ('5.1.01.002', 'Mano de Obra Directa (Panaderos)',     'Costo',  'Costo de Ventas',       'Deudora',   4, 1, 'Salario de panaderos asignado a producción',                  512),
            ('5.1.01.003', 'Costos Indirectos de Fabricación (CIF)','Costo',  'Costo de Ventas',       'Deudora',   4, 1, 'Gas, energía, mantenimiento de equipo de producción',        513),
            
            ('5.1.02',     'Pérdidas Operativas',                   'Costo',  'Costo de Ventas',       'Deudora',   3, 0, 'Pérdidas inherentes a la operación',                          521),
            ('5.1.02.001', 'Mermas y Desperdicios (Pan Frío)',     'Costo',  'Costo de Ventas',       'Deudora',   4, 1, 'Pan frío, defectuoso, vencido — Tabla Mermas del sistema',    522),
            
            # ═══════ CLASE 6: GASTOS ═══════
            ('6',          'GASTOS DE OPERACIÓN',                   'Gasto',  'Gastos',                'Deudora',   1, 0, 'Clase principal de gastos operativos',                        600),
            ('6.1',        'Gastos de Administración',              'Gasto',  'Gastos de Administración','Deudora', 2, 0, 'Gastos del área administrativa',                              610),
            ('6.1.01',     'Gastos de Personal Administrativo',     'Gasto',  'Gastos de Administración','Deudora', 3, 0, 'Costos de personal administrativo',                           611),
            ('6.1.01.001', 'Sueldos y Salarios (Admin)',            'Gasto',  'Gastos de Administración','Deudora', 4, 1, 'Sueldos del personal administrativo y gerencial',             612),
            ('6.1.01.002', 'INSS Patronal (Admin)',                 'Gasto',  'Gastos de Administración','Deudora', 4, 1, 'Aporte patronal INSS del personal administrativo',           613),
            ('6.1.01.003', 'INATEC (Admin)',                        'Gasto',  'Gastos de Administración','Deudora', 4, 1, 'Aporte INATEC del personal administrativo',                  614),
            ('6.1.01.004', 'Aguinaldo (Admin)',                     'Gasto',  'Gastos de Administración','Deudora', 4, 1, 'Provisión de aguinaldo del personal administrativo',          615),
            ('6.1.01.005', 'Vacaciones (Admin)',                    'Gasto',  'Gastos de Administración','Deudora', 4, 1, 'Provisión de vacaciones del personal administrativo',         616),
            ('6.1.01.006', 'Indemnización (Admin)',                 'Gasto',  'Gastos de Administración','Deudora', 4, 1, 'Provisión de indemnización del personal administrativo',      617),
            
            ('6.1.02',     'Gastos Generales de Administración',    'Gasto',  'Gastos de Administración','Deudora', 3, 0, 'Gastos generales del negocio',                                621),
            ('6.1.02.001', 'Alquiler del Local',                    'Gasto',  'Gastos de Administración','Deudora', 4, 1, 'Renta mensual del local comercial',                          622),
            ('6.1.02.002', 'Servicios Públicos (Agua, Luz, Internet)','Gasto','Gastos de Administración','Deudora', 4, 1, 'Servicios básicos del negocio',                              623),
            ('6.1.02.003', 'Útiles y Papelería de Oficina',         'Gasto',  'Gastos de Administración','Deudora', 4, 1, 'Material de oficina y papelería',                             624),
            ('6.1.02.004', 'Depreciación de Equipo (Admin)',        'Gasto',  'Gastos de Administración','Deudora', 4, 1, 'Gasto por depreciación de activos administrativos',           625),
            ('6.1.02.005', 'Mantenimiento y Reparaciones',          'Gasto',  'Gastos de Administración','Deudora', 4, 1, 'Mantenimiento de equipo, local e instalaciones',             626),
            ('6.1.02.006', 'Seguros',                               'Gasto',  'Gastos de Administración','Deudora', 4, 1, 'Pólizas de seguro del negocio',                              627),
            ('6.1.02.007', 'Servicios Profesionales (Contables/Legal)','Gasto','Gastos de Administración','Deudora',4, 1, 'Honorarios de contador, abogado, etc.',                       628),
            ('6.1.02.008', 'Gastos Varios de Administración',       'Gasto',  'Gastos de Administración','Deudora', 4, 1, 'Egresos privados no clasificados del sistema',               629),
            
            ('6.2',        'Gastos de Venta',                       'Gasto',  'Gastos de Venta',       'Deudora',   2, 0, 'Gastos relacionados con la actividad comercial',              640),
            ('6.2.01',     'Gastos de Personal de Ventas',          'Gasto',  'Gastos de Venta',       'Deudora',   3, 0, 'Costos de personal de ventas (dependientas)',                 641),
            ('6.2.01.001', 'Sueldos y Salarios (Ventas)',           'Gasto',  'Gastos de Venta',       'Deudora',   4, 1, 'Sueldos de dependientas del POS',                             642),
            ('6.2.01.002', 'INSS Patronal (Ventas)',                'Gasto',  'Gastos de Venta',       'Deudora',   4, 1, 'Aporte patronal INSS del personal de ventas',                643),
            ('6.2.01.003', 'INATEC (Ventas)',                       'Gasto',  'Gastos de Venta',       'Deudora',   4, 1, 'Aporte INATEC del personal de ventas',                       644),
            
            ('6.2.02',     'Gastos Generales de Venta',             'Gasto',  'Gastos de Venta',       'Deudora',   3, 0, 'Gastos generales del área comercial',                         651),
            ('6.2.02.001', 'Empaques y Material de Empaque',        'Gasto',  'Gastos de Venta',       'Deudora',   4, 1, 'Bolsas, cajas para pasteles, envolturas',                    652),
            ('6.2.02.002', 'Publicidad y Promoción',                'Gasto',  'Gastos de Venta',       'Deudora',   4, 1, 'Publicidad, redes sociales, promociones',                    653),
            ('6.2.02.003', 'Transporte y Entregas',                 'Gasto',  'Gastos de Venta',       'Deudora',   4, 1, 'Combustible y costos de entrega de encargos',                654),
            ('6.2.02.004', 'Depreciación de Equipo (Ventas)',       'Gasto',  'Gastos de Venta',       'Deudora',   4, 1, 'Gasto por depreciación de equipo del área de ventas',        655),
            
            ('6.3',        'Gastos Financieros',                    'Gasto',  'Gastos Financieros',    'Deudora',   2, 0, 'Costos del financiamiento',                                   660),
            ('6.3.01',     'Costos Financieros',                    'Gasto',  'Gastos Financieros',    'Deudora',   3, 0, 'Gastos bancarios y financieros',                              661),
            ('6.3.01.001', 'Intereses sobre Préstamos',             'Gasto',  'Gastos Financieros',    'Deudora',   4, 1, 'Intereses de préstamos bancarios',                            662),
            ('6.3.01.002', 'Comisiones Bancarias',                  'Gasto',  'Gastos Financieros',    'Deudora',   4, 1, 'Comisiones y mantenimiento de cuentas bancarias',            663),
            ('6.3.01.003', 'Pérdida por Diferencial Cambiario',     'Gasto',  'Gastos Financieros',    'Deudora',   4, 1, 'Pérdida por fluctuación USD/NIO',                             664),
        ]

        insertadas = 0
        omitidas = 0
        for cuenta in catalogo_completo:
            codigo = cuenta[0]
            cursor.execute("SELECT ID FROM CatalogoCuentas WHERE Codigo = ?", (codigo,))
            if cursor.fetchone():
                omitidas += 1
                continue
            
            cursor.execute("""
                INSERT INTO CatalogoCuentas 
                    (Codigo, Nombre, Clase, Grupo, Naturaleza, Nivel, EsTransaccional, Descripcion, OrdenVisualizacion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, cuenta)
            insertadas += 1

        print(f"   ✅ {insertadas} cuentas nuevas insertadas, {omitidas} ya existían (omitidas)")

        # Asignar CuentaPadreID basándose en la jerarquía de códigos
        print("   Vinculando jerarquía padre-hijo...")
        cursor.execute("""
            UPDATE hijo SET hijo.CuentaPadreID = padre.ID
            FROM CatalogoCuentas hijo
            INNER JOIN CatalogoCuentas padre ON 
                LEFT(hijo.Codigo, LEN(hijo.Codigo) - CHARINDEX('.', REVERSE(hijo.Codigo) + '.')) = padre.Codigo
            WHERE hijo.Nivel > 1 AND hijo.CuentaPadreID IS NULL;
        """)
        print("   ✅ Jerarquía padre-hijo vinculada")

        # ============================================================
        # PASO 8: Insertar Tipos de Comprobante
        # ============================================================
        print("[8/8] Insertando tipos de comprobante...")

        tipos_comprobante = [
            ('DI', 'Diario',               'CD'),
            ('IN', 'Ingreso',              'CI'),
            ('EG', 'Egreso',               'CE'),
            ('AJ', 'Ajuste',               'CA'),
            ('CI', 'Cierre',               'CC'),
            ('AP', 'Apertura',             'CO'),
            ('NM', 'Nómina',               'CN'),
            ('FV', 'Factura de Venta',     'FV'),
            ('FC', 'Factura de Compra',    'FC'),
        ]

        for codigo, nombre, prefijo in tipos_comprobante:
            cursor.execute("SELECT ID FROM TiposComprobante WHERE Codigo = ?", (codigo,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO TiposComprobante (Codigo, Nombre, Prefijo) VALUES (?, ?, ?)",
                    (codigo, nombre, prefijo)
                )

        print("   ✅ 9 tipos de comprobante insertados")

        # ============================================================
        # PASO 9: Crear índices de rendimiento contable
        # ============================================================
        print("\n[Extra] Creando índices de rendimiento...")

        indices = [
            ("IX_CatalogoCuentas_Clase",    "CatalogoCuentas", "Clase"),
            ("IX_CatalogoCuentas_Padre",    "CatalogoCuentas", "CuentaPadreID"),
            ("IX_CatalogoCuentas_Nivel",    "CatalogoCuentas", "Nivel"),
            ("IX_AsientosDiario_Periodo",   "AsientosDiario",  "PeriodoID"),
            ("IX_AsientosDiario_Fecha",     "AsientosDiario",  "Fecha"),
            ("IX_AsientosDiario_Estado",    "AsientosDiario",  "Estado"),
            ("IX_DetalleAsientos_Asiento",  "DetalleAsientos", "AsientoID"),
            ("IX_DetalleAsientos_Cuenta",   "DetalleAsientos", "CuentaID"),
            ("IX_CxC_Cliente",              "CuentasPorCobrar","ClienteID"),
            ("IX_CxC_Estado",               "CuentasPorCobrar","Estado"),
            ("IX_CxP_Proveedor",            "CuentasPorPagar", "ProveedorID"),
            ("IX_CxP_Estado",               "CuentasPorPagar", "Estado"),
        ]

        for idx_name, table, column in indices:
            cursor.execute(f"""
                IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = '{idx_name}')
                CREATE INDEX {idx_name} ON {table}({column});
            """)

        print("   ✅ 12 índices de rendimiento creados")

        # ============================================================
        # COMMIT
        # ============================================================
        conn.commit()
        
        # Verificación final
        cursor.execute("SELECT COUNT(*) FROM CatalogoCuentas")
        total_cuentas = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM CatalogoCuentas WHERE EsTransaccional = 1")
        transaccionales = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM CatalogoCuentas WHERE EsTransaccional = 0")
        agrupadores = cursor.fetchone()[0]

        print("\n" + "=" * 60)
        print("✅ MIGRACIÓN COMPLETADA EXITOSAMENTE")
        print("=" * 60)
        print(f"   Total de cuentas:    {total_cuentas}")
        print(f"   Transaccionales:     {transaccionales}")
        print(f"   De agrupación:       {agrupadores}")
        print(f"   Tablas nuevas:       6 (TiposComprobante, CxC, CxP, PagosCxC, ConcBancaria, DetConciliacion)")
        print(f"   Índices creados:     12")
        print(f"   Tipos comprobante:   9")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ ERROR DURANTE LA MIGRACIÓN: {e}")
        import traceback
        traceback.print_exc()
        try:
            conn.rollback()
            print("   ⚠️ ROLLBACK ejecutado — no se aplicaron cambios")
        except:
            pass
    finally:
        try:
            conn.close()
        except:
            pass


if __name__ == "__main__":
    migrate()
