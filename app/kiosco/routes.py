# app/kiosco/routes.py
# Rutas públicas para el Kiosco de Marcaje de Asistencia.
# No requieren autenticación ya que se ejecutan en un dispositivo dedicado.

from flask import render_template, request, jsonify
from app.kiosco import kiosco_bp
from app.db import get_db_connection
from app.extensions import csrf
from datetime import datetime, timedelta


@kiosco_bp.route('/')
def kiosco_vista():
    """Página principal del kiosco de marcaje (pública, sin login)."""
    return render_template('kiosco.html')


@kiosco_bp.route('/api/empleados/referencias', methods=['GET'])
def get_empleados_referencias():
    """Devuelve lista de empleados activos con foto de perfil para reconocimiento facial."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ID, NombreCompleto, FotoPerfil FROM Empleados "
        "WHERE EstadoEmpleado = 'Activo' AND FotoPerfil IS NOT NULL"
    )
    empleados = [{'id': r.ID, 'nombre': r.NombreCompleto, 'foto': r.FotoPerfil} for r in cursor.fetchall()]
    conn.close()
    return jsonify(empleados)


@kiosco_bp.route('/api/marcar', methods=['POST'])
@csrf.exempt
def marcar_asistencia():
    """
    Marca asistencia automáticamente.
    
    Lógica:
    - Si no hay registro hoy → crea entrada
    - Si hay entrada pero no salida → registra salida
    - Si ya tiene entrada y salida → error (jornada completada)
    
    Solo recibe empleado_id, el tipo se determina automáticamente.
    """
    datos = request.json
    empleado_id = datos.get('empleado_id')
    
    if not empleado_id:
        return jsonify({'error': 'Falta el ID del empleado'}), 400
    
    fecha = datetime.now().strftime('%Y-%m-%d')
    hora = datetime.now().strftime('%H:%M:%S')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Verificar que el empleado existe y está activo
        cursor.execute(
            "SELECT ID, NombreCompleto FROM Empleados "
            "WHERE ID = ? AND EstadoEmpleado = 'Activo'", int(empleado_id)
        )
        empleado = cursor.fetchone()
        if not empleado:
            return jsonify({'error': 'Empleado no encontrado o inactivo'}), 404
        
        nombre = empleado.NombreCompleto
        
        # Obtener turno activo para verificar tolerancia
        cursor.execute(
            "SELECT TOP 1 ID, HoraEntrada, ToleranciaMinutos "
            "FROM TurnosLaborales WHERE Activo = 1"
        )
        turno = cursor.fetchone()
        turno_id = turno.ID if turno else 1
        
        # Verificar registro de asistencia de hoy
        cursor.execute(
            "SELECT ID, HoraEntrada, HoraSalida FROM Asistencia "
            "WHERE EmpleadoID = ? AND Fecha = ?", int(empleado_id), fecha
        )
        asistencia = cursor.fetchone()
        
        if not asistencia:
            # ═══ PRIMERA MARCA DEL DÍA → ENTRADA ═══
            estado_entrada = 'A Tiempo'
            if turno and turno.HoraEntrada:
                hora_limite = (
                    datetime.combine(datetime.today(), turno.HoraEntrada) +
                    timedelta(minutes=turno.ToleranciaMinutos or 0)
                ).time()
                if datetime.now().time() > hora_limite:
                    estado_entrada = 'Llegada Tardia'
            
            cursor.execute("""
                INSERT INTO Asistencia (EmpleadoID, TurnoID, Fecha, HoraEntrada, EstadoEntrada, RegistradoPor)
                VALUES (?, ?, ?, ?, ?, NULL)
            """, int(empleado_id), turno_id, fecha, hora, estado_entrada)
            
            conn.commit()
            return jsonify({
                'status': 'success',
                'tipo': 'entrada',
                'mensaje': f'¡Bienvenido {nombre}! Entrada registrada a las {hora}.',
                'estado': estado_entrada
            })
        
        elif asistencia.HoraEntrada and not asistencia.HoraSalida:
            # ═══ YA TIENE ENTRADA, NO SALIDA → SALIDA ═══
            cursor.execute(
                "UPDATE Asistencia SET HoraSalida = ? WHERE ID = ?",
                hora, asistencia.ID
            )
            conn.commit()
            return jsonify({
                'status': 'success',
                'tipo': 'salida',
                'mensaje': f'¡Hasta mañana {nombre}! Salida registrada a las {hora}.'
            })
        
        else:
            # ═══ YA TIENE ENTRADA Y SALIDA → JORNADA COMPLETADA ═══
            return jsonify({
                'error': f'{nombre}, ya completaste tu jornada hoy.',
                'tipo': 'completado'
            }), 400
    
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Error en kiosco marcaje: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500
    finally:
        conn.close()
