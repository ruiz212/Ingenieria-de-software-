/**
 * api_services.js
 * Módulo para centralizar todas las peticiones (POST/GET) al servidor
 * Aislando la lógica de negocio de la manipulación del DOM
 */

function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

const API = {
    // ==========================================
    // COTIZACIONES
    // ==========================================
    obtenerCotizacionesPendientes: async () => {
        try {
            const res = await fetch('/api/cotizaciones/pendientes');
            if (!res.ok) {
                const errData = await res.json().catch(() => null);
                throw new Error((errData && errData.error) || 'Error al obtener cotizaciones pendientes');
            }
            return await res.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    obtenerCotizacionesCliente: async () => {
        try {
            const res = await fetch('/api/cotizaciones/cliente');
            if (!res.ok) {
                const errData = await res.json().catch(() => null);
                throw new Error((errData && errData.error) || 'Error al obtener cotizaciones del cliente');
            }
            return await res.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    cotizarPedido: async (id, precio) => {
        try {
            const res = await fetch(`/api/cotizaciones/${id}/cotizar`, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({ precio: precio })
            });
            const data = await res.json().catch(() => null);
            if (!res.ok) throw new Error((data && data.error) || 'Error al asignar precio');
            return true;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    rechazarPedido: async (id) => {
        try {
            const res = await fetch(`/api/cotizaciones/${id}/rechazar`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({})
            });
            const data = await res.json().catch(() => null);
            if (!res.ok) throw new Error((data && data.error) || 'Error al rechazar pedido');
            return data || true;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    aceptarCotizacion: async (id) => {
        try {
            const response = await fetch(`/api/cotizaciones/${id}/aceptar`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({})
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || 'No se pudo aceptar la cotización');
            return result;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    solicitarCotizacion: async (cotizacionData) => {
        try {
            const response = await fetch('/api/cotizaciones', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify(cotizacionData)
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || `Error del servidor (${response.status})`);
            return result;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    // ==========================================
    // ARCHIVOS
    // ==========================================
    subirImagenReferencia: async (file) => {
        const formData = new FormData();
        formData.append('foto', file);
        try {
            const response = await fetch('/api/upload_referencia', {
                method: 'POST',
                body: formData
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Error al subir imagen');
            return result.ruta;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    // ==========================================
    // FACTURACIÓN
    // ==========================================
    obtenerTipoCambio: async () => {
        if (window.tipoCambioOficial && window.tipoCambioOficial > 0) {
            return window.tipoCambioOficial;
        }
        const globalTc = parseFloat(window.configuracionGlobal?.tipo_cambio_usd);
        if (globalTc > 0) {
            window.tipoCambioOficial = globalTc;
            return globalTc;
        }
        try {
            const res = await fetch('/admin/api/tipo_cambio');
            if (res.ok) {
                const data = await res.json();
                const tc = data.tipo_cambio || 36.6243;
                window.tipoCambioOficial = tc;
                return tc;
            }
            return 36.6243;
        } catch (error) {
            return 36.6243; // Fallback
        }
    },

    procesarFactura: async (datosFactura) => {
        if (!datosFactura.clave_solicitud) {
            datosFactura.clave_solicitud = crypto.randomUUID();
        }
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 60000);
            const response = await fetch('/api/factura', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify(datosFactura),
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            const result = await response.json().catch(() => null);
            if (!response.ok) {
                throw new Error((result && result.error) || `Error ${response.status} al registrar factura`);
            }
            sessionStorage.removeItem('venta-pendiente');
            return result;
        } catch (error) {
            if (error.name === 'AbortError') {
                throw new Error('La facturación tardó demasiado tiempo en responder (timeout 60s). Revise la conexión.');
            }
            console.error('API Error:', error);
            throw error;
        }
    },

    // ==========================================
    // ARQUEO DE CAJA
    // ==========================================
    cerrarTurno: async (datosArqueo) => {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 60000);
            const response = await fetch('/admin/api/arqueo/etapa1-conteo', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify(datosArqueo),
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            const result = await response.json().catch(() => null);
            if (!response.ok) {
                throw new Error((result && result.error) || `Error ${response.status} al cerrar turno`);
            }
            return result;
        } catch (error) {
            if (error.name === 'AbortError') {
                throw new Error('El cierre de turno tardó demasiado tiempo en responder (timeout 60s). Revise la conexión.');
            }
            console.error('API Error:', error);
            throw error;
        }
    }
};

window.API = API; // Hacerlo disponible globalmente
