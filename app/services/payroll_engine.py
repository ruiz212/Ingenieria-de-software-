"""Motor de cálculo de Planilla en 3 Partes, Vacaciones, IR Ley 822 y Métricas de Asistencia.

Estructura de Nómina:
- Parte 1: Ingresos Salariales y No Salariales (Viáticos, Depreciación Vehículo).
- Parte 2: Deducciones (INSS 7%, IR Progresivo Acumulado, Embargos, Préstamos, Vales, Cobros Pérdidas).
- Parte 3: Cargos y Provisiones Patronales (INSS Pat, INATEC, Vacaciones 8.33%, Aguinaldo 8.33%, Indemnización).
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timedelta
import json
from app.services.validation import amount


def d_round(val: Decimal | float | int) -> Decimal:
    """Redondeo a 2 decimales bancario/financiero estándar."""
    if isinstance(val, (float, int, str)):
        val = Decimal(str(val))
    return val.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


# Tabla Progresiva Oficial IR Nicaragua - Ley 822 (Art. 23)
TABLA_IR_LEY_822 = [
    {'desde': Decimal('0.00'),       'hasta': Decimal('100000.00'), 'base': Decimal('0.00'),    'tasa': Decimal('0.00'), 'exceso': Decimal('0.00')},
    {'desde': Decimal('100000.00'), 'hasta': Decimal('200000.00'), 'base': Decimal('0.00'),    'tasa': Decimal('15.00'),'exceso': Decimal('100000.00')},
    {'desde': Decimal('200000.00'), 'hasta': Decimal('350000.00'), 'base': Decimal('15000.00'),'tasa': Decimal('20.00'),'exceso': Decimal('200000.00')},
    {'desde': Decimal('350000.00'), 'hasta': Decimal('500000.00'), 'base': Decimal('45000.00'),'tasa': Decimal('25.00'),'exceso': Decimal('350000.00')},
    {'desde': Decimal('500000.00'), 'hasta': Decimal('999999999.00'), 'base': Decimal('82500.00'), 'tasa': Decimal('30.00'),'exceso': Decimal('500000.00')},
]


def calcular_ir_ley822(renta_neta_anual: Decimal, tabla_ir: list = None) -> Decimal:
    """Calcula el IR anual conforme a la tabla de estratos de la Ley 822 sin saltos ni huecos."""
    renta = max(Decimal('0.00'), Decimal(str(renta_neta_anual)))
    tramos = tabla_ir or TABLA_IR_LEY_822
    for estrato in tramos:
        desde = Decimal(str(estrato['desde']))
        hasta = Decimal(str(estrato['hasta']))
        base = Decimal(str(estrato['base']))
        tasa = Decimal(str(estrato['tasa']))
        exceso = Decimal(str(estrato['exceso']))
        if renta > desde and renta <= hasta:
            return d_round(base + ((renta - exceso) * (tasa / Decimal('100.00'))))
        elif renta <= Decimal('100000.00'):
            return Decimal('0.00')
    if renta > Decimal('500000.00'):
        return d_round(Decimal('82500.00') + ((renta - Decimal('500000.00')) * Decimal('0.30')))
    return Decimal('0.00')


def calcular_ir_metodo_acumulado(
    renta_gravable_mes: Decimal,
    acumulado_renta_anio: Decimal,
    mes_del_anio: int,
    ir_retenido_acumulado: Decimal,
    tabla_ir: list = None
) -> Decimal:
    """Calcula la retención de IR del mes aplicando el método acumulado proporcional.

    Evita la sobre-retención en meses atípicos (con horas extras o bonos).
    """
    mes = max(1, min(12, int(mes_del_anio)))
    renta_mes = max(Decimal('0.00'), Decimal(str(renta_gravable_mes)))
    acum_renta = max(Decimal('0.00'), Decimal(str(acumulado_renta_anio))) + renta_mes
    
    # Proyección anual basada en el promedio acumulado trabajado
    renta_anual_proyectada = (acum_renta / Decimal(str(mes))) * Decimal('12.00')
    ir_anual_proyectado = calcular_ir_ley822(renta_anual_proyectada, tabla_ir)
    
    # Porción del IR anual correspondiente a los meses transcurridos a la fecha
    ir_acumulado_debido = d_round(ir_anual_proyectado * (Decimal(str(mes)) / Decimal('12.00')))
    ret_previa = max(Decimal('0.00'), Decimal(str(ir_retenido_acumulado)))
    
    ir_mes = max(Decimal('0.00'), ir_acumulado_debido - ret_previa)
    return d_round(ir_mes)


def calcular_tasa_provision_indemnizacion(antiguedad_anios: int) -> Decimal:
    """Tasa de provisión mensual para indemnización por antigüedad (Art. 45 Código del Trabajo).

    - Primeros 3 años: 1 mes de salario por año = 1/12 = 8.3333% mensual.
    - A partir del 4.º año: 20 días por año = 20/360 = 5.5555% mensual.
    - Tope legal: 5 meses de salario (alcanzado a los 6 años).
    """
    if antiguedad_anios >= 6:
        return Decimal('0.00')  # Ya alcanzó el tope de 5 meses
    elif antiguedad_anios >= 3:
        return Decimal('0.055556')  # 20 días por año = 20 / 360
    else:
        return Decimal('0.083333')  # 30 días por año = 1 / 12


class ItemDetalleNomina:
    def __init__(self, concepto: str, tipo: str, monto: Decimal, descripcion: str = '', salarial: bool = True):
        self.concepto = concepto
        self.tipo = tipo  # 'Ingreso', 'Deduccion', 'Patronal'
        self.monto = d_round(monto)
        self.descripcion = descripcion
        self.salarial = salarial

    def to_dict(self):
        return {
            'concepto': self.concepto,
            'tipo': self.tipo,
            'monto': float(self.monto),
            'descripcion': self.descripcion,
            'salarial': self.salarial,
        }


class ResultadoPlanillaEstructurada:
    def __init__(self):
        self.ingresos = []
        self.deducciones = []
        self.patronales = []
        
        # Subtotales Parte 1
        self.sueldo_ordinario = Decimal('0.00')
        self.incentivos = Decimal('0.00')
        self.sueldo_extraordinario = Decimal('0.00')
        self.monto_horas_extras = Decimal('0.00')
        self.horas_extras_cantidad = Decimal('0.00')
        self.riesgo = Decimal('0.00')
        self.viaticos = Decimal('0.00')
        self.depreciacion_vehiculo = Decimal('0.00')
        self.otros_ingresos = Decimal('0.00')
        
        self.total_ingresos_salariales = Decimal('0.00')
        self.total_ingresos_no_salariales = Decimal('0.00')
        self.total_devengado = Decimal('0.00')

        # Subtotales Parte 2
        self.inss_laboral = Decimal('0.00')
        self.ir_mensual = Decimal('0.00')
        self.embargo_pension = Decimal('0.00')
        self.deduccion_prestamo = Decimal('0.00')
        self.vales_descontados = Decimal('0.00')
        self.cobro_perdidas = Decimal('0.00')
        self.total_deducciones = Decimal('0.00')
        self.salario_neto = Decimal('0.00')
        
        # Saldos pendientes posteriores
        self.saldo_prestamo_restante = Decimal('0.00')
        self.saldo_perdida_restante = Decimal('0.00')

        # Subtotales Parte 3
        self.inss_patronal = Decimal('0.00')
        self.inatec = Decimal('0.00')
        self.provision_vacaciones = Decimal('0.00')
        self.provision_aguinaldo = Decimal('0.00')
        self.provision_indemnizacion = Decimal('0.00')
        self.total_cargos_patronales = Decimal('0.00')
        self.costo_total_empresa = Decimal('0.00')

        # Métricas de Asistencia
        self.promedio_asistencia = Decimal('100.00')
        self.promedio_puntualidad = Decimal('100.00')
        self.horas_promedio_dia = Decimal('8.00')

    @property
    def sueldo_base_efectivo(self):
        return self.sueldo_ordinario

    @property
    def riesgo_laboral(self):
        return self.riesgo

    @property
    def embargo_salarial(self):
        return self.embargo_pension

    @property
    def deduccion_prestamos(self):
        return self.deduccion_prestamo

    @property
    def vales_adelanto(self):
        return self.vales_descontados

    @property
    def cobros_perdidas(self):
        return self.cobro_perdidas

    @property
    def total_ingresos(self):
        return self.total_devengado

    @property
    def total_patronal(self):
        return self.total_cargos_patronales

    @property
    def promedio_asistencia_pct(self):
        return self.promedio_asistencia

    @property
    def promedio_puntualidad_pct(self):
        return self.promedio_puntualidad

    @property
    def promedio_horas_diarias(self):
        return self.horas_promedio_dia

    def to_dict(self):
        return {
            'parte1_ingresos': {
                'items': [item.to_dict() for item in self.ingresos],
                'sueldo_ordinario': float(self.sueldo_ordinario),
                'incentivos': float(self.incentivos),
                'sueldo_extraordinario': float(self.sueldo_extraordinario),
                'monto_horas_extras': float(self.monto_horas_extras),
                'horas_extras_cantidad': float(self.horas_extras_cantidad),
                'riesgo': float(self.riesgo),
                'viaticos': float(self.viaticos),
                'depreciacion_vehiculo': float(self.depreciacion_vehiculo),
                'otros_ingresos': float(self.otros_ingresos),
                'total_ingresos_salariales': float(self.total_ingresos_salariales),
                'total_ingresos_no_salariales': float(self.total_ingresos_no_salariales),
                'total_devengado': float(self.total_devengado),
            },
            'parte2_deducciones': {
                'items': [item.to_dict() for item in self.deducciones],
                'inss_laboral': float(self.inss_laboral),
                'ir_mensual': float(self.ir_mensual),
                'embargo_pension': float(self.embargo_pension),
                'deduccion_prestamo': float(self.deduccion_prestamo),
                'vales_descontados': float(self.vales_descontados),
                'cobro_perdidas': float(self.cobro_perdidas),
                'total_deducciones': float(self.total_deducciones),
                'salario_neto': float(self.salario_neto),
                'saldo_prestamo_restante': float(self.saldo_prestamo_restante),
                'saldo_perdida_restante': float(self.saldo_perdida_restante),
            },
            'parte3_patronal': {
                'items': [item.to_dict() for item in self.patronales],
                'inss_patronal': float(self.inss_patronal),
                'inatec': float(self.inatec),
                'provision_vacaciones': float(self.provision_vacaciones),
                'provision_aguinaldo': float(self.provision_aguinaldo),
                'provision_indemnizacion': float(self.provision_indemnizacion),
                'total_cargos_patronales': float(self.total_cargos_patronales),
                'costo_total_empresa': float(self.costo_total_empresa),
            },
            'asistencia': {
                'promedio_asistencia': float(self.promedio_asistencia),
                'promedio_puntualidad': float(self.promedio_puntualidad),
                'horas_promedio_dia': float(self.horas_promedio_dia),
            }
        }


def calcular_planilla_completa(
    salario_base: Decimal | float,
    dias_ausentes: float = 0.0,
    horas_extras: float = 0.0,
    incentivos: Decimal | float = 0.0,
    sueldo_extraordinario: Decimal | float = 0.0,
    riesgo_monto: Decimal | float = 0.0,
    viaticos: Decimal | float = 0.0,
    depreciacion_vehiculo: Decimal | float = 0.0,
    otros_ingresos: Decimal | float = 0.0,
    dias_feriados_trabajados: float = 0.0,
    # Deducciones
    pension_alimenticia: Decimal | float = 0.0,
    vales_pendientes: Decimal | float = 0.0,
    saldo_prestamo: Decimal | float = 0.0,
    cuota_prestamo_pactada: Decimal | float = 0.0,
    saldo_cobro_perdida: Decimal | float = 0.0,
    # Parámetros IR e Historial
    mes_del_anio: int = 1,
    acumulado_renta_anio: Decimal | float = 0.0,
    ir_retenido_acumulado: Decimal | float = 0.0,
    # Datos de empresa y empleado
    total_empleados: int = 10,
    antiguedad_anios: int = 0,
    salario_minimo_legal: Decimal | float = Decimal('7000.00'),
    # Tasas configurables
    tasa_inss_laboral: Decimal | float = Decimal('7.00'),
    tasa_inss_patronal: Decimal | float = None,
    tasa_inatec: Decimal | float = Decimal('2.00'),
    tabla_ir: list = None,
    # Asistencia
    dias_esperados: int = 26,
    dias_asistidos: int = 26,
    llegadas_tardias: int = 0,
    horas_promedio_dia: float = 8.0,
    # Aliases
    riesgo_laboral: Decimal | float = None,
    deduccion_prestamos: Decimal | float = None,
    vales_adelanto: Decimal | float = None,
    cobros_perdidas: Decimal | float = None,
    embargo_salarial: Decimal | float = None,
    anios_antiguedad: Decimal | float = None,
    dias_tardanzas: int = None,
    horas_totales_trabajadas: Decimal | float = None,
    mes_numero: int = None,
    acumulado_gravable_anio: Decimal | float = None,
    ir_retenido_acumulado_anio: Decimal | float = None,
    usar_metodo_acumulado_ir: bool = True,
    **kwargs
) -> ResultadoPlanillaEstructurada:
    """Calcula integralmente la planilla en sus 3 partes garantizando consistencia legal y contable."""
    if riesgo_laboral is not None and float(riesgo_monto) == 0:
        riesgo_monto = riesgo_laboral
    if deduccion_prestamos is not None and float(cuota_prestamo_pactada) == 0:
        cuota_prestamo_pactada = deduccion_prestamos
        if float(saldo_prestamo) == 0:
            saldo_prestamo = deduccion_prestamos
    if cobros_perdidas is not None and float(saldo_cobro_perdida) == 0:
        saldo_cobro_perdida = cobros_perdidas
    if embargo_salarial is not None and float(pension_alimenticia) == 0:
        pension_alimenticia = embargo_salarial
    if vales_adelanto is not None and float(vales_pendientes) == 0:
        vales_pendientes = vales_adelanto
    if anios_antiguedad is not None and antiguedad_anios == 0:
        antiguedad_anios = int(anios_antiguedad)
    if dias_tardanzas is not None and llegadas_tardias == 0:
        llegadas_tardias = dias_tardanzas
    if mes_numero is not None:
        mes_del_anio = mes_numero
    if acumulado_gravable_anio is not None:
        acumulado_renta_anio = acumulado_gravable_anio
    if ir_retenido_acumulado_anio is not None:
        ir_retenido_acumulado = ir_retenido_acumulado_anio

    res = ResultadoPlanillaEstructurada()
    
    salario_base_dec = max(Decimal('0.00'), Decimal(str(salario_base)))
    salario_diario = salario_base_dec / Decimal('30.00')
    salario_hora = salario_diario / Decimal('8.00')
    
    # -------------------------------------------------------------
    # PARTE 1: INGRESOS
    # -------------------------------------------------------------
    # Sueldo ordinario con descuento proporcional de ausencias
    dias_aus = Decimal(str(dias_ausentes))
    monto_ausencias = dias_aus * salario_diario * Decimal('1.1667')
    sueldo_ordinario = max(Decimal('0.00'), salario_base_dec - monto_ausencias)
    res.sueldo_ordinario = d_round(sueldo_ordinario)
    res.ingresos.append(ItemDetalleNomina('Sueldo Ordinario', 'Ingreso', res.sueldo_ordinario, 'Salario ordinario del período', salarial=True))
    
    # Incentivos
    res.incentivos = d_round(Decimal(str(incentivos)))
    if res.incentivos > 0:
        res.ingresos.append(ItemDetalleNomina('Incentivos', 'Ingreso', res.incentivos, 'Incentivos y bonos de productividad', salarial=True))
        
    # Sueldo Extraordinario (feriados trabajados + descanso trabajado al 200%)
    monto_feriados_calc = Decimal(str(dias_feriados_trabajados)) * salario_diario * Decimal('2.00')
    sueldo_extra_input = Decimal(str(sueldo_extraordinario))
    res.sueldo_extraordinario = d_round(monto_feriados_calc + sueldo_extra_input)
    if res.sueldo_extraordinario > 0:
        res.ingresos.append(ItemDetalleNomina('Sueldo Extraordinario', 'Ingreso', res.sueldo_extraordinario, 'Trabajo en días feriados o descanso semanal', salarial=True))
        
    # Horas Extras (pagadas al 200% según art. 62 CT)
    he_cant = Decimal(str(horas_extras))
    res.horas_extras_cantidad = d_round(he_cant)
    res.monto_horas_extras = d_round(he_cant * salario_hora * Decimal('2.00'))
    if res.monto_horas_extras > 0:
        res.ingresos.append(ItemDetalleNomina('Horas Extras', 'Ingreso', res.monto_horas_extras, f"{float(res.horas_extras_cantidad):.1f} horas extras al doble", salarial=True))
        
    # Riesgo 1.5 (bono/recargo por labores de riesgo térmico u operacional)
    res.riesgo = d_round(Decimal(str(riesgo_monto)))
    if res.riesgo > 0:
        res.ingresos.append(ItemDetalleNomina('Riesgo Laboral', 'Ingreso', res.riesgo, 'Compensación por riesgo laboral 1.5', salarial=True))
        
    # Otros ingresos salariales
    res.otros_ingresos = d_round(Decimal(str(otros_ingresos)))
    if res.otros_ingresos > 0:
        res.ingresos.append(ItemDetalleNomina('Otros Ingresos', 'Ingreso', res.otros_ingresos, 'Otros ingresos salariales', salarial=True))
        
    # Subtotal Ingresos Salariales (base para INSS, IR y provisiones laborales)
    res.total_ingresos_salariales = d_round(
        res.sueldo_ordinario + res.incentivos + res.sueldo_extraordinario +
        res.monto_horas_extras + res.riesgo + res.otros_ingresos
    )
    
    # Ingresos No Salariales (reembolsos justificados exentos de INSS e IR)
    res.viaticos = d_round(Decimal(str(viaticos)))
    if res.viaticos > 0:
        res.ingresos.append(ItemDetalleNomina('Viáticos', 'Ingreso', res.viaticos, 'Reembolso de viáticos justificados (No Salarial)', salarial=False))
        
    res.depreciacion_vehiculo = d_round(Decimal(str(depreciacion_vehiculo)))
    if res.depreciacion_vehiculo > 0:
        res.ingresos.append(ItemDetalleNomina('Depreciación de Vehículo', 'Ingreso', res.depreciacion_vehiculo, 'Reembolso por uso de vehículo particular (No Salarial)', salarial=False))
        
    res.total_ingresos_no_salariales = d_round(res.viaticos + res.depreciacion_vehiculo)
    
    # Total Devengado Bruto
    res.total_devengado = d_round(res.total_ingresos_salariales + res.total_ingresos_no_salariales)
    
    # -------------------------------------------------------------
    # PARTE 2: DEDUCCIONES (EN ORDEN LEGAL DE PRELACIÓN)
    # -------------------------------------------------------------
    # 1. INSS Laboral (7% sobre base salarial)
    tasa_inss_lab = Decimal(str(tasa_inss_laboral))
    res.inss_laboral = d_round(res.total_ingresos_salariales * (tasa_inss_lab / Decimal('100.00')))
    res.deducciones.append(ItemDetalleNomina('INSS Laboral', 'Deduccion', res.inss_laboral, f'Cotización INSS {float(tasa_inss_lab):.1f}%'))
    
    # 2. IR Laboral Progresivo (Método Acumulado Ley 822)
    renta_gravable_mes = max(Decimal('0.00'), res.total_ingresos_salariales - res.inss_laboral)
    res.ir_mensual = calcular_ir_metodo_acumulado(
        renta_gravable_mes=renta_gravable_mes,
        acumulado_renta_anio=Decimal(str(acumulado_renta_anio)),
        mes_del_anio=mes_del_anio,
        ir_retenido_acumulado=Decimal(str(ir_retenido_acumulado)),
        tabla_ir=tabla_ir
    )
    if res.ir_mensual > 0:
        res.deducciones.append(ItemDetalleNomina('IR Retenido', 'Deduccion', res.ir_mensual, 'Retención IR según tabla progresiva Ley 822'))
        
    # Remanente disponible antes de deducciones privadas/judiciales
    neto_pre = max(Decimal('0.00'), res.total_devengado - res.inss_laboral - res.ir_mensual)
    
    # 3. Embargo Salarial / Pensión Alimenticia
    pension_req = Decimal(str(pension_alimenticia))
    res.embargo_pension = d_round(min(neto_pre, pension_req))
    if res.embargo_pension > 0:
        res.deducciones.append(ItemDetalleNomina('Pensión / Embargo', 'Deduccion', res.embargo_pension, 'Orden judicial de alimentos o embargo'))
        
    neto_disponible = max(Decimal('0.00'), neto_pre - res.embargo_pension)
    
    # 4. Deducción por Préstamos a Empleados (cuota fija mensual sin exceder saldo ni neto)
    s_prestamo = Decimal(str(saldo_prestamo))
    cuota_p = Decimal(str(cuota_prestamo_pactada))
    if s_prestamo > 0 and cuota_p > 0:
        ded_prestamo = min(neto_disponible, min(s_prestamo, cuota_p))
        res.deduccion_prestamo = d_round(ded_prestamo)
        res.saldo_prestamo_restante = d_round(s_prestamo - res.deduccion_prestamo)
        if res.deduccion_prestamo > 0:
            res.deducciones.append(ItemDetalleNomina('Abono a Préstamo', 'Deduccion', res.deduccion_prestamo, f'Cuota de préstamo empleado (Saldo resta: C${float(res.saldo_prestamo_restante):.2f})'))
        neto_disponible = max(Decimal('0.00'), neto_disponible - res.deduccion_prestamo)
    else:
        res.saldo_prestamo_restante = d_round(s_prestamo)
        
    # 5. Vales / Adelantos
    vales_req = Decimal(str(vales_pendientes))
    if vales_req > 0:
        res.vales_descontados = d_round(min(neto_disponible, vales_req))
        if res.vales_descontados > 0:
            res.deducciones.append(ItemDetalleNomina('Vales / Adelantos', 'Deduccion', res.vales_descontados, 'Deducción de vales de caja entregados'))
        neto_disponible = max(Decimal('0.00'), neto_disponible - res.vales_descontados)
        
    # 6. Cobros por Pérdidas (Tope máximo de protección del 10% del neto disponible)
    s_perdida = Decimal(str(saldo_cobro_perdida))
    if s_perdida > 0:
        tope_perdida = d_round(neto_disponible * Decimal('0.10'))
        ded_perdida = min(neto_disponible, min(s_perdida, tope_perdida))
        res.cobro_perdidas = d_round(ded_perdida)
        res.saldo_perdida_restante = d_round(s_perdida - res.cobro_perdidas)
        if res.cobro_perdidas > 0:
            res.deducciones.append(ItemDetalleNomina('Cobro por Pérdidas', 'Deduccion', res.cobro_perdidas, f'Deducción autorizada por pérdidas (Tope 10% neto. Saldo resta: C${float(res.saldo_perdida_restante):.2f})'))
        neto_disponible = max(Decimal('0.00'), neto_disponible - res.cobro_perdidas)
    else:
        res.saldo_perdida_restante = d_round(s_perdida)
        
    # Totales deducciones y Salario Neto Final
    res.total_deducciones = d_round(
        res.inss_laboral + res.ir_mensual + res.embargo_pension +
        res.deduccion_prestamo + res.vales_descontados + res.cobro_perdidas
    )
    res.salario_neto = d_round(max(Decimal('0.00'), res.total_devengado - res.total_deducciones))

    # -------------------------------------------------------------
    # PARTE 3: CARGOS Y PROVISIONES PATRONALES
    # -------------------------------------------------------------
    # Tasa INSS Patronal (21.5% para < 50 trabajadores, 22.5% para >= 50)
    if tasa_inss_patronal is None:
        tasa_inss_pat = Decimal('22.50') if total_empleados >= 50 else Decimal('21.50')
    else:
        tasa_inss_pat = Decimal(str(tasa_inss_patronal))
        
    res.inss_patronal = d_round(res.total_ingresos_salariales * (tasa_inss_pat / Decimal('100.00')))
    res.patronales.append(ItemDetalleNomina('INSS Patronal', 'Patronal', res.inss_patronal, f'Aporte patronal INSS ({float(tasa_inss_pat):.1f}%)'))
    
    # INATEC (2%)
    tasa_ina = Decimal(str(tasa_inatec))
    res.inatec = d_round(res.total_ingresos_salariales * (tasa_ina / Decimal('100.00')))
    res.patronales.append(ItemDetalleNomina('INATEC', 'Patronal', res.inatec, f'Aporte patronal INATEC ({float(tasa_ina):.1f}%)'))
    
    # Provisión Vacaciones: 8.333% (1/12 o 2.5/30 días por mes)
    res.provision_vacaciones = d_round(res.total_ingresos_salariales * Decimal('2.5') / Decimal('30'))
    res.patronales.append(ItemDetalleNomina('Provisión Vacaciones', 'Patronal', res.provision_vacaciones, 'Provisión mensual de vacaciones (2.5 días/mes = 8.33%)'))
    
    # Provisión Aguinaldo / Treceavo Mes: 8.333% (1/12)
    res.provision_aguinaldo = d_round(res.total_ingresos_salariales / Decimal('12'))
    res.patronales.append(ItemDetalleNomina('Provisión Aguinaldo', 'Patronal', res.provision_aguinaldo, 'Provisión mensual de aguinaldo (1/12 = 8.33%)'))
    
    # Provisión Indemnización por Antigüedad
    tasa_indemnizacion = calcular_tasa_provision_indemnizacion(antiguedad_anios)
    res.provision_indemnizacion = d_round(res.total_ingresos_salariales * tasa_indemnizacion)
    res.patronales.append(ItemDetalleNomina('Provisión Indemnización', 'Patronal', res.provision_indemnizacion, f'Provisión mensual de indemnización ({float(tasa_indemnizacion*100):.2f}%)'))
    
    res.total_cargos_patronales = d_round(
        res.inss_patronal + res.inatec + res.provision_vacaciones +
        res.provision_aguinaldo + res.provision_indemnizacion
    )
    res.costo_total_empresa = d_round(res.total_devengado + res.total_cargos_patronales)
    
    # -------------------------------------------------------------
    # MÉTRICAS DE ASISTENCIA
    # -------------------------------------------------------------
    if dias_esperados > 0:
        res.promedio_asistencia = d_round((Decimal(str(dias_asistidos)) / Decimal(str(dias_esperados))) * Decimal('100.00'))
    else:
        res.promedio_asistencia = Decimal('100.00')
        
    if dias_asistidos > 0:
        a_tiempo = max(0, dias_asistidos - llegadas_tardias)
        res.promedio_puntualidad = d_round((Decimal(str(a_tiempo)) / Decimal(str(dias_asistidos))) * Decimal('100.00'))
    else:
        res.promedio_puntualidad = Decimal('100.00')
        
    res.horas_promedio_dia = d_round(Decimal(str(horas_promedio_dia)))
    
    return res


# -------------------------------------------------------------
# GESTIÓN Y PLANIFICADOR DE VACACIONES
# -------------------------------------------------------------

def calcular_saldo_vacaciones_empleado(
    fecha_ingreso,
    fecha_corte=None,
    licencias=None,
    dias_gozados=None,
    as_of=None,
    **kwargs
):
    """Calcula el saldo de vacaciones devengadas, gozadas y disponibles con semáforo."""
    from app.services.hr_calculations import as_date, vacation_days_consumed
    f_ingreso = as_date(fecha_ingreso)
    f_corte = as_date(as_of or fecha_corte or date.today())
    if f_corte < f_ingreso:
        f_corte = f_ingreso
        
    dias_trabajados = (f_corte - f_ingreso).days
    dias_devengados = round(dias_trabajados * (30.0 / 365.0), 2)
    if dias_gozados is not None:
        gozados = float(dias_gozados)
    elif licencias:
        gozados = round(vacation_days_consumed(licencias, f_ingreso, f_corte), 2)
    else:
        gozados = 0.0
    dias_disponibles = max(0.0, round(dias_devengados - gozados, 2))
    
    # Semáforo de acumulación:
    # Verde: < 15 días (al día)
    # Amarillo: 15 a 29.99 días (acumulando más de un semestre)
    # Rojo: >= 30 días (acumulando 1 año o más, riesgo laboral)
    if dias_disponibles < 15.0:
        semaforo = 'verde'
        alerta_semaforo = 'Verde'
        estado_alerta = 'Normal'
        acumulacion_excesiva = False
    elif dias_disponibles < 30.0:
        semaforo = 'amarillo'
        alerta_semaforo = 'Amarillo'
        estado_alerta = 'Atención (Semestre Acumulado)'
        acumulacion_excesiva = False
    else:
        semaforo = 'rojo'
        alerta_semaforo = 'Rojo'
        estado_alerta = 'Crítico (Exceso Acumulado)'
        acumulacion_excesiva = True
        
    # Vencimiento estimado de semestre (cada 180 días de servicio)
    semestres_cumplidos = dias_trabajados // 180
    prox_vencimiento = f_ingreso + timedelta(days=(semestres_cumplidos + 1) * 180)
    dias_para_vencer = (prox_vencimiento - f_corte).days

    return {
        'fecha_ingreso': f_ingreso.isoformat(),
        'dias_trabajados': dias_trabajados,
        'dias_devengados': dias_devengados,
        'dias_gozados': gozados,
        'dias_disponibles': dias_disponibles,
        'semaforo': semaforo,
        'alerta_semaforo': alerta_semaforo,
        'estado_alerta': estado_alerta,
        'acumulacion_excesiva': acumulacion_excesiva,
        'dias_para_vencer': dias_para_vencer,
        'dias_para_vencer_semestre': dias_para_vencer,
        'proximo_vencimiento': prox_vencimiento.isoformat(),
    }


def generar_plan_recomendado_vacaciones(
    empleados_con_saldo: list = None,
    fecha_inicio_plan: date = None,
    bloques_dias: int = 15,
    max_por_cargo: int = 1,
    temporadas_bloqueadas: list = None,
    meses_proyeccion: int = 6,
    empleados_saldos: list = None,
    **kwargs
) -> list:
    if empleados_con_saldo is None:
        empleados_con_saldo = empleados_saldos or []
    """Algoritmo de optimización que asigna turnos de vacaciones rotativas para abatir acumulación.

    Reglas de negocio:
    1. Prioridad estricta a semáforo ROJO, luego AMARILLO, ordenado por saldo disponible desc.
    2. No más de `max_por_cargo` personas del mismo cargo ausentes simultáneamente.
    3. Bloquea temporadas altas de la panadería (15-31 dic, semana previa al 30 de mayo, Semana Santa).
    """
    inicio = fecha_inicio_plan or (date.today() + timedelta(days=7))
    
    # Temporadas bloqueadas por defecto si no se especifican
    if temporadas_bloqueadas is None:
        anio = inicio.year
        temporadas_bloqueadas = [
            # Temporada Navideña
            (date(anio, 12, 15), date(anio, 12, 31)),
            # Día de las Madres
            (date(anio, 5, 20), date(anio, 5, 31)),
        ]
        
    # Ordenar candidatos por prioridad
    def _prioridad_key(emp):
        sem_score = {'rojo': 3, 'amarillo': 2, 'verde': 1}.get(emp.get('semaforo', 'verde'), 0)
        return (sem_score, emp.get('dias_disponibles', 0), emp.get('antiguedad_anios', 0))
        
    candidatos = [e for e in empleados_con_saldo if e.get('dias_disponibles', 0) >= 5.0]
    candidatos.sort(key=_prioridad_key, reverse=True)
    
    asignaciones_por_cargo = {}  # cargo -> list of (start_date, end_date)
    propuestas = []
    
    cursor_fecha = inicio
    # Asegurar que cursor_fecha comience en día hábil (lunes)
    while cursor_fecha.weekday() != 0:
        cursor_fecha += timedelta(days=1)
        
    for emp in candidatos:
        cargo = emp.get('cargo', 'General').strip().lower()
        dias_disponibles = emp.get('dias_disponibles', 0)
        dias_a_programar = min(bloques_dias, int(dias_disponibles))
        if dias_a_programar < 5:
            continue
            
        fecha_propuesta_inicio = cursor_fecha
        asignado = False
        intentos = 0
        
        while not asignado and intentos < 60:
            intentos += 1
            fecha_propuesta_fin = fecha_propuesta_inicio + timedelta(days=dias_a_programar - 1)
            
            # 1. Verificar temporadas bloqueadas
            en_temporada_bloqueada = False
            for b_ini, b_fin in temporadas_bloqueadas:
                if not (fecha_propuesta_fin < b_ini or fecha_propuesta_inicio > b_fin):
                    en_temporada_bloqueada = True
                    fecha_propuesta_inicio = b_fin + timedelta(days=1)
                    while fecha_propuesta_inicio.weekday() != 0:
                        fecha_propuesta_inicio += timedelta(days=1)
                    break
            if en_temporada_bloqueada:
                continue
                
            # 2. Verificar traslape de cargo
            traslapes_cargo = 0
            for a_ini, a_fin in asignaciones_por_cargo.get(cargo, []):
                if not (fecha_propuesta_fin < a_ini or fecha_propuesta_inicio > a_fin):
                    traslapes_cargo += 1
                    
            if traslapes_cargo >= max_por_cargo:
                # Mover al siguiente bloque
                fecha_propuesta_inicio += timedelta(days=7)
                continue
                
            # Asignación válida encontrada
            asignado = True
            asignaciones_por_cargo.setdefault(cargo, []).append((fecha_propuesta_inicio, fecha_propuesta_fin))
            propuestas.append({
                'empleado_id': emp.get('id') or emp.get('empleado_id'),
                'nombre_completo': emp.get('nombre_completo') or emp.get('nombre'),
                'nombre': emp.get('nombre') or emp.get('nombre_completo'),
                'cargo': emp.get('cargo'),
                'dias_disponibles': dias_disponibles,
                'semaforo': emp.get('semaforo'),
                'fecha_inicio': fecha_propuesta_inicio.isoformat(),
                'fecha_fin': fecha_propuesta_fin.isoformat(),
                'dias': dias_a_programar,
                'dias_propuestos': dias_a_programar,
                'saldo_restante_estimado': round(dias_disponibles - dias_a_programar, 2),
                'motivo': f"Plan Rotativo Semestral - Abatimiento Semáforo {emp.get('semaforo', 'Normal').upper()}",
            })
            
    return propuestas
