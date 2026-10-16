"""Una fecha comercial consistente aunque Flask y SQL estén en zonas diferentes."""
from datetime import datetime, timedelta, timezone

NICARAGUA = timezone(timedelta(hours=-6), name='America/Managua')


def business_now():
    """DATETIME comercial local, sin zona y a segundos para evitar redondeo de SQL DATETIME."""
    return datetime.now(NICARAGUA).replace(tzinfo=None, microsecond=0)


def invoice_time_evidence(recorded, document, linked_entry=None):
    """No cambia la fuente. Solo resuelve hora histórica cuando hay evidencia concordante.

    Las versiones anteriores mezclaban GETDATE() UTC de Azure con datetime.now()
    local. Un recibo legado y su asiento deben concordar antes de adoptar su fecha.
    Sin evidencia suficiente se mantiene la fecha original y se pide revisión.
    """
    evidence = dict(fecha=recorded, fecha_bd=recorded, criterio_fecha='REGISTRO_ORIGINAL',
                    fecha_por_revisar=False, fecha_normalizada=False)
    if not isinstance(document, dict):
        return evidence
    try:
        printed = datetime.strptime(f'{document["fecha"]} {document["hora"]}', '%d/%m/%Y %H:%M:%S')
    except (KeyError, TypeError, ValueError):
        return evidence
    explicit = document.get('zona_horaria') == 'America/Managua'
    supported = linked_entry is not None and abs((printed - linked_entry).total_seconds()) <= 300
    difference = (recorded - printed).total_seconds()
    if abs(difference) <= 300:
        return evidence
    if (explicit or supported) and abs(difference - 21600) <= 300:
        evidence.update(fecha=printed, criterio_fecha='COMPROBANTE_Y_ASIENTO' if supported else 'COMPROBANTE_CON_ZONA',
                        fecha_normalizada=True)
    else:
        evidence['fecha_por_revisar'] = True
    return evidence


def reversal_time_evidence(recorded, reversal):
    if recorded is not None and reversal is not None and abs((recorded - reversal).total_seconds() - 21600) <= 300:
        return reversal
    return recorded
