"""Read-only checks of the rendered administrative views."""

from pathlib import Path

from bs4 import BeautifulSoup
from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parents[1]
BASE = """{% block content %}{% endblock %}{% block extra_scripts %}{% endblock %}{% block page_styles %}{% endblock %}"""
ENV = Environment(loader=ChoiceLoader([
    DictLoader({"admin_base.html": BASE}),
    FileSystemLoader(ROOT / "templates"),
]))
ENV.globals.update(css_url=lambda value: value, csrf_token=lambda: "test-token")


def render(name, **context):
    return BeautifulSoup(ENV.get_template(f"admin/{name}.html").render(**context), "html.parser")


def test_catalog_dialog_has_name_and_contextual_product_actions():
    soup = render("catalogo", productos=[{
        "id": 7, "nombre": "Pan integral", "imagen_url": "", "categoria": "Pan",
        "categoria_id": 1, "precio": 20, "descuento": 0, "activo": True,
    }], categorias=[])
    dialog = soup.select_one("#modal-nuevo-producto")
    assert dialog["role"] == "dialog"
    assert dialog["aria-modal"] == "true"
    assert dialog["aria-labelledby"] == "modal-title"
    assert soup.find("button", string=lambda s: s and "Editar" in s)["aria-label"] == "Editar Pan integral"


def test_clients_search_and_row_action_have_names():
    soup = render("fidelizacion", metricas={"total_clientes": 0, "porcentaje_vip": 0,
                  "promedios_nivel": {}}, clientes=[{"id": 3, "nombre": "Ana López",
                  "telefono": "8888-8888", "nivel": "Nuevo", "total_compras": 1,
                  "ultima_compra": "2026-10-01", "total_gastado": 10}])
    search = soup.select_one("#buscador-clientes")
    assert soup.find("label", attrs={"for": search["id"]})
    assert soup.select_one(".btn-cliente-detalle")["aria-label"] == "Ver y editar a Ana López"
    assert soup.select_one("#tabla-clientes tbody tr")["data-nivel"] == "Nuevo"
    assert not soup.select_one("#tabla-clientes thead tr").has_attr("data-nivel")


def test_statistics_charts_have_equivalent_data_tables():
    soup = render("estadistica", ventas_por_hora=[{"hora": 9, "total": 25}],
                  ventas_diarias=[{"dia": "2026-10-01", "total": 30}],
                  clientes_nivel=[{"nivel": "VIP", "cantidad": 2}],
                  pronostico_ventas_data={"fechas": ["2026-11-01"],
                                          "historico": [10], "prediccion": [12]},
                  rotacion_productos=[], mermas_mes=[], rendimiento_lotes=[],
                  arqueos=[], pronostico=[])
    for canvas in soup.select("canvas"):
        assert canvas.get("aria-label")
        table = soup.select_one(f"#{canvas['id']}-datos")
        assert table and table.select("tbody tr")
    assert "9:00 25" in soup.select_one("#chart-ventas-hora-datos").get_text(" ", strip=True)
    assert "2026-10-01 30" in soup.select_one("#chart-ventas-diarias-datos").get_text(" ", strip=True)
    assert "2026-11-01 10 12" in soup.select_one("#chart-pronostico-ventas-datos").get_text(" ", strip=True)
    assert "VIP 2" in soup.select_one("#chart-clientes-nivel-datos").get_text(" ", strip=True)


def test_audit_record_keeps_details_out_of_main_columns():
    soup = render("auditoria", desde="", hasta="", entidad="", eventos=[{
        "fecha": "2026-10-01 10:00", "usuario": "Ana", "accion": "UPDATE",
        "entidad": "Producto", "entidad_id": 7, "ip": "127.0.0.1",
        "antes": '{"nombre":"Pan"}', "despues": '{"nombre":"Pan dulce"}',
    }])
    headings = [th.get_text(" ", strip=True) for th in soup.select(".data-table thead th")]
    assert headings == ["Fecha", "Usuario", "Acción", "Entidad", "Detalle"]
    assert soup.select_one("details pre")


def test_staff_roster_uses_four_primary_columns_and_details():
    role = {"id": 1, "nombre": "ADMIN", "etiqueta": "Administrador",
            "usuarios_activos": 1, "usuarios_inactivos": 0, "badge_class": "badge-neutral",
            "puede_asignar": True, "modulos": ["Catálogo"]}
    user = {"id": 8, "nombre": "Ana", "username": "ana", "rol": "ADMIN",
            "etiqueta_rol": "Administrador", "perfil_rol": "Gestión", "badge_class": "badge-neutral",
            "modulos": ["Catálogo", "Caja"], "activo": True, "puede_administrar": True}
    soup = render("usuarios", usuarios=[user], roles=[role], user={"id": 1})
    headings = [th.get_text(" ", strip=True) for th in soup.select("#tabla-usuarios thead th")]
    assert headings == ["Colaborador", "Perfil de trabajo", "Estado", "Gestión de acceso"]
    assert soup.select_one("#tabla-usuarios details")
