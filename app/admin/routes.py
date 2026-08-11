# app/admin/routes.py
# Rutas del Panel de Administración (Solo Dueña)

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from app.admin import admin_bp
from app.db import get_db_connection
from app.auth.decorators import roles_required
from app.extensions import csrf


@admin_bp.route('/dashboard')
@login_required
@roles_required('Admin', 'SuperAdmin')
def dashboard():
    """Dashboard Financiero de la Panadería."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Ingresos totales del día y Ticket Promedio
    cursor.execute(
        "SELECT ISNULL(SUM(Total), 0), ISNULL(COUNT(ID), 0) FROM Facturas WHERE CONVERT(date, FechaHora) = CONVERT(date, GETDATE())"
    )
    row_ventas = cursor.fetchone()
    ventas_hoy = float(row_ventas[0])
    total_facturas = int(row_ventas[1])
    ticket_promedio = ventas_hoy / total_facturas if total_facturas > 0 else 0.0

    # 2. Tasa de Completitud de Encargos
    cursor.execute(
        "SELECT ISNULL(SUM(CASE WHEN Estado = 'Entregado' THEN 1 ELSE 0 END), 0) AS Entregados, "
        "       ISNULL(COUNT(*), 0) AS Totales "
        "FROM Encargos e JOIN Facturas f ON e.FacturaID = f.ID "
        "WHERE CONVERT(date, f.FechaHora) = CONVERT(date, GETDATE())"
    )
    row_encargos = cursor.fetchone()
    encargos_entregados = int(row_encargos.Entregados)
    encargos_totales = int(row_encargos.Totales)
    tasa_completitud = int((encargos_entregados / encargos_totales) * 100) if encargos_totales > 0 else 100
    encargos_pendientes = encargos_totales - encargos_entregados

    # 3. Productos más vendidos hoy
    cursor.execute(
        "SELECT TOP 5 p.Nombre, SUM(df.Cantidad) as Cantidad "
        "FROM DetalleFacturas df "
        "JOIN Productos p ON df.ProductoID = p.ID "
        "JOIN Facturas f ON df.FacturaID = f.ID "
        "WHERE CONVERT(date, f.FechaHora) = CONVERT(date, GETDATE()) "
        "GROUP BY p.Nombre "
        "ORDER BY Cantidad DESC"
    )
    top_productos = [{'nombre': r.Nombre, 'cantidad': r.Cantidad} for r in cursor.fetchall()]

    # 3.5 Ventas por Categoría hoy
    cursor.execute(
        "SELECT c.Nombre, SUM(df.Subtotal) as TotalGenerado "
        "FROM DetalleFacturas df "
        "JOIN Productos p ON df.ProductoID = p.ID "
        "JOIN Categorias c ON p.CategoriaID = c.ID "
        "JOIN Facturas f ON df.FacturaID = f.ID "
        "WHERE CONVERT(date, f.FechaHora) = CONVERT(date, GETDATE()) "
        "GROUP BY c.Nombre "
        "ORDER BY TotalGenerado DESC"
    )
    ventas_categoria = [{'categoria': r.Nombre, 'total': float(r.TotalGenerado)} for r in cursor.fetchall()]

    # 4. Turnos de caja activos (Arqueo)
    cursor.execute(
        "SELECT t.ID, u.NombreCompleto, t.FechaApertura "
        "FROM TurnosCaja t "
        "JOIN Usuarios u ON t.UsuarioID = u.ID "
        "WHERE t.Cerrado = 0"
    )
    turnos_activos = []
    for r in cursor.fetchall():
        turnos_activos.append({
            'id': r.ID,
            'usuario': r.NombreCompleto,
            'apertura': r.FechaApertura.strftime('%H:%M:%S')
        })

    conn.close()

    metricas = {
        'ventas_hoy': ventas_hoy,
        'ticket_promedio': ticket_promedio,
        'encargos_pendientes': encargos_pendientes,
        'tasa_completitud': tasa_completitud,
        'top_productos': top_productos,
        'ventas_categoria': ventas_categoria,
        'turnos_activos': turnos_activos
    }

    return render_template('admin/dashboard.html', user=current_user, metricas=metricas)


@admin_bp.route('/catalogo')
@login_required
@roles_required('Admin', 'SuperAdmin')
def catalogo():
    """Gestor de Catálogo y Precios."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Obtener categorías
    cursor.execute("SELECT ID, Nombre FROM Categorias ORDER BY Nombre")
    categorias = [{'id': row.ID, 'nombre': row.Nombre} for row in cursor.fetchall()]

    # Obtener productos
    cursor.execute(
        "SELECT p.ID, p.Nombre, c.Nombre AS Categoria, p.CategoriaID, p.PrecioBase, p.Activo, p.EsFicticio, p.PorcentajeDescuento "
        "FROM Productos p "
        "JOIN Categorias c ON p.CategoriaID = c.ID "
        "ORDER BY c.Nombre, p.Nombre"
    )
    productos = [
        {'id': row.ID, 'nombre': row.Nombre, 'categoria': row.Categoria, 'categoria_id': row.CategoriaID,
         'precio': float(row.PrecioBase), 'activo': bool(row.Activo), 
         'es_ficticio': bool(row.EsFicticio), 'descuento': float(row.PorcentajeDescuento)}
        for row in cursor.fetchall()
    ]

    conn.close()
    return render_template('admin/catalogo.html', user=current_user, productos=productos, categorias=categorias)


