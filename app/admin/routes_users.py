# app/admin/routes_users.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback

from app.admin import admin_bp
from app.db import get_db_connection, execute_sp
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime
from app.services.fiscal_service import audit
from app.services.audit import registrar_auditoria
from app.services.validation import amount, validate_telefono_nicaragua


LAST_SUPERADMIN_ERROR_MSG = 'No se puede desactivar ni cambiar el rol del último SuperAdmin activo del sistema'


def _is_last_superadmin_error(exc: Exception) -> bool:
    msg = str(exc or '').lower()
    return (
        '52005' in msg
        or 'último superadmin' in msg
        or 'ultimo superadmin' in msg
    )


def _check_last_active_superadmin(cursor, target_user_id: int) -> tuple[bool, str | None, bool, int]:
    """Verifica bajo bloqueo (UPDLOCK, HOLDLOCK) cuántos otros SuperAdmin activos existen.
    Retorna: (es_ultimo_superadmin_activo, rol_objetivo, activo_objetivo, otros_superadmins_activos)
    """
    execute_sp(
        cursor,
        'seguridad.sp_ContarSuperAdminsActivosBloqueo',
        (int(target_user_id),),
        fallback_sql=(
            "SELECT "
            "SUM(CASE WHEN r.Nombre = 'SuperAdmin' AND u.Activo = 1 AND u.ID <> ? THEN 1 ELSE 0 END) AS OtrosSuperAdminsActivos, "
            "MAX(CASE WHEN u.ID = ? THEN r.Nombre END) AS RolObjetivo, "
            "MAX(CASE WHEN u.ID = ? THEN CAST(u.Activo AS INT) END) AS ActivoObjetivo "
            "FROM Usuarios u WITH (UPDLOCK, HOLDLOCK) "
            "JOIN Roles r ON r.ID = u.RolID "
            "WHERE (r.Nombre = 'SuperAdmin' AND u.Activo = 1) OR u.ID = ?"
        ),
        fallback_params=(int(target_user_id), int(target_user_id), int(target_user_id), int(target_user_id)),
    )
    row = cursor.fetchone()
    if not row:
        return False, None, False, 0
    if hasattr(row, 'SuperAdminsActivosRestantes'):
        otros = int(row.SuperAdminsActivosRestantes or 0)
        rol_obj = row.TargetRolNombre
        activo_obj = bool(row.TargetActivo) if row.TargetActivo is not None else False
    elif len(row) >= 5:
        otros = int(row[4] or 0)
        rol_obj = row[1]
        activo_obj = bool(row[2]) if row[2] is not None else False
    else:
        otros = int(getattr(row, 'OtrosSuperAdminsActivos', row[0]) or 0)
        rol_obj = getattr(row, 'RolObjetivo', row[1] if len(row) > 1 else None)
        activo_raw = getattr(row, 'ActivoObjetivo', row[2] if len(row) > 2 else None)
        activo_obj = bool(activo_raw) if activo_raw is not None else False
    is_last = (rol_obj == 'SuperAdmin' and activo_obj and otros < 1)
    return is_last, rol_obj, activo_obj, otros


