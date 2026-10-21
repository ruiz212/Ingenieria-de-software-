"""Cálculos de RRHH puros, compartidos por API y reportes."""
from datetime import date, datetime, timedelta, time


def can_mark_exit(entry_time, now):
    """Una salida explícita requiere al menos 60 segundos desde la entrada."""
    if isinstance(entry_time, str):
        entry_time = time.fromisoformat(entry_time)
    return (now - datetime.combine(now.date(), entry_time)).total_seconds() >= 60


def as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def working_dates(start, end):
    start, end = as_date(start), as_date(end)
    return {start + timedelta(days=i) for i in range((end - start).days + 1)
            if (start + timedelta(days=i)).weekday() != 6}


def absent_dates(start, end, attended, licenses):
    expected = working_dates(start, end)
    justified = set()
    for license in licenses:
        justified.update(working_dates(max(start, as_date(license.FechaInicio)),
                                       min(end, as_date(license.FechaFin))))
    return expected - ({as_date(day) for day in attended} | justified)


def vacation_days_consumed(licenses, hire_date, cutoff):
    """DiasOtorgados distribuidos en días calendario, sólo dentro del empleo/corte.

    El esquema registra licencias concedidas sin estados de consumo o pago separado.
    PagoEmpleador/PagoINSS son porcentajes, no días ni indicadores de pago: una
    licencia de vacaciones consume sus días concedidos aunque cambie ese porcentaje.
    Una licencia futura no consume; una en curso consume la fracción transcurrida.
    """
    consumed = 0.0
    for license in licenses:
        if license.TipoLicencia != 'Vacaciones':
            continue
        start, end = as_date(license.FechaInicio), as_date(license.FechaFin)
        days = float(license.DiasOtorgados)
        if end < start or days < 0:
            raise ValueError('Licencia de vacaciones con fechas o días inválidos.')
        clipped_start, clipped_end = max(start, hire_date), min(end, cutoff)
        if clipped_start <= clipped_end:
            consumed += days * ((clipped_end - clipped_start).days + 1) / ((end - start).days + 1)
    return consumed


def liquidation(employee, cutoff, reason, recent_salaries, licenses):
    """Conserva las tasas y fórmulas existentes; descuenta vacaciones concedidas."""
    hire_date, cutoff = as_date(employee.FechaIngreso), as_date(cutoff)
    if cutoff < hire_date:
        raise ValueError('La fecha de egreso no puede ser anterior al ingreso.')
    salary = float(employee.SalarioBase)
    daily_salary = salary / 30
    worked_days = (cutoff - hire_date).days
    years, remaining_months = worked_days // 365, (worked_days % 365) // 30
    earned = worked_days * (30 / 365)
    consumed = vacation_days_consumed(licenses, hire_date, cutoff)
    pending = max(0.0, earned - consumed)
    vacation_salary = (sum(recent_salaries) / len(recent_salaries) if recent_salaries else salary) / 30
    vacation_gross = pending * vacation_salary
    vacation_inss = vacation_gross * 0.07
    maximum_salary = max(recent_salaries) if recent_salaries else salary
    cycle_start = date(cutoff.year if cutoff.month == 12 else cutoff.year - 1, 12, 1)
    bonus_days = (cutoff - max(cycle_start, hire_date)).days + 1
    bonus = maximum_salary * (bonus_days / 365.0)
    applies = reason in ('Despido Injustificado', 'Renuncia Voluntaria')
    compensation_days = 0
    if applies:
        compensation_days = min(min(years, 3) * 30 + max(0, years - 3) * 20
                                + remaining_months * (2.5 if years < 3 else 1.667), 150)
    compensation = compensation_days * daily_salary
    compensation_ir = max(0, compensation - 500000) * 0.15
    return {
        'empleado': employee.NombreCompleto,
        'fecha_ingreso': hire_date.strftime('%d/%m/%Y'),
        'fecha_egreso': cutoff.strftime('%d/%m/%Y'),
        'dias_trabajados': worked_days, 'anios': years, 'meses_fraccion': remaining_months,
        'salario_base': salary, 'salario_diario': round(daily_salary, 2),
        'vacaciones': {
            'dias': round(pending, 2), 'dias_devengados': round(earned, 2),
            'dias_consumidos': round(consumed, 2),
            'salario_diario_usado': round(vacation_salary, 2),
            'monto_bruto': round(vacation_gross, 2), 'inss': round(vacation_inss, 2),
            'neto': round(vacation_gross - vacation_inss, 2),
        },
        'aguinaldo': {'salario_max_6m': maximum_salary, 'dias_ciclo': bonus_days,
                      'monto': round(bonus, 2), 'nota': 'Exento de INSS e IR'},
        'indemnizacion': {
            'aplica': applies, 'motivo': reason, 'dias': round(compensation_days, 2),
            'monto_bruto': round(compensation, 2), 'ir': round(compensation_ir, 2),
            'neto': round(compensation - compensation_ir, 2),
            'nota': 'Exento INSS. IR exento hasta C$500,000',
        },
        'total_liquidacion': round(vacation_gross - vacation_inss + bonus + compensation - compensation_ir, 2),
        'motivo': reason,
    }
