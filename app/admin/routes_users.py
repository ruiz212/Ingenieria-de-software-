# app/admin/routes_users.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback

from app.admin import admin_bp
from app.db import get_db_connection
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime
from app.services.fiscal_service import audit
from app.services.audit import registrar_auditoria
from app.services.validation import amount


def puede_administrar_usuario(cursor, user_id):
    cursor.execute('SELECT r.Nombre FROM Usuarios u JOIN Roles r ON r.ID=u.RolID WHERE u.ID=?', user_id)
    row = cursor.fetchone()
    return row and (row[0] != 'SuperAdmin' or current_user.rol_nombre == 'SuperAdmin')

@admin_bp.route('/usuarios')
@login_required
@roles_required('Admin', 'SuperAdmin')
def usuarios():
    """Gestor de Usuarios y Roles."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT ID, Nombre FROM Roles ORDER BY ID")
    roles = [{'id': row.ID, 'nombre': row.Nombre} for row in cursor.fetchall()]

    cursor.execute(
        "SELECT u.ID, u.NombreCompleto, u.Username, r.Nombre AS Rol, u.Activo "
        "FROM Usuarios u "
        "JOIN Roles r ON u.RolID = r.ID "
        "ORDER BY u.NombreCompleto"
    )
    usuarios = [
        {'id': row.ID, 'nombre': row.NombreCompleto, 'username': row.Username,
         'rol': row.Rol, 'activo': bool(row.Activo)}
        for row in cursor.fetchall()
    ]
    conn.close()
    return render_template('admin/usuarios.html', user=current_user, usuarios=usuarios, roles=roles)



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
        return jsonify(error='Use una contraseña de al menos 12 caracteres.'),400
    hashed_pw = generate_password_hash(password)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT Nombre FROM Roles WHERE ID=?', int(rol_id))
        role = cursor.fetchone()
        if not role:
            return jsonify(error='Rol inexistente.'),400
        if role[0] == 'SuperAdmin' and current_user.rol_nombre != 'SuperAdmin':
            return jsonify(error='Solo SuperAdmin puede asignar ese rol.'),403
        cursor.execute(
            "INSERT INTO Usuarios (NombreCompleto, Username, PasswordHash, RolID, Activo) "
            "OUTPUT INSERTED.ID VALUES (?, ?, ?, ?, 1)",
            nombre, username, hashed_pw, int(rol_id)
        )
        new_id = cursor.fetchone()[0]
        registrar_auditoria(cursor, current_user.id, 'CREAR', 'Usuarios', new_id,
                            datos_despues={'username': username, 'rol': role[0]}, ip=request.remote_addr)
        audit(cursor,current_user.id,'CREAR_USUARIO','Usuarios',None,{'username':username,'rol':role[0]},request.remote_addr)
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Usuario creado'})
    except Exception as e:
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
        # Evitar desactivarse a si mismo
        if user_id == current_user.id:
            return jsonify({'error': 'No puedes desactivar tu propio usuario'}), 400
        if not puede_administrar_usuario(cursor, user_id):
            return jsonify(error='Usuario inexistente o sin permiso para administrarlo.'),403
            
        cursor.execute("SELECT NombreCompleto, Username, RolID, Activo FROM Usuarios WHERE ID=?", user_id)
        before = cursor.fetchone()
        cursor.execute("UPDATE Usuarios SET Activo = 1 ^ Activo WHERE ID = ?", user_id)
        registrar_auditoria(cursor, current_user.id, 'CAMBIAR_ESTADO', 'Usuarios', user_id,
                    datos_antes=dict(nombre=before.NombreCompleto, username=before.Username, rol_id=before.RolID, activo=before.Activo),
                    datos_despues={'activo': not bool(before.Activo)}, ip=request.remote_addr)
        audit(cursor,current_user.id,'CAMBIAR_ACCESO','Usuarios',user_id,{},request.remote_addr)
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Estado de usuario actualizado'})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()

# ============================================================
# MÓDULO DE CONTABILIDAD
# ============================================================


@admin_bp.route('/configuracion')
@login_required
@roles_required('Admin', 'SuperAdmin')
def configuracion():
    """Panel de Configuración del Sistema."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Leer todas las configuraciones
    cursor.execute("SELECT Clave, Valor, Descripcion FROM ConfiguracionSistema ORDER BY Clave")
    config_rows = cursor.fetchall()
    config = {row.Clave: {'valor': row.Valor, 'descripcion': row.Descripcion} for row in config_rows}

    # Usuarios y su estado TOTP
    cursor.execute(
        "SELECT u.ID, u.NombreCompleto, u.Username, r.Nombre AS Rol, u.TOTPEnabled "
        "FROM Usuarios u JOIN Roles r ON u.RolID = r.ID "
        "WHERE u.Activo = 1 ORDER BY u.NombreCompleto"
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
    """Panel de solo lectura para revisar cambios auditados."""
    desde = request.args.get('desde') or None
    hasta = request.args.get('hasta') or None
    entidad = (request.args.get('entidad') or '').strip() or None
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT TOP 500 a.ID, a.FechaHora, a.Accion, a.Entidad, a.EntidadID, "
            "a.DatosAntes, a.DatosDespues, a.IP, u.NombreCompleto "
            "FROM AuditLog a LEFT JOIN Usuarios u ON u.ID=a.UsuarioID "
            "WHERE (? IS NULL OR a.FechaHora >= ?) "
            "AND (? IS NULL OR a.FechaHora < DATEADD(DAY, 1, ?)) "
            "AND (? IS NULL OR a.Entidad = ?) ORDER BY a.FechaHora DESC",
            desde, desde, hasta, hasta, entidad, entidad
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
            return jsonify(error='Use el módulo Fiscal para cambiar datos tributarios.'),400
        for clave, valor in datos.items():
            if clave == 'tipo_cambio_usd':
                valor = str(amount(valor, 'Tipo de cambio', minimum=0.01, maximum=999999))
            cursor.execute(
                "UPDATE ConfiguracionSistema SET Valor = ? WHERE Clave = ?",
                str(valor), clave
            )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Configuración guardada'})
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
            return jsonify(error='Usuario inexistente o sin permiso para administrarlo.'),403
        cursor.execute("UPDATE Usuarios SET TOTPSecret = NULL, TOTPEnabled = 0 WHERE ID = ?", user_id)
        audit(cursor,current_user.id,'RESTABLECER_TOTP','Usuarios',user_id,{},request.remote_addr)
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'TOTP desactivado para el usuario'})
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Internal server error: {e}")
        return jsonify({'error': 'Error interno del servidor al procesar la solicitud.'}), 500
    finally:
        conn.close()

# ============================================================
# MÓDULO DE INVENTARIO Y MATERIA PRIMA
# ============================================================


