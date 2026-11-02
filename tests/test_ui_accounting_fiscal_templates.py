"""UI regressions rendered with synthetic data; no database access."""

from pathlib import Path
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from flask import Flask
from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader


TEMPLATES = Path(__file__).resolve().parents[1] / 'templates'


def render(name, **context):
    env = Environment(loader=ChoiceLoader([
        DictLoader({'admin_base.html': '<title>{% block title %}{% endblock %}</title><h1>{% block page_title %}{% endblock %}</h1>{% block content %}{% endblock %}'}),
        FileSystemLoader(TEMPLATES),
    ]), autoescape=True)
    env.globals.update(url_for=lambda endpoint, **kwargs: f'/{endpoint}' + (f'?{urlencode(kwargs)}' if kwargs else ''), css_url=lambda path: path, csrf_token=lambda: 'synthetic')
    return BeautifulSoup(env.get_template(name).render(**context), 'html.parser')


def test_mayor_without_account_prompts_selection_without_none():
    soup = render('admin/libro_mayor.html', cuenta_seleccionada=None, cuentas=[], mes=10, anio=2026)
    assert 'None' not in soup.get_text(' ', strip=True)
    assert 'Seleccione una cuenta' in soup.get_text(' ', strip=True)
    assert soup.select_one('label[for="cuenta_search"]')


def test_uncreated_results_period_explains_absence_without_zero_totals():
    soup = render('admin/estado_resultados.html', mes=11, anio=2026, periodo_creado=False,
                  ingresos=[], costos=[], gastos=[], total_ingresos=0, total_costos=0,
                  total_gastos=0, utilidad_bruta=0, utilidad_neta=0)
    text = soup.get_text(' ', strip=True)
    assert 'No hay un período contable creado' in text
    assert 'C$ 0.00' not in text


def test_accounting_reports_supply_nonempty_main_page_title():
    for template, context in [
        ('admin/balance_general.html', dict(fecha_corte='2026-10-31', activos=[], pasivos=[], capital=[], total_activos=0, total_pasivos=0, total_capital=0)),
        ('admin/estado_resultados.html', dict(mes=10, anio=2026, periodo_creado=True, ingresos=[], costos=[], gastos=[], total_ingresos=0, total_costos=0, total_gastos=0, utilidad_bruta=0, utilidad_neta=0)),
    ]:
        soup = render(template, **context)
        assert soup.select_one('title').get_text(strip=True)
        assert soup.select_one('h1') and soup.select_one('h1').get_text(strip=True)


def test_settings_labels_and_help_are_connected_to_fields():
    soup = render('admin/configuracion.html', config={}, usuarios_totp=[], current_user={'rol_nombre': 'Admin'})
    for field in ('nombre_negocio', 'telefono_negocio', 'direccion_negocio', 'iva_porcentaje', 'moneda_simbolo', 'max_items_factura'):
        control = soup.select_one(f'#cfg-{field}')
        assert soup.select_one(f'label[for="cfg-{field}"]')
        help_id = control.get('aria-describedby')
        assert help_id and soup.select_one(f'#{help_id}')


def test_fiscal_sections_have_task_navigation_and_recent_invoice_page_size():
    soup = render('admin/fiscal.html', config={}, products=[], invoices=[], periods=[], events=[], entries=[])
    assert soup.select_one('nav[aria-label="Tareas de control fiscal"]')
    for target in ('emisor', 'productos', 'documentos', 'periodos', 'bitacora', 'comprobantes'):
        assert soup.select_one(f'#{target}')
    assert soup.select_one('#fiscal-page-size')
    assert not soup.select_one('details.fiscal-task details.fiscal-task')


def test_results_route_marks_created_and_uncreated_periods(monkeypatch):
    from app.admin import routes_accounting

    class Cursor:
        period = None
        calls = 0

        def fetchone(self):
            return self.period

        def fetchall(self):
            return []

    class Connection:
        def __init__(self, cursor):
            self._cursor = cursor

        def cursor(self):
            return self._cursor

        def close(self):
            pass

    cursor = Cursor()
    monkeypatch.setattr(routes_accounting, 'get_db_connection', lambda: Connection(cursor))
    monkeypatch.setattr(routes_accounting, 'execute_sp', lambda *args, **kwargs: None)
    monkeypatch.setattr(routes_accounting, 'render_template', lambda template, **kwargs: kwargs)
    monkeypatch.setattr(routes_accounting, 'flash', lambda *args: None)
    route = routes_accounting.estado_resultados
    while hasattr(route, '__wrapped__'):
        route = route.__wrapped__
    with Flask(__name__).test_request_context('/admin/contabilidad/estado-resultados?mes=11&anio=2026'):
        assert route()['periodo_creado'] is False
        cursor.period = (7,)
        assert route()['periodo_creado'] is True


def test_print_links_keep_the_report_period():
    results = render('admin/estado_resultados.html', mes=9, anio=2025, periodo_creado=True,
                     ingresos=[], costos=[], gastos=[], total_ingresos=0, total_costos=0,
                     total_gastos=0, utilidad_bruta=0, utilidad_neta=0)
    balance = render('admin/balance_general.html', fecha_corte='2025-09-30', activos=[], pasivos=[],
                     capital=[], total_activos=0, total_pasivos=0, total_capital=0)
    results_print = next(a['href'] for a in results.select('a[href]') if 'Imprimir Reporte' in a.get_text())
    balance_print = next(a['href'] for a in balance.select('a[href]') if 'Imprimir Reporte' in a.get_text())
    assert 'mes=9' in results_print
    assert 'anio=2025' in results_print
    assert 'fecha_corte=2025-09-30' in balance_print
