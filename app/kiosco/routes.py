# app/kiosco/routes.py
# Rutas públicas para el Kiosco de Marcaje de Asistencia y reconocimiento facial backend.

from flask import render_template, request, jsonify
from app.kiosco import kiosco_bp
from app.db import get_db_connection
from app.extensions import csrf
from datetime import datetime, timedelta
import logging

# Importamos el servicio de reconocimiento facial (se inicializa al cargar el módulo)
from app.services.face_service import face_service

@kiosco_bp.route('/')
def kiosco_vista():
    """Página principal del kiosco de marcaje (pública, sin login)."""
    return render_template('kiosco.html')

@kiosco_bp.route('/api/empleados/registrar_rostro', methods=['POST'])
@csrf.exempt
def registrar_rostro():
    """Endpoint para registrar/actualizar el rostro de un empleado desde un archivo de imagen."""
    empleado_id = request.form.get('empleado_id')
    
    if not empleado_id or 'foto' not in request.files:
        return jsonify({'status': 'error', 'message': 'Falta empleado_id o archivo de foto'}), 400
        
    foto = request.files['foto']
    if foto.filename == '':
        return jsonify({'status': 'error', 'message': 'No se seleccionó ningún archivo'}), 400
        
    # Procesar imagen con el servicio
    resultado = face_service.procesar_imagen_registro(foto)
    
    if resultado['status'] == 'error':
        return jsonify(resultado), 400
        
    descriptor = resultado['descriptor']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        import json
        descriptor_str = json.dumps(descriptor)
        
        cursor.execute(
            "UPDATE Empleados SET FaceDescriptor = ? WHERE ID = ?",
            descriptor_str, int(empleado_id)
        )
        conn.commit()
        
        # Actualizar caché en RAM
        face_service.actualizar_cache_empleado(empleado_id, descriptor)
        
        return jsonify({'status': 'success', 'message': 'Rostro registrado y modelo actualizado correctamente.'})
    except Exception as e:
        conn.rollback()
        logging.error(f"Error guardando descriptor en DB: {e}")
        return jsonify({'status': 'error', 'message': 'Error interno de base de datos'}), 500
    finally:
        conn.close()

@kiosco_bp.route('/api/kiosco/reconocer', methods=['POST'])
@csrf.exempt
def reconocer():
    """Recibe un frame base64 del kiosco, busca coincidencias y marca asistencia automáticamente."""
    datos = request.json
    base64_img = datos.get('image')
    
    if not base64_img:
        return jsonify({'status': 'error', 'message': 'No se proporcionó imagen'}), 400
        
    # Llamar al servicio de reconocimiento
    resultado = face_service.reconocer_rostro(base64_img, tolerancia=0.45)
    
    if resultado['status'] == 'match':
        # Hay coincidencia, procedemos a marcar asistencia
        return _procesar_marcaje(resultado['empleado_id'])
    
    # Devuelve 'no_face' o 'unknown' con status 200 para que el frontend siga iterando sin errores HTTP
    return jsonify(resultado), 200

def _procesar_marcaje(empleado_id):
    """Lógica interna para registrar entrada/salida de un empleado."""
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
            return jsonify({'status': 'error', 'message': 'Empleado no encontrado o inactivo'}), 404
        
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
                'empleado': nombre,
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
                'empleado': nombre,
                'mensaje': f'¡Hasta mañana {nombre}! Salida registrada a las {hora}.'
            })
        
        else:
            # ═══ YA TIENE ENTRADA Y SALIDA → JORNADA COMPLETADA ═══
            return jsonify({
                'status': 'completado',
                'empleado': nombre,
                'mensaje': f'{nombre}, ya completaste tu jornada hoy.'
            })
    
    except Exception as e:
        conn.rollback()
        logging.error(f"Error en kiosco marcaje: {e}")
        return jsonify({'status': 'error', 'message': 'Error interno del servidor'}), 500
    finally:
        conn.close()

# Mantenemos el endpoint de /api/marcar antiguo por compatibilidad o pruebas manuales
@kiosco_bp.route('/api/marcar', methods=['POST'])
@csrf.exempt
def marcar_asistencia():
    datos = request.json
    empleado_id = datos.get('empleado_id')
    if not empleado_id:
        return jsonify({'error': 'Falta el ID del empleado'}), 400
    return _procesar_marcaje(empleado_id)
