/* Consulta una página por vez; las respuestas viejas nunca reemplazan filtros nuevos. */
(() => {
  const panel = document.getElementById('facturas-periodo');
  if (!panel) return;
  const $ = id => document.getElementById(id);
  const query = $('dgi-invoices-query');
  const state = $('dgi-invoices-state');
  const type = $('dgi-invoices-type');
  const from = $('dgi-invoices-from');
  const to = $('dgi-invoices-to');
  const size = $('dgi-invoices-size');
  const body = $('dgi-invoices-body');
  const status = $('dgi-invoices-status');
  const previous = $('dgi-invoices-prev');
  const next = $('dgi-invoices-next');
  let page = 1;
  let pages = 1;
  let request = null;
  let debounce = null;

  function cell(tr, value) {
    const td = document.createElement('td');
    td.textContent = value;
    tr.appendChild(td);
    return td;
  }
  function render(records) {
    body.replaceChildren();
    for (const invoice of records) {
      const tr = document.createElement('tr');
      if (invoice.reciente) tr.classList.add('dgi-invoice-recent');
      cell(tr, invoice.numero);
      cell(tr, invoice.fecha.replace('T', ' ').slice(0, 16));
      cell(tr, invoice.cliente);
      cell(tr, invoice.tipo);
      cell(tr, invoice.estado);
      cell(tr, `C$ ${Number(invoice.total).toLocaleString('es-NI', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
      const linkCell = cell(tr, '');
      const link = document.createElement('a');
      link.href = `/admin/fiscal/facturas/${encodeURIComponent(invoice.id)}/imprimir`;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'Ver factura';
      linkCell.appendChild(link);
      body.appendChild(tr);
    }
    if (!records.length) {
      const tr = document.createElement('tr');
      const empty = cell(tr, 'No hay facturas con estos filtros.');
      empty.colSpan = 7;
      body.appendChild(tr);
    }
  }
  async function load() {
    request?.abort();
    request = new AbortController();
    const params = new URLSearchParams({ periodo: panel.dataset.period, buscar: query.value.trim(), estado: state.value,
      tipo: type.value, desde: from.value, hasta: to.value, tamano: size.value, pagina: String(page) });
    status.textContent = 'Buscando facturas…';
    try {
      const response = await fetch(`${panel.dataset.searchUrl}?${params}`, { signal: request.signal, cache: 'no-store' });
      if (!response.ok) throw new Error('No se pudo consultar el período.');
      const result = await response.json();
      pages = Math.max(1, Math.ceil(result.total / Number(size.value)));
      if (page > pages) { page = pages; return load(); }
      render(result.facturas);
      status.textContent = `${result.total} factura(s) encontradas`;
      $('dgi-invoices-page').textContent = `Página ${page} de ${pages}`;
      previous.disabled = page <= 1;
      next.disabled = page >= pages;
    } catch (error) {
      if (error.name !== 'AbortError') status.textContent = error.message;
    }
  }
  function reset() { page = 1; load(); }
  query.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(reset, 250); });
  for (const select of [state, type, from, to, size]) select.addEventListener('change', reset);
  previous.addEventListener('click', () => { if (page > 1) { page--; load(); } });
  next.addEventListener('click', () => { if (page < pages) { page++; load(); } });
  $('dgi-invoices-refresh').addEventListener('click', load);
  window.addEventListener('focus', () => { if (!document.hidden) load(); });
  setInterval(() => { if (!document.hidden) load(); }, 30000);
  load();
})();
