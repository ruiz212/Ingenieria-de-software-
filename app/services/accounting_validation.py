"""Invariantes puras de partida doble, sin redondear los importes recibidos."""
from decimal import Decimal


def validate_double_entry(lines):
    """Valida pares (Debe, Haber) Decimal ya normalizados por cada consumidor."""
    if len(lines) < 2:
        raise ValueError('El asiento requiere al menos dos líneas.')
    for debit, credit in lines:
        if not debit.is_finite() or not credit.is_finite() or min(debit, credit) < 0:
            raise ValueError('Los importes contables deben ser finitos y no negativos.')
        if (debit > 0) == (credit > 0):
            raise ValueError('Cada línea debe tener un importe positivo en Debe o Haber, nunca en ambos.')
    debit_total = sum((debit for debit, _ in lines), Decimal('0'))
    credit_total = sum((credit for _, credit in lines), Decimal('0'))
    if debit_total != credit_total:
        raise ValueError(
            f'Partida doble violada: Debe ({debit_total}) != Haber ({credit_total}). '
            f'Diferencia: {abs(debit_total - credit_total)}')
    if debit_total <= 0:
        raise ValueError('El asiento debe tener un importe total positivo.')
