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

# ============================================================
# MÓDULO DE CONFIGURACIÓN
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# ============================================================
# MÓDULO DE INVENTARIO Y MATERIA PRIMA
# ============================================================

@admin_bp.route('/inventario')
@login_required
@roles_required('Admin', 'SuperAdmin')
def inventario():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Materia Prima
    cursor.execute(
        "SELECT m.ID, m.Nombre, u.Nombre AS Unidad, m.StockActual, m.StockMinimo "
        "FROM MateriaPrima m JOIN UnidadesMedida u ON m.UnidadMedidaID = u.ID "
        "ORDER BY m.Nombre"
    )
    materias = [{'id': r.ID, 'nombre': r.Nombre, 'unidad': r.Unidad, 'stock': float(r.StockActual), 'minimo': float(r.StockMinimo)} for r in cursor.fetchall()]

    # Proveedores
    cursor.execute("SELECT ID, Nombre, Telefono FROM Proveedores WHERE Activo = 1 ORDER BY Nombre")
    proveedores = [{'id': r.ID, 'nombre': r.Nombre, 'telefono': r.Telefono or ''} for r in cursor.fetchall()]

    # Unidades de Medida
    cursor.execute("SELECT ID, Nombre, Abreviatura FROM UnidadesMedida ORDER BY Nombre")
    unidades = [{'id': r.ID, 'nombre': r.Nombre, 'abreviatura': r.Abreviatura} for r in cursor.fetchall()]

    # Historial de Compras (Últimas 50)
    cursor.execute(
        "SELECT TOP 50 c.ID, m.Nombre AS Materia, p.Nombre AS Proveedor, c.Cantidad, c.CostoTotal, c.Fecha "
        "FROM ComprasMateriaPrima c "
        "JOIN MateriaPrima m ON c.MateriaPrimaID = m.ID "
        "JOIN Proveedores p ON c.ProveedorID = p.ID "
        "ORDER BY c.Fecha DESC"
    )
    compras = [{'id': r.ID, 'materia': r.Materia, 'proveedor': r.Proveedor, 'cantidad': float(r.Cantidad), 'costo': float(r.CostoTotal), 'fecha': r.Fecha.strftime('%d/%m/%Y %H:%M')} for r in cursor.fetchall()]

    conn.close()
    return render_template('admin/inventario.html', user=current_user, materias=materias, proveedores=proveedores, unidades=unidades, compras=compras)


