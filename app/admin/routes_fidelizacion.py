# app/admin/routes_fidelizacion.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback

from app.admin import admin_bp
from app.db import get_db_connection
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime

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


# ============================================================
# MÓDULO DE ARQUEO DE CAJA v2 (Multi-Etapa)
# ============================================================