ROLE_ARCHITECTURE_MAP = {
    'SuperAdmin': {
        'orden': 1,
        'nombre_amigable': 'Administrador General',
        'etiqueta': 'Administrador General',
        'perfil': 'Control total del sistema, seguridad, auditoría y alertas',
        'rol_bd': 'db_rol_superadmin',
        'usuario_bd': 'usr_bd_superadmin',
        'badge_class': 'usuarios-role-superadmin',
        'modulos': [
            'Resumen del Día y Estadística',
            'Auditoría y Alertas por Correo',
            'Contabilidad y Estados Financieros',
            'Gestión Tributaria y Control Fiscal DGI',
            'Recursos Humanos, Planilla y Asistencia',
            'Punto de Venta y Arqueos de Caja',
            'Producción, Recetas e Inventario',
            'Catálogo, Clientes, Usuarios y Ajustes',
        ],
        'esquemas_sql': 'Acceso completo a los 8 módulos de datos del sistema y lectura de datos protegidos.',
        'restricciones': 'Bitácoras de auditoría, errores y registros contables/fiscales protegidos contra eliminación. Solo un Administrador General puede crear o modificar otro igual.',
    },
    'Admin': {
        'orden': 2,
        'nombre_amigable': 'Gerencia y Administración',
        'etiqueta': 'Gerencia y Administración',
        'perfil': 'Dirección general, contabilidad, planilla, DGI y supervisión',
        'rol_bd': 'db_rol_gerencia',
        'usuario_bd': 'usr_bd_gerencia',
        'badge_class': 'usuarios-role-admin',
        'modulos': [
            'Resumen del Día y Estadística',
            'Contabilidad, Asientos y Reportes',
            'Gestión Tributaria y Control Fiscal DGI',
            'Recursos Humanos, Planilla y Asistencia',
            'Verificación de Arqueos de Caja',
            'Catálogo, Clientes, Inventario y Producción',
            'Punto de Venta y Monitor de Pedidos',
            'Gestión de Usuarios y Ajustes',
        ],
        'esquemas_sql': 'Acceso ejecutivo a todos los módulos operativos, contables, fiscales y de personal.',
        'restricciones': 'Sin acceso a la bitácora técnica interna del servidor ni permisos para modificar cuentas de Administrador General.',
    },
    'Estandar': {
        'orden': 3,
        'nombre_amigable': 'Cajero / Punto de Venta',
        'etiqueta': 'Cajero / Punto de Venta',
        'perfil': 'Atención en mostrador, facturación en caja, turnos y entregas',
        'rol_bd': 'db_rol_cajero_pos',
        'usuario_bd': 'usr_bd_cajero_pos',
        'badge_class': 'usuarios-role-estandar',
        'modulos': [
            'Punto de Venta y Facturación',
            'Apertura y Cierre de Turno',
            'Conteo Ciego de Arqueo (Etapa 1)',
            'Cotizaciones y Encargos',
            'Monitor de Pedidos y Cobro de Entregas',
            'Registro de Mermas de Mostrador',
        ],
        'esquemas_sql': 'Permisos exclusivos para ventas, consulta de catálogo, clientes y recepción de pagos.',
        'restricciones': 'Bloqueado para ver planillas, salarios, contabilidad general, reportes DGI, anulación de facturas o compras de bodega.',
    },
    'Operativo': {
        'orden': 4,
        'nombre_amigable': 'Producción y Bodega',
        'etiqueta': 'Producción y Bodega',
        'perfil': 'Maestro panadero, cocina (KDS), horneado e inventario de insumos',
        'rol_bd': 'db_rol_produccion',
        'usuario_bd': 'usr_bd_produccion',
        'badge_class': 'usuarios-role-operativo',
        'modulos': [
            'Monitor de Cocina (Preparación de Pedidos)',
            'Producción, Lotes y Recetas',
            'Inventario de Materia Prima y Proveedores',
            'Registro de Compras de Insumos y Mermas',
        ],
        'esquemas_sql': 'Permisos sobre producción, recetas, bodega de insumos y estados de preparación de encargos.',
        'restricciones': 'Bloqueado para cobrar en caja, abrir arqueos, ver salarios/planillas, estados financieros o reportes fiscales.',
    },
    'Kiosco': {
        'orden': 5,
        'nombre_amigable': 'Kiosco de Asistencia',
        'etiqueta': 'Kiosco de Asistencia',
        'perfil': 'Terminal biométrica para marcaje de entrada y salida del personal',
        'rol_bd': 'db_rol_kiosco',
        'usuario_bd': 'usr_bd_kiosco',
        'badge_class': 'usuarios-role-kiosco',
        'modulos': [
            'Kiosco de Reconocimiento Facial',
            'Marcaje de Entrada y Salida de Personal',
        ],
        'esquemas_sql': 'Permiso aislado únicamente para validar rostro y registrar asistencia del día.',
        'restricciones': 'Aislamiento total: sin acceso a salarios, nóminas, ventas, inventario, clientes ni contabilidad.',
    },
    'Invitado': {
        'orden': 6,
        'nombre_amigable': 'Consulta de Catálogo',
        'etiqueta': 'Consulta de Catálogo',
        'perfil': 'Vista pública de productos, solicitud de cotizaciones y seguimiento',
        'rol_bd': 'db_rol_portal_cliente',
        'usuario_bd': 'usr_bd_portal_cliente',
        'badge_class': 'usuarios-role-invitado',
        'modulos': [
            'Vitrina y Catálogo de Productos',
            'Solicitud de Cotizaciones Propias',
            'Seguimiento de Estado de Pedido',
        ],
        'esquemas_sql': 'Solo lectura del catálogo activo y consulta de sus propias cotizaciones o pedidos.',
        'restricciones': 'Sin acceso a ningún módulo interno, administrativo, de caja, producción ni finanzas.',
    },
}


