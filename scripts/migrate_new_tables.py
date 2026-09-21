import pyodbc

def run_migration():
    print("Conectando a la base de datos...")
    drivers = [driver for driver in pyodbc.drivers() if 'SQL Server' in driver or 'ODBC Driver' in driver]
    if not drivers:
        print("No SQL Server ODBC drivers found.")
        return
    driver = drivers[-1]
    server = r'localhost\SQLDEV'
    conn_db_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE=PanaderiaDB;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;"
    
    try:
        conn = pyodbc.connect(conn_db_str, autocommit=True)
        cursor = conn.cursor()

        tables_sql = [
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Mermas' AND xtype='U')
            BEGIN
                CREATE TABLE Mermas (
                    ID INT PRIMARY KEY IDENTITY(1,1),
                    ProductoID INT NOT NULL,
                    Cantidad INT NOT NULL,
                    Motivo VARCHAR(50) NOT NULL,
                    Observaciones VARCHAR(200) NULL,
                    UsuarioID INT NOT NULL,
                    Fecha DATETIME NOT NULL DEFAULT GETDATE(),
                    CONSTRAINT FK_Mermas_Productos FOREIGN KEY (ProductoID) REFERENCES Productos(ID),
                    CONSTRAINT FK_Mermas_Usuarios FOREIGN KEY (UsuarioID) REFERENCES Usuarios(ID),
                    CONSTRAINT CK_Mermas_Motivo CHECK (Motivo IN ('Pan Frio', 'Defectuoso', 'Merma Horneado', 'Vencido', 'Otro'))
                );
                PRINT 'Tabla Mermas creada exitosamente.'
            END
            """,
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='TipoCambio' AND xtype='U')
            BEGIN
                CREATE TABLE TipoCambio (
                    ID INT PRIMARY KEY IDENTITY(1,1),
                    Fecha DATE NOT NULL UNIQUE,
                    TasaCompra DECIMAL(10, 4) NOT NULL,
                    TasaVenta DECIMAL(10, 4) NOT NULL,
                    Fuente VARCHAR(50) NOT NULL DEFAULT 'Manual'
                );
                PRINT 'Tabla TipoCambio creada exitosamente.'
            END
            """,
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ArqueoCaja' AND xtype='U')
            BEGIN
                CREATE TABLE ArqueoCaja (
                    ID INT PRIMARY KEY IDENTITY(1,1),
                    TurnoID INT NOT NULL,
                    UsuarioID INT NOT NULL,
                    EfectivoContado DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    TransferenciasContadas DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    DolaresContados DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    TipoCambioUsado DECIMAL(10, 4) NULL,
                    EfectivoSistema DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    TransferenciasSistema DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    DiferenciaEfectivo DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    DiferenciaTransferencias DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    Observaciones VARCHAR(500) NULL,
                    FechaArqueo DATETIME NOT NULL DEFAULT GETDATE(),
                    CONSTRAINT FK_ArqueoCaja_TurnosCaja FOREIGN KEY (TurnoID) REFERENCES TurnosCaja(ID),
                    CONSTRAINT FK_ArqueoCaja_Usuarios FOREIGN KEY (UsuarioID) REFERENCES Usuarios(ID)
                );
                PRINT 'Tabla ArqueoCaja creada exitosamente.'
            END
            """,
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ConfiguracionSistema' AND xtype='U')
            BEGIN
                CREATE TABLE ConfiguracionSistema (
                    Clave VARCHAR(50) PRIMARY KEY NOT NULL,
                    Valor VARCHAR(255) NOT NULL,
                    Descripcion VARCHAR(200) NULL
                );
                PRINT 'Tabla ConfiguracionSistema creada exitosamente.'
            END
            """,
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Empleados' AND xtype='U')
            BEGIN
                CREATE TABLE Empleados (
                    ID INT PRIMARY KEY IDENTITY(1,1),
                    UsuarioID INT NULL,
                    NombreCompleto VARCHAR(150) NOT NULL,
                    Cedula VARCHAR(20) NOT NULL UNIQUE,
                    FechaNacimiento DATE NULL,
                    Genero VARCHAR(10) NULL,
                    Direccion VARCHAR(300) NULL,
                    Telefono VARCHAR(20) NULL,
                    CorreoElectronico VARCHAR(100) NULL,
                    NumeroINSS VARCHAR(20) NULL,
                    Cargo VARCHAR(100) NOT NULL,
                    FechaIngreso DATE NOT NULL,
                    FechaEgreso DATE NULL,
                    TipoContrato VARCHAR(30) NOT NULL DEFAULT 'Indefinido',
                    TipoJornada VARCHAR(20) NOT NULL DEFAULT 'Diurna',
                    SalarioBase DECIMAL(10, 2) NOT NULL,
                    FormaPago VARCHAR(20) NOT NULL DEFAULT 'Mensual',
                    EstadoEmpleado VARCHAR(20) NOT NULL DEFAULT 'Activo',
                    MotivoEgreso VARCHAR(100) NULL,
                    ConsentimientoDatos BIT NOT NULL DEFAULT 0,
                    FechaConsentimiento DATETIME NULL,
                    CreadoEn DATETIME NOT NULL DEFAULT GETDATE(),
                    CONSTRAINT FK_Empleados_Usuarios FOREIGN KEY (UsuarioID) REFERENCES Usuarios(ID),
                    CONSTRAINT CK_Empleados_Contrato CHECK (TipoContrato IN ('Indefinido', 'Determinado', 'Por Obra')),
                    CONSTRAINT CK_Empleados_Jornada CHECK (TipoJornada IN ('Diurna', 'Nocturna', 'Mixta')),
                    CONSTRAINT CK_Empleados_FormaPago CHECK (FormaPago IN ('Semanal', 'Catorcenal', 'Quincenal', 'Mensual')),
                    CONSTRAINT CK_Empleados_Estado CHECK (EstadoEmpleado IN ('Activo', 'Subsidio', 'Licencia', 'Suspendido', 'Liquidado'))
                );
                PRINT 'Tabla Empleados creada exitosamente.'
            END
            """,
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='FeriadosNacionales' AND xtype='U')
            BEGIN
                CREATE TABLE FeriadosNacionales (
                    ID INT PRIMARY KEY IDENTITY(1,1),
                    Fecha DATE NOT NULL,
                    Descripcion VARCHAR(100) NOT NULL,
                    Anio INT NOT NULL,
                    EsMovil BIT NOT NULL DEFAULT 0
                );
                PRINT 'Tabla FeriadosNacionales creada exitosamente.'
            END
            """,
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Nomina' AND xtype='U')
            BEGIN
                CREATE TABLE Nomina (
                    ID INT PRIMARY KEY IDENTITY(1,1),
                    EmpleadoID INT NOT NULL,
                    PeriodoInicio DATE NOT NULL,
                    PeriodoFin DATE NOT NULL,
                    SalarioBruto DECIMAL(10, 2) NOT NULL,
                    HorasExtras DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    MontoHorasExtras DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    OtrosIngresos DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    TotalDevengado DECIMAL(10, 2) NOT NULL,
                    INSSLaboral DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    IRMensual DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    PensionAlimenticia DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    ValesDescontados DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    OtrasDeducciones DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    TotalDeducciones DECIMAL(10, 2) NOT NULL,
                    SalarioNeto DECIMAL(10, 2) NOT NULL,
                    INSSPatronal DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    INATEC DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    Estado VARCHAR(20) NOT NULL DEFAULT 'Borrador',
                    FechaGeneracion DATETIME NOT NULL DEFAULT GETDATE(),
                    GeneradoPor INT NULL,
                    CONSTRAINT FK_Nomina_Empleados FOREIGN KEY (EmpleadoID) REFERENCES Empleados(ID),
                    CONSTRAINT FK_Nomina_GeneradoPor FOREIGN KEY (GeneradoPor) REFERENCES Usuarios(ID),
                    CONSTRAINT CK_Nomina_Estado CHECK (Estado IN ('Borrador', 'Aprobada', 'Pagada', 'Anulada'))
                );
                PRINT 'Tabla Nomina creada exitosamente.'
            END
            """,
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DetalleNomina' AND xtype='U')
            BEGIN
                CREATE TABLE DetalleNomina (
                    ID INT PRIMARY KEY IDENTITY(1,1),
                    NominaID INT NOT NULL,
                    Concepto VARCHAR(100) NOT NULL,
                    Tipo VARCHAR(10) NOT NULL,
                    Monto DECIMAL(10, 2) NOT NULL,
                    Descripcion VARCHAR(200) NULL,
                    CONSTRAINT FK_DetalleNomina_Nomina FOREIGN KEY (NominaID) REFERENCES Nomina(ID),
                    CONSTRAINT CK_DetalleNomina_Tipo CHECK (Tipo IN ('Ingreso', 'Deduccion', 'Patronal'))
                );
                PRINT 'Tabla DetalleNomina creada exitosamente.'
            END
            """,
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='LicenciasEmpleados' AND xtype='U')
            BEGIN
                CREATE TABLE LicenciasEmpleados (
                    ID INT PRIMARY KEY IDENTITY(1,1),
                    EmpleadoID INT NOT NULL,
                    TipoLicencia VARCHAR(50) NOT NULL,
                    FechaInicio DATE NOT NULL,
                    FechaFin DATE NOT NULL,
                    DiasOtorgados INT NOT NULL,
                    PagoEmpleador DECIMAL(5, 2) NOT NULL DEFAULT 100.00,
                    PagoINSS DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
                    Observaciones VARCHAR(300) NULL,
                    AprobadoPor INT NULL,
                    FechaRegistro DATETIME NOT NULL DEFAULT GETDATE(),
                    CONSTRAINT FK_LicenciasEmpleados_Empleados FOREIGN KEY (EmpleadoID) REFERENCES Empleados(ID),
                    CONSTRAINT FK_LicenciasEmpleados_Aprobador FOREIGN KEY (AprobadoPor) REFERENCES Usuarios(ID),
                    CONSTRAINT CK_Licencias_Tipo CHECK (TipoLicencia IN (
                        'Vacaciones', 'Enfermedad Comun', 'Maternidad', 'Paternidad',
                        'Matrimonio', 'Luto', 'Riesgo Profesional', 'Permiso Personal', 'Otro'
                    ))
                );
                PRINT 'Tabla LicenciasEmpleados creada exitosamente.'
            END
            """,
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DeduccionesJudiciales' AND xtype='U')
            BEGIN
                CREATE TABLE DeduccionesJudiciales (
                    ID INT PRIMARY KEY IDENTITY(1,1),
                    EmpleadoID INT NOT NULL,
                    TipoDeduccion VARCHAR(30) NOT NULL,
                    Beneficiario VARCHAR(150) NOT NULL,
                    PorcentajeSalarioNeto DECIMAL(5, 2) NOT NULL,
                    MontoFijo DECIMAL(10, 2) NULL,
                    NumeroJuzgado VARCHAR(50) NULL,
                    FechaInicio DATE NOT NULL,
                    FechaFin DATE NULL,
                    Activa BIT NOT NULL DEFAULT 1,
                    CONSTRAINT FK_DeduccionesJudiciales_Empleados FOREIGN KEY (EmpleadoID) REFERENCES Empleados(ID),
                    CONSTRAINT CK_DeduccionesJudiciales_Tipo CHECK (TipoDeduccion IN ('Pension Alimenticia', 'Embargo Comercial'))
                );
                PRINT 'Tabla DeduccionesJudiciales creada exitosamente.'
            END
            """,
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='IncidentesLaborales' AND xtype='U')
            BEGIN
                CREATE TABLE IncidentesLaborales (
                    ID INT PRIMARY KEY IDENTITY(1,1),
                    EmpleadoID INT NOT NULL,
                    TipoIncidente VARCHAR(30) NOT NULL,
                    Gravedad VARCHAR(20) NOT NULL,
                    Descripcion VARCHAR(MAX) NOT NULL,
                    FechaIncidente DATETIME NOT NULL,
                    FechaReporte DATETIME NOT NULL DEFAULT GETDATE(),
                    NotificadoMITRAB BIT NOT NULL DEFAULT 0,
                    FechaNotificacionMITRAB DATETIME NULL,
                    AccionesCorrectivas VARCHAR(MAX) NULL,
                    RegistradoPor INT NOT NULL,
                    CONSTRAINT FK_IncidentesLaborales_Empleados FOREIGN KEY (EmpleadoID) REFERENCES Empleados(ID),
                    CONSTRAINT FK_IncidentesLaborales_Registrador FOREIGN KEY (RegistradoPor) REFERENCES Usuarios(ID),
                    CONSTRAINT CK_Incidentes_Tipo CHECK (TipoIncidente IN ('Accidente', 'Casi Accidente', 'Enfermedad Ocupacional')),
                    CONSTRAINT CK_Incidentes_Gravedad CHECK (Gravedad IN ('Leve', 'Grave', 'Muy Grave', 'Mortal'))
                );
                PRINT 'Tabla IncidentesLaborales creada exitosamente.'
            END
            """,
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='AuditLog' AND xtype='U')
            BEGIN
                CREATE TABLE AuditLog (
                    ID INT PRIMARY KEY IDENTITY(1,1),
                    UsuarioID INT NULL,
                    Accion VARCHAR(100) NOT NULL,
                    Entidad VARCHAR(50) NOT NULL,
                    EntidadID INT NULL,
                    DatosAntes VARCHAR(MAX) NULL,
                    DatosDespues VARCHAR(MAX) NULL,
                    IP VARCHAR(45) NULL,
                    FechaHora DATETIME NOT NULL DEFAULT GETDATE(),
                    CONSTRAINT FK_AuditLog_Usuarios FOREIGN KEY (UsuarioID) REFERENCES Usuarios(ID)
                );
                PRINT 'Tabla AuditLog creada exitosamente.'
            END
            """
        ]
        
        for stmt in tables_sql:
            cursor.execute(stmt)
            
        print("Migración completada con éxito.")
    except Exception as e:
        print(f"Error al ejecutar la migración: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    run_migration()
