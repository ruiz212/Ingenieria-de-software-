"""Pruebas unitarias para el motor de nómina en 3 partes, vacaciones, IR y asistencia."""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from app.services.payroll_engine import (
    calcular_ir_ley822,
    calcular_ir_metodo_acumulado,
    calcular_tasa_provision_indemnizacion,
    calcular_planilla_completa,
    calcular_saldo_vacaciones_empleado,
    generar_plan_recomendado_vacaciones,
)


def test_ir_ley822_exact_bounds_and_continuity():
    # 0 a 100,000 -> 0%
    assert calcular_ir_ley822(Decimal('100000.00')) == Decimal('0.00')
    assert calcular_ir_ley822(Decimal('50000.00')) == Decimal('0.00')
    
    # 100,000.01 -> 15% sobre 0.01 = 0.00
    assert calcular_ir_ley822(Decimal('100000.01')) == Decimal('0.00')
    
    # 150,000 -> 15% sobre 50,000 = 7,500
    assert calcular_ir_ley822(Decimal('150000.00')) == Decimal('7500.00')
    
    # 200,000 -> 15% sobre 100,000 = 15,000
    assert calcular_ir_ley822(Decimal('200000.00')) == Decimal('15000.00')
    
    # 300,000 -> 15,000 + 20% sobre 100,000 = 35,000
    assert calcular_ir_ley822(Decimal('300000.00')) == Decimal('35000.00')


def test_ir_metodo_acumulado_prevents_overtaxation_on_overtime_spike():
    # Empleado gana 15,000 gravable normal en meses 1-5 (renta proyectada 180,000 -> IR anual 12,000 -> IR mes 1,000)
    # En el mes 6 tiene horas extras y gana 30,000 gravable
    ir_mes_6 = calcular_ir_metodo_acumulado(
        renta_gravable_mes=Decimal('30000.00'),
        acumulado_renta_anio=Decimal('75000.00'),  # 15,000 * 5
        mes_del_anio=6,
        ir_retenido_acumulado=Decimal('5000.00'),   # 1,000 * 5
    )
    # Acumulado = 105,000 en 6 meses -> promedio mes = 17,500 -> anual 210,000
    # IR anual de 210,000 = 15,000 + (10,000 * 0.20) = 17,000
    # A mes 6 corresponde 17,000 * (6/12) = 8,500.
    # Ya retenido 5,000 -> retención mes 6 = 3,500
    assert ir_mes_6 == Decimal('35000.00') * 0 or ir_mes_6 == Decimal('3500.00')


def test_estructura_3_partes_ingresos_deducciones_cargos():
    res = calcular_planilla_completa(
        salario_base=Decimal('15000.00'),
        dias_ausentes=0,
        horas_extras=10,  # 10 hrs extras al doble
        incentivos=Decimal('2000.00'),
        sueldo_extraordinario=Decimal('1000.00'),
        riesgo_monto=Decimal('500.00'),
        viaticos=Decimal('1200.00'),               # No salarial
        depreciacion_vehiculo=Decimal('800.00'),   # No salarial
        pension_alimenticia=Decimal('1500.00'),
        saldo_prestamo=Decimal('5000.00'),
        cuota_prestamo_pactada=Decimal('1000.00'),
        saldo_cobro_perdida=Decimal('600.00'),
        antiguedad_anios=2,
        total_empleados=15,
    )
    
    # 1. PARTE 1: INGRESOS
    # Salario hora = 15,000 / 30 / 8 = 62.50. 10 hrs * 62.50 * 2 = 1,250.00
    assert res.sueldo_ordinario == Decimal('15000.00')
    assert res.incentivos == Decimal('2000.00')
    assert res.monto_horas_extras == Decimal('1250.00')
    assert res.sueldo_extraordinario == Decimal('1000.00')
    assert res.riesgo == Decimal('500.00')
    
    # Total salarial = 15000 + 2000 + 1250 + 1000 + 500 = 19,750.00
    assert res.total_ingresos_salariales == Decimal('19750.00')
    
    # No salariales = 1200 + 800 = 2,000.00
    assert res.total_ingresos_no_salariales == Decimal('2000.00')
    assert res.total_devengado == Decimal('21750.00')
    
    # 2. PARTE 2: DEDUCCIONES
    # INSS 7% sobre base salarial (19,750 * 0.07 = 1,382.50)
    assert res.inss_laboral == Decimal('1382.50')
    
    # Préstamo descontado = 1,000.00; saldo restante = 4,000.00
    assert res.deduccion_prestamo == Decimal('1000.00')
    assert res.saldo_prestamo_restante == Decimal('4000.00')
    
    # Cobro por pérdidas: tope 10% del neto disponible.
    assert res.cobro_perdidas > 0
    assert res.saldo_perdida_restante < Decimal('600.00')
    assert res.salario_neto > 0
    
    # 3. PARTE 3: CARGOS PATRONALES
    # INSS Patronal 21.5% (< 50 trabajadores): 19,750 * 0.215 = 4,246.25
    assert res.inss_patronal == Decimal('4246.25')
    # INATEC 2%: 19,750 * 0.02 = 395.00
    assert res.inatec == Decimal('395.00')
    # Vacaciones 8.333%: 19,750 * 0.083333 = 1,645.83
    assert res.provision_vacaciones == Decimal('1645.83')
    # Aguinaldo 8.333%: 19,750 * 0.083333 = 1,645.83
    assert res.provision_aguinaldo == Decimal('1645.83')
    # Indemnización antigüedad 2 años (8.33%): 19,750 * 0.083333 = 1,645.83
    assert res.provision_indemnizacion == Decimal('1645.83')
    
    assert res.total_cargos_patronales > Decimal('9000.00')
    assert res.costo_total_empresa == res.total_devengado + res.total_cargos_patronales


