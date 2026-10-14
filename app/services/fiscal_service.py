"""Facturación calculada en servidor e instantáneas para reimpresión."""
import json
from decimal import Decimal
from app.services.validation import amount, positive_int, required_text


def audit(cursor, user_id, action, entity, entity_id, detail, ip=None):
    cursor.execute('INSERT INTO BitacoraFiscal(UsuarioID,Accion,Entidad,EntidadID,Detalle,IP) VALUES(?,?,?,?,?,?)',
                   user_id, action, entity, entity_id, json.dumps(detail, ensure_ascii=False, default=str), ip)


def configuration(cursor):
    cursor.execute('SELECT Clave, Valor FROM ConfiguracionSistema')
    return {r[0]: r[1] for r in cursor.fetchall()}


def next_invoice(cursor, serie='FAC'):
    cursor.execute('UPDATE SecuenciasFiscales WITH (UPDLOCK,HOLDLOCK) SET Ultimo=Ultimo+1 OUTPUT INSERTED.Ultimo WHERE Serie=?', serie)
    row = cursor.fetchone()
    if not row:
        raise ValueError('La serie fiscal no está configurada. Ejecute la migración fiscal.')
    return f'{serie}-{row[0]:08d}'


def calculate_sale(cursor, items, config):
    if not isinstance(items, list) or not 1 <= len(items) <= 200:
        raise ValueError('El carrito debe contener entre 1 y 200 líneas.')
    regime = config.get('fiscal_regimen', 'Pendiente')
    if regime != 'Pendiente':
        for key in ('fiscal_razon_social', 'fiscal_ruc', 'fiscal_direccion', 'fiscal_telefono', 'fiscal_autorizacion'):
            required_text(config.get(key), key.replace('fiscal_', ''), 255)
    lines = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Línea de carrito inválida.')
        product_id = positive_int(str(item.get('id', '')).split('_')[0], 'Producto')
        quantity = positive_int(item.get('cantidad'), 'Cantidad')
        cursor.execute('SELECT Nombre,PrecioBase,PorcentajeDescuento,TasaIVA,MotivoExencion,EsFicticio FROM Productos WHERE ID=? AND Activo=1', product_id)
        row = cursor.fetchone()
        if not row:
            raise ValueError('El producto ya no está disponible. Actualice el carrito.')
        name, base, discount, tax_rate, reason, fictitious = row
        # Las bases personalizables usan exclusivamente el precio del catálogo.
        price = amount(base)
        extras = []
        detail = item.get('detalle_ingredientes') or {}
        if not isinstance(detail, dict) or not isinstance(detail.get('ingredientes', []), list):
            raise ValueError('Ingredientes inválidos.')
        for extra in detail.get('ingredientes', []):
            if not isinstance(extra, dict):
                raise ValueError('Ingrediente inválido.')
            cursor.execute('SELECT ID,Nombre,PrecioAdicional FROM Ingredientes WHERE Nombre=? AND Activo=1', required_text(extra.get('nombre'), 'Ingrediente',100))
            ingredient = cursor.fetchone()
            if not ingredient:
                raise ValueError('Ingrediente no disponible.')
            price += amount(ingredient[2])
            extras.append({'id':ingredient[0], 'nombre':ingredient[1], 'precio':float(ingredient[2])})
        discount = amount(discount, 'Descuento', maximum=Decimal('100'))
        unit_price = amount(price * (1-discount/100))
        subtotal = amount(unit_price * quantity)
        rate = Decimal('0')
        if regime == 'General':
            if tax_rate is None:
                raise ValueError(f'Configure el tratamiento de IVA de {name} en el catálogo fiscal.')
            rate = amount(tax_rate, 'IVA', maximum=Decimal('100'))
            if rate == 0 and not reason:
                raise ValueError(f'Indique el fundamento de exención o tasa cero de {name}.')
        tax = amount(subtotal * rate / 100)
        lines.append({'id':product_id, 'nombre':name, 'cantidad':quantity, 'precio':float(unit_price),
            'precio_lista':float(price), 'descuento':float(amount(price*quantity-subtotal)),
            'subtotal':float(subtotal), 'iva':float(tax), 'tasa_iva':float(rate),
            'motivo_exencion': reason if rate == 0 else '', 'detalle_ingredientes':{'ingredientes':extras}})
    subtotal = sum((amount(x['subtotal']) for x in lines), Decimal('0'))
    tax = sum((amount(x['iva']) for x in lines), Decimal('0'))
    return lines, subtotal, tax, subtotal+tax


def normalize_payments(payments, total, advance=None):
    if not isinstance(payments, list) or not 1 <= len(payments) <= 20:
        raise ValueError('Indique al menos un pago válido.')
    normalized = []
    for payment in payments:
        if not isinstance(payment, dict):
            raise ValueError('Pago inválido.')
        method = payment.get('metodo')
        if method not in ('Efectivo','Efectivo USD','Transferencia'):
            raise ValueError('Método de pago inválido.')
        value = amount(payment.get('monto'), 'Pago')
        reference = payment.get('referencia', '')
        if method == 'Transferencia' and value:
            required_text(reference, 'Referencia de transferencia',100)
        normalized.append({'metodo':method,'monto':value,'referencia':reference})
    paid = sum((p['monto'] for p in normalized), Decimal('0'))
    target = amount(advance) if advance is not None else total
    if advance is not None and target < amount(total * Decimal('0.5')):
        raise ValueError('El adelanto debe ser al menos el 50% del total.')
    if target > total or paid < target:
        raise ValueError('El pago es insuficiente o el adelanto supera el total.')
    change = paid-target
    if change > sum(p['monto'] for p in normalized if p['metodo'] in ('Efectivo','Efectivo USD')):
        raise ValueError('No se puede devolver cambio de una transferencia.')
    remaining = change
    for payment in normalized:
        if payment['metodo'] in ('Efectivo','Efectivo USD'):
            deducted = min(payment['monto'],remaining)
            payment['monto'] -= deducted
            remaining -= deducted
    return [p for p in normalized if p['monto'] > 0], change
