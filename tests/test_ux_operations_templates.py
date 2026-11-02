from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def template(name):
    return (ROOT / "templates" / name).read_text(encoding="utf-8")


def test_pos_header_uses_operator_shift_state_and_closed_view_has_return():
    source = template("pos.html")
    assert "Caja: Activa" not in source
    assert "Turno propio: {{ 'Abierto' if turno_activo else 'Cerrado' }}" in source
    assert 'href="{{ url_for(\'admin.dashboard\') }}"' in source


def test_rrhh_dossiers_precede_profiles_and_counts_are_server_rendered():
    source = template("admin/rrhh.html")
    assert source.index("<!-- Empleados Grid -->") < source.index("rrhh-profiles-title")
    assert "{{ empleados | selectattr('estado', 'equalto', 'Activo') | list | length }}" in source
    assert "{{ empleados | rejectattr('estado', 'equalto', 'Activo') | list | length }}" in source
    assert 'data-estado="INACTIVE"' in source
    assert 'role="group" aria-label="Filtrar por estado"' in source
    assert 'data-estado="ALL" aria-pressed="true"' in source


def test_dashboard_labels_preparation_and_deadline_separately():
    source = template("admin/dashboard.html")
    assert "Preparación:" in source
    assert "Fuera de plazo:" in source


def test_attendance_metrics_are_bounded_to_five_columns():
    source = (ROOT / "static/css/pages/admin/asistencia.css").read_text(encoding="utf-8")
    assert "repeat(5, minmax(0, 1fr))" in source


def test_inventory_offers_stock_status_filter_without_changing_threshold():
    source = template("admin/inventario.html")
    assert 'id="filtro-estado-materia"' in source
    assert 'value="agotado"' in source
    assert 'value="bajo"' in source
    assert "m.stock <= m.minimo" in source


def test_production_offers_history_filters_and_recipe_search():
    source = template("admin/produccion.html")
    assert 'id="filtro-lotes-producto"' in source
    assert 'id="filtro-lotes-fecha"' in source
    assert 'id="buscar-receta"' in source
    assert "Quitar ingrediente de la receta" in source
    assert '<details class="produccion-receta-detalle">' in source


def test_monitor_exposes_overdue_filter_and_delivery_priority():
    source = template("monitor.html")
    card = (ROOT / "static/js/features/monitor-card.js").read_text(encoding="utf-8")
    assert 'id="kds-overdue-only"' in source
    assert "card.dataset.overdue" in card
    assert "card.insertBefore(delivery, customer)" in card


def test_monitor_overdue_detection_accepts_display_date_format():
    script = r"""
const fs = require('fs');
const vm = require('vm');
global.window = {};
const NativeDate = Date;
const fixed = new NativeDate('2026-11-02T03:00:00Z').valueOf();
global.Date = class extends NativeDate { constructor(...args) { super(...(args.length ? args : [fixed])); } };
vm.runInThisContext(fs.readFileSync('static/js/features/monitor-card.js', 'utf8'));
if (!window.isOverdueDelivery('31/10/2026')) process.exit(1);
if (window.isOverdueDelivery('01/11/2026')) process.exit(2);
if (window.isOverdueDelivery('2026-11-02')) process.exit(3);
"""
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
