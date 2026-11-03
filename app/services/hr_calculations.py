"""Cálculos de RRHH puros, compartidos por API y reportes."""
from datetime import date, datetime, timedelta, time
from app.services.business_time import business_now


class ResultadoHorarioAsistencia(dict):
    """Diccionario de resultado de clasificación de asistencia con acceso por atributo."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _extraer_campo(obj, nombre, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(nombre, default)
    return getattr(obj, nombre, default)


def _normalizar_hora(valor):
    if valor is None or valor == '':
        return None
    if isinstance(valor, datetime):
        return valor.time()
    if isinstance(valor, time):
        return valor
    if isinstance(valor, str):
        return time.fromisoformat(valor)
    return None


def resolver_horario_y_clasificar_asistencia(empleado, turno=None, ahora=None, tolerancia_default=15):
    """Política única y determinista de horario y tolerancia para Kiosco y Administración.

    Prioriza la HoraEntrada asignada al empleado si existe; de lo contrario utiliza la
    HoraEntrada del turno activo por defecto, aplicando la misma tolerancia en minutos.
    """
    if ahora is None:
        ahora_dt = business_now()
    elif isinstance(ahora, datetime):
        ahora_dt = ahora
    elif isinstance(ahora, time):
        ahora_dt = datetime.combine(business_now().date(), ahora)
    elif isinstance(ahora, str):
        if 'T' in ahora or '-' in ahora or ' ' in ahora:
            ahora_dt = datetime.fromisoformat(ahora)
        else:
            ahora_dt = datetime.combine(business_now().date(), time.fromisoformat(ahora))
    else:
        raise TypeError('Formato de fecha/hora inválido para asistencia.')

    turno_id_raw = _extraer_campo(empleado, 'TurnoID')
    if turno_id_raw is None:
        turno_id_raw = _extraer_campo(turno, 'ID')
    turno_id = int(turno_id_raw) if turno_id_raw is not None else 1

    hora_entrada_emp = _normalizar_hora(_extraer_campo(empleado, 'HoraEntrada'))
    hora_entrada_turno = _normalizar_hora(_extraer_campo(turno, 'HoraEntrada'))
    hora_entrada_objetivo = hora_entrada_emp if hora_entrada_emp is not None else hora_entrada_turno
    fuente_horario = 'empleado' if hora_entrada_emp is not None else ('turno' if hora_entrada_turno is not None else 'ninguno')

    tol_emp = _extraer_campo(empleado, 'ToleranciaMinutos')
    tol_turno = _extraer_campo(turno, 'ToleranciaMinutos')
    if tol_emp is not None:
        tolerancia_minutos = int(tol_emp)
    elif tol_turno is not None:
        tolerancia_minutos = int(tol_turno)
    else:
        tolerancia_minutos = int(tolerancia_default)

    estado = 'A Tiempo'
    hora_limite = None
    limite_dt = None
    if hora_entrada_objetivo is not None:
        limite_dt = datetime.combine(ahora_dt.date(), hora_entrada_objetivo) + timedelta(minutes=tolerancia_minutos)
        hora_limite = limite_dt.time()
        if ahora_dt > limite_dt:
            estado = 'Llegada Tardia'

    return ResultadoHorarioAsistencia(
        estado=estado,
        turno_id=turno_id,
        hora_entrada=hora_entrada_objetivo,
        tolerancia_minutos=tolerancia_minutos,
        hora_limite=hora_limite,
        limite_dt=limite_dt,
        fuente_horario=fuente_horario,
    )


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
    return date.fromisoformat(str(value))


def working_dates(start, end):
    start, end = as_date(start), as_date(end)
    if end < start:
        return set()
    return {start + timedelta(days=i) for i in range((end - start).days + 1)
            if (start + timedelta(days=i)).weekday() != 6}


def absent_dates(start, end, attended, licenses, as_of_date=None):
    start, end = as_date(start), as_date(end)
    cutoff = business_now().date() if as_of_date is None else as_date(as_of_date)
    effective_end = min(end, cutoff)
    if effective_end < start:
        return set()
    expected = working_dates(start, effective_end)
    justified = set()
    for license in licenses:
        lic_start = max(start, as_date(license.FechaInicio))
        lic_end = min(effective_end, as_date(license.FechaFin))
        if lic_start <= lic_end:
            justified.update(working_dates(lic_start, lic_end))
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