def _enrich_role_info(nombre_rol: str, descripcion_bd: str | None = None) -> dict:
    meta = ROLE_ARCHITECTURE_MAP.get(nombre_rol, {
        'orden': 99,
        'nombre_amigable': nombre_rol,
        'etiqueta': nombre_rol,
        'perfil': descripcion_bd or 'Perfil de acceso del sistema',
        'rol_bd': 'db_rol_portal_cliente',
        'usuario_bd': 'usr_bd_portal_cliente',
        'badge_class': 'usuarios-role-invitado',
        'modulos': ['Acceso según configuración'],
        'esquemas_sql': 'Permisos configurados en el servidor',
        'restricciones': 'Acceso protegido por procedimientos almacenados',
    })
    return {
        **meta,
        'descripcion': meta['perfil'],
        'puede_asignar': (nombre_rol != 'SuperAdmin' or getattr(current_user, 'rol_nombre', None) == 'SuperAdmin'),
    }


def puede_administrar_usuario(cursor, user_id):
    execute_sp(
        cursor,
        'seguridad.sp_ObtenerRolUsuario',
        (user_id,),
        fallback_sql='SELECT r.Nombre FROM Usuarios u JOIN Roles r ON r.ID=u.RolID WHERE u.ID=?',
    )
    row = cursor.fetchone()
    return row and (row[0] != 'SuperAdmin' or current_user.rol_nombre == 'SuperAdmin')


@admin_bp.route('/usuarios')
@login_required
@roles_required('Admin', 'SuperAdmin')
def usuarios():
    """Gestor de Usuarios y Roles mediante Stored Procedures."""
    conn = get_db_connection()
    cursor = conn.cursor()

    execute_sp(
        cursor,
        'seguridad.sp_ListarRoles',
        fallback_sql="SELECT ID, Nombre, Descripcion FROM Roles ORDER BY ID",
    )
    raw_roles = cursor.fetchall()
    roles = []
    for row in raw_roles:
        desc = getattr(row, 'Descripcion', None) if hasattr(row, 'Descripcion') else (row[2] if len(row) > 2 else None)
        info = _enrich_role_info(row.Nombre, desc)
        roles.append({
            'id': row.ID,
            'nombre': row.Nombre,
            **info,
        })
    roles.sort(key=lambda r: (r['orden'], r['id']))

    execute_sp(
        cursor,
        'seguridad.sp_ListarUsuariosYRoles',
        fallback_sql=(
            "SELECT u.ID, u.NombreCompleto, u.Username, r.Nombre AS Rol, u.Activo, u.RolID "
            "FROM Usuarios u "
            "JOIN Roles r ON u.RolID = r.ID "
            "ORDER BY u.NombreCompleto"
        ),
    )
    usuarios_list = []
    conteo_por_rol = {r['nombre']: {'activos': 0, 'inactivos': 0} for r in roles}
    for row in cursor.fetchall():
        rol_nombre = row.Rol
        activo = bool(row.Activo)
        rol_id = getattr(row, 'RolID', None)
        info = _enrich_role_info(rol_nombre)
        if rol_nombre not in conteo_por_rol:
            conteo_por_rol[rol_nombre] = {'activos': 0, 'inactivos': 0}
        if activo:
            conteo_por_rol[rol_nombre]['activos'] += 1
        else:
            conteo_por_rol[rol_nombre]['inactivos'] += 1

        puede_admin = (rol_nombre != 'SuperAdmin' or current_user.rol_nombre == 'SuperAdmin')
        usuarios_list.append({
            'id': row.ID,
            'nombre': row.NombreCompleto,
            'username': row.Username,
            'rol': rol_nombre,
            'rol_id': rol_id,
            'activo': activo,
            'etiqueta_rol': info['etiqueta'],
            'perfil_rol': info['perfil'],
            'rol_bd': info['rol_bd'],
            'usuario_bd': info['usuario_bd'],
            'badge_class': info['badge_class'],
            'modulos': info['modulos'],
            'puede_administrar': puede_admin,
        })

    for r in roles:
        stats = conteo_por_rol.get(r['nombre'], {'activos': 0, 'inactivos': 0})
        r['usuarios_activos'] = stats['activos']
        r['usuarios_inactivos'] = stats['inactivos']

    conn.close()
    return render_template('admin/usuarios.html', user=current_user, usuarios=usuarios_list, roles=roles)


