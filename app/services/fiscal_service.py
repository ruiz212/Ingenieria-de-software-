"""Facturación calculada en servidor e instantáneas para reimpresión."""
import json
from decimal import Decimal
from app.db import execute_sp, is_sqlserver_cursor
from app.services.validation import amount, positive_int, required_text


def audit(cursor, user_id, action, entity, entity_id, detail, ip=None):
    detail_json = json.dumps(detail, ensure_ascii=False, default=str)
    execute_sp(
        cursor,
        'ventas.sp_RegistrarEventoFiscalOperacion',
        (user_id, action, entity, entity_id, detail_json, ip),
        fallback_sql='INSERT INTO BitacoraFiscal(UsuarioID,Accion,Entidad,EntidadID,Detalle,IP) VALUES(?,?,?,?,?,?)',
    )


def configuration(cursor):
    execute_sp(
        cursor,
        'seguridad.sp_ObtenerConfiguracionGlobal',
        fallback_sql='SELECT Clave, Valor FROM ConfiguracionSistema',
    )
    return {r[0]: r[1] for r in cursor.fetchall()}


def next_invoice(cursor, serie='FAC'):
    execute_sp(
        cursor,
        'ventas.sp_SiguienteNumeroFactura',
        (serie,),
        fallback_sql='UPDATE SecuenciasFiscales WITH (UPDLOCK,HOLDLOCK) SET Ultimo=Ultimo+1 OUTPUT INSERTED.Ultimo WHERE Serie=?',
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError('La serie fiscal no está configurada. Ejecute la migración fiscal.')
    seq_val = getattr(row, 'Ultimo', None)
    if seq_val is None:
        seq_val = row[0] if str(row[0]).isdigit() else row[1]
    return f'{serie}-{int(seq_val):08d}'


def calculate_sale(cursor, items, config):
    if not isinstance(items, list) or not 1 <= len(items) <= 200:
        raise ValueError('El carrito debe contener entre 1 y 200 líneas.')
    regime = config.get('fiscal_regimen', 'Pendiente')
    if regime != 'Pendiente':
        for key in ('fiscal_razon_social', 'fiscal_ruc', 'fiscal_direccion', 'fiscal_telefono', 'fiscal_autorizacion'):
            required_text(config.get(key), key.replace('fiscal_', ''), 255)
    lines = []
    seen_cotizaciones = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Línea de carrito inválida.')
        raw_id = str(item.get('id', ''))
        quantity = positive_int(item.get('cantidad'), 'Cantidad')
        cotizacion_id = None
        if raw_id.startswith('custom_'):
            cotizacion_id = positive_int(raw_id.split('_', 1)[1], 'Cotización')
            if cotizacion_id in seen_cotizaciones:
                raise ValueError('La cotización personalizada solo puede convertirse en factura una única vez.')
            seen_cotizaciones.add(cotizacion_id)
            execute_sp(
                cursor,
                'crm.sp_ObtenerCotizacionParaCalculoVenta',
                (cotizacion_id,),
                fallback_sql=(
                    "SELECT ID, Especificaciones, PrecioCotizado FROM Cotizaciones WITH (UPDLOCK, HOLDLOCK) "
                    "WHERE ID=? AND Estado IN ('Cotizada', 'Aceptada') AND PrecioCotizado IS NOT NULL"
                ),
            )
            cot_row = cursor.fetchone()
            if not cot_row or (len(cot_row) > 3 and cot_row[3] not in ('Cotizada', 'Aceptada')):
                raise ValueError('La cotización personalizada no existe, ya fue facturada o aún no tiene precio autorizado.')
            execute_sp(
                cursor,
                'catalogo.sp_ObtenerProductoBaseParaCotizacion',
                fallback_sql=(
                    "SELECT TOP 1 ID, TasaIVA, MotivoExencion FROM Productos "
                    "WHERE Activo=1 ORDER BY EsFicticio DESC, ID ASC"
                ),
            )
            base_prod = cursor.fetchone()
            if not base_prod:
                raise ValueError('No hay un producto base activo para asociar la cotización.')
            product_id = base_prod[0]
            name = f'Pastel Personalizado (#COT-{cotizacion_id:04d})'
            base = cot_row[2]
            discount = Decimal('0')
            tax_rate = base_prod[1]
            reason = base_prod[2]
        else:
            product_id = positive_int(raw_id.split('_')[0], 'Producto')
            execute_sp(
                cursor,
                'catalogo.sp_ObtenerProductoParaCalculoVenta',
                (product_id,),
                fallback_sql='SELECT Nombre,PrecioBase,PorcentajeDescuento,TasaIVA,MotivoExencion,EsFicticio FROM Productos WHERE ID=? AND Activo=1',
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError('El producto ya no está disponible. Actualice el carrito.')
            name, base, discount, tax_rate, reason, fictitious = row
        # Las bases personalizables usan exclusivamente el precio del catálogo o cotización autorizada.
        base_price = amount(base)
        discount = amount(discount, 'Descuento', maximum=Decimal('100'))
        discounted_base = amount(base_price * (1 - discount / 100))
        extras = []
        extras_total = Decimal('0')
        detail = item.get('detalle_ingredientes') or {}
        if not isinstance(detail, dict) or not isinstance(detail.get('ingredientes', []), list):
            raise ValueError('Ingredientes inválidos.')
        for extra in detail.get('ingredientes', []):
            if not isinstance(extra, dict):
                raise ValueError('Ingrediente inválido.')
            ing_name = required_text(extra.get('nombre'), 'Ingrediente', 100)
            execute_sp(
                cursor,
                'catalogo.sp_ObtenerIngredientePorNombreActivo',
                (ing_name,),
                fallback_sql='SELECT ID,Nombre,PrecioAdicional FROM Ingredientes WHERE Nombre=? AND Activo=1',
            )
            ingredient = cursor.fetchone()
            if not ingredient:
                raise ValueError('Ingrediente no disponible.')
            ing_price = amount(ingredient[2])
            extras_total += ing_price
            extras.append({'id':ingredient[0], 'nombre':ingredient[1], 'precio':float(ing_price)})
        price = amount(base_price + extras_total)
        unit_price = amount(discounted_base + extras_total)
        subtotal = amount(unit_price * quantity)
        rate = Decimal('0')
        if regime == 'General':
            if tax_rate is None:
                raise ValueError(f'Configure el tratamiento de IVA de {name} en el catálogo fiscal.')
            rate = amount(tax_rate, 'IVA', maximum=Decimal('100'))
            if rate == 0 and not reason:
                raise ValueError(f'Indique el fundamento de exención o tasa cero de {name}.')
        tax = amount(subtotal * rate / 100)
        line_data = {'id':product_id, 'nombre':name, 'cantidad':quantity, 'precio':float(unit_price),
            'precio_lista':float(price), 'descuento':float(amount(price*quantity-subtotal)),
            'subtotal':float(subtotal), 'iva':float(tax), 'tasa_iva':float(rate),
            'motivo_exencion': reason if rate == 0 else '',
            'detalle_ingredientes':{'precio_base': float(discounted_base), 'ingredientes':extras}}
        if cotizacion_id is not None:
            line_data['cotizacion_id'] = cotizacion_id
        lines.append(line_data)
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