@admin_bp.route('/api/inventario/materia_prima', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_materia_prima():
    datos = request.json
    if not datos.get('nombre') or not datos.get('unidad_id') or not datos.get('stock_minimo'):
        return jsonify({'error': 'Faltan datos requeridos'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO MateriaPrima (Nombre, UnidadMedidaID, StockMinimo, StockActual) VALUES (?, ?, ?, 0.0)",
            datos.get('nombre'), int(datos.get('unidad_id')), float(datos.get('stock_minimo'))
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Materia prima creada con éxito'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/inventario/proveedor', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_proveedor():
    datos = request.json
    if not datos.get('nombre'):
        return jsonify({'error': 'Faltan datos requeridos'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO Proveedores (Nombre, Telefono) VALUES (?, ?)",
            datos.get('nombre'), datos.get('telefono', '')
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Proveedor creado con éxito'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/inventario/compra', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def registrar_compra():
    datos = request.json
    if not all([datos.get('materia_id'), datos.get('proveedor_id'), datos.get('cantidad'), datos.get('costo')]):
        return jsonify({'error': 'Faltan datos requeridos'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Registrar compra
        cursor.execute(
            "INSERT INTO ComprasMateriaPrima (MateriaPrimaID, ProveedorID, Cantidad, CostoTotal) VALUES (?, ?, ?, ?)",
            int(datos.get('materia_id')), int(datos.get('proveedor_id')), float(datos.get('cantidad')), float(datos.get('costo'))
        )
        # Sumar stock
        cursor.execute(
            "UPDATE MateriaPrima SET StockActual = StockActual + ? WHERE ID = ?",
            float(datos.get('cantidad')), int(datos.get('materia_id'))
        )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Compra registrada y stock actualizado'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


# ============================================================
# MÓDULO DE PRODUCCIÓN Y RECETAS
# ============================================================

@admin_bp.route('/produccion')
@login_required
@roles_required('Admin', 'SuperAdmin')
def produccion():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Productos
    cursor.execute("SELECT ID, Nombre FROM Productos WHERE Activo = 1 ORDER BY Nombre")
    productos = [{'id': r.ID, 'nombre': r.Nombre} for r in cursor.fetchall()]

    # Materias Primas para agregar a receta
    cursor.execute(
        "SELECT m.ID, m.Nombre, u.Abreviatura "
        "FROM MateriaPrima m JOIN UnidadesMedida u ON m.UnidadMedidaID = u.ID "
        "ORDER BY m.Nombre"
    )
    materias = [{'id': r.ID, 'nombre': f"{r.Nombre} ({r.Abreviatura})" } for r in cursor.fetchall()]

    # Recetas agrupadadas por producto
    cursor.execute(
        "SELECT r.ID, p.Nombre AS Producto, m.Nombre AS Materia, r.CantidadNecesaria, u.Abreviatura "
        "FROM RecetaProducto r "
        "JOIN Productos p ON r.ProductoID = p.ID "
        "JOIN MateriaPrima m ON r.MateriaPrimaID = m.ID "
        "JOIN UnidadesMedida u ON m.UnidadMedidaID = u.ID "
        "ORDER BY p.Nombre, m.Nombre"
    )
    recetas_raw = cursor.fetchall()
    recetas_agrupadas = {}
    for r in recetas_raw:
        if r.Producto not in recetas_agrupadas:
            recetas_agrupadas[r.Producto] = []
        recetas_agrupadas[r.Producto].append({'id': r.ID, 'materia': r.Materia, 'cantidad': float(r.CantidadNecesaria), 'abreviatura': r.Abreviatura})

    # Historial de Producción (Últimos 50 lotes)
    cursor.execute(
        "SELECT TOP 50 pl.ID, p.Nombre AS Producto, pl.CantidadProducida, pl.Fecha "
        "FROM ProduccionLotes pl "
        "JOIN Productos p ON pl.ProductoID = p.ID "
        "ORDER BY pl.Fecha DESC"
    )
    lotes = [{'id': r.ID, 'producto': r.Producto, 'cantidad': r.CantidadProducida, 'fecha': r.Fecha.strftime('%d/%m/%Y %H:%M')} for r in cursor.fetchall()]

    conn.close()
    return render_template('admin/produccion.html', user=current_user, productos=productos, materias=materias, recetas_agrupadas=recetas_agrupadas, lotes=lotes)


@admin_bp.route('/api/produccion/receta', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def crear_receta():
    datos = request.json
    if not all([datos.get('producto_id'), datos.get('materia_id'), datos.get('cantidad')]):
        return jsonify({'error': 'Faltan datos requeridos'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Verificar si ya existe para actualizar o insertar
        cursor.execute("SELECT ID FROM RecetaProducto WHERE ProductoID = ? AND MateriaPrimaID = ?", int(datos.get('producto_id')), int(datos.get('materia_id')))
        existente = cursor.fetchone()
        
        if existente:
            cursor.execute("UPDATE RecetaProducto SET CantidadNecesaria = ? WHERE ID = ?", float(datos.get('cantidad')), existente.ID)
        else:
            cursor.execute(
                "INSERT INTO RecetaProducto (ProductoID, MateriaPrimaID, CantidadNecesaria) VALUES (?, ?, ?)",
                int(datos.get('producto_id')), int(datos.get('materia_id')), float(datos.get('cantidad'))
            )
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Receta actualizada con éxito'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/produccion/receta/<int:receta_id>/delete', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def eliminar_receta(receta_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM RecetaProducto WHERE ID = ?", receta_id)
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': 'Ingrediente removido de la receta'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/produccion/lote', methods=['POST'])
@csrf.exempt
@login_required
@roles_required('Admin', 'SuperAdmin')
def registrar_lote():
    datos = request.json
    producto_id = datos.get('producto_id')
    cantidad = datos.get('cantidad')
    
    if not producto_id or not cantidad or int(cantidad) <= 0:
        return jsonify({'error': 'Datos inválidos'}), 400
        
    cantidad = int(cantidad)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Obtener receta
        cursor.execute("SELECT MateriaPrimaID, CantidadNecesaria FROM RecetaProducto WHERE ProductoID = ?", int(producto_id))
        receta = cursor.fetchall()
        
        if not receta:
            return jsonify({'error': 'El producto no tiene receta definida. Imposible producir sin receta.'}), 400
            
        # Verificar stock
        materiales_requeridos = []
        for r in receta:
            req_qty = float(r.CantidadNecesaria) * cantidad
            cursor.execute("SELECT Nombre, StockActual FROM MateriaPrima WHERE ID = ?", r.MateriaPrimaID)
            mat = cursor.fetchone()
            if mat.StockActual < req_qty:
                return jsonify({'error': f'Stock insuficiente de {mat.Nombre}. Se requieren {req_qty} y hay {mat.StockActual}.'}), 400
            materiales_requeridos.append((r.MateriaPrimaID, req_qty))
            
        # Todo bien, insertar lote
        cursor.execute("INSERT INTO ProduccionLotes (ProductoID, CantidadProducida) OUTPUT INSERTED.ID VALUES (?, ?)", int(producto_id), cantidad)
        lote_id = cursor.fetchone().ID
        
        # Descontar stock e insertar consumo
        for mat_id, req_qty in materiales_requeridos:
            cursor.execute("UPDATE MateriaPrima SET StockActual = StockActual - ? WHERE ID = ?", req_qty, mat_id)
            cursor.execute("INSERT INTO ConsumoLote (LoteID, MateriaPrimaID, CantidadUsada) VALUES (?, ?, ?)", lote_id, mat_id, req_qty)
            
        conn.commit()
        return jsonify({'status': 'success', 'mensaje': f'Lote producido con éxito. Se crearon {cantidad} unidades.'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# ============================================================
# MÓDULO DE FIDELIZACIÓN (CRM)
# ============================================================

@admin_bp.route('/fidelizacion')
@login_required
@roles_required('Admin', 'SuperAdmin')
def fidelizacion():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Métricas Globales
    cursor.execute("SELECT COUNT(ID) FROM Clientes WHERE ID > 1")
    total_clientes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(ID) FROM Clientes WHERE NivelConfianzaID = 3")
    total_vip = cursor.fetchone()[0]
    
    porcentaje_vip = int((total_vip / total_clientes * 100)) if total_clientes > 0 else 0

    # Promedio de ventas por nivel
    cursor.execute(
        "SELECT nc.Nombre, ISNULL(AVG(f.Total), 0) AS Promedio "
        "FROM Facturas f "
        "JOIN Clientes c ON f.ClienteID = c.ID "
        "JOIN NivelesConfianza nc ON c.NivelConfianzaID = nc.ID "
        "GROUP BY nc.Nombre"
    )
    promedios_nivel = {r.Nombre: float(r.Promedio) for r in cursor.fetchall()}

    # Listado de clientes con gasto total
    cursor.execute(
        "SELECT c.ID, c.Nombre, c.Telefono, c.TotalCompras, nc.Nombre AS Nivel, "
        "ISNULL(SUM(f.Total), 0) AS TotalGastado, MAX(f.FechaHora) AS UltimaCompra "
        "FROM Clientes c "
        "JOIN NivelesConfianza nc ON c.NivelConfianzaID = nc.ID "
        "LEFT JOIN Facturas f ON f.ClienteID = c.ID "
        "WHERE c.ID > 1 "
        "GROUP BY c.ID, c.Nombre, c.Telefono, c.TotalCompras, nc.Nombre "
        "ORDER BY c.TotalCompras DESC"
    )
    clientes = [{
        'id': r.ID,
        'nombre': r.Nombre,
        'telefono': r.Telefono or 'No registrado',
        'total_compras': r.TotalCompras,
        'nivel': r.Nivel,
        'total_gastado': float(r.TotalGastado),
        'ultima_compra': r.UltimaCompra.strftime('%d/%m/%Y') if r.UltimaCompra else 'N/A'
    } for r in cursor.fetchall()]

    conn.close()
    
    metricas = {
        'total_clientes': total_clientes,
        'porcentaje_vip': porcentaje_vip,
        'promedios_nivel': promedios_nivel
    }

    return render_template('admin/fidelizacion.html', user=current_user, clientes=clientes, metricas=metricas)
