/* Filtros locales; los permisos y el flujo se validan siempre en servidor. */
(() => {
    const table = document.getElementById('dgi-findings');
    if (!table) return;
    const search = document.getElementById('dgi-search');
    const severity = document.getElementById('dgi-severity');
    const counter = document.getElementById('dgi-filter-count');
    const rows = Array.from(table.querySelectorAll('tbody tr[data-severity]'));
    const empty = document.getElementById('dgi-no-matches');
    const normalize = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    function filter() {
        const query = normalize(search.value.trim());
        let visible = 0;
        for (const row of rows) {
            const show = (!severity.value || row.dataset.severity === severity.value) && normalize(row.textContent).includes(query);
            row.hidden = !show;
            if (show) visible += 1;
        }
        counter.textContent = `${visible} de ${rows.length} hallazgos visibles`;
        if (empty) empty.hidden = visible > 0;
    }
    search.addEventListener('input', filter);
    severity.addEventListener('change', filter);
    filter();
})();
