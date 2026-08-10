# app/auth/routes.py
# Rutas de autenticación: Login y Logout

from flask import render_template, request, redirect, url_for, flash, current_app, session, jsonify
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import os
import random
from app.extensions import csrf
from twilio.rest import Client

from app.auth import auth_bp
from app.models import User, Cliente
from app.db import get_db_connection


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Pantalla de inicio de sesión."""
    if current_user.is_authenticated:
        return redirect(url_for('hub.main_hub'))

    if request.method == 'POST':
        identificador = request.form.get('identificador')
        password = request.form.get('password')

        # 1. Intentar como Administrador / Empleado
        user, password_hash = User.get_by_username(identificador)
        if user and check_password_hash(password_hash, password):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('hub.main_hub'))

        # 2. Intentar como Cliente
        cliente, password_hash_cli = Cliente.get_by_telefono(identificador)
        if cliente and password_hash_cli and check_password_hash(password_hash_cli, password):
            login_user(cliente, remember=True)
            return redirect('/pos')

        # Si ninguno coincide
        flash("Usuario/Teléfono o contraseña incorrectos", "error")

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



@auth_bp.route('/cliente/registro', methods=['GET', 'POST'])
def cliente_registro():
    """Formulario de registro para nuevos clientes (multi-paso con SMS)."""
    if current_user.is_authenticated:
        return redirect('/pos')

    if request.method == 'POST':
        nombre = request.form.get('nombre')
        apellidos = request.form.get('apellidos')
        telefono = request.form.get('telefono')
        password = request.form.get('password')
        genero = request.form.get('genero')
        fecha_nacimiento = request.form.get('fecha_nacimiento')
        
        # Validar que el teléfono fue verificado por SMS
        if not session.get('telefono_verificado') or session.get('sms_phone') != telefono:
            flash("Debes verificar tu número de teléfono por SMS antes de registrarte.", "error")
            return redirect(url_for('auth.cliente_registro'))
        
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
        
        # Limpiar sesión tras registro exitoso
        session.pop('sms_code', None)
        session.pop('sms_phone', None)
        session.pop('telefono_verificado', None)

        # Iniciar sesión automáticamente
        cliente_nuevo, _ = Cliente.get_by_telefono(telefono)
        if cliente_nuevo:
            login_user(cliente_nuevo)
            
        return redirect(url_for('auth.cliente_inicio_exitoso'))
        
    return render_template('cliente_registro.html')

# ============================================================
# API DE VERIFICACIÓN SMS
# ============================================================

@auth_bp.route('/api/enviar_codigo_sms', methods=['POST'])
@csrf.exempt
def enviar_codigo_sms():
    data = request.json
    telefono = data.get('telefono')
    
    if not telefono:
        return jsonify({'error': 'El teléfono es requerido'}), 400
        
    existente, _ = Cliente.get_by_telefono(telefono)
    if existente:
        return jsonify({'error': 'Este teléfono ya está registrado'}), 400
        
    # Generar código de 6 dígitos
    codigo = str(random.randint(100000, 999999))
    session['sms_code'] = codigo
    session['sms_phone'] = telefono
    session['telefono_verificado'] = False
    
    try:
        account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        
        if not account_sid or not auth_token:
            print("⚠️ ADVERTENCIA: Credenciales de Twilio no encontradas. Ejecutando en modo simulado.")
            print(f"\n[{'='*40}]\n SIMULACIÓN API SMS \n Enviar a: {telefono} \n Código: {codigo} \n[{'='*40}]\n")
            return jsonify({
                'mensaje': 'Código enviado exitosamente',
                'dev_codigo': codigo
            })
            
        client = Client(account_sid, auth_token)
        
        # Enviar el SMS real a través de Twilio
        message = client.messages.create(
            to=telefono,
            from_="+17372212163",
            body=f"Tu código de verificación para Panadería Amada es: {codigo}"
        )
        print(f"✅ Twilio SMS enviado con SID: {message.sid}")
        
        return jsonify({'mensaje': 'Código enviado exitosamente'})
        
    except Exception as e:
        print(f"❌ Error al enviar SMS con Twilio: {str(e)}")
        return jsonify({'error': f'No se pudo enviar el SMS. Verifica que el número sea correcto y tenga formato internacional (ej. +505...). Detalle: {str(e)}'}), 500

@auth_bp.route('/api/verificar_codigo_sms', methods=['POST'])
@csrf.exempt
def verificar_codigo_sms():
    data = request.json
    codigo_ingresado = data.get('codigo')
    telefono = data.get('telefono')
    
    codigo_guardado = session.get('sms_code')
    telefono_guardado = session.get('sms_phone')
    
    if not codigo_ingresado or not codigo_guardado:
        return jsonify({'error': 'No hay código pendiente de verificación'}), 400
        
    if str(codigo_ingresado) == str(codigo_guardado) and str(telefono) == str(telefono_guardado):
        session['telefono_verificado'] = True
        return jsonify({'mensaje': 'Teléfono verificado correctamente'})
    else:
        return jsonify({'error': 'El código es incorrecto'}), 400


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
