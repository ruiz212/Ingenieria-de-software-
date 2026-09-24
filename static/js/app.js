import { LoginController } from './features/login.js';
import { ToastController } from './components/toast.js';

// Exponer Toast globalmente para que las plantillas de Flask (Jinja2) puedan invocarlo
window.Toast = ToastController;

document.addEventListener('DOMContentLoaded', () => {
    // Inicializar Features según la vista en la que estemos
    LoginController.init();
    
    // Procesar mensajes directos de error (ej. Login)
    const serverError = document.getElementById('js-server-error');
    if (serverError && serverError.dataset.message) {
        window.Toast.show(serverError.dataset.message, 'danger');
    }

    // Procesar mensajes globales de Flask (get_flashed_messages)
    const flashMessages = document.getElementById('js-flash-messages');
    if (flashMessages && flashMessages.dataset.messages) {
        try {
            const messages = JSON.parse(flashMessages.dataset.messages);
            messages.forEach(([category, msg]) => {
                // Mapear categorías de Flask a las del Toast
                const type = category === 'error' ? 'danger' : category;
                window.Toast.show(msg, type);
            });
        } catch (e) {
            console.error('Error parsing flash messages', e);
        }
    }
});
