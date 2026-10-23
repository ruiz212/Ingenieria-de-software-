/* Fichas contractuales y marcaje excepcional: no se editan datos salariales. */
(() => {
  const profilesForm = document.getElementById('form-perfil-puesto');
  if (!profilesForm) return;
  const profiles = JSON.parse(document.getElementById('rrhh-profiles-data')?.textContent || '[]');
  const $ = id => document.getElementById(id);

  for (const button of document.querySelectorAll('[data-edit-profile]')) {
    button.addEventListener('click', () => {
      const profile = profiles[Number(button.dataset.editProfile)];
      if (!profile) return;
      $('perfil-cargo').value = profile.cargo;
      $('perfil-descripcion').value = profile.perfil;
      $('perfil-obligaciones').value = profile.obligaciones;
      $('perfil-competencias').value = profile.competencias;
      $('rrhh-profile-editor').open = true;
      $('perfil-cargo').focus();
    });
  }

  async function submit(form, url, payload) {
    const button = form.querySelector('[type="submit"]');
    button.disabled = true;
    try {
      const response = await fetch(url, { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || '' },
        body: JSON.stringify(payload) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || result.message || 'No se pudo guardar.');
      return result;
    } finally { button.disabled = false; }
  }

  profilesForm.addEventListener('submit', async event => {
    event.preventDefault();
    try {
      await submit(profilesForm, '/admin/api/rrhh/puestos', {
        cargo: $('perfil-cargo').value, perfil_puesto: $('perfil-descripcion').value,
        obligaciones: $('perfil-obligaciones').value, requisitos_competencias: $('perfil-competencias').value
      });
      window.clearFormDraft?.(profilesForm);
      location.reload();
    } catch (error) { window.showToast?.(error.message, true); }
  });

  const attendanceForm = $('form-asistencia-contingencia');
  attendanceForm?.addEventListener('submit', async event => {
    event.preventDefault();
    try {
      const result = await submit(attendanceForm, '/kiosco/api/marcar', {
        empleado_id: Number($('contingencia-empleado').value),
        accion: $('contingencia-accion').value, motivo: $('contingencia-motivo').value
      });
      window.showToast?.(result.repetido ? 'Ese marcaje ya estaba registrado.' : 'Marcaje autorizado y auditado.');
      if (!result.repetido) {
        window.clearFormDraft?.(attendanceForm);
        attendanceForm.reset();
        window.fetchAsistencia?.();
      }
    } catch (error) { window.showToast?.(error.message, true); }
  });
})();