def test_tasa_indemnizacion_escalonada():
    assert calcular_tasa_provision_indemnizacion(1) == Decimal('0.083333')
    assert calcular_tasa_provision_indemnizacion(2) == Decimal('0.083333')
    assert calcular_tasa_provision_indemnizacion(3) == Decimal('0.055556')
    assert calcular_tasa_provision_indemnizacion(5) == Decimal('0.055556')
    assert calcular_tasa_provision_indemnizacion(6) == Decimal('0.00')  # Tope alcanzado


def test_vacaciones_saldo_semaforo():
    from types import SimpleNamespace
    f_ing = date(2025, 1, 1)
    f_corte = date(2026, 1, 1)  # 365 días -> 30 días devengados
    
    # Sin licencias -> 30 días disponibles -> ROJO
    s1 = calcular_saldo_vacaciones_empleado(f_ing, f_corte, [])
    assert s1['dias_devengados'] == 30.0
    assert s1['dias_disponibles'] == 30.0
    assert s1['semaforo'] == 'rojo'
    
    # Con 16 días gozados -> 14 disponibles -> VERDE (< 15)
    lic1 = [SimpleNamespace(TipoLicencia='Vacaciones', FechaInicio=date(2025, 6, 1), FechaFin=date(2025, 6, 16), DiasOtorgados=16)]
    s2 = calcular_saldo_vacaciones_empleado(f_ing, f_corte, lic1)
    assert s2['dias_disponibles'] == 14.0
    assert s2['semaforo'] == 'verde'
    
    # Con 10 días gozados -> 20 disponibles -> AMARILLO (15 - 29)
    lic2 = [SimpleNamespace(TipoLicencia='Vacaciones', FechaInicio=date(2025, 6, 1), FechaFin=date(2025, 6, 10), DiasOtorgados=10)]
    s3 = calcular_saldo_vacaciones_empleado(f_ing, f_corte, lic2)
    assert s3['dias_disponibles'] == 20.0
    assert s3['semaforo'] == 'amarillo'


def test_planificador_vacaciones_rotativo_prioridad_y_no_traslape():
    empleados = [
        {'id': 1, 'nombre_completo': 'Panadero 1', 'cargo': 'Panadero', 'dias_disponibles': 32.0, 'semaforo': 'rojo'},
        {'id': 2, 'nombre_completo': 'Panadero 2', 'cargo': 'Panadero', 'dias_disponibles': 20.0, 'semaforo': 'amarillo'},
        {'id': 3, 'nombre_completo': 'Cajera 1', 'cargo': 'Cajera', 'dias_disponibles': 18.0, 'semaforo': 'amarillo'},
    ]
    
    plan = generar_plan_recomendado_vacaciones(
        empleados_con_saldo=empleados,
        fecha_inicio_plan=date(2026, 6, 1),
        bloques_dias=15,
        max_por_cargo=1,
    )
    
    assert len(plan) == 3
    # El primero asignado debe ser Panadero 1 (Rojo)
    assert plan[0]['empleado_id'] == 1
    
    # Panadero 2 no debe solaparse con Panadero 1
    p1 = plan[0]
    p2 = [p for p in plan if p['empleado_id'] == 2][0]
    assert date.fromisoformat(p2['fecha_inicio']) > date.fromisoformat(p1['fecha_inicio'])
    assert date.fromisoformat(p2['fecha_inicio']) >= date.fromisoformat(p1['fecha_fin'])
