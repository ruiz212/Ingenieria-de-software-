"""Diagnóstico interno determinista. No contiene tasas ni reglas tributarias oficiales."""
import calendar
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from app.services.accounting_validation import validate_double_entry

ENGINE_VERSION = 'dgi-interno-1.2'
NOTICE = 'SIMULACIÓN ACADÉMICA — NO VÁLIDA PARA PRESENTACIÓN ANTE LA DGI'
BLOCK = 'ERROR_BLOQUEANTE'
WARN = 'ADVERTENCIA'
INFO = 'INFORMATIVO'

# Metadatos versionados: la severidad expresa confiabilidad técnica, no gravedad legal.
RULES = {
    'PERFIL': ('Configuración fiscal pendiente', INFO),
    'VIGENCIA': ('Vigencia del perfil por revisar', INFO),
    'IMPORTE': ('Importe inválido', BLOCK),
    'ARITMETICA': ('Suma del documento inconsistente', BLOCK),
    'DETALLE': ('Detalle de factura inconsistente', BLOCK),
    'NUMERO': ('Falta número de documento', BLOCK),
    'DUPLICADO': ('Posible documento duplicado', WARN),
    'ESTADO': ('Estado de factura desconocido', BLOCK),
    'FUERA_PERIODO': ('Documento fuera del período de emisión', INFO),
    'ANULACION': ('Anulación en un período diferente', BLOCK),
    'HISTORICO': ('Factura histórica sin instantánea', WARN),
    'SIN_COMPRAS': ('No hay compras registradas', INFO),
    'SOPORTE': ('Compra sin soporte completo', BLOCK),
    'SIN_CONTABILIDAD': ('Información contable insuficiente', BLOCK),
    'CONCILIACION': ('Ventas e ingresos contables no coinciden', BLOCK),
    'BORRADOR_CONTABLE': ('Asiento contable en borrador', WARN),
    'PARTIDA_DOBLE': ('Asiento desbalanceado', BLOCK),
    'NORMATIVA': ('Revisión normativa pendiente', INFO),
    'PROVEEDOR_RUC': ('Identificación fiscal de proveedores no disponible', INFO),
    'FECHA_FUENTE': ('Fechas de origen requieren revisión', WARN),
    'DOCUMENTO': ('Instantánea de documento ilegible', BLOCK),
}
CONFIG_RULES = {'PERFIL', 'VIGENCIA'}
CONTEXT_RULES = {'SIN_COMPRAS', 'NORMATIVA', 'PROVEEDOR_RUC'}


def category(code):
    return 'CONFIGURACION' if code in CONFIG_RULES else ('CONTEXTO' if code in CONTEXT_RULES else 'DATOS')


def rule_catalog():
    return [dict(codigo=code, nombre=name, severidad=severity, categoria=category(code),
                 version=ENGINE_VERSION, fuente='Integridad y conciliación del sistema',
                 vigente_desde='2026-10-15', vigente_hasta=None, habilitada=True,
                 responsable_aprobacion='Equipo del proyecto (reglas internas)')
            for code, (name, severity) in RULES.items()]


def json_dump(value):
    def encode(item):
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        if isinstance(item, Decimal):
            return str(item)
        raise TypeError(f'Tipo no serializable: {type(item).__name__}')
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      default=encode, allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(json_dump(value).encode('utf-8')).hexdigest()


def monthly_period(value):
    try:
        start = date.fromisoformat(str(value) + '-01')
        if not 2000 <= start.year <= 2100:
            raise ValueError()
    except (TypeError, ValueError) as error:
        raise ValueError('Seleccione un mes entre 2000 y 2100 (AAAA-MM).') from error
    return start, start.replace(day=calendar.monthrange(start.year, start.month)[1])


