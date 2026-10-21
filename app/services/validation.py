"""Validación compartida de cantidades y moneda nacional."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def amount(value, label='Monto', minimum=Decimal('0'), maximum=Decimal('99999999.99')):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < minimum or number > maximum:
            raise ValueError()
        return number.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f'{label}: ingrese un número entre {minimum} y {maximum}.') from None


def positive_int(value, label='Cantidad', maximum=100000):
    number = amount(value, label, Decimal('1'), Decimal(maximum))
    if Decimal(str(value)) != number.to_integral_value():
        raise ValueError(f'{label}: debe ser un entero positivo.')
    return int(number)


def required_text(value, label, maximum=200):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f'{label}: es obligatorio y admite hasta {maximum} caracteres.')
    return value.strip()
