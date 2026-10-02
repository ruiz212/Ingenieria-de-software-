from app import create_app
from app.db import get_db_connection
from datetime import datetime, date
import traceback

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Empleados WHERE EstadoEmpleado = 'Activo'")
    empleados = cursor.fetchall()
    anio = 2026
    fecha_fin_ciclo = date(anio, 11, 30)
    fecha_inicio_ciclo = date(anio - 1, 12, 1)
    
    for emp in empleados:
        print('Empleado:', emp.NombreCompleto)
        fecha_ingreso = emp.FechaIngreso
        if type(fecha_ingreso) is str:
            fecha_ingreso = datetime.strptime(fecha_ingreso, '%Y-%m-%d').date()
        elif hasattr(fecha_ingreso, 'date'):
            fecha_ingreso = fecha_ingreso.date()
        print('Fecha Ingreso:', fecha_ingreso)
        
        cursor.execute("SELECT TOP 6 SalarioBruto FROM Nomina WHERE EmpleadoID = ? AND PeriodoFin <= ? ORDER BY PeriodoFin DESC", (emp.ID, fecha_fin_ciclo.strftime('%Y-%m-%d')))
        nominas_recientes = [float(r.SalarioBruto) for r in cursor.fetchall()]
        salario_base = float(emp.SalarioBase)
        salario_max_6m = max(nominas_recientes) if nominas_recientes else salario_base
        print('Salario Max 6m:', salario_max_6m)
        
        inicio_aguinaldo_real = max(fecha_inicio_ciclo, fecha_ingreso)
        if inicio_aguinaldo_real <= fecha_fin_ciclo:
            dias_aguinaldo = (fecha_fin_ciclo - inicio_aguinaldo_real).days + 1
            aguinaldo_proporcional = salario_max_6m * (dias_aguinaldo / 365.0)
            print('Aguinaldo:', aguinaldo_proporcional)
            try:
                cursor.execute("""
                    INSERT INTO Nomina (EmpleadoID, PeriodoInicio, PeriodoFin, SalarioBruto,
                        HorasExtras, MontoHorasExtras, OtrosIngresos, TotalDevengado,
                        INSSLaboral, IRMensual, PensionAlimenticia, ValesDescontados,
                        TotalDeducciones, SalarioNeto, INSSPatronal, INATEC, Estado, GeneradoPor)
                    VALUES (?, ?, ?, 0, 0, 0, ?, ?, 0, 0, 0, 0, 0, ?, 0, 0, 'Aguinaldo', ?)
                """,
                    emp.ID, fecha_inicio_ciclo.strftime('%Y-%m-%d'), fecha_fin_ciclo.strftime('%Y-%m-%d'),
                    aguinaldo_proporcional, aguinaldo_proporcional, aguinaldo_proporcional, 1
                )
                print('Inserted!')
            except Exception as e:
                print("INSERT ERROR:", str(e))
                traceback.print_exc()
    conn.rollback()
    print('Done!')
