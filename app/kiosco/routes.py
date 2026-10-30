# app/kiosco/routes.py
# Rutas públicas para el Kiosco de Marcaje de Asistencia y reconocimiento facial backend.

from flask import render_template, request, jsonify
from app.kiosco import kiosco_bp
from app.db import get_db_connection, execute_sp
from app.extensions import csrf
from flask_login import login_required, current_user
from app.auth.decorators import roles_required
from datetime import datetime, timedelta
from app.services.business_time import business_now
from app.services.hr_calculations import can_mark_exit, resolver_horario_y_clasificar_asistencia
import logging
import json

# Importamos el servicio de reconocimiento facial (se inicializa al cargar el módulo)
from app.services.face_service import face_service

@kiosco_bp.route('/')
def kiosco_vista():
    """Página principal del kiosco de marcaje (pública, sin login)."""
    return render_template('kiosco.html')

@kiosco_bp.route('/api/empleados/registrar_rostro', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
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
        
        execute_sp(
            cursor,
            'rrhh.sp_ActualizarDescriptorFacialEmpleado',
            (descriptor_str, int(empleado_id)),
            fallback_sql="UPDATE Empleados SET FaceDescriptor = ? WHERE ID = ?",
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
def reconocer():
    """Recibe un frame base64 del kiosco, busca coincidencias y marca asistencia automáticamente."""
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify(status='error', message='Datos inválidos'), 400
    accion = datos.get('accion', 'entrada')
    if accion not in ('entrada', 'salida'):
        return jsonify(status='error', message='Acción inválida'), 400
    base64_img = datos.get('image')
    
    if not base64_img:
        return jsonify({'status': 'error', 'message': 'No se proporcionó imagen'}), 400
        
    # Llamar al servicio de reconocimiento
    resultado = face_service.reconocer_rostro(base64_img, tolerancia=0.45)
    
    if resultado['status'] == 'match':
        # Hay coincidencia, procedemos a marcar asistencia
        return _procesar_marcaje(resultado['empleado_id'], accion)
    
    # Devuelve 'no_face' o 'unknown' con status 200 para que el frontend siga iterando sin errores HTTP
    return jsonify(resultado), 200

def _procesar_marcaje(empleado_id, accion='entrada', *, exception_reason=None, supervisor_id=None):
    """Operaciones idempotentes; una nueva lectura nunca alterna entrada/salida."""
    if accion not in ('entrada', 'salida'):
        return jsonify(status='error', message='Acción inválida'), 400
    ahora = business_now()
    fecha, hora = ahora.date().isoformat(), ahora.strftime('%H:%M:%S')
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Serializar las operaciones por empleado, incluso cuando aún no hay marca.
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerEmpleadoActivoPorIDBloqueo',
            (int(empleado_id),),
            fallback_sql=(
                "SELECT ID, NombreCompleto, HoraEntrada, HoraSalida FROM Empleados WITH (UPDLOCK, HOLDLOCK) "
                "WHERE ID = ? AND EstadoEmpleado = 'Activo'"
            ),
        )
        empleado = cursor.fetchone()
        if not empleado:
            return jsonify(status='error', message='Empleado no encontrado o inactivo'), 404
        nombre = empleado.NombreCompleto
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerTurnoLaboralActivoDefecto',
            fallback_sql="SELECT TOP 1 ID, HoraEntrada, ToleranciaMinutos FROM TurnosLaborales WHERE Activo = 1 ORDER BY ID ASC",
        )
        turno = cursor.fetchone()
        clasificacion = resolver_horario_y_clasificar_asistencia(empleado, turno, ahora)
        turno_id = clasificacion['turno_id']
        execute_sp(
            cursor,
            'rrhh.sp_ObtenerAsistenciaPorEmpleadoFechaBloqueo',
            (int(empleado_id), fecha),
            fallback_sql=(
                "SELECT ID, HoraEntrada, HoraSalida FROM Asistencia WITH (UPDLOCK, HOLDLOCK) "
                "WHERE EmpleadoID = ? AND Fecha = ?"
            ),
        )
        asistencia = cursor.fetchone()
        if accion == 'entrada':
            if asistencia and asistencia.HoraEntrada:
                return jsonify(status='success', tipo='entrada', empleado=nombre, repetido=True,
                               mensaje=f'{nombre}, tu entrada ya está registrada hoy.')
            if asistencia and asistencia.HoraSalida:
                return jsonify(status='error', message='Registro de asistencia incompleto; solicita revisión.'), 409
            estado = clasificacion['estado']
            if asistencia:
                execute_sp(
                    cursor,
                    'rrhh.sp_ActualizarEntradaAsistenciaKiosco',
                    (hora, estado, turno_id, asistencia.ID),
                    fallback_sql="UPDATE Asistencia SET HoraEntrada = ?, EstadoEntrada = ?, TurnoID = ? WHERE ID = ?",
                )
            else:
                execute_sp(
                    cursor,
                    'rrhh.sp_InsertarEntradaAsistenciaKiosco',
                    (int(empleado_id), turno_id, fecha, hora, estado),
                    fallback_sql=(
                        "INSERT INTO Asistencia (EmpleadoID, TurnoID, Fecha, HoraEntrada, EstadoEntrada, RegistradoPor) "
                        "VALUES (?, ?, ?, ?, ?, NULL)"
                    ),
                )
            if exception_reason:
                _audit_attendance_exception(cursor, empleado_id, accion, fecha, hora,
                                            exception_reason, supervisor_id)
            conn.commit()
            return jsonify(status='success', tipo='entrada', empleado=nombre, estado=estado,
                           mensaje=f'¡Bienvenido {nombre}! Entrada registrada a las {hora}.')
        if not asistencia or not asistencia.HoraEntrada:
            return jsonify(status='error', message='Debes registrar entrada antes de la salida.'), 409
        if asistencia.HoraSalida:
            return jsonify(status='success', tipo='salida', empleado=nombre, repetido=True,
                           mensaje=f'{nombre}, tu salida ya está registrada hoy.')
        if not can_mark_exit(asistencia.HoraEntrada, ahora):
            return jsonify(status='error', message='Espera al menos un minuto desde la entrada para marcar salida.'), 409
        execute_sp(
            cursor,
            'rrhh.sp_ActualizarSalidaAsistenciaKiosco',
            (hora, asistencia.ID),
            fallback_sql="UPDATE Asistencia SET HoraSalida = ? WHERE ID = ? AND HoraSalida IS NULL",
        )
        if exception_reason:
            _audit_attendance_exception(cursor, empleado_id, accion, fecha, hora,
                                        exception_reason, supervisor_id)
        conn.commit()
        return jsonify(status='success', tipo='salida', empleado=nombre,
                       mensaje=f'¡Hasta mañana {nombre}! Salida registrada a las {hora}.')
    except Exception:
        conn.rollback()
        logging.exception('Error en kiosco marcaje')
        return jsonify(status='error', message='Error interno del servidor'), 500
    finally:
        conn.close()


