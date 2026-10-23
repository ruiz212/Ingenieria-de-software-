/* Borradores de esta pestaña, separados por usuario; nunca se guardan fotos o tokens. */
(() => {
  const root = document.querySelector('[data-draft-user]');
  if (!root) return;
  const prefix = `amada:draft:${root.dataset.draftUser}:`;
  const tracked = new Map();
  const eligible = input => input.matches('input:not([type="hidden"]):not([type="file"]):not([type="password"]), textarea, select') && !input.hasAttribute('data-no-draft');

  function fields(form) {
    return [...form.querySelectorAll('input, textarea, select')].filter(eligible);
  }
  function values(form) {
    const data = {};
    for (const input of fields(form)) {
      const key = input.id || input.name;
      if (key) data[key] = input.type === 'checkbox' ? input.checked : input.value;
    }
    return data;
  }
  function persist(form) {
    const item = tracked.get(form);
    if (!item) return;
    const current = values(form);
    item.dirty = JSON.stringify(current) !== item.initial;
    try {
      if (item.dirty) sessionStorage.setItem(item.key, JSON.stringify({ savedAt: Date.now(), values: current }));
      else sessionStorage.removeItem(item.key);
    } catch (_) { /* El formulario sigue usable sin almacenamiento local. */ }
  }
  function clear(form) {
    const item = tracked.get(form);
    if (!item) return;
    try { sessionStorage.removeItem(item.key); } catch (_) {}
    item.initial = JSON.stringify(values(form));
    item.dirty = false;
  }

  for (const form of document.querySelectorAll('form[data-draft-key]')) {
    const key = prefix + form.dataset.draftKey;
    const serverValues = JSON.stringify(values(form));
    const savedMarker = new URLSearchParams(location.search).get('borrador_guardado');
    if (savedMarker === form.dataset.draftKey) {
      try { sessionStorage.removeItem(key); } catch (_) {}
      const cleanUrl = new URL(location.href);
      cleanUrl.searchParams.delete('borrador_guardado');
      history.replaceState(null, '', cleanUrl);
    }
    let item;
    try {
      const saved = JSON.parse(sessionStorage.getItem(key) || 'null');
      if (saved && Date.now() - saved.savedAt < 86400000 && saved.values) {
        for (const input of fields(form)) {
          const name = input.id || input.name;
          if (!name || !(name in saved.values)) continue;
          if (input.type === 'checkbox') input.checked = Boolean(saved.values[name]);
          else input.value = saved.values[name];
        }
        const note = document.createElement('p');
        note.className = 'draft-restored-note';
        note.setAttribute('role', 'status');
        note.textContent = 'Borrador recuperado de esta pestaña. '; 
        const discard = document.createElement('button');
        discard.type = 'button';
        discard.textContent = 'Descartar borrador';
        discard.addEventListener('click', () => {
          sessionStorage.removeItem(key);
          item.dirty = false;
          location.reload();
        });
        note.appendChild(discard);
        form.prepend(note);
      }
    } catch (_) {}
    item = { key, initial: serverValues, dirty: JSON.stringify(values(form)) !== serverValues };
    tracked.set(form, item);
    form.addEventListener('input', () => persist(form));
    form.addEventListener('change', () => persist(form));
    if (form.hasAttribute('data-native-draft-submit')) {
      form.addEventListener('submit', () => { item.dirty = false; });
    }
  }

  window.clearFormDraft = clear;
  window.clearFormDrafts = () => {
    for (const item of tracked.values()) {
      try { sessionStorage.removeItem(item.key); } catch (_) {}
      item.dirty = false;
    }
  };
  document.addEventListener('click', event => {
    if (event.target.closest('a[href$="/logout"]')) window.clearFormDrafts();
  });
  window.addEventListener('beforeunload', event => {
    if (![...tracked.values()].some(item => item.dirty)) return;
    event.preventDefault();
    event.returnValue = '';
  });
})();
