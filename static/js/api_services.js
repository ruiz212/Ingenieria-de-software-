/**
 * api_services.js
 * Módulo para centralizar todas las peticiones (POST/GET) al servidor
 * Aislando la lógica de negocio de la manipulación del DOM
 */

const API = {
    // ==========================================
    // COTIZACIONES
    // ==========================================
    obtenerCotizacionesPendientes: async () => {
        try {
            const res = await fetch('/api/cotizaciones/pendientes');
            if (!res.ok) throw new Error('Error al obtener cotizaciones');
            return await res.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    obtenerCotizacionesCliente: async () => {
        try {
            const res = await fetch('/api/cotizaciones/cliente');
            if (!res.ok) throw new Error('Error al obtener cotizaciones del cliente');
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
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ precio: precio })
            });
            if (!res.ok) throw new Error('Error al asignar precio');
            return true;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    rechazarPedido: async (id) => {
        try {
            const res = await fetch(`/api/cotizaciones/${id}/rechazar`, {
                method: 'POST'
            });
            if (!res.ok) throw new Error('Error al rechazar pedido');
            return true;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    solicitarCotizacion: async (cotizacionData) => {
        try {
            const response = await fetch('/api/cotizaciones', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(cotizacionData)
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Error al enviar cotización');
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
        try {
            const res = await fetch('/api/tipo_cambio');
            if (res.ok) {
                const data = await res.json();
                return data.tipo_cambio;
            }
            return 36.6243;
        } catch (error) {
            return 36.6243; // Fallback
        }
    },

    procesarFactura: async (datosFactura) => {
        try {
            const response = await fetch('/api/factura', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(datosFactura)
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Error al registrar factura');
            return result;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    // ==========================================
    // ARQUEO DE CAJA
    // ==========================================
    cerrarTurno: async (datosArqueo) => {
        try {
            const response = await fetch('/api/turno/cerrar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(datosArqueo)
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Error al cerrar turno');
            return result;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    }
};

window.API = API; // Hacerlo disponible globalmente
