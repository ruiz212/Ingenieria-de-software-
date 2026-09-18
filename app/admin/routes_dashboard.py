# app/admin/routes_dashboard.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback

from app.admin import admin_bp
from app.db import get_db_connection
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime

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



@admin_bp.route('/estadistica')
@login_required
@roles_required('Admin', 'SuperAdmin')
def estadistica():
    """Módulo de Reportes Analíticos y Estadísticas."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Ventas por hora del día (horas pico)
    cursor.execute("""
        SELECT DATEPART(HOUR, FechaHora) AS Hora, COUNT(*) AS Cantidad, ISNULL(SUM(Total), 0) AS Total
        FROM Facturas
        WHERE FechaHora >= DATEADD(DAY, -30, GETDATE())
        GROUP BY DATEPART(HOUR, FechaHora)
        ORDER BY Hora
    """)
    ventas_por_hora = [{'hora': r.Hora, 'cantidad': r.Cantidad, 'total': float(r.Total)} for r in cursor.fetchall()]

    # 2. Ventas últimos 30 días
    cursor.execute("""
        SELECT CONVERT(date, FechaHora) AS Dia, COUNT(*) AS Cantidad, ISNULL(SUM(Total), 0) AS Total
        FROM Facturas
        WHERE FechaHora >= DATEADD(DAY, -30, GETDATE())
        GROUP BY CONVERT(date, FechaHora)
        ORDER BY Dia
    """)
    ventas_diarias = [{'dia': r.Dia.strftime('%Y-%m-%d'), 'cantidad': r.Cantidad, 'total': float(r.Total)} for r in cursor.fetchall()]

    # 3. Rotación de productos (más y menos vendidos en 30 días)
    cursor.execute("""
        SELECT TOP 15 p.Nombre, SUM(df.Cantidad) AS Vendidos, SUM(df.Subtotal) AS Ingresos
        FROM DetalleFacturas df
        JOIN Productos p ON df.ProductoID = p.ID
        JOIN Facturas f ON df.FacturaID = f.ID
        WHERE f.FechaHora >= DATEADD(DAY, -30, GETDATE())
        GROUP BY p.Nombre
        ORDER BY Vendidos DESC
    """)
    rotacion_productos = [{'nombre': r.Nombre, 'vendidos': r.Vendidos, 'ingresos': float(r.Ingresos)} for r in cursor.fetchall()]

    # 4. Mermas del mes
    cursor.execute("""
        SELECT p.Nombre, m.Motivo, SUM(m.Cantidad) AS Total
        FROM Mermas m
        JOIN Productos p ON m.ProductoID = p.ID
        WHERE m.Fecha >= DATEADD(DAY, -30, GETDATE())
        GROUP BY p.Nombre, m.Motivo
        ORDER BY Total DESC
    """)
    mermas_mes = [{'producto': r.Nombre, 'motivo': r.Motivo, 'total': r.Total} for r in cursor.fetchall()]

    # 5. Clientes por nivel
    cursor.execute("""
        SELECT nc.Nombre AS Nivel, COUNT(c.ID) AS Cantidad
        FROM Clientes c
        JOIN NivelesConfianza nc ON c.NivelConfianzaID = nc.ID
        WHERE c.ID > 1
        GROUP BY nc.Nombre
    """)
    clientes_nivel = [{'nivel': r.Nivel, 'cantidad': r.Cantidad} for r in cursor.fetchall()]

    # 6. Rendimiento de lotes (últimos lotes con varianza)
    cursor.execute("""
        SELECT TOP 20 pl.ID, p.Nombre AS Producto, pl.CantidadProducida, pl.CantidadEsperada, pl.Fecha
        FROM ProduccionLotes pl
        JOIN Productos p ON pl.ProductoID = p.ID
        WHERE pl.CantidadEsperada IS NOT NULL
        ORDER BY pl.Fecha DESC
    """)
    rendimiento_lotes = []
    for r in cursor.fetchall():
        varianza = ((r.CantidadProducida - r.CantidadEsperada) / r.CantidadEsperada * 100) if r.CantidadEsperada > 0 else 0
        rendimiento_lotes.append({
            'id': r.ID, 'producto': r.Producto,
            'producido': r.CantidadProducida, 'esperado': r.CantidadEsperada,
            'varianza': round(varianza, 2),
            'alerta': abs(varianza) > 5,
            'fecha': r.Fecha.strftime('%d/%m/%Y')
        })

    # 7. Arqueos recientes
    cursor.execute("""
        SELECT TOP 10 a.ID, u.NombreCompleto, a.EfectivoContado, a.EfectivoSistema,
               a.DiferenciaEfectivo, a.DiferenciaTransferencias, a.FechaArqueo
        FROM ArqueoCaja a
        JOIN Usuarios u ON a.UsuarioID = u.ID
        ORDER BY a.FechaArqueo DESC
    """)
    arqueos = [{
        'usuario': r.NombreCompleto,
        'contado': float(r.EfectivoContado),
        'sistema': float(r.EfectivoSistema),
        'dif_efectivo': float(r.DiferenciaEfectivo),
        'dif_transferencias': float(r.DiferenciaTransferencias),
        'fecha': r.FechaArqueo.strftime('%d/%m/%Y %H:%M')
    } for r in cursor.fetchall()]

    conn.close()

    return render_template('admin/estadistica.html', user=current_user,
        ventas_por_hora=ventas_por_hora, ventas_diarias=ventas_diarias,
        rotacion_productos=rotacion_productos, mermas_mes=mermas_mes,
        clientes_nivel=clientes_nivel, rendimiento_lotes=rendimiento_lotes,
        arqueos=arqueos)


# ============================================================
# MÓDULO DE RECURSOS HUMANOS (Ley Nicaragua)
# ============================================================

import json
from datetime import datetime, date, timedelta


