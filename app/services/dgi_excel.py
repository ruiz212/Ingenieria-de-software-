"""Exportador XLSX interno para el servidor Flask, sin procesos externos.

OOXML con valores tipados y texto literal: ningún dato del usuario crea fórmulas,
macros, relaciones externas ni enlaces ejecutables. No es un formato DGI.
"""
import io
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal
from xml.etree.ElementTree import Element, SubElement, tostring

from app.services.dgi_engine import NOTICE, money

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'


def report_amount(value):
    try:
        return money(value)
    except ValueError:
        return 'DATO INVÁLIDO: ' + str(value)


def _xml(element):
    return tostring(element, encoding='utf-8', xml_declaration=True)


def _letter(number):
    result = ''
    while number:
        number, rest = divmod(number - 1, 26)
        result = chr(65 + rest) + result
    return result


def workbook_tables(review, snapshot, result):
    totals = result['totales']
    summary = [
        ['Razón social', snapshot['perfil'].get('fiscal_razon_social', '')],
        ['Régimen declarado', snapshot['perfil'].get('fiscal_regimen', 'Pendiente')],
        ['Obligación declarada (sin validación normativa)', snapshot['obligacion']],
        ['Desde', date.fromisoformat(snapshot['desde'])], ['Hasta', date.fromisoformat(snapshot['hasta'])],
        ['Revisión / versión', f'{review["ID"]} / {review["Version"]}'],
        ['Estado de preparación interna', review['Estado']],
        ['Motor', result['motor']], ['Huella de las fuentes', review['Huella']],
        ['Generado por usuario', review['CreadoPor']], ['Aprobado por usuario', review.get('AprobadoPor')],
        ['Revisión humana', review.get('NotaRevision') or ''],
    ]
    labels = dict(ventas_base='Base registrada de ventas C$', ventas_iva='IVA registrado en ventas C$',
        ventas_total='Total registrado de ventas C$', compras_total='Compras registradas C$',
        compras_iva='IVA documentado en compras C$ (sin validar deducibilidad)',
        ingresos_contables='Ingresos contables netos C$', diferencia='Diferencia de conciliación C$')
    summary += [[labels[key], money(totals[key])] for key in labels]
    summary += [['Fórmula de conciliación', 'Base de ventas − ingresos contables (Haber − Debe de clase Ingreso)'],
                ['Errores bloqueantes', result['bloqueantes']],
                ['Resultado tributario oficial', 'Pendiente de validación normativa. No se calcula impuesto ni multa.']]
    sales = [[r['id'], r.get('numero') or '', datetime.fromisoformat(r['fecha']),
              report_amount(r['base']), report_amount(r['iva']), report_amount(r['total']), r['estado'],
              'Sí' if r['incluida'] else 'No', f'/admin/dgi/fuentes/factura/{r["id"]}',
              datetime.fromisoformat(r.get('fecha_bd',r['fecha'])), r.get('criterio_fecha','REGISTRO_ORIGINAL')]
             for r in result['ventas']]
    purchases = [[r['id'], r.get('numero') or '', datetime.fromisoformat(r['fecha']), r.get('proveedor') or '',
                  r['materia_id'], report_amount(r['cantidad']), report_amount(r['total']), report_amount(r['iva']),
                  'Sí' if r['incluida'] else 'No', f'/admin/dgi/fuentes/compra/{r["id"]}'] for r in result['compras']]
    findings = [[f['id'], f['codigo'], f['severidad'], f['detalle'], f['accion'],
                 f['tipo'] or 'Revisión', f['origen_id'], money(f['diferencia']) if f['diferencia'] is not None else None]
                for f in result['hallazgos']]
    trace = [[r['id'], r.get('numero'), datetime.fromisoformat(r['fecha']), r['estado'],
              d['cuenta'], d['nombre'], d['clase'], report_amount(d['debe']), report_amount(d['haber']),
              r.get('referencia') or ''] for r in result['asientos'] for d in r['detalles']]
    return [
        ('Resumen', ['Concepto', 'Valor'], summary, [58, 105]),
        ('Ventas', ['ID', 'Número', 'Fecha comercial', 'Base C$', 'IVA registrado C$', 'Total C$', 'Estado', 'Incluida', 'Origen', 'Fecha original BD', 'Criterio de fecha'],
         sales, [12, 25, 23, 22, 24, 22, 18, 15, 48, 23, 35]),
        ('Compras', ['ID', 'Comprobante', 'Fecha', 'Proveedor', 'Materia ID', 'Cantidad', 'Total C$', 'IVA documentado C$', 'Incluida', 'Origen'],
         purchases, [12, 24, 23, 34, 15, 18, 22, 26, 15, 48]),
        ('Hallazgos', ['ID hallazgo', 'Regla', 'Severidad técnica', 'Explicación', 'Acción correctiva', 'Origen', 'Origen ID', 'Diferencia C$'],
         findings, [30, 24, 28, 70, 80, 18, 14, 22]),
        ('Trazabilidad', ['Asiento ID', 'Número', 'Fecha', 'Estado', 'Cuenta', 'Nombre', 'Clase', 'Debe C$', 'Haber C$', 'Referencia'],
         trace, [15, 24, 23, 20, 24, 38, 22, 22, 22, 30]),
        ('Supuestos', ['N.º', 'Condiciones y límites'], [[i, v] for i, v in enumerate(result['supuestos'], 1)] +
         [[len(result['supuestos']) + 1, 'Origen: instantánea SQL de la revisión. No incluye credenciales ni datos de clientes.']], [12, 140]),
    ]


