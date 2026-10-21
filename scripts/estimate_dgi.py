"""Medición reproducible de archivos del incremento, sin afirmar equivalencia SLOC histórica."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    'app/admin/routes_dgi.py', 'app/services/dgi_engine.py',
    'app/services/dgi_repository.py', 'app/services/dgi_excel.py',
    'scripts/migrate_dgi.py', 'static/css/pages/dgi.css', 'static/js/dgi.js',
] + [str(p.relative_to(ROOT)).replace('\\', '/') for p in sorted((ROOT/'templates/admin/dgi').glob('*.html'))]


def measurement():
    counts = {name: len([line for line in (ROOT/name).read_text(encoding='utf-8').splitlines() if line.strip()])
              for name in FILES}
    size = sum(counts.values())
    # Sensibilidad con coeficientes heredados del Corte 2, no una calibración nueva.
    scenarios = {}
    for label, a, b, c, d in [('Organico_heredado',3.2,1.05,2.5,.38), ('Semiacoplado_heredado',3,1.12,2.5,.35)]:
        base_effort = a * 9.04**b
        total_effort = a * (9.04 + size/1000)**b
        scenarios[label] = dict(base_PM=round(base_effort,3), escenario_PM=round(total_effort,3),
            diferencia_PM=round(total_effort-base_effort,3), escenario_meses=round(c*total_effort**d,3),
            costo_escenario_a_800_USD_PM=round(total_effort*800,2))
    return dict(metrica='Líneas físicas no vacías (incluye docstrings y marcado; no equivale a SLOC)',
                archivos=counts, total=size, baseline_historico_KLOC=9.04,
                escenarios_no_calibrados=scenarios,
                limitacion='La línea base histórica no acredita método de conteo comparable. Escenario de sensibilidad, no nueva línea base aprobada.')


if __name__ == '__main__':
    print(json.dumps(measurement(),ensure_ascii=False,indent=2))
