# app/admin/routes_dashboard.py
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback

from app.admin import admin_bp
from app.db import get_db_connection, execute_sp
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime, date, timedelta
from app.services.business_time import business_now


def business_today() -> date:
    """Retorna la fecha operativa actual del negocio (Nicaragua)."""
    now_val = business_now()
    return now_val.date() if isinstance(now_val, datetime) else now_val


def _coerce_day(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def calcular_pronostico_ventas(historico_ventas, hoy=None) -> dict:
    """
    Calcula la serie diaria continua (rellenando días sin ventas con 0.0) hasta `hoy`
    y proyecta los próximos 7 días mediante regresión lineal sobre días calendario reales.
    """
    hoy_ni = _coerce_day(hoy) if hoy is not None else business_today()
    inicio_ventana = hoy_ni - timedelta(days=29)

    ventas_por_dia = {}
    for r in (historico_ventas or []):
        if isinstance(r, dict):
            raw_dia = r.get('Dia') or r.get('dia')
            raw_total = r.get('Total', r.get('total', 0.0))
        elif hasattr(r, 'Dia') or hasattr(r, 'Total'):
            raw_dia = getattr(r, 'Dia')
            raw_total = getattr(r, 'Total', 0.0)
        else:
            raw_dia, raw_total = r[0], r[1]
        dia = _coerce_day(raw_dia)
        if dia <= hoy_ni:
            ventas_por_dia[dia] = round(ventas_por_dia.get(dia, 0.0) + float(raw_total or 0.0), 2)

    pronostico_ventas_data = {
        'fechas': [],
        'historico': [],
        'prediccion': [],
        'fechas_iso': [],
        'prediccion_fechas_iso': [],
        'serie_diaria': [],
    }

    if not ventas_por_dia:
        return pronostico_ventas_data

    primer_dia = max(min(ventas_por_dia.keys()), inicio_ventana)
    if (hoy_ni - primer_dia).days + 1 < 3:
        primer_dia = min(min(ventas_por_dia.keys()), hoy_ni - timedelta(days=2))

    dias_calendario = []
    cursor_dia = primer_dia
    while cursor_dia <= hoy_ni:
        total_dia = round(float(ventas_por_dia.get(cursor_dia, 0.0)), 2)
        dias_calendario.append((cursor_dia, total_dia))
        cursor_dia += timedelta(days=1)

    if len(dias_calendario) < 3:
        return pronostico_ventas_data

    n = len(dias_calendario)
    sum_x = sum(range(1, n + 1))
    sum_y = sum(total for _, total in dias_calendario)
    sum_xy = sum(i * total for i, (_, total) in enumerate(dias_calendario, 1))
    sum_x2 = sum(i ** 2 for i in range(1, n + 1))

    denominador = (n * sum_x2 - sum_x ** 2)
    m = (n * sum_xy - sum_x * sum_y) / denominador if denominador != 0 else 0.0
    b = (sum_y - m * sum_x) / n

    for i, (dia_cal, total_dia) in enumerate(dias_calendario, 1):
        pronostico_ventas_data['fechas'].append(dia_cal.strftime('%d/%m'))
        pronostico_ventas_data['fechas_iso'].append(dia_cal.isoformat())
        pronostico_ventas_data['historico'].append(float(total_dia))
        pronostico_ventas_data['serie_diaria'].append({'dia': dia_cal.isoformat(), 'total': float(total_dia)})
        if i == n:
            pronostico_ventas_data['prediccion'].append(float(total_dia))
        else:
            pronostico_ventas_data['prediccion'].append(None)

    for i in range(1, 8):
        next_x = n + i
        predicted_y = max(0.0, m * next_x + b)
        next_date = hoy_ni + timedelta(days=i)
        pronostico_ventas_data['fechas'].append(next_date.strftime('%d/%m'))
        pronostico_ventas_data['fechas_iso'].append(next_date.isoformat())
        pronostico_ventas_data['prediccion_fechas_iso'].append(next_date.isoformat())
        pronostico_ventas_data['historico'].append(None)
        pronostico_ventas_data['prediccion'].append(round(predicted_y, 2))

    return pronostico_ventas_data

@admin_bp.route('/dashboard')
@login_required
@roles_required('Admin', 'SuperAdmin')
def dashboard():
    """Dashboard Financiero de la Panadería."""
    conn = get_db_connection()
    cursor = conn.cursor()
    hoy_ni = business_now().date()

    # 1. Ingresos totales del día y Ticket Promedio
    execute_sp(
        cursor,
        'ventas.sp_DashboardIngresosHoy',
        (hoy_ni,),
        fallback_sql="SELECT ISNULL(SUM(Total), 0), ISNULL(COUNT(ID), 0) FROM Facturas WHERE EstadoFiscal='Emitida' AND CONVERT(date, FechaHora) = ?",
    )
    row_ventas = cursor.fetchone()
    ventas_hoy = float(row_ventas[0])
    total_facturas = int(row_ventas[1])
    ticket_promedio = ventas_hoy / total_facturas if total_facturas > 0 else 0.0

    # 2. Carga operativa global, con el mismo alcance del monitor de cocina.
    execute_sp(
        cursor,
        'produccion.sp_DashboardEncargosResumen',
        (hoy_ni,),
        fallback_sql=(
            "SELECT COUNT(*) AS Pendientes, "
            "       ISNULL(SUM(CASE WHEN e.Estado = 'Listo' THEN 1 ELSE 0 END), 0) AS Listos, "
            "       ISNULL(SUM(CASE WHEN CONVERT(date, e.FechaEntrega) < ? THEN 1 ELSE 0 END), 0) AS Atrasados "
            "FROM Encargos e JOIN Facturas f ON e.FacturaID = f.ID "
            "WHERE (f.EstadoFiscal IS NULL OR f.EstadoFiscal != 'Anulada') "
            "AND e.Estado != 'Entregado'"
        ),
    )
    row_encargos = cursor.fetchone()
    encargos_pendientes = int(row_encargos.Pendientes)
    encargos_listos = int(row_encargos.Listos)
    encargos_atrasados = int(row_encargos.Atrasados)

    # 3. Productos más vendidos hoy
    execute_sp(
        cursor,
        'ventas.sp_DashboardTopProductosHoy',
        (hoy_ni,),
        fallback_sql=(
            "SELECT TOP 5 p.Nombre, SUM(df.Cantidad) as Cantidad "
            "FROM DetalleFacturas df "
            "JOIN Productos p ON df.ProductoID = p.ID "
            "JOIN Facturas f ON df.FacturaID = f.ID AND f.EstadoFiscal='Emitida' "
            "WHERE CONVERT(date, f.FechaHora) = ? "
            "GROUP BY p.Nombre "
            "ORDER BY Cantidad DESC"
        ),
    )
    top_productos = [{'nombre': r.Nombre, 'cantidad': r.Cantidad} for r in cursor.fetchall()]

    # 3.5 Ventas por Categoría hoy
    execute_sp(
        cursor,
        'ventas.sp_DashboardVentasCategoriaHoy',
        (hoy_ni,),
        fallback_sql=(
            "SELECT c.Nombre, SUM(df.Subtotal) as TotalGenerado "
            "FROM DetalleFacturas df "
            "JOIN Productos p ON df.ProductoID = p.ID "
            "JOIN Categorias c ON p.CategoriaID = c.ID "
            "JOIN Facturas f ON df.FacturaID = f.ID AND f.EstadoFiscal='Emitida' "
            "WHERE CONVERT(date, f.FechaHora) = ? "
            "GROUP BY c.Nombre "
            "ORDER BY TotalGenerado DESC"
        ),
    )
    ventas_categoria = [{'categoria': r.Nombre, 'total': float(r.TotalGenerado)} for r in cursor.fetchall()]

    # 4. Turnos de caja activos (Arqueo)
    execute_sp(
        cursor,
        'ventas.sp_DashboardTurnosActivos',
        fallback_sql=(
            "SELECT t.ID, u.NombreCompleto, t.FechaApertura "
            "FROM TurnosCaja t "
            "JOIN Usuarios u ON t.UsuarioID = u.ID "
            "WHERE t.Cerrado = 0"
        ),
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
        'encargos_listos': encargos_listos,
        'encargos_atrasados': encargos_atrasados,
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
    execute_sp(
        cursor,
        'ventas.sp_EstadisticaVentasPorHora',
        fallback_sql="""
        SELECT DATEPART(HOUR, FechaHora) AS Hora, COUNT(*) AS Cantidad, ISNULL(SUM(Total), 0) AS Total
        FROM Facturas
        WHERE EstadoFiscal='Emitida' AND FechaHora >= DATEADD(DAY, -30, GETDATE())
        GROUP BY DATEPART(HOUR, FechaHora)
        ORDER BY Hora
    """,
    )
    ventas_por_hora = [{'hora': r.Hora, 'cantidad': r.Cantidad, 'total': float(r.Total)} for r in cursor.fetchall()]

    # 2. Ventas últimos 30 días
    execute_sp(
        cursor,
        'ventas.sp_EstadisticaVentasDiarias30d',
        fallback_sql="""
        SELECT CONVERT(date, FechaHora) AS Dia, COUNT(*) AS Cantidad, ISNULL(SUM(Total), 0) AS Total
        FROM Facturas
        WHERE EstadoFiscal='Emitida' AND FechaHora >= DATEADD(DAY, -30, GETDATE())
        GROUP BY CONVERT(date, FechaHora)
        ORDER BY Dia
    """,
    )
    ventas_diarias = [{'dia': r.Dia.strftime('%Y-%m-%d'), 'cantidad': r.Cantidad, 'total': float(r.Total)} for r in cursor.fetchall()]

    # 3. Rotación de productos (más y menos vendidos en 30 días)
    execute_sp(
        cursor,
        'ventas.sp_EstadisticaRotacionProductos30d',
        fallback_sql="""
        SELECT TOP 15 p.Nombre, SUM(df.Cantidad) AS Vendidos, SUM(df.Subtotal) AS Ingresos
        FROM DetalleFacturas df
        JOIN Productos p ON df.ProductoID = p.ID
        JOIN Facturas f ON df.FacturaID = f.ID AND f.EstadoFiscal='Emitida'
        WHERE f.FechaHora >= DATEADD(DAY, -30, GETDATE())
        GROUP BY p.Nombre
        ORDER BY Vendidos DESC
    """,
    )
    rotacion_productos = [{'nombre': r.Nombre, 'vendidos': r.Vendidos, 'ingresos': float(r.Ingresos)} for r in cursor.fetchall()]

    # 4. Mermas del mes
    execute_sp(
        cursor,
        'produccion.sp_EstadisticaMermasMes',
        fallback_sql="""
        SELECT p.Nombre, m.Motivo, SUM(m.Cantidad) AS Total
        FROM Mermas m
        JOIN Productos p ON m.ProductoID = p.ID
        WHERE m.Fecha >= DATEADD(DAY, -30, GETDATE())
        GROUP BY p.Nombre, m.Motivo
        ORDER BY Total DESC
    """,
    )
    mermas_mes = [{'producto': r.Nombre, 'motivo': r.Motivo, 'total': r.Total} for r in cursor.fetchall()]

    # 5. Clientes por nivel
    execute_sp(
        cursor,
        'crm.sp_EstadisticaClientesPorNivel',
        fallback_sql="""
        SELECT nc.Nombre AS Nivel, COUNT(c.ID) AS Cantidad
        FROM Clientes c
        JOIN NivelesConfianza nc ON c.NivelConfianzaID = nc.ID
        WHERE c.ID > 1
        GROUP BY nc.Nombre
    """,
    )
    clientes_nivel = [{'nivel': r.Nivel, 'cantidad': r.Cantidad} for r in cursor.fetchall()]

    # 6. Rendimiento de lotes (últimos lotes con varianza)
    execute_sp(
        cursor,
        'produccion.sp_EstadisticaRendimientoLotes',
        fallback_sql="""
        SELECT TOP 20 pl.ID, p.Nombre AS Producto, pl.CantidadProducida, pl.CantidadEsperada, pl.Fecha
        FROM ProduccionLotes pl
        JOIN Productos p ON pl.ProductoID = p.ID
        WHERE pl.CantidadEsperada IS NOT NULL
        ORDER BY pl.Fecha DESC
    """,
    )
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
    execute_sp(
        cursor,
        'ventas.sp_EstadisticaArqueosRecientes',
        fallback_sql="""
        SELECT TOP 10 a.ID, u.NombreCompleto, a.EfectivoContado, a.EfectivoSistema,
               a.DiferenciaEfectivo, a.DiferenciaTransferencias, a.FechaArqueo
        FROM ArqueoCaja a
        JOIN Usuarios u ON a.UsuarioID = u.ID
        ORDER BY a.FechaArqueo DESC
    """,
    )
    arqueos = [{
        'usuario': r.NombreCompleto,
        'contado': float(r.EfectivoContado),
        'sistema': float(r.EfectivoSistema),
        'dif_efectivo': float(r.DiferenciaEfectivo),
        'dif_transferencias': float(r.DiferenciaTransferencias),
        'fecha': r.FechaArqueo.strftime('%d/%m/%Y %H:%M')
    } for r in cursor.fetchall()]

    # 8. Pronóstico de Abastecimiento (Inteligencia / Últimos 30 días)
    execute_sp(
        cursor,
        'produccion.sp_EstadisticaPronosticoAbastecimiento',
        fallback_sql="""
        SELECT 
            m.Nombre, 
            u.Abreviatura, 
            m.StockActual,
            ISNULL(SUM(cl.CantidadUsada) / 30.0, 0) AS ConsumoPromedioDiario
        FROM MateriaPrima m
        JOIN UnidadesMedida u ON m.UnidadMedidaID = u.ID
        JOIN ConsumoLote cl ON m.ID = cl.MateriaPrimaID
        JOIN ProduccionLotes pl ON cl.LoteID = pl.ID
        WHERE pl.Fecha >= DATEADD(DAY, -30, GETDATE())
        GROUP BY m.ID, m.Nombre, u.Abreviatura, m.StockActual
        HAVING ISNULL(SUM(cl.CantidadUsada), 0) > 0
    """,
    )
    pronostico = []
    for r in cursor.fetchall():
        consumo_diario = float(r.ConsumoPromedioDiario)
        stock = float(r.StockActual)
        dias_restantes = int(stock / consumo_diario) if consumo_diario > 0 else 999
        pronostico.append({
            'nombre': r.Nombre,
            'stock': f"{stock:.2f} {r.Abreviatura}",
            'consumo_diario': f"{consumo_diario:.2f} {r.Abreviatura}",
            'dias_restantes': dias_restantes,
            'alerta': dias_restantes <= 7
        })
    pronostico.sort(key=lambda x: x['dias_restantes'])

    # 9. Pronóstico Estadístico de Ventas (Regresión Lineal para próximos 7 días)
    hoy_ni = business_today()
    inicio_30d = hoy_ni - timedelta(days=29)
    execute_sp(
        cursor,
        'ventas.sp_EstadisticaHistoricoVentasRegresion',
        (hoy_ni,),
        fallback_sql="""
        SELECT CONVERT(date, FechaHora) AS Dia, ISNULL(SUM(Total), 0) AS Total
        FROM Facturas
        WHERE EstadoFiscal='Emitida'
          AND CONVERT(date, FechaHora) >= ?
          AND CONVERT(date, FechaHora) <= ?
        GROUP BY CONVERT(date, FechaHora)
        ORDER BY Dia
    """,
        fallback_params=(inicio_30d, hoy_ni),
    )
    historico_ventas = cursor.fetchall()
    pronostico_ventas_data = calcular_pronostico_ventas(historico_ventas, hoy=hoy_ni)

    conn.close()

    return render_template('admin/estadistica.html', user=current_user,
        ventas_por_hora=ventas_por_hora, ventas_diarias=ventas_diarias,
        rotacion_productos=rotacion_productos, mermas_mes=mermas_mes,
        clientes_nivel=clientes_nivel, rendimiento_lotes=rendimiento_lotes,
        arqueos=arqueos, pronostico=pronostico, pronostico_ventas_data=pronostico_ventas_data)
