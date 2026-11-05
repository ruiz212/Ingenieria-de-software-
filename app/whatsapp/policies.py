from datetime import datetime, timedelta
from app.services.business_time import business_now


def delivery_date(value, hours=24, now=None):
    try:
        date = datetime.fromisoformat(value)
        if date.tzinfo is not None:
            raise ValueError()
        if date < (now or business_now()) + timedelta(hours=hours):
            raise ValueError()
        return date
    except (ValueError, TypeError):
        raise ValueError(f'La entrega requiere fecha y hora de Nicaragua con {hours} horas de anticipación.') from None
