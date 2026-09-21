from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.db import get_db_connection

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Alterar tabla Empleados
    try:
        cursor.execute("ALTER TABLE Empleados ADD FechaFinContrato DATE NULL")
        print("Columna FechaFinContrato añadida a Empleados.")
    except Exception as e:
        print(f"Aviso Empleados: {e}")

    # 2. Crear tabla TurnosLaborales
    try:
        cursor.execute("""
        CREATE TABLE TurnosLaborales (
            ID INT PRIMARY KEY IDENTITY(1,1),
            Nombre VARCHAR(50) NOT NULL,
            HoraEntrada TIME NOT NULL,
            HoraSalida TIME NOT NULL,
            ToleranciaMinutos INT NOT NULL DEFAULT 15,
            Activo BIT NOT NULL DEFAULT 1
        )
        """)
        # Insertar turno por defecto
        cursor.execute("INSERT INTO TurnosLaborales (Nombre, HoraEntrada, HoraSalida) VALUES ('Diurno Estándar', '06:00', '14:00')")
        print("Tabla TurnosLaborales creada e inicializada.")
    except Exception as e:
        print(f"Aviso TurnosLaborales: {e}")

    # 3. Crear tabla Asistencia
    try:
        cursor.execute("""
        CREATE TABLE Asistencia (
            ID INT PRIMARY KEY IDENTITY(1,1),
            EmpleadoID INT NOT NULL,
            TurnoID INT NOT NULL,
            Fecha DATE NOT NULL,
            HoraEntrada TIME NULL,
            HoraSalida TIME NULL,
            EstadoEntrada VARCHAR(20) NULL,
            Observaciones VARCHAR(200) NULL,
            RegistradoPor INT NOT NULL,
            FechaRegistro DATETIME NOT NULL DEFAULT GETDATE(),
            CONSTRAINT FK_Asistencia_Empleados FOREIGN KEY (EmpleadoID) REFERENCES Empleados(ID),
            CONSTRAINT FK_Asistencia_Turnos FOREIGN KEY (TurnoID) REFERENCES TurnosLaborales(ID),
            CONSTRAINT FK_Asistencia_Usuarios FOREIGN KEY (RegistradoPor) REFERENCES Usuarios(ID),
            CONSTRAINT CK_Asistencia_Estado CHECK (EstadoEntrada IN ('A Tiempo', 'Llegada Tardia', 'Ausente'))
        )
        """)
        print("Tabla Asistencia creada.")
    except Exception as e:
        print(f"Aviso Asistencia: {e}")

    conn.commit()
    conn.close()
    print("Migración Fase 2 completada.")