@admin_bp.route('/api/usuarios/<int:user_id>/rol', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def cambiar_rol_usuario(user_id):
    datos = request.get_json(silent=True) or {}
    nuevo_rol_id = datos.get('rol_id')
    if not nuevo_rol_id:
        return jsonify({'error': 'Debe seleccionar un rol válido.'}), 400
    if user_id == current_user.id:
        return jsonify({'error': 'No puedes cambiar el rol de tu propio usuario en sesión.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if not puede_administrar_usuario(cursor, user_id):
            return jsonify({'error': 'Usuario inexistente o sin permiso para administrarlo.'}), 403

        execute_sp(
            cursor,
            'seguridad.sp_ObtenerRolPorID',
            (int(nuevo_rol_id),),
            fallback_sql='SELECT Nombre FROM Roles WHERE ID=?',
        )
        nuevo_rol_row = cursor.fetchone()
        if not nuevo_rol_row:
            return jsonify({'error': 'El rol seleccionado no existe.'}), 400
        nuevo_rol_nombre = nuevo_rol_row[0]
        if nuevo_rol_nombre == 'SuperAdmin' and current_user.rol_nombre != 'SuperAdmin':
            return jsonify({'error': 'Solo SuperAdmin puede asignar el rol SuperAdmin.'}), 403

        execute_sp(
            cursor,
            'seguridad.sp_ObtenerEstadoUsuario',
            (user_id,),
            fallback_sql="SELECT NombreCompleto, Username, RolID, Activo FROM Usuarios WHERE ID=?",
        )
        before = cursor.fetchone()
        if not before:
            return jsonify({'error': 'Usuario no encontrado.'}), 404

        is_last_sa, _, _, _ = _check_last_active_superadmin(cursor, user_id)
        if is_last_sa and nuevo_rol_nombre != 'SuperAdmin':
            conn.rollback()
            return jsonify({'error': LAST_SUPERADMIN_ERROR_MSG}), 400

        execute_sp(
            cursor,
            'seguridad.sp_ActualizarRolUsuario',
            (user_id, int(nuevo_rol_id)),
            fallback_sql="UPDATE Usuarios SET RolID = ? WHERE ID = ?",
            fallback_params=(int(nuevo_rol_id), user_id),
        )
        registrar_auditoria(
            cursor,
            current_user.id,
            'CAMBIAR_ROL',
            'Usuarios',
            user_id,
            datos_antes={'username': before.Username, 'rol_id': before.RolID},
            datos_despues={'username': before.Username, 'rol_id': int(nuevo_rol_id), 'rol': nuevo_rol_nombre},
            ip=request.remote_addr,
        )
        audit(
            cursor,
            current_user.id,
            'CAMBIAR_ROL_USUARIO',
            'Usuarios',
            user_id,
            {'rol_id': int(nuevo_rol_id), 'rol': nuevo_rol_nombre},
            request.remote_addr,
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': f'Rol actualizado a {nuevo_rol_nombre}'})
    except Exception as e:
        conn.rollback()
        if _is_last_superadmin_error(e):
            return jsonify({'error': LAST_SUPERADMIN_ERROR_MSG}), 400
        import logging
        logging.error(f"Error actualizando rol de usuario: {e}")
        return jsonify({'error': 'No se pudo actualizar el rol del usuario.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/usuarios', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_usuario():
    from werkzeug.security import generate_password_hash
    datos = request.json
    nombre = datos.get('nombre')
    username = datos.get('username')
    password = datos.get('password')
    rol_id = datos.get('rol_id')

    if not all([nombre, username, password, rol_id]):
        return jsonify({'error': 'Todos los campos son requeridos'}), 400

    if len(password) < 12:
        return jsonify(error='Use una contraseña de al menos 12 caracteres.'), 400
    hashed_pw = generate_password_hash(password)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'seguridad.sp_ObtenerRolPorID',
            (int(rol_id),),
            fallback_sql='SELECT Nombre FROM Roles WHERE ID=?',
        )
        role = cursor.fetchone()
        if not role:
            return jsonify(error='Rol inexistente.'), 400
        if role[0] == 'SuperAdmin' and current_user.rol_nombre != 'SuperAdmin':
            return jsonify(error='Solo SuperAdmin puede asignar ese rol.'), 403
        execute_sp(
            cursor,
            'seguridad.sp_InsertarUsuario',
            (nombre, username, hashed_pw, int(rol_id)),
            fallback_sql=(
                "INSERT INTO Usuarios (NombreCompleto, Username, PasswordHash, RolID, Activo) "
                "OUTPUT INSERTED.ID VALUES (?, ?, ?, ?, 1)"
            ),
        )
        new_id = cursor.fetchone()[0]
        registrar_auditoria(cursor, current_user.id, 'CREAR', 'Usuarios', new_id,
                            datos_despues={'username': username, 'rol': role[0]}, ip=request.remote_addr)
        audit(cursor, current_user.id, 'CREAR_USUARIO', 'Usuarios', None, {'username': username, 'rol': role[0]}, request.remote_addr)
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Usuario creado'})
    except Exception:
        conn.rollback()
        return jsonify({'error': 'El usuario ya existe o error en base de datos'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/usuarios/<int:user_id>/toggle', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def toggle_usuario(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if user_id == current_user.id:
            return jsonify({'error': 'No puedes desactivar tu propio usuario'}), 400
        if not puede_administrar_usuario(cursor, user_id):
            return jsonify(error='Usuario inexistente o sin permiso para administrarlo.'), 403

        execute_sp(
            cursor,
            'seguridad.sp_ObtenerEstadoUsuario',
            (user_id,),
            fallback_sql="SELECT NombreCompleto, Username, RolID, Activo FROM Usuarios WHERE ID=?",
        )
        before = cursor.fetchone()
        if not before:
            return jsonify({'error': 'Usuario no encontrado.'}), 404

        is_last_sa, _, _, _ = _check_last_active_superadmin(cursor, user_id)
        if is_last_sa and bool(before.Activo):
            conn.rollback()
            return jsonify({'error': LAST_SUPERADMIN_ERROR_MSG}), 400

        execute_sp(
            cursor,
            'seguridad.sp_ToggleActivoUsuario',
            (user_id,),
            fallback_sql="UPDATE Usuarios SET Activo = 1 ^ Activo WHERE ID = ?",
        )
        registrar_auditoria(cursor, current_user.id, 'CAMBIAR_ESTADO', 'Usuarios', user_id,
                    datos_antes=dict(nombre=before.NombreCompleto, username=before.Username, rol_id=before.RolID, activo=before.Activo),
                    datos_despues={'activo': not bool(before.Activo)}, ip=request.remote_addr)
        audit(cursor, current_user.id, 'CAMBIAR_ACCESO', 'Usuarios', user_id, {}, request.remote_addr)
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Estado de usuario actualizado'})
    except Exception as e:
        conn.rollback()
        if _is_last_superadmin_error(e):
            return jsonify({'error': LAST_SUPERADMIN_ERROR_MSG}), 400
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


@admin_bp.route('/configuracion')
@login_required
@roles_required('Admin', 'SuperAdmin')
def configuracion():
    """Panel de Configuración del Sistema."""
    conn = get_db_connection()
    cursor = conn.cursor()

    execute_sp(
        cursor,
        'seguridad.sp_ObtenerConfiguracionSistema',
        (None,),
        fallback_sql="SELECT Clave, Valor, Descripcion FROM ConfiguracionSistema ORDER BY Clave",
        fallback_params=(),
    )
    config_rows = cursor.fetchall()
    config = {row.Clave: {'valor': row.Valor, 'descripcion': row.Descripcion} for row in config_rows}

    execute_sp(
        cursor,
        'seguridad.sp_ListarUsuariosTOTP',
        fallback_sql=(
            "SELECT u.ID, u.NombreCompleto, u.Username, r.Nombre AS Rol, u.TOTPEnabled "
            "FROM Usuarios u JOIN Roles r ON u.RolID = r.ID "
            "WHERE u.Activo = 1 ORDER BY u.NombreCompleto"
        ),
    )
    usuarios_totp = [
        {'id': row.ID, 'nombre': row.NombreCompleto, 'username': row.Username,
         'rol': row.Rol, 'totp_enabled': bool(row.TOTPEnabled)}
        for row in cursor.fetchall()
    ]

    conn.close()
    return render_template('admin/configuracion.html', user=current_user, config=config, usuarios_totp=usuarios_totp)


@admin_bp.route('/auditoria')
@login_required
@roles_required('SuperAdmin')
def auditoria():
    """Panel de solo lectura para revisar cambios auditados vía SP."""
    desde = request.args.get('desde') or None
    hasta = request.args.get('hasta') or None
    entidad = (request.args.get('entidad') or '').strip() or None
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'seguridad.sp_ListarAuditoria',
            (desde, hasta, entidad),
            fallback_sql=(
                "SELECT TOP 500 a.ID, a.FechaHora, a.Accion, a.Entidad, a.EntidadID, "
                "a.DatosAntes, a.DatosDespues, a.IP, u.NombreCompleto "
                "FROM AuditLog a LEFT JOIN Usuarios u ON u.ID=a.UsuarioID "
                "WHERE (? IS NULL OR a.FechaHora >= ?) "
                "AND (? IS NULL OR a.FechaHora < DATEADD(DAY, 1, ?)) "
                "AND (? IS NULL OR a.Entidad = ?) ORDER BY a.FechaHora DESC"
            ),
            fallback_params=(desde, desde, hasta, hasta, entidad, entidad),
        )
        eventos = [{
            'id': row.ID, 'fecha': row.FechaHora.strftime('%d/%m/%Y %H:%M:%S'),
            'accion': row.Accion, 'entidad': row.Entidad, 'entidad_id': row.EntidadID,
            'antes': row.DatosAntes, 'despues': row.DatosDespues,
            'ip': row.IP or '', 'usuario': row.NombreCompleto or 'Sistema'
        } for row in cursor.fetchall()]
        return render_template('admin/auditoria.html', eventos=eventos, desde=desde or '', hasta=hasta or '', entidad=entidad or '')
    finally:
        conn.close()


@admin_bp.route('/api/seguridad/bitacora-errores', methods=['GET'])
@login_required
@roles_required('SuperAdmin')
def api_bitacora_errores():
    """Consulta la bitácora de errores de BD y alertas SMTP mediante SP."""
    severidad = (request.args.get('severidad') or '').strip() or None
    origen = (request.args.get('origen') or '').strip() or None
    solo_no_notificados = 1 if request.args.get('pendientes') in ('1', 'true') else 0

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        execute_sp(
            cursor,
            'seguridad.sp_ListarBitacoraErrores',
            (200, severidad, origen, solo_no_notificados),
        )
        errores = [
            {
                'id': r.ID,
                'fecha_hora': r.FechaHora.strftime('%d/%m/%Y %H:%M:%S') if r.FechaHora else '',
                'origen': r.Origen,
                'severidad': r.Severidad,
                'numero_error': r.NumeroError,
                'linea_error': r.LineaError,
                'procedimiento': r.Procedimiento or '',
                'esquema': r.EsquemaOrigen or '',
                'mensaje': r.MensajeError,
                'usuario': r.Username or '',
                'rol': r.RolAplicacion or '',
                'usuario_bd': r.UsuarioBD or '',
                'ip': r.DireccionIP or '',
                'ruta_http': r.RutaHTTP or '',
                'notificado_smtp': bool(r.NotificadoSMTP),
                'fecha_notificacion': r.FechaNotificacion.strftime('%d/%m/%Y %H:%M:%S') if r.FechaNotificacion else None,
            }
            for r in cursor.fetchall()
        ]
        return jsonify({'status': 'success', 'success': True, 'errores': errores})
    finally:
        conn.close()


@admin_bp.route('/api/seguridad/smtp-test', methods=['POST'])
@login_required
@roles_required('SuperAdmin')
def api_smtp_test():
    """Envía un correo de prueba SMTP y registra el evento en seguridad.BitacoraErrores."""
    from app.services.smtp_alerts import notify_error, reset_rate_limit_cache
    datos = request.get_json(silent=True) or {}
    raw_dest = datos.get('destinatarios') if datos.get('destinatarios') is not None else datos.get('destinatario')
    if isinstance(raw_dest, (list, tuple)):
        override = [str(r).strip() for r in raw_dest if str(r).strip()] or None
    else:
        dest_str = (str(raw_dest or '')).strip()
        override = [r.strip() for r in dest_str.split(',') if r.strip()] if dest_str else None
    mensaje = (datos.get('mensaje') or '').strip() or "Prueba manual de notificación de seguridad y errores por correo SMTP."

    reset_rate_limit_cache()
    resultado = notify_error(
        mensaje,
        origen='SEGURIDAD_AUTH',
        severidad='INFO',
        numero_error=50000,
        estado_error=1,
        linea_error=1,
        procedimiento='seguridad.sp_PruebaAlertaSMTP',
        esquema_origen='seguridad',
        detalle_tecnico=f"Disparado manualmente por {current_user.username} ({current_user.rol_nombre}).",
        async_send=False,
        force_send=True,
        override_recipients=override,
    )
    return jsonify({
        'status': 'success',
        'success': True,
        'error_id': resultado.get('error_id'),
        'smtp_enviado': bool(resultado.get('sent')),
        'rate_limited': bool(resultado.get('rate_limited')),
        'resultado': resultado,
    })


@admin_bp.route('/api/configuracion', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def guardar_configuracion():
    """API para guardar configuraciones del sistema."""
    datos = request.json
    if not datos:
        return jsonify({'error': 'No se recibieron datos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if any(str(k).startswith('fiscal_') for k in datos):
            return jsonify(error='Use el módulo Fiscal para cambiar datos tributarios.'), 400
        for clave, valor in datos.items():
            if clave == 'tipo_cambio_usd':
                valor = str(amount(valor, 'Tipo de cambio', minimum=0.01, maximum=999999))
            elif clave == 'telefono_negocio' and valor:
                valor = str(validate_telefono_nicaragua(valor, 'Teléfono de negocio', optional=True) or '')
            execute_sp(
                cursor,
                'seguridad.sp_GuardarConfiguracionSistema',
                (clave, str(valor)),
                fallback_sql="UPDATE ConfiguracionSistema SET Valor = ? WHERE Clave = ?",
                fallback_params=(str(valor), clave),
            )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Configuración guardada'})
    except ValueError as e:
        conn.rollback()
        return jsonify(error=str(e)), 400
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()


@admin_bp.route('/api/usuarios/<int:user_id>/reset_totp', methods=['POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def reset_totp_usuario(user_id):
    """API para desactivar el TOTP de un usuario (en caso de pérdida del dispositivo)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if not puede_administrar_usuario(cursor, user_id):
            return jsonify(error='Usuario inexistente o sin permiso para administrarlo.'), 403
        execute_sp(
            cursor,
            'seguridad.sp_RestablecerTOTPUsuario',
            (user_id,),
            fallback_sql="UPDATE Usuarios SET TOTPSecret = NULL, TOTPEnabled = 0 WHERE ID = ?",
        )
        audit(cursor, current_user.id, 'RESTABLECER_TOTP', 'Usuarios', user_id, {}, request.remote_addr)
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'TOTP desactivado para el usuario'})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()
