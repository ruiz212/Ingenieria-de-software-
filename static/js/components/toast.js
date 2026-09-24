/**
 * Toast Notification Controller
 * Maneja la creación y destrucción de notificaciones flotantes (Toasts).
 */
export const ToastController = (() => {
    let container = null;

    // Íconos SVG para cada tipo de Toast
    const ICONS = {
        success: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`,
        danger: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`,
        warning: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`,
        info: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`
    };

    const TITLES = {
        success: '¡Éxito!',
        danger: 'Error',
        warning: 'Advertencia',
        info: 'Información'
    };

    /**
     * Inicializa el contenedor principal de Toasts si no existe.
     */
    const initContainer = () => {
        if (!container) {
            container = document.createElement('div');
            container.className = 'c-toast-container';
            document.body.appendChild(container);
        }
    };

    /**
     * Muestra una nueva notificación Toast.
     * @param {string} message - El mensaje a mostrar.
     * @param {string} type - 'success', 'danger', 'warning', 'info' (default: 'info').
     * @param {number} duration - Tiempo en ms antes de auto-cerrarse (default: 4000).
     */
    const show = (message, type = 'info', duration = 4000) => {
        initContainer();

        const toast = document.createElement('div');
        toast.className = `c-toast c-toast--${type}`;
        toast.setAttribute('role', 'alert');

        // Construir HTML interno del Toast
        toast.innerHTML = `
            <div class="c-toast__icon">
                ${ICONS[type] || ICONS.info}
            </div>
            <div class="c-toast__content">
                <span class="c-toast__title">${TITLES[type] || TITLES.info}</span>
                <span class="c-toast__message">${message}</span>
            </div>
            <button class="c-toast__close" aria-label="Cerrar notificación">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
            <div class="c-toast__progress">
                <div class="c-toast__progress-bar" style="animation-duration: ${duration}ms;"></div>
            </div>
        `;

        // Añadir al contenedor
        container.appendChild(toast);

        // Lógica de cerrado
        let timeoutId;
        
        const closeToast = () => {
            if (toast.classList.contains('is-closing')) return;
            toast.classList.add('is-closing');
            
            // Esperar a que termine la animación de salida (300ms)
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        };

        // Evento de clic en el botón de cerrar
        const closeBtn = toast.querySelector('.c-toast__close');
        closeBtn.addEventListener('click', () => {
            clearTimeout(timeoutId);
            closeToast();
        });

        // Auto-cierre
        if (duration > 0) {
            timeoutId = setTimeout(closeToast, duration);
            
            // Pausar timer al hacer hover (opcional, aunque la animación en CSS ya se pausa)
            toast.addEventListener('mouseenter', () => clearTimeout(timeoutId));
            toast.addEventListener('mouseleave', () => {
                // Reiniciar un pequeño timer al quitar el mouse si quedaba poco tiempo
                timeoutId = setTimeout(closeToast, 1500); 
            });
        }
    };

    return { show };
})();
