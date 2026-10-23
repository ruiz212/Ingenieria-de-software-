/* La actividad humana habilita el ping; el polling de la aplicación no renueva la sesión. */
(() => {
  const root = document.querySelector('[data-session-guard]');
  if (!root) return;
  const tokenElement = document.querySelector('meta[name="csrf-token"]');
  const dialog = document.createElement('dialog');
  dialog.className = 'session-guard-dialog';
  dialog.setAttribute('aria-labelledby', 'session-guard-title');
  dialog.innerHTML = '<div class="session-guard-panel"><p class="session-guard-kicker">Sesión de trabajo</p><h2 id="session-guard-title">Tu sesión está por vencer</h2><p id="session-guard-message">Guarda tu trabajo o continúa tu sesión.</p><div class="session-guard-actions"><button type="button" class="btn btn-primary" data-session-continue>Continuar sesión</button><a class="btn btn-outline" href="/logout" data-session-logout>Cerrar sesión de forma segura</a></div></div>';
  document.body.appendChild(dialog);

  let expiry = 0;
  let lastActivity = 0;
  let pingPending = false;
  const message = dialog.querySelector('#session-guard-message');
  const continueButton = dialog.querySelector('[data-session-continue]');

  async function ping(renew) {
    if (pingPending) return;
    pingPending = true;
    try {
      const response = await fetch('/auth/ping', {
        method: renew ? 'POST' : 'GET',
        headers: renew ? { 'X-CSRFToken': tokenElement?.content || '' } : {},
        credentials: 'same-origin', cache: 'no-store'
      });
      if (response.status === 401) {
        expiry = Date.now();
        showWarning();
        return;
      }
      if (!response.ok) return;
      const result = await response.json();
      if (result.csrf_token && tokenElement) {
        tokenElement.content = result.csrf_token;
        document.querySelectorAll('input[name="csrf_token"]').forEach(input => { input.value = result.csrf_token; });
      }
      expiry = Date.now() + Math.max(0, Number(result.expires_in_seconds)) * 1000;
      if (renew && dialog.open) dialog.close();
    } catch (_) {
      if (dialog.open) message.textContent = 'No hay conexión. Conserva tu borrador y vuelve a intentar.';
    } finally {
      pingPending = false;
    }
  }

  function showWarning() {
    if (!dialog.open) dialog.showModal();
    const seconds = Math.max(0, Math.ceil((expiry - Date.now()) / 1000));
    message.textContent = seconds
      ? `Tu sesión vencerá en ${Math.ceil(seconds / 60)} minuto(s). Los borradores de esta pestaña se conservan.`
      : 'La sesión venció. Inicia sesión de nuevo; tu borrador sigue en esta pestaña.';
    continueButton.disabled = seconds === 0;
  }

  const noteActivity = () => { lastActivity = Date.now(); };
  for (const event of ['pointermove', 'pointerdown', 'keydown', 'input', 'focusin']) {
    document.addEventListener(event, noteActivity, { passive: true });
  }
  continueButton.addEventListener('click', () => ping(true));
  dialog.querySelector('[data-session-logout]').addEventListener('click', () => {
    window.clearFormDrafts?.();
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) ping(false);
  });
  setInterval(() => {
    if (expiry && expiry - Date.now() <= 120000) showWarning();
  }, 1000);
  setInterval(() => {
    if (!document.hidden && !dialog.open && Date.now() - lastActivity < 300000) ping(true);
  }, 300000);
  setInterval(() => { if (!document.hidden) ping(false); }, 1800000);
  ping(false);
})();
