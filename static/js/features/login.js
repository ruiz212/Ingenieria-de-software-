/**
 * Login Feature Module
 * Maneja la lógica de interacción en la vista de login.
 */
export const LoginController = (() => {
    // 1. Caché del DOM
    const DOM = {
        passwordInput: document.getElementById('password'),
        toggleBtn: document.getElementById('js-password-toggle'),
        eyeIcon: document.getElementById('js-eye-icon')
    };

    // 2. Lógica
    const togglePasswordVisibility = () => {
        if (!DOM.passwordInput || !DOM.eyeIcon) return;

        if (DOM.passwordInput.type === 'password') {
            DOM.passwordInput.type = 'text';
            DOM.eyeIcon.innerHTML = '<path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>';
        } else {
            DOM.passwordInput.type = 'password';
            DOM.eyeIcon.innerHTML = '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>';
        }
    };

    // 3. Setup de Eventos
    const setupEvents = () => {
        if (DOM.toggleBtn) {
            DOM.toggleBtn.addEventListener('click', togglePasswordVisibility);
        }
    };

    // 4. Init
    const init = () => {
        // Solo inicializar si estamos en la página de login
        if (!DOM.passwordInput) return;
        setupEvents();
    };

    return { init };
})();
