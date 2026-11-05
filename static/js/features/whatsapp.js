/* QR and connection state only; never reload while the administrator is typing. */
(() => {
  const root = document.querySelector('[data-wa-panel]');
  if (!root || root.dataset.ready !== '1') return;
  const qr = document.getElementById('wa-qr');
  const placeholder = document.getElementById('wa-qr-placeholder');
  const error = document.getElementById('wa-poll-error');
  let stopped = false;
  const text = (id, value) => {
    const element = document.getElementById(id);
    if (element && element.textContent !== value) element.textContent = value;
  };
  function update(state) {
    const status = state.Estado === 'Worker desconectado' ? 'Conexión no iniciada' : state.Estado;
    text('wa-status', status || 'Sin conexión');
    document.getElementById('wa-status').dataset.connected = String(state.Estado === 'Conectado');
    text('wa-account', state.CuentaTelefono || 'Aún no hay un teléfono vinculado');
    text('wa-assistant-status', state.Activo ? 'Asistente y envíos activos.' : 'Asistente y envíos pausados.');
    const hasQR = Boolean(state.QR && state.QR.startsWith('data:image/png;base64,'));
    if (hasQR && qr.getAttribute('src') !== state.QR) qr.src = state.QR;
    if (!hasQR) qr.removeAttribute('src');
    qr.hidden = !hasQR;
    placeholder.hidden = hasQR;
    text('wa-qr-help', state.Vinculado ? 'Teléfono vinculado. Puedes atender a tus clientes.' :
      state.needs_auth ? 'Verifica tu identidad para mostrar el código QR.' :
      state.Estado === 'Worker desconectado' ? 'La conexión aún no se ha iniciado. Vuelve a conectar para reintentar.' :
      'Preparando un nuevo QR. Aparecerá aquí cuando esté disponible.');
    text('wa-operation', state.SolicitudEstado === 'Error' ? state.SolicitudError || 'La operación no se completó. Vuelve a intentarlo.' :
      state.SolicitudEstado === 'Pendiente' ? (state.SolicitudAccion === 'DESVINCULAR' ?
        'Desvinculando la cuenta. Espera antes de agregar otra.' : 'Preparando la vinculación. El QR aparecerá aquí.') :
      state.SolicitudAccion === 'DESVINCULAR' ? 'Cuenta desvinculada. Ya puedes vincular otro teléfono.' : '');
    const globalForm = document.getElementById('wa-global-form');
    if (globalForm) {
      globalForm.elements.enabled.value = state.Activo ? '0' : '1';
      const button = globalForm.querySelector('button');
      button.textContent = state.Activo ? 'Pausar asistente y envíos' : 'Activar asistente y envíos';
      button.disabled = !state.Activo && (state.Estado !== 'Conectado' || !state.Vinculado ||
        (state.SolicitudAccion === 'DESVINCULAR' && state.SolicitudEstado === 'Pendiente'));
    }
    if (String(state.ConnectionRevision) !== root.dataset.revision) {
      root.querySelectorAll('[data-account-submit]').forEach(button => { button.disabled = true; });
      error.hidden = false;
      error.textContent = 'La cuenta cambió desde que abriste esta página. Actualiza el panel antes de modificarla.';
    }
  }
  async function poll() {
    if (stopped) return;
    if (!document.hidden) {
      try {
        const response = await fetch(root.dataset.statusUrl, { cache: 'no-store', headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(10000) });
        if (response.status === 401 || response.status === 403 || response.redirected) stopped = true;
        if (!response.ok || response.redirected) throw new Error('status');
        const state = await response.json();
        error.hidden = true;
        update(state);
      } catch (_) {
        if (stopped || !qr.getAttribute('src')) {
          qr.hidden = true;
          qr.removeAttribute('src');
          placeholder.hidden = false;
        }
        error.hidden = false;
        error.textContent = stopped ? 'La sesión terminó. Inicia sesión de nuevo para ver la conexión.' :
          'No se pudo actualizar la conexión. Se volverá a intentar automáticamente.';
      }
    }
    if (!stopped) window.setTimeout(poll, 2500);
  }
  poll();
})();
