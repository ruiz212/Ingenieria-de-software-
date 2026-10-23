/* Filtros locales; los permisos y el flujo se validan siempre en servidor. */
(() => {
    // 1. Filtro de Hallazgos y Comprobaciones
    const findingsTable = document.getElementById('dgi-findings');
    if (findingsTable) {
        const search = document.getElementById('dgi-search');
        const severity = document.getElementById('dgi-severity');
        const counter = document.getElementById('dgi-filter-count');
        const rows = Array.from(findingsTable.querySelectorAll('tbody tr[data-severity]'));
        const empty = document.getElementById('dgi-no-matches');
        const normalize = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

        function filterFindings() {
            const query = normalize(search.value.trim());
            let visible = 0;
            for (const row of rows) {
                const show = (!severity.value || row.dataset.severity === severity.value) && normalize(row.textContent).includes(query);
                row.hidden = !show;
                if (show) visible += 1;
            }
            if (counter) counter.textContent = `${visible} de ${rows.length} hallazgos visibles`;
            if (empty) empty.hidden = visible > 0;
        }

        if (search) search.addEventListener('input', filterFindings);
        if (severity) severity.addEventListener('change', filterFindings);
        filterFindings();
    }

    // 2. Búsqueda, Filtro y Paginación en vivo para Ventas del Período
    const ventasTable = document.getElementById('dgi-ventas-table');
    if (ventasTable) {
        const searchInput = document.getElementById('dgi-ventas-search');
        const estadoSelect = document.getElementById('dgi-ventas-estado');
        const incluidaSelect = document.getElementById('dgi-ventas-incluida');
        const sizeSelect = document.getElementById('dgi-ventas-size');
        const resetBtn = document.getElementById('dgi-ventas-reset');
        const countSpan = document.getElementById('dgi-ventas-count');
        const paginationContainer = document.getElementById('dgi-ventas-pagination');
        const pageInfoSpan = document.getElementById('dgi-ventas-page-info');
        const pageNumSpan = document.getElementById('dgi-ventas-page-num');
        const prevBtn = document.getElementById('dgi-ventas-prev');
        const nextBtn = document.getElementById('dgi-ventas-next');
        const noMatchRow = document.getElementById('dgi-ventas-no-match');

        const rows = Array.from(ventasTable.querySelectorAll('tbody tr.dgi-venta-row'));
        if (!rows.length) return;

        let currentPage = 1;

        const normalize = text => (text || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();

        function updateVentas() {
            const query = normalize(searchInput ? searchInput.value : '');
            const selectedEstado = estadoSelect ? estadoSelect.value : '';
            const selectedIncluida = incluidaSelect ? incluidaSelect.value : '';
            const pageSize = sizeSelect && sizeSelect.value !== 'all' ? parseInt(sizeSelect.value, 10) : rows.length;

            // Filtrar filas
            const matchingRows = [];
            for (const row of rows) {
                const rowSearch = normalize(row.dataset.search || row.textContent);
                const rowEstado = row.dataset.estado || '';
                const rowIncluida = row.dataset.incluida || '';

                const matchesQuery = !query || rowSearch.includes(query) || normalize(row.textContent).includes(query);
                const matchesEstado = !selectedEstado || rowEstado === selectedEstado;
                const matchesIncluida = !selectedIncluida || rowIncluida === selectedIncluida;

                if (matchesQuery && matchesEstado && matchesIncluida) {
                    matchingRows.push(row);
                } else {
                    row.hidden = true;
                }
            }

            const totalMatches = matchingRows.length;
            const totalPages = Math.max(1, Math.ceil(totalMatches / (pageSize || 1)));

            if (currentPage > totalPages) {
                currentPage = totalPages;
            }
            if (currentPage < 1) {
                currentPage = 1;
            }

            // Paginar filas visibles
            const startIndex = (currentPage - 1) * pageSize;
            const endIndex = startIndex + pageSize;

            matchingRows.forEach((row, idx) => {
                row.hidden = !(idx >= startIndex && idx < endIndex);
            });

            // Mensaje de sin coincidencias
            if (noMatchRow) {
                noMatchRow.hidden = totalMatches > 0;
            }

            // Actualizar contadores
            if (countSpan) {
                if (query || selectedEstado || selectedIncluida) {
                    countSpan.textContent = `${totalMatches} de ${rows.length} ventas encontradas`;
                } else {
                    countSpan.textContent = `${rows.length} ventas registradas`;
                }
            }

            if (pageInfoSpan) {
                if (totalMatches === 0) {
                    pageInfoSpan.textContent = 'Sin resultados';
                } else {
                    const displayStart = startIndex + 1;
                    const displayEnd = Math.min(endIndex, totalMatches);
                    pageInfoSpan.textContent = `Mostrando ${displayStart}–${displayEnd} de ${totalMatches}`;
                }
            }

            if (pageNumSpan) {
                pageNumSpan.textContent = `Pág. ${currentPage} de ${totalPages}`;
            }

            if (prevBtn) {
                prevBtn.disabled = currentPage <= 1;
            }
            if (nextBtn) {
                nextBtn.disabled = currentPage >= totalPages || totalMatches === 0;
            }

            if (paginationContainer) {
                paginationContainer.style.display = totalMatches === 0 ? 'none' : 'flex';
            }
        }

        if (searchInput) {
            searchInput.addEventListener('input', () => {
                currentPage = 1;
                updateVentas();
            });
        }

        if (estadoSelect) {
            estadoSelect.addEventListener('change', () => {
                currentPage = 1;
                updateVentas();
            });
        }

        if (incluidaSelect) {
            incluidaSelect.addEventListener('change', () => {
                currentPage = 1;
                updateVentas();
            });
        }

        if (sizeSelect) {
            sizeSelect.addEventListener('change', () => {
                currentPage = 1;
                updateVentas();
            });
        }

        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                if (searchInput) searchInput.value = '';
                if (estadoSelect) estadoSelect.value = '';
                if (incluidaSelect) incluidaSelect.value = '';
                if (sizeSelect) sizeSelect.value = '25';
                currentPage = 1;
                updateVentas();
                if (searchInput) searchInput.focus();
            });
        }

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                if (currentPage > 1) {
                    currentPage -= 1;
                    updateVentas();
                    ventasTable.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                currentPage += 1;
                updateVentas();
                ventasTable.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            });
        }

        updateVentas();
    }
})();
