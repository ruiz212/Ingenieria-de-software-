# app/auth/routes.py
# Rutas de autenticación: Login y Logout

from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import os

from app.auth import auth_bp
from app.models import User, Cliente
from app.db import get_db_connection


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Pantalla de inicio de sesión."""
    if current_user.is_authenticated:
        return redirect(url_for('hub.main_hub'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user, password_hash = User.get_by_username(username)

        if user and check_password_hash(password_hash, password):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('hub.main_hub'))
        else:
            flash("Usuario o contraseña incorrectos", "error")

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Cierra la sesión del usuario activo."""
    es_cliente = getattr(current_user, 'rol_nombre', '') in ['Cliente', 'Invitado']
    logout_user()
    if es_cliente:
        return redirect(url_for('auth.cliente_bienvenida'))
    return redirect(url_for('auth.login'))

@auth_bp.route('/cliente/bienvenida')
def cliente_bienvenida():
    """Pantalla inicial para clientes."""
    if current_user.is_authenticated:
        if getattr(current_user, 'rol_nombre', None) in ['Cliente', 'Invitado']:
            return redirect('/pos')
        return redirect(url_for('hub.main_hub'))
    return render_template('cliente_bienvenida.html')

@auth_bp.route('/cliente/login', methods=['GET', 'POST'])
def cliente_login():
    """Pantalla de inicio de sesión para clientes."""
    if current_user.is_authenticated:
        return redirect('/pos')

    if request.method == 'POST':
        telefono = request.form.get('telefono')
        password = request.form.get('password')

        cliente, password_hash = Cliente.get_by_telefono(telefono)
        
        if cliente and password_hash and check_password_hash(password_hash, password):
            login_user(cliente, remember=True)
            return redirect('/pos')
        else:
            flash("Teléfono o contraseña incorrectos", "error")

    return render_template('cliente_login.html')

@auth_bp.route('/cliente/registro', methods=['GET', 'POST'])
def cliente_registro():
    """Formulario de registro para nuevos clientes."""
    if current_user.is_authenticated:
        return redirect('/pos')

    if request.method == 'POST':
        nombre = request.form.get('nombre')
        apellidos = request.form.get('apellidos')
        telefono = request.form.get('telefono')
        password = request.form.get('password')
        genero = request.form.get('genero')
        fecha_nacimiento = request.form.get('fecha_nacimiento')
        
        foto = request.files.get('foto')
        ruta_foto = None

        # Verificar si el teléfono ya está registrado
        existente, _ = Cliente.get_by_telefono(telefono)
        if existente:
            flash("El teléfono ya está registrado.", "error")
            return redirect(url_for('auth.cliente_registro'))

        # Manejo de la foto de perfil
        if foto and foto.filename != '':
            filename = secure_filename(foto.filename)
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'perfiles')
            os.makedirs(upload_folder, exist_ok=True)
            
            # Guardamos la ruta relativa para usarla en templates
            ruta_foto = os.path.join('uploads', 'perfiles', filename).replace('\\', '/')
            foto.save(os.path.join(upload_folder, filename))

        hashed_pwd = generate_password_hash(password)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Clientes (Nombre, Apellidos, Telefono, PasswordHash, Genero, 
                                  FechaNacimiento, RutaFotoPerfil, EsInvitado, NivelConfianzaID)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 1)
            """,
            nombre, apellidos, telefono, hashed_pwd, genero, 
            fecha_nacimiento if fecha_nacimiento else None, ruta_foto
        )
        conn.commit()
        conn.close()
        
        # Iniciar sesión automáticamente
        cliente_nuevo, _ = Cliente.get_by_telefono(telefono)
        if cliente_nuevo:
            login_user(cliente_nuevo)
            
        return redirect(url_for('auth.cliente_inicio_exitoso'))
        
    return render_template('cliente_registro.html')

@auth_bp.route('/cliente/inicio_exitoso')
@login_required
def cliente_inicio_exitoso():
    """Pantalla temporal de bienvenida tras crear cuenta."""
    return render_template('cliente_inicio_exitoso.html')

@auth_bp.route('/cliente/invitado')
def cliente_invitado():
    """Inicia sesión con el perfil de cliente invitado por defecto (ID=1)."""
    if current_user.is_authenticated:
        return redirect('/pos')
        
    cliente_invitado = Cliente.get_by_id(1)
    if cliente_invitado:
        login_user(cliente_invitado)
        return redirect('/pos')
    else:
        flash("No se pudo iniciar sesión como invitado.", "error")
        return redirect(url_for('auth.cliente_bienvenida'))
