"""La tasa usada y su instantánea tienen la misma precisión en todos los cobros."""
from decimal import Decimal,InvalidOperation
from app.db import execute_sp


def official_usd_rate(cursor):
    row=execute_sp(
        cursor,
        'seguridad.sp_ObtenerValorConfiguracion',
        ('tipo_cambio_usd',),
        fallback_sql="SELECT Valor FROM ConfiguracionSistema WHERE Clave = 'tipo_cambio_usd'",
        fallback_params=(),
    ).fetchone()
    try:
        rate=Decimal(str(row.Valor if row else ''))
        if not rate.is_finite() or not Decimal('0') < rate <= Decimal('100000'):
            raise ValueError()
        rate=rate.quantize(Decimal('0.000001'))
        if rate <= 0:raise ValueError()
        return rate
    except (ValueError,InvalidOperation):
        raise ValueError('Configure un tipo de cambio USD válido antes del cobro o arqueo.') from None