def export_xlsx(review, snapshot, result):
    tables = workbook_tables(review, snapshot, result)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        types = Element('Types', xmlns='http://schemas.openxmlformats.org/package/2006/content-types')
        for ext, content in [('rels', 'application/vnd.openxmlformats-package.relationships+xml'), ('xml', 'application/xml')]:
            SubElement(types, 'Default', Extension=ext, ContentType=content)
        for part, content in [('/xl/workbook.xml', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'),
                              ('/xl/styles.xml', 'application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml')] + [
            (f'/xl/worksheets/sheet{i}.xml', 'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml') for i in range(1, len(tables) + 1)]:
            SubElement(types, 'Override', PartName=part, ContentType=content)
        archive.writestr('[Content_Types].xml', _xml(types))
        relns = 'http://schemas.openxmlformats.org/package/2006/relationships'
        base = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
        rootrels = Element('Relationships', xmlns=relns)
        SubElement(rootrels, 'Relationship', Id='rId1', Type=base + 'officeDocument', Target='xl/workbook.xml')
        archive.writestr('_rels/.rels', _xml(rootrels))
        book = Element('workbook', xmlns=NS, **{'xmlns:r': base[:-1]})
        sheets = SubElement(book, 'sheets')
        rels = Element('Relationships', xmlns=relns)
        for index, (name, headers, data, widths) in enumerate(tables, 1):
            if len(data) > 1048572:
                raise ValueError('El detalle supera el límite de filas de Excel; use un período menor.')
            SubElement(sheets, 'sheet', name=name, sheetId=str(index), **{'r:id': f'rId{index}'})
            SubElement(rels, 'Relationship', Id=f'rId{index}', Type=base + 'worksheet', Target=f'worksheets/sheet{index}.xml')
            sheet = Element('worksheet', xmlns=NS)
            views = SubElement(sheet, 'sheetViews')
            view = SubElement(views, 'sheetView', workbookViewId='0', showGridLines='0')
            SubElement(view, 'pane', ySplit='4', topLeftCell='A5', activePane='bottomLeft', state='frozen')
            cols = SubElement(sheet, 'cols')
            for col, width in enumerate(widths, 1):
                SubElement(cols, 'col', min=str(col), max=str(col), width=str(width), customWidth='1')
            body = SubElement(sheet, 'sheetData')
            context = f'Brajher’s Cake. Período {snapshot["desde"]} a {snapshot["hasta"]}. Revisión {review["ID"]}, versión {review["Version"]}. {review["Estado"]}. NO APTO PARA PRESENTACIÓN DGI.'
            values = [[NOTICE], [context], [], headers] + data
            for row_index, values_row in enumerate(values, 1):
                height = 38 if row_index <= 2 else (32 if row_index == 4 else (66 if name in ('Hallazgos', 'Supuestos') else 42))
                row = SubElement(body, 'row', r=str(row_index), ht=str(height), customHeight='1')
                for col, value in enumerate(values_row, 1):
                    attrs = {'r': f'{_letter(col)}{row_index}', 's': '1' if row_index <= 2 else ('2' if row_index == 4 else '0')}
                    if value is None:
                        SubElement(row, 'c', **attrs)
                    elif isinstance(value, (int, Decimal)):
                        if isinstance(value, Decimal) and (name == 'Resumen' or 'C$' in headers[col - 1]):
                            attrs['s'] = '3'
                        SubElement(SubElement(row, 'c', t='n', **attrs), 'v').text = str(value)
                    elif isinstance(value, (date, datetime)):
                        attrs['s'] = '4'
                        epoch = datetime(1899, 12, 30)
                        stamp = datetime.combine(value, datetime.min.time()) if not isinstance(value, datetime) else value
                        number = Decimal(str((stamp - epoch).total_seconds())) / Decimal('86400')
                        SubElement(SubElement(row, 'c', t='n', **attrs), 'v').text = str(number)
                    else:
                        # inlineStr impide interpretación de =, +, -, @, tabs o espacios como fórmulas.
                        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', str(value))[:32767]
                        textnode = SubElement(SubElement(SubElement(row, 'c', t='inlineStr', **attrs), 'is'), 't',
                                              **{'xml:space': 'preserve'})
                        textnode.text = text
            merges = SubElement(sheet, 'mergeCells', count='2')
            for n in (1, 2):
                SubElement(merges, 'mergeCell', ref=f'A{n}:{_letter(len(headers))}{n}')
            archive.writestr(f'xl/worksheets/sheet{index}.xml', _xml(sheet))
        SubElement(rels, 'Relationship', Id='styles', Type=base + 'styles', Target='styles.xml')
        archive.writestr('xl/workbook.xml', _xml(book))
        archive.writestr('xl/_rels/workbook.xml.rels', _xml(rels))
        archive.writestr('xl/styles.xml', f'''<?xml version="1.0" encoding="UTF-8"?>
        <styleSheet xmlns="{NS}"><numFmts count="2"><numFmt numFmtId="164" formatCode="&quot;C$&quot; #,##0.00;[Red](&quot;C$&quot; #,##0.00);&quot;C$&quot; 0.00"/><numFmt numFmtId="165" formatCode="dd/mm/yyyy hh:mm"/></numFmts>
        <fonts count="3"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="12"/><color rgb="FF7C2D12"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>
        <fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFEDD5"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FF70452E"/><bgColor indexed="64"/></patternFill></fill></fills>
        <borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
        <cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf><xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment vertical="center"/></xf><xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment vertical="center"/></xf></cellXfs>
        <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>''')
    return stream.getvalue()