def money(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or abs(result) > Decimal('99999999999999.99'):
            raise ValueError()
        return result
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError('Importe ausente, no finito o fuera de rango.') from error


def day(value):
    return date.fromisoformat(str(value)[:10])


def analyze(snapshot):
    """Entradas normalizadas con IDs reales. Resultados monetarios como decimales en texto."""
    start, end = day(snapshot['desde']), day(snapshot['hasta'])
    if start > end:
        raise ValueError('Período invertido.')
    findings, sales, purchases, journals = [], [], [], []
    totals = {key: Decimal('0') for key in (
        'ventas_base', 'ventas_iva', 'ventas_total', 'compras_total', 'compras_iva', 'ingresos_contables')}

    def add(code, detail, action, kind=None, entity_id=None, difference=None):
        name, severity = RULES[code]
        findings.append(dict(id=fingerprint([code, kind, entity_id, detail])[:24],
                             codigo=code, nombre=name, severidad=severity,
                             detalle=detail, accion=action, tipo=kind, origen_id=entity_id, categoria=category(code),
                             diferencia=str(difference) if difference is not None else None))

    profile = snapshot['perfil']
    missing = [label for key, label in [('fiscal_razon_social', 'razón social'), ('fiscal_ruc', 'RUC'),
               ('dgi_responsable', 'responsable'), ('dgi_obligaciones', 'obligación'),
               ('dgi_vigente_desde', 'inicio de vigencia')]
               if not profile.get(key, '').strip()]
    if profile.get('fiscal_regimen', 'Pendiente') not in ('General', 'Cuota fija'):
        missing.append('régimen')
    if profile.get('dgi_obligaciones') and snapshot['obligacion'] not in profile['dgi_obligaciones'].splitlines():
        missing.append('obligación seleccionada en el perfil')
    if missing:
        add('PERFIL', 'Falta configurar: ' + ', '.join(missing) + '.',
            'Complete el perfil cuando disponga de datos verificados. Puede continuar el análisis y reportar los datos internos sin inventar RUC ni régimen.')
    try:
        since = day(profile['dgi_vigente_desde']) if profile.get('dgi_vigente_desde') else None
        until = day(profile['dgi_vigente_hasta']) if profile.get('dgi_vigente_hasta') else None
        if (since and since > start) or (until and until < end) or (since and until and since > until):
            add('VIGENCIA', 'El perfil no cubre el período completo.', 'Revise la vigencia y genere otra revisión.')
    except (ValueError, KeyError):
        add('VIGENCIA', 'Las fechas del perfil son inválidas.', 'Corrija las fechas del perfil.')

    seen = {}
    for source in snapshot['ventas']:
        row = dict(source)
        row['incluida'] = False
        sales.append(row)
        rid, number = row['id'], str(row.get('numero') or '').strip()
        if row.get('fecha_por_revisar'):
            add('FECHA_FUENTE', 'La hora del registro difiere del comprobante y no hay evidencia suficiente para normalizarla.',
                'Compare comprobante y asiento. Se conserva la fecha de la base; no se cambia el documento.', 'factura', rid)
        if row.get('documento_corrupto'):
            add('DOCUMENTO', 'La instantánea guardada no es un documento JSON válido.',
                'Revise el respaldo original. No se reconstruye ni reemplaza el documento automáticamente.', 'factura', rid)
        issued = day(row['fecha'])
        voided = day(row['anulada_en']) if row.get('anulada_en') else None
        if not start <= issued <= end:
            add('FUERA_PERIODO', 'Emisión fuera del período: se excluye de ventas.', 'Consulte el período de emisión.', 'factura', rid)
            if voided and start <= voided <= end:
                add('ANULACION', 'La anulación corresponde a una factura de otro período.',
                    'Revise con contabilidad el documento de ajuste; no se genera automáticamente.', 'factura', rid)
            continue
        if row.get('estado') not in ('Emitida', 'Anulada'):
            add('ESTADO', 'Estado no reconocido; no se incluye en el resumen.', 'Revise el documento en control fiscal.', 'factura', rid)
            continue
        if row['estado'] == 'Anulada':
            if not voided:
                add('ANULACION', 'Factura anulada sin fecha de anulación.', 'Revise el soporte y la fecha en origen.', 'factura', rid)
                continue
            if voided < issued:
                add('ANULACION', 'La anulación precede a la emisión.', 'Revise las fechas y el soporte original.', 'factura', rid)
                continue
            if voided <= end:
                continue
            add('ANULACION', 'La anulación ocurrió después del período; se conserva la emisión histórica.',
                'Revise el ajuste en el período de anulación con contabilidad.', 'factura', rid)
        if not number:
            add('NUMERO', 'Factura sin número.', 'Revise el soporte en el módulo propietario.', 'factura', rid)
        elif number.casefold() in seen:
            add('DUPLICADO', f'Número repetido; también aparece en factura #{seen[number.casefold()]}.',
                'Compare series y documentos originales antes de corregir.', 'factura', rid)
        else:
            seen[number.casefold()] = rid
        try:
            base, tax, total = (money(row.get(k)) for k in ('base', 'iva', 'total'))
            if min(base, tax, total) < 0:
                raise ValueError()
            if base + tax != total:
                add('ARITMETICA', f'Base {base} + IVA registrado {tax} no coincide con total {total}.',
                    'Revise el documento y un ajuste autorizado en el módulo propietario.', 'factura', rid)
            details = row.get('detalles', [])
            if not details or sum((money(d['subtotal']) for d in details), Decimal('0')) != base:
                add('DETALLE', 'La suma del detalle no coincide con la base o el detalle está ausente.',
                    'Compare detalle y comprobante original; no edite una factura emitida.', 'factura', rid)
            if any(money(d.get('cantidad')) <= 0 or money(d.get('precio')) < 0 or
                   money(d['subtotal']) < 0 or money(d['precio']) * money(d['cantidad']) != money(d['subtotal'])
                   for d in details):
                add('DETALLE', 'Cantidad, precio o subtotal de una línea no son consistentes.',
                    'Compare cantidad × precio unitario neto con el subtotal del detalle.', 'factura', rid)
            row['incluida'] = True
            for key, value in [('ventas_base', base), ('ventas_iva', tax), ('ventas_total', total)]:
                totals[key] += value
        except (ValueError, KeyError):
            add('IMPORTE', 'Factura con importes inválidos; se excluye del resumen.', 'Revise el soporte en origen.', 'factura', rid)
        if not row.get('documento'):
            add('HISTORICO', 'No hay instantánea fiscal conservada para esta factura.', 'Consulte el soporte histórico original.', 'factura', rid)

    seen = {}
    for source in snapshot['compras']:
        row = dict(source)
        row['incluida'] = False
        purchases.append(row)
        rid = row['id']
        if not start <= day(row['fecha']) <= end:
            add('FUERA_PERIODO', 'Compra fuera del período; se excluye.', 'Revise el período de registro.', 'compra', rid)
            continue
        if not row.get('numero') or not row.get('proveedor'):
            add('SOPORTE', 'Falta comprobante o nombre del proveedor.', 'Revise el soporte en Inventario.', 'compra', rid)
        try:
            total, tax = money(row.get('total')), money(row.get('iva'))
            if min(total, tax) < 0 or tax > total or money(row.get('cantidad')) <= 0:
                raise ValueError()
            # ComprasMateriaPrima almacena líneas: varias materias de una factura no son duplicados.
            key = (row.get('proveedor_id'), str(row.get('numero', '')).strip().casefold(),
                   row.get('materia_id'), str(row['fecha'])[:10], total, money(row['cantidad']))
            if key in seen:
                add('DUPLICADO', f'Línea de compra similar a #{seen[key]}.',
                    'Confirme si son líneas legítimas del mismo documento.', 'compra', rid)
            seen[key] = rid
            row['incluida'] = True
            totals['compras_total'] += total
            totals['compras_iva'] += tax
        except ValueError:
            add('IMPORTE', 'Compra con importe, cantidad o IVA registrado inválido.', 'Revise el comprobante y el registro.', 'compra', rid)
    if not any(r['incluida'] for r in purchases):
        add('SIN_COMPRAS', 'No hay compras consolidadas. No permite concluir que el crédito fiscal sea cero.', 'Confirme la integridad de los soportes del período.')
    if purchases:
        add('PROVEEDOR_RUC', 'El catálogo de proveedores no almacena RUC.', 'Solicite y conserve soportes; no se valida crédito fiscal.')

    posted = 0
    for row in snapshot['asientos']:
        if not start <= day(row['fecha']) <= end:
            continue
        journals.append(row)
        if row['estado'] == 'Borrador':
            add('BORRADOR_CONTABLE', 'El asiento está en borrador y se excluye del mayor.', 'Revise y contabilice mediante el módulo contable.', 'asiento', row['id'])
            continue
        if row['estado'] not in ('Contabilizado', 'Anulado'):
            add('SIN_CONTABILIDAD', 'El asiento tiene un estado desconocido.', 'Revise el registro contable.', 'asiento', row['id'])
            continue
        try:
            amounts = [(money(d['debe']), money(d['haber'])) for d in row['detalles']]
            debit = sum((value for value, _ in amounts), Decimal('0'))
            credit = sum((value for _, value in amounts), Decimal('0'))
            try:
                validate_double_entry(amounts)
            except ValueError as error:
                add('PARTIDA_DOBLE', f'{error} Debe {debit}; Haber {credit}.',
                    'Revise y corrija mediante ajuste o reversión.', 'asiento', row['id'])
            totals['ingresos_contables'] += sum((money(d['haber']) - money(d['debe'])
                for d in row['detalles'] if d['clase'] == 'Ingreso'), Decimal('0'))
            posted += 1
        except (ValueError, KeyError):
            add('IMPORTE', 'Detalle contable con importe inválido.', 'Revise el asiento original.', 'asiento', row['id'])
    if not posted and any(r['incluida'] for r in sales):
        add('SIN_CONTABILIDAD', 'Hay ventas, pero no hay asientos contabilizados en el período.', 'Revise la integridad del mayor y las fechas de contabilización.')
    difference = totals['ventas_base'] - totals['ingresos_contables']
    if difference:
        add('CONCILIACION', f'Base de ventas {totals["ventas_base"]} − ingresos contables {totals["ingresos_contables"]} = {difference} C$.',
            'Compare los documentos de Ventas y Trazabilidad. Revise fechas, ajustes y registros faltantes; la diferencia no es impuesto ni multa.', difference=difference)
    add('NORMATIVA', 'No hay reglas ni plantilla oficial validadas para esta obligación y período.',
        'El responsable debe verificar régimen, obligación, guía y plantilla vigentes antes de una fase oficial.')
    totals['diferencia'] = difference
    return dict(motor=ENGINE_VERSION, aviso=NOTICE, totales={k: str(v) for k, v in totals.items()},
                hallazgos=findings, ventas=sales, compras=purchases, asientos=journals,
                bloqueantes=sum(f['severidad'] == BLOCK for f in findings),
                advertencias=sum(f['severidad'] == WARN for f in findings),
                pendientes_configuracion=sum(f['categoria'] == 'CONFIGURACION' for f in findings),
                datos_consistentes=not any(f['severidad'] in (BLOCK, WARN) for f in findings),
                fechas_normalizadas=sum(bool(r.get('fecha_normalizada')) for r in sales),
                supuestos=[
                    'Consolidación interna de una empresa; moneda registrada: córdobas (NIO).',
                    'Fechas nuevas en hora de Nicaragua. Un histórico UTC se interpreta en fecha del comprobante solo si concuerda con el asiento o tiene zona explícita; el registro original se conserva.',
                    'Perfil fiscal pendiente no equivale a un error contable. La validación interna no acredita régimen ni autorización fiscal.',
                    'Ventas: base registrada después de descuentos. IVA mostrado como registro, sin validar procedencia fiscal.',
                    'Conciliación: base de ventas menos Haber−Debe de cuentas clase Ingreso. No compara el total con IVA.',
                    'El mayor incluye originales anulados y sus contrapartidas; excluye borradores.',
                    'Las compras son líneas de materia prima; el IVA documentado no equivale a crédito deducible.',
                    'No se calculan impuestos por pagar, multas, retenciones ni sanciones.',
                    'No hay envío a VET ni compatibilidad oficial certificada.',
                ])
