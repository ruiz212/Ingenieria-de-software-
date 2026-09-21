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
@csrf.exempt
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

    hashed_pw = generate_password_hash(password)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO Usuarios (NombreCompleto, Username, PasswordHash, RolID, Activo) "
            "VALUES (?, ?, ?, ?, 1)",
            nombre, username, hashed_pw, int(rol_id)
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Usuario creado'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': 'El usuario ya existe o error en base de datos'}), 500
    finally:
        conn.close()



@admin_bp.route('/api/usuarios/<int:user_id>/toggle', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def toggle_usuario(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Evitar desactivarse a si mismo
        if user_id == current_user.id:
            return jsonify({'error': 'No puedes desactivar tu propio usuario'}), 400
            
        cursor.execute("UPDATE Usuarios SET Activo = 1 ^ Activo WHERE ID = ?", user_id)
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



@admin_bp.route('/api/configuracion', methods=['POST'])
@csrf.exempt
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
        for clave, valor in datos.items():
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
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def reset_totp_usuario(user_id):
    """API para desactivar el TOTP de un usuario (en caso de pérdida del dispositivo)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE Usuarios SET TOTPSecret = NULL, TOTPEnabled = 0 WHERE ID = ?", user_id)
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