@admin_bp.route('/api/productos', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_producto():
    """API para crear un nuevo producto."""
    datos = request.json
    nombre = datos.get('nombre')
    precio = datos.get('precio')
    categoria_id = datos.get('categoria_id')
    descuento = datos.get('descuento', 0.0)

    if not nombre or not precio or not categoria_id:
        return jsonify({'error': 'Faltan datos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO Productos (Nombre, PrecioBase, CategoriaID, EsFicticio, Activo, PorcentajeDescuento) "
            "VALUES (?, ?, ?, 0, 1, ?)",
            nombre, float(precio), int(categoria_id), float(descuento)
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Producto creado con éxito'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/productos/<int:producto_id>/toggle', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def toggle_producto(producto_id):
    """API para activar/desactivar un producto."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE Productos SET Activo = 1 ^ Activo WHERE ID = ?", producto_id
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Estado actualizado'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@admin_bp.route('/api/productos/<int:producto_id>/editar', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def editar_producto(producto_id):
    """API para editar un producto existente."""
    datos = request.json
    nombre = datos.get('nombre')
    precio = datos.get('precio')
    categoria_id = datos.get('categoria_id')
    descuento = datos.get('descuento', 0.0)

    if not nombre or not precio or not categoria_id:
        return jsonify({'error': 'Faltan datos requeridos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE Productos SET Nombre = ?, PrecioBase = ?, CategoriaID = ?, PorcentajeDescuento = ? WHERE ID = ?",
            nombre, float(precio), int(categoria_id), float(descuento), producto_id
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Producto actualizado con éxito'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

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
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# ============================================================
# MÓDULO DE CONTABILIDAD
# ============================================================

@admin_bp.route('/contabilidad')
@login_required
@roles_required('Admin', 'SuperAdmin')
def contabilidad():
    """Módulo de Contabilidad Privada (Egresos y Vales)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Egresos Privados
    cursor.execute(
        "SELECT e.ID, e.Concepto, e.Monto, e.Fecha, u.NombreCompleto AS RegistradoPor "
        "FROM EgresosPrivados e "
        "JOIN Usuarios u ON e.UsuarioID = u.ID "
        "ORDER BY e.Fecha DESC"
    )
    egresos = [
        {'id': row.ID, 'concepto': row.Concepto, 'monto': float(row.Monto), 
         'fecha': row.Fecha.strftime('%d/%m/%Y %H:%M'), 'registrado_por': row.RegistradoPor}
        for row in cursor.fetchall()
    ]

    # Vales a Empleados
    cursor.execute(
        "SELECT v.ID, u.NombreCompleto AS Empleado, v.Monto, v.Fecha, v.Descontado "
        "FROM ValesEmpleados v "
        "JOIN Usuarios u ON v.EmpleadoID = u.ID "
        "ORDER BY v.Fecha DESC"
    )
    vales = [
        {'id': row.ID, 'empleado': row.Empleado, 'monto': float(row.Monto), 
         'fecha': row.Fecha.strftime('%d/%m/%Y %H:%M'), 'descontado': bool(row.Descontado)}
        for row in cursor.fetchall()
    ]

    # Lista de usuarios para el dropdown de vales
    cursor.execute("SELECT ID, NombreCompleto FROM Usuarios WHERE Activo = 1 ORDER BY NombreCompleto")
    empleados = [{'id': row.ID, 'nombre': row.NombreCompleto} for row in cursor.fetchall()]

    # Totales del MES actual
    # 1. Ingresos (Ventas)
    cursor.execute("SELECT ISNULL(SUM(Total), 0) FROM Facturas WHERE MONTH(FechaHora) = MONTH(GETDATE()) AND YEAR(FechaHora) = YEAR(GETDATE())")
    ingresos_mes = float(cursor.fetchone()[0])
    
    # 2. Compras de Materia Prima
    cursor.execute("SELECT ISNULL(SUM(CostoTotal), 0) FROM ComprasMateriaPrima WHERE MONTH(Fecha) = MONTH(GETDATE()) AND YEAR(Fecha) = YEAR(GETDATE())")
    compras_mes = float(cursor.fetchone()[0])

    # 3. Egresos Privados
    cursor.execute("SELECT ISNULL(SUM(Monto), 0) FROM EgresosPrivados WHERE MONTH(Fecha) = MONTH(GETDATE()) AND YEAR(Fecha) = YEAR(GETDATE())")
    egresos_mes = float(cursor.fetchone()[0])

    # Totales del DIA actual
    cursor.execute("SELECT ISNULL(SUM(Total), 0) FROM Facturas WHERE CONVERT(date, FechaHora) = CONVERT(date, GETDATE())")
    ingresos_hoy = float(cursor.fetchone()[0])

    cursor.execute("SELECT ISNULL(SUM(CostoTotal), 0) FROM ComprasMateriaPrima WHERE CONVERT(date, Fecha) = CONVERT(date, GETDATE())")
    compras_hoy = float(cursor.fetchone()[0])
    
    cursor.execute("SELECT ISNULL(SUM(Monto), 0) FROM EgresosPrivados WHERE CONVERT(date, Fecha) = CONVERT(date, GETDATE())")
    egresos_hoy = float(cursor.fetchone()[0])

    # Vales Pendientes
    cursor.execute("SELECT ISNULL(SUM(Monto), 0) FROM ValesEmpleados WHERE Descontado = 0")
    total_vales_pendientes = float(cursor.fetchone()[0])

    conn.close()

    metricas = {
        'ingresos_mes': ingresos_mes,
        'compras_mes': compras_mes,
        'egresos_mes': egresos_mes,
        'balance_mes': ingresos_mes - compras_mes - egresos_mes,
        'ingresos_hoy': ingresos_hoy,
        'compras_hoy': compras_hoy,
        'egresos_hoy': egresos_hoy,
        'balance_hoy': ingresos_hoy - compras_hoy - egresos_hoy,
        'total_vales_pendientes': total_vales_pendientes
    }

    return render_template('admin/contabilidad.html', user=current_user, egresos=egresos, vales=vales, empleados=empleados, metricas=metricas)

@admin_bp.route('/api/contabilidad/egresos', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_egreso():
    datos = request.json
    concepto = datos.get('concepto')
    monto = datos.get('monto')

    if not concepto or not monto:
        return jsonify({'error': 'Faltan datos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO EgresosPrivados (Concepto, Monto, UsuarioID) VALUES (?, ?, ?)",
            concepto, float(monto), current_user.id
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Egreso registrado'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@admin_bp.route('/api/contabilidad/vales', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_vale():
    datos = request.json
    empleado_id = datos.get('empleado_id')
    monto = datos.get('monto')

    if not empleado_id or not monto:
        return jsonify({'error': 'Faltan datos'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO ValesEmpleados (EmpleadoID, Monto) VALUES (?, ?)",
            int(empleado_id), float(monto)
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Vale registrado'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@admin_bp.route('/api/contabilidad/vales/<int:vale_id>/toggle', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def toggle_vale(vale_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE ValesEmpleados SET Descontado = 1 ^ Descontado WHERE ID = ?", vale_id)
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Estado de vale actualizado'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