def _audit_attendance_exception(cursor, empleado_id, accion, fecha, hora, motivo, supervisor_id):
    """El motivo se confirma en la misma transacción que el marcaje."""
    detail = json.dumps({'accion': accion, 'fecha': fecha, 'hora': hora,
                         'motivo': motivo, 'metodo': 'Autorización supervisor'}, ensure_ascii=False)
    execute_sp(
        cursor, 'seguridad.sp_RegistrarAuditoria',
        (supervisor_id, 'ASISTENCIA_EXCEPCION', 'Asistencia', int(empleado_id),
         None, detail, request.remote_addr),
        fallback_sql='''INSERT INTO AuditLog(UsuarioID,Accion,Entidad,EntidadID,DatosAntes,DatosDespues,IP)
                        VALUES(?,?,?,?,?,?,?)''',
    )

# Mantenemos el endpoint de /api/marcar antiguo por compatibilidad o pruebas manuales
@kiosco_bp.route('/api/marcar', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def marcar_asistencia():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify(error='Datos inválidos'), 400
    empleado_id = datos.get('empleado_id')
    if not empleado_id:
        return jsonify({'error': 'Falta el ID del empleado'}), 400
    motivo = str(datos.get('motivo') or '').strip()
    if len(motivo) < 10 or len(motivo) > 300 or '\x00' in motivo:
        return jsonify(error='Indica un motivo de contingencia entre 10 y 300 caracteres.'), 400
    try:
        empleado_id = int(empleado_id)
        if empleado_id <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify(error='Empleado inválido.'), 400
    return _procesar_marcaje(empleado_id, datos.get('accion', 'entrada'),
                            exception_reason=motivo, supervisor_id=current_user.id)
