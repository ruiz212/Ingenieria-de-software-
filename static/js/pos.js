// Utilidad para prevenir Cross-Site Scripting (XSS)
function escapeHTML(str) {
    if (!str) return '';
    return str.toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

let carrito = [];

// Utilidad: debounce para evitar ráfagas de ejecuciones
function debounce(fn, delay = 150) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), delay); };
}

// Cachear tipo de cambio al inicio y refrescar cada 30 min
API.obtenerTipoCambio().then(tc => window.tipoCambioOficial = tc).catch(() => {});
setInterval(() => API.obtenerTipoCambio().then(tc => window.tipoCambioOficial = tc).catch(() => {}), 30 * 60 * 1000);

document.addEventListener('DOMContentLoaded', () => {
    // Escuchar clics en productos (event delegation)
    const catalogPanel = document.querySelector('.catalog-panel');
    catalogPanel.addEventListener('click', (e) => {
        const card = e.target.closest('.product-card');
        if (card) {
            // Ignorar los clics en las bases de encargo en esta vista principal
            if (card.classList.contains('base-encargo-option')) return;

            const id = card.dataset.id;
            const nombre = card.dataset.nombre;
            let precio = parseFloat(card.dataset.precio);
            const categoria = card.dataset.categoria;
            const descuento = parseFloat(card.dataset.descuento) || 0;

            if (descuento > 0) {
                precio = precio - (precio * descuento / 100);
            }

            if (categoria === 'Reposteria') {
                abrirModalIngredientes(id, nombre, precio, categoria);
            } else {
                agregarAlCarrito(id, nombre, precio, categoria);
            }
        }
    });

    // Lógica de Pestañas (Categorías)
    const categoryBtns = document.querySelectorAll('.category-btn');
    const filterableProducts = document.querySelectorAll('.filterable-product');
    const currentCategoryTitle = document.getElementById('current-category-title');

    categoryBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remover 'active' de todos y poner al actual
            categoryBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            const filter = btn.dataset.filter;
            if (currentCategoryTitle) {
                currentCategoryTitle.textContent = `Mostrador - ${filter}`;
            }
            
            filterableProducts.forEach(product => {
                if (filter === 'Todos' || product.dataset.categoria === filter) {
                    product.classList.remove('hidden');
                } else {
                    product.classList.add('hidden');
                }
            });
        });
    });

    // Lógica del Botón "+ Nuevo Encargo Especial"
    const btnNuevoEncargo = document.getElementById('btn-nuevo-encargo');
    const baseEncargoModal = document.getElementById('base-encargo-modal');
    const btnCerrarBaseEncargo = document.getElementById('btn-cerrar-base-encargo');

    if (btnNuevoEncargo) {
        btnNuevoEncargo.addEventListener('click', () => {
            baseEncargoModal.classList.remove('hidden');
        });
    }

    if (btnCerrarBaseEncargo) {
        btnCerrarBaseEncargo.addEventListener('click', () => {
            baseEncargoModal.classList.add('hidden');
        });
    }

    // Lógica del Botón "Solicitudes Web" (Cotizaciones pendientes)
    const btnVerPedidosClientes = document.getElementById('btn-ver-pedidos-clientes');
    const pedidosClientesModal = document.getElementById('pedidos-clientes-modal');
    const btnCerrarPedidosClientes = document.getElementById('btn-cerrar-pedidos-clientes');
    const badgePedidos = document.getElementById('badge-pedidos');

    if (btnVerPedidosClientes) {
        btnVerPedidosClientes.addEventListener('click', async () => {
            const listContainer = document.getElementById('cotizaciones-pendientes-list');
            listContainer.innerHTML = '<p style="text-align: center; color: var(--text-muted);">Cargando...</p>';
            pedidosClientesModal.classList.remove('hidden');

            try {
                const cotizaciones = await API.obtenerCotizacionesPendientes();
                    if (badgePedidos) {
                        badgePedidos.textContent = cotizaciones.length;
                        badgePedidos.style.display = cotizaciones.length > 0 ? 'flex' : 'none';
                    }

                    if (cotizaciones.length === 0) {
                        listContainer.innerHTML = '<div style="text-align: center; padding: 2rem; color: var(--text-muted);"><span style="font-size: 2rem; display: block; margin-bottom: 0.5rem;">🎉</span>No hay solicitudes web pendientes.</div>';
                        return;
                    }

                    listContainer.innerHTML = '';
                    cotizaciones.forEach(c => {
                        const div = document.createElement('div');
                        div.className = 'modal-section';
                        
                        div.innerHTML = `
                            <div class="modal-section-header">
                                <div>
                                    <h4>Solicitud #${c.id}</h4>
                                    <div class="modal-section-meta">
                                        <strong>Cliente:</strong> ${c.cliente} <br>
                                        <strong>Teléfono:</strong> ${c.telefono || 'No proporcionado'} <br>
                                        <strong>Para:</strong> ${c.fecha_entrega}
                                    </div>
                                </div>
                                <span class="modal-badge modal-badge--pending">Pendiente</span>
                            </div>
                            <div class="modal-specs-box">
                                <strong>Especificaciones:</strong>
                                ${c.especificaciones}
                            </div>
                            ${c.ruta_imagen ? `<a href="${c.ruta_imagen.startsWith('http') ? c.ruta_imagen : '/static/' + c.ruta_imagen}" target="_blank" style="font-size: 0.85rem; color: var(--primary-color); text-decoration: underline;">Ver Foto de Referencia</a>` : ''}
                            
                            <div class="modal-action-row">
                                <input type="number" id="precio-cotizacion-${c.id}" class="form-control" placeholder="Precio (C$)" min="0" step="0.01">
                                <button type="button" class="modal-btn modal-btn--primary" onclick="cotizarPedido(${c.id})">Cotizar</button>
                                <button type="button" class="modal-btn modal-btn--danger-outline" onclick="rechazarPedido(${c.id})">Rechazar</button>
                            </div>
                        `;
                        listContainer.appendChild(div);
                    });
            } catch (error) {
                listContainer.innerHTML = '<p style="text-align: center; color: var(--danger);">Error de conexión.</p>';
            }
        });
        
        // Polling para actualizar el badge de notificaciones cada minuto
        // Polling inteligente: pausa cuando la pestaña está oculta, backoff si no hay datos
        let _pollTimer;
        function _pollCotizaciones() {
            clearTimeout(_pollTimer);
            if (document.hidden) return;
            API.obtenerCotizacionesPendientes()
                .then(data => {
                    if (badgePedidos) {
                        badgePedidos.textContent = data.length;
                        badgePedidos.style.display = data.length > 0 ? 'flex' : 'none';
                    }
                    _pollTimer = setTimeout(_pollCotizaciones, data.length > 0 ? 60000 : 180000);
                })
                .catch(() => { _pollTimer = setTimeout(_pollCotizaciones, 180000); });
        }
        document.addEventListener('visibilitychange', () => { if (!document.hidden) _pollCotizaciones(); });
        _pollTimer = setTimeout(_pollCotizaciones, 60000);
        
        // Lanzar una vez al inicio
        setTimeout(() => {
            if (badgePedidos) {
                API.obtenerCotizacionesPendientes()
                    .then(data => {
                        badgePedidos.textContent = data.length;
                        badgePedidos.style.display = data.length > 0 ? 'flex' : 'none';
                    }).catch(() => {});
            }
        }, 2000);
    }

    if (btnCerrarPedidosClientes) {
        btnCerrarPedidosClientes.addEventListener('click', () => {
            pedidosClientesModal.classList.add('hidden');
        });
    }

    // Funciones globales para cotizar o rechazar
    window.cotizarPedido = async function(id) {
        const input = document.getElementById(`precio-cotizacion-${id}`);
        const precio = parseFloat(input.value);
        if (isNaN(precio) || precio <= 0) {
            showToast('Ingresa un precio válido', true);
            return;
        }
        
        if (confirm(`¿Asignar precio de C$${precio.toFixed(2)} a esta solicitud?`)) {
            try {
                const res = await fetch(`/api/cotizaciones/${id}/cotizar`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ precio: precio })
                });
                if (res.ok) {
                    showToast('Precio asignado correctamente');
                    document.getElementById('btn-ver-pedidos-clientes').click(); // Recargar lista
                } else {
                    showToast('Error al asignar precio', true);
                }
            } catch (e) {
                showToast('Error de conexión', true);
            }
        }
    }

    window.rechazarPedido = async function(id) {
        if (confirm('¿Estás seguro de que deseas rechazar esta solicitud?')) {
            try {
                const res = await fetch(`/api/cotizaciones/${id}/rechazar`, {
                    method: 'POST'
                });
                if (res.ok) {
                    showToast('Solicitud rechazada');
                    document.getElementById('btn-ver-pedidos-clientes').click(); // Recargar lista
                } else {
                    showToast('Error al rechazar', true);
                }
            } catch (e) {
                showToast('Error de conexión', true);
            }
        }
    }

    // Lógica del Botón "Pastel Personalizado"
    const btnPastelPersonalizado = document.getElementById('btn-pastel-personalizado');
    const pastelPersonalizadoModal = document.getElementById('pastel-personalizado-modal');
    const btnCerrarPastel = document.getElementById('btn-cerrar-pastel');
    const formPastel = document.getElementById('form-pastel-personalizado');

    if (btnPastelPersonalizado) {
        btnPastelPersonalizado.addEventListener('click', () => {
            pastelPersonalizadoModal.classList.remove('hidden');
        });
    }

    if (btnCerrarPastel) {
        btnCerrarPastel.addEventListener('click', () => {
            pastelPersonalizadoModal.classList.add('hidden');
        });
    }

    if (formPastel) {
        formPastel.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const btnSubmit = formPastel.querySelector('button[type="submit"]');
            btnSubmit.disabled = true;
            btnSubmit.textContent = 'Procesando...';

            const especificaciones = document.getElementById('pastel-especificaciones').value;
            const fechaEntrega = document.getElementById('pastel-fecha').value;
            const fotoInput = document.getElementById('pastel-foto');
            const telefonoInput = document.getElementById('pastel-telefono');
            
            let rutaImagen = null;

            // Si hay foto, subirla primero
            if (fotoInput.files.length > 0) {
                const formData = new FormData();
                formData.append('foto', fotoInput.files[0]);
                try {
                    rutaImagen = await API.subirImagenReferencia(fotoInput.files[0]);
                } catch (error) {
                    showToast('Error de conexión al subir la imagen.', true);
                    btnSubmit.disabled = false;
                    btnSubmit.textContent = 'Enviar Solicitud';
                    return;
                }
            }

            // Enviar solicitud de cotización al backend
            const cotizacionData = {
                especificaciones: especificaciones,
                fecha_entrega: fechaEntrega,
                ruta_imagen_referencia: rutaImagen,
                telefono: telefonoInput ? telefonoInput.value : null
            };

            try {
                const result = await API.solicitarCotizacion(cotizacionData);
                showToast('¡Cotización enviada a recepción!');
                pastelPersonalizadoModal.classList.add('hidden');
                formPastel.reset();
            } catch (error) {
                showToast('Error de conexión.', true);
            }
            
            btnSubmit.disabled = false;
            btnSubmit.textContent = 'Enviar Solicitud';
        });
    }

    // Seleccionar Base del Pastel
    document.querySelectorAll('.base-encargo-option').forEach(option => {
        option.addEventListener('click', () => {
            baseEncargoModal.classList.add('hidden');
            const id = option.dataset.id;
            const nombre = option.dataset.nombre;
            let precio = parseFloat(option.dataset.precio);
            const categoria = option.dataset.categoria;
            const descuento = parseFloat(option.dataset.descuento) || 0;

            if (descuento > 0) {
                precio = precio - (precio * descuento / 100);
            }

            abrirModalIngredientes(id, nombre, precio, categoria);
        });
    });

    // Modal de Ingredientes
    const ingredientesModal = document.getElementById('ingredientes-modal');
    const btnConfirmarIngredientes = document.getElementById('btn-confirmar-ingredientes');
    const btnCerrarIngredientes = document.getElementById('btn-cerrar-ingredientes');
    const inputIngredientesTotal = document.getElementById('modal-ingredientes-total');

    let itemPendienteParaCarrito = null;

    window.abrirModalIngredientes = function(id, nombre, precio, categoria) {
        itemPendienteParaCarrito = { id, nombre, precioBase: precio, categoria };
        
        // Resetear checkboxes y eliminar los personalizados para la próxima vez
        document.querySelectorAll('.ingrediente-cb').forEach(cb => {
            if (cb.closest('.custom-added')) {
                cb.closest('.ingrediente-option').remove();
            } else {
                cb.checked = false;
            }
        });
        document.getElementById('custom-ing-nombre').value = '';
        document.getElementById('custom-ing-precio').value = '';

        actualizarTotalIngredientes();
        
        document.getElementById('modal-ingredientes-title').textContent = `Personalizar ${nombre}`;
        ingredientesModal.classList.remove('hidden');
    }

    function actualizarTotalIngredientes() {
        if (!itemPendienteParaCarrito) return;
        let total = itemPendienteParaCarrito.precioBase;
        document.querySelectorAll('.ingrediente-cb').forEach(cb => {
            if (cb.checked) total += parseFloat(cb.value);
        });
        inputIngredientesTotal.value = `C$${total.toFixed(2)}`;
    }

    // Eventos a checkboxes iniciales
    document.querySelectorAll('.ingrediente-cb').forEach(cb => {
        cb.addEventListener('change', actualizarTotalIngredientes);
    });

    // Lógica para agregar ingrediente personalizado
    const btnAddCustomIng = document.getElementById('btn-add-custom-ing');
    if (btnAddCustomIng) {
        btnAddCustomIng.addEventListener('click', () => {
            const nombreInput = document.getElementById('custom-ing-nombre');
            const precioInput = document.getElementById('custom-ing-precio');
            const nombre = nombreInput.value.trim();
            const precio = parseFloat(precioInput.value);

            if (!nombre || isNaN(precio) || precio < 0) {
                showToast('Ingresa un nombre y precio válido', true);
                return;
            }

            const label = document.createElement('label');
            label.className = 'ingrediente-option custom-added';
            label.innerHTML = `
                <input type="checkbox" class="ingrediente-cb" value="${precio}" data-nombre="${nombre}" checked>
                <span>${nombre}</span>
                <span class="ing-precio">+C$${precio.toFixed(2)}</span>
            `;
            
            label.querySelector('.ingrediente-cb').addEventListener('change', actualizarTotalIngredientes);
            document.getElementById('ingredientes-list-container').appendChild(label);
            
            nombreInput.value = '';
            precioInput.value = '';
            actualizarTotalIngredientes();
        });
    }

    if (btnCerrarIngredientes) {
        btnCerrarIngredientes.addEventListener('click', () => {
            ingredientesModal.classList.add('hidden');
            itemPendienteParaCarrito = null;
        });
    }

    if (btnConfirmarIngredientes) {
        btnConfirmarIngredientes.addEventListener('click', () => {
            if (!itemPendienteParaCarrito) return;
            
            let ingredientesSeleccionados = [];
            let total = itemPendienteParaCarrito.precioBase;
            
            document.querySelectorAll('.ingrediente-cb').forEach(cb => {
                if (cb.checked) {
                    const precioIng = parseFloat(cb.value);
                    total += precioIng;
                    ingredientesSeleccionados.push({
                        nombre: cb.dataset.nombre,
                        precio: precioIng
                    });
                }
            });

            let nombreFinal = itemPendienteParaCarrito.nombre;
            if (ingredientesSeleccionados.length > 0) {
                nombreFinal += ` (${ingredientesSeleccionados.map(i => i.nombre).join(', ')})`;
            }

            // Usamos un ID único si tiene ingredientes para no agruparlo con otro distinto
            let idFinal = itemPendienteParaCarrito.id;
            if (ingredientesSeleccionados.length > 0) {
                idFinal = idFinal + "_" + Date.now();
            }

            agregarAlCarrito(idFinal, nombreFinal, total, itemPendienteParaCarrito.categoria, {
                precio_base: itemPendienteParaCarrito.precioBase,
                ingredientes: ingredientesSeleccionados
            });
            
            ingredientesModal.classList.add('hidden');
            itemPendienteParaCarrito = null;
        });
    }

    // Lógica de Facturación y Modal de Encargos
    const btnFacturar = document.getElementById('btn-facturar');
    const modal = document.getElementById('encargo-modal');
    const btnConfirmarEncargo = document.getElementById('btn-confirmar-encargo');
    const btnCerrarModal = document.getElementById('btn-cerrar-modal');

    const inputAdelanto = document.getElementById('modal-adelanto');
    const inputSaldo = document.getElementById('modal-saldo');
    const inputTotalModal = document.getElementById('modal-total');

    window.abrirModalEncargo = function(esClienteOnline = false) {
        const { total } = calcularTotales();
        document.getElementById('modal-total').value = `C$${total.toFixed(2)}`;
        document.getElementById('modal-adelanto').value = esClienteOnline ? 0 : (total / 2).toFixed(2);
        
        // Si es cliente online, ocultar adelanto requerido y efectivo
        const adelantoContainer = document.getElementById('modal-adelanto').closest('.form-group');
        if (adelantoContainer) {
            adelantoContainer.style.display = esClienteOnline ? 'none' : 'block';
        }
        
        const efectivoContainer = document.getElementById('encargo-efectivo-container');
        if (efectivoContainer) {
            efectivoContainer.style.display = esClienteOnline ? 'none' : 'block';
        }

        // Si es cliente online, forzar 'Transferencia' o 'Efectivo contra entrega' (usaremos Efectivo pero sin recibir caja)
        const metodoPago = document.getElementById('modal-metodo-pago');
        if (metodoPago && esClienteOnline) {
            // Opcionalmente se puede bloquear o ajustar
        }
        
        const dateInput = document.getElementById('modal-fecha');
        if (dateInput) {
            const tzOffset = (new Date()).getTimezoneOffset() * 60000; 
            const today = (new Date(Date.now() - tzOffset)).toISOString().split('T')[0];
            dateInput.min = today;
            dateInput.value = today;
        }

        const fechaContainer = document.getElementById('encargo-fecha-container');
        if (fechaContainer) {
            fechaContainer.style.display = 'block';
        }

        modal.classList.remove('hidden');
    }

    if (btnFacturar) {
        btnFacturar.addEventListener('click', () => {
            if (carrito.length === 0) {
                showToast('El carrito está vacío', true);
                return;
            }
            
            const hayEncargos = carrito.some(item => 
                item.categoria === 'Reposteria' || item.es_custom
            );
            
            if (hayEncargos) {
                abrirModalEncargo();
            } else {
                const { total } = calcularTotales();
                document.getElementById('pago-total').textContent = `Total a Pagar: C$${total.toFixed(2)}`;
                document.getElementById('pago-efectivo').value = '';
                document.getElementById('pago-dolares').value = '';
                document.getElementById('pago-transferencia').value = '';
                document.getElementById('pago-cambio').value = '';
                document.getElementById('desglose-cambio-normal').innerHTML = '';
                
                // Fetch tipo de cambio real
                API.obtenerTipoCambio().then(tc => {
                        window.tipoCambioOficial = tc;
                        document.getElementById('tc-display').textContent = window.tipoCambioOficial.toFixed(2);
                    }).catch(err => {
                        window.tipoCambioOficial = 36.6243;
                    });
                
                document.getElementById('pago-modal').classList.remove('hidden');
                setTimeout(() => document.getElementById('pago-efectivo').focus(), 100);
            }
        });
    }

    // Lógica del Botón Realizar Pedido (Clientes / Invitados)
    const btnRealizarPedido = document.getElementById('btn-realizar-pedido');
    if (btnRealizarPedido) {
        btnRealizarPedido.addEventListener('click', () => {
            if (carrito.length === 0) {
                showToast('El carrito está vacío', true);
                return;
            }
            // Para clientes, todo el pedido es un encargo (delivery/pickup)
            abrirModalEncargo(true); 
        });
    }

    const metodoPagoSelect = document.getElementById('modal-metodo-pago');
    if (metodoPagoSelect) {
        metodoPagoSelect.addEventListener('change', (e) => {
            const efectivoContainer = document.getElementById('encargo-efectivo-container');
            if (e.target.value === 'Efectivo') {
                efectivoContainer.style.display = 'block';
            } else {
                efectivoContainer.style.display = 'none';
                document.getElementById('modal-efectivo-encargo').value = '';
                document.getElementById('modal-cambio-encargo').value = '';
                document.getElementById('desglose-cambio-encargo').innerHTML = '';
            }
        });
    }

    function actualizarCambioEncargo() {
        const adelanto = parseFloat(inputAdelanto.value) || 0;
        const efectivo = parseFloat(document.getElementById('modal-efectivo-encargo').value) || 0;
        const cambio = efectivo - adelanto;
        
        if (efectivo >= adelanto && adelanto > 0) {
            document.getElementById('modal-cambio-encargo').value = `C$${cambio.toFixed(2)}`;
            document.getElementById('desglose-cambio-encargo').innerHTML = calcularDesgloseCambio(cambio);
        } else {
            document.getElementById('modal-cambio-encargo').value = '';
            document.getElementById('desglose-cambio-encargo').innerHTML = '';
        }
    }

    document.getElementById('modal-efectivo-encargo').addEventListener('input', debounce(actualizarCambioEncargo, 150));

    function cerrarModal() {
        modal.classList.add('hidden');
    }

    if(btnCerrarModal) {
        btnCerrarModal.addEventListener('click', cerrarModal);
    }

    btnConfirmarEncargo.addEventListener('click', () => {
        if (btnConfirmarEncargo.disabled) return;
        btnConfirmarEncargo.disabled = true;
        btnConfirmarEncargo.textContent = 'Procesando...';
        const adelanto = parseFloat(inputAdelanto.value);
        const fecha = document.getElementById('modal-fecha').value;
        const nombreCliente = document.getElementById('modal-nombre-cliente').value.trim();
        const telefonoCliente = document.getElementById('modal-telefono-cliente').value.trim();
        const { total } = calcularTotales();
        const metodoPago = document.getElementById('modal-metodo-pago') ? document.getElementById('modal-metodo-pago').value : 'Efectivo';
        
        // Verificar si es cliente online (adelanto oculto)
        const adelantoContainer = document.getElementById('modal-adelanto').closest('.form-group');
        const esClienteOnline = adelantoContainer && adelantoContainer.style.display === 'none';
        
        let adelantoReal = adelanto;
        if (esClienteOnline) {
            adelantoReal = 0; // Clientes online no pagan adelanto físico en el POS
        } else {
            if (isNaN(adelantoReal) || !fecha) {
                showToast('Por favor, revisa el adelanto y la fecha de entrega', true);
                return;
            }
            if (metodoPago === 'Efectivo') {
                const efectivo = parseFloat(document.getElementById('modal-efectivo-encargo').value) || 0;
                if (efectivo < adelantoReal && adelantoReal > 0) {
                    showToast('El efectivo recibido es menor al adelanto', true);
                    return;
                }
            }
        }
        
        if (!fecha) {
            showToast('Por favor, selecciona una fecha de entrega', true);
            return;
        }
        
        let especificaciones = null;
        let ruta_imagen = null;
        let telefonoCustom = null;
        let fechaCustom = null;
        
        const customItem = carrito.find(item => item.es_custom);
        if (customItem) {
            especificaciones = customItem.encargo_detalles.especificaciones;
            ruta_imagen = customItem.encargo_detalles.ruta_imagen_referencia;
            telefonoCustom = customItem.encargo_detalles.telefono;
            fechaCustom = customItem.encargo_detalles.fecha_entrega;
        }
        
        cerrarModal();
        procesarFactura(true, {
            adelanto: adelantoReal,
            saldo: total - adelantoReal,
            metodo_adelanto: metodoPago,
            fecha_entrega: fechaCustom ? fechaCustom : fecha,
            nombre_cliente: nombreCliente,
            telefono: telefonoCustom ? telefonoCustom : telefonoCliente,
            especificaciones: especificaciones,
            ruta_imagen_referencia: ruta_imagen
        }).finally(() => {
            btnConfirmarEncargo.disabled = false;
            btnConfirmarEncargo.textContent = 'Confirmar Encargo';
        });
    });

    // Lógica del Modal de Pago Normal
    const pagoModal = document.getElementById('pago-modal');
    const inputPagoEfectivo = document.getElementById('pago-efectivo');
    const inputPagoDolares = document.getElementById('pago-dolares');
    const inputPagoTransferencia = document.getElementById('pago-transferencia');
    const selectPagoMetodo = document.getElementById('pago-metodo');
    const toggleRUC = document.getElementById('factura-ruc-toggle');
    const containerRUC = document.getElementById('factura-ruc-container');
    
    toggleRUC.addEventListener('change', (e) => {
        containerRUC.style.display = e.target.checked ? 'block' : 'none';
        containerRUC.classList.toggle('hidden', !e.target.checked);
    });

    selectPagoMetodo.addEventListener('change', (e) => {
        const efContainer = document.getElementById('pago-efectivo-container');
        const trContainer = document.getElementById('pago-transferencia-container');
        
        inputPagoEfectivo.value = '';
        inputPagoDolares.value = '';
        inputPagoTransferencia.value = '';
        document.getElementById('pago-cambio').value = '';
        document.getElementById('desglose-cambio-normal').innerHTML = '';

        if (e.target.value === 'Efectivo') {
            efContainer.style.display = 'grid';
            trContainer.classList.add('hidden');
        } else if (e.target.value === 'Transferencia') {
            efContainer.style.display = 'none';
            trContainer.classList.remove('hidden');
        } else if (e.target.value === 'Mixto') {
            efContainer.style.display = 'grid';
            trContainer.classList.remove('hidden');
        }
    });

    document.getElementById('btn-cerrar-pago').addEventListener('click', () => {
        pagoModal.classList.add('hidden');
    });

    function calcularCambioNormal() {
        const metodo = selectPagoMetodo.value;
        const { total } = calcularTotales();
        
        let efCordobas = parseFloat(inputPagoEfectivo.value) || 0;
        let efDolares = parseFloat(inputPagoDolares.value) || 0;
        let trMonto = parseFloat(inputPagoTransferencia.value) || 0;
        
        let tc = window.tipoCambioOficial || 36.6243;
        let totalRecibido = 0;

        if (metodo === 'Efectivo') {
            totalRecibido = efCordobas + (efDolares * tc);
        } else if (metodo === 'Transferencia') {
            totalRecibido = trMonto;
        } else if (metodo === 'Mixto') {
            totalRecibido = efCordobas + (efDolares * tc) + trMonto;
        }
        
        const cambio = totalRecibido - total;
        
        if (totalRecibido >= total) {
            document.getElementById('pago-cambio').value = `C$${cambio.toFixed(2)}`;
            document.getElementById('desglose-cambio-normal').innerHTML = calcularDesgloseCambio(cambio);
        } else {
            document.getElementById('pago-cambio').value = '';
            document.getElementById('desglose-cambio-normal').innerHTML = 'Monto insuficiente...';
        }
    }

    inputPagoEfectivo.addEventListener('input', debounce(calcularCambioNormal, 150));
    inputPagoDolares.addEventListener('input', debounce(calcularCambioNormal, 150));
    inputPagoTransferencia.addEventListener('input', debounce(calcularCambioNormal, 150));

    const btnConfirmarPago = document.getElementById('btn-confirmar-pago');
    btnConfirmarPago.addEventListener('click', () => {
        if (btnConfirmarPago.disabled) return;
        btnConfirmarPago.disabled = true;
        btnConfirmarPago.textContent = 'Procesando...';
        const metodo = selectPagoMetodo.value;
        const { total } = calcularTotales();
        
        let efCordobas = parseFloat(inputPagoEfectivo.value) || 0;
        let efDolares = parseFloat(inputPagoDolares.value) || 0;
        let trMonto = parseFloat(inputPagoTransferencia.value) || 0;
        let tc = window.tipoCambioOficial || 36.6243;
        
        let totalRecibido = 0;
        let pagosArray = [];

        if (metodo === 'Efectivo') {
            totalRecibido = efCordobas + (efDolares * tc);
            if (efCordobas > 0) pagosArray.push({ metodo: 'Efectivo', monto: efCordobas });
            if (efDolares > 0) pagosArray.push({ metodo: 'Efectivo USD', monto: efDolares, monto_cordobas: (efDolares * tc) });
        } else if (metodo === 'Transferencia') {
            totalRecibido = trMonto;
            pagosArray.push({ metodo: 'Transferencia', monto: trMonto, referencia: document.getElementById('pago-referencia').value });
        } else if (metodo === 'Mixto') {
            totalRecibido = efCordobas + (efDolares * tc) + trMonto;
            if (efCordobas > 0) pagosArray.push({ metodo: 'Efectivo', monto: efCordobas });
            if (efDolares > 0) pagosArray.push({ metodo: 'Efectivo USD', monto: efDolares, monto_cordobas: (efDolares * tc) });
            if (trMonto > 0) pagosArray.push({ metodo: 'Transferencia', monto: trMonto, referencia: document.getElementById('pago-referencia').value });
        }
        
        if (totalRecibido < total) {
            showToast('El monto recibido es menor al total a pagar', true);
            return;
        }
        
        let datosFactura = {
            pagos_multiples: pagosArray,
            cambio: totalRecibido - total
        };

        if (toggleRUC.checked) {
            const rz = document.getElementById('ruc-razon-social').value.trim();
            const num = document.getElementById('ruc-numero').value.trim();
            if (!rz || !num) {
                showToast('Debe ingresar la Razón Social y el Número RUC', true);
                return;
            }
            datosFactura.ruc = { razon_social: rz, numero: num };
        }

        pagoModal.classList.add('hidden');
        procesarFactura(false, datosFactura).finally(() => {
            btnConfirmarPago.disabled = false;
            btnConfirmarPago.textContent = 'Confirmar Pago';
        });
    });

    // ==========================================
    // ARQUEO Y CIERRE DE TURNO
    // ==========================================
    const btnCerrarTurno = document.getElementById('btn-cerrar-turno');
    const arqueoModal = document.getElementById('arqueo-modal');
    if (btnCerrarTurno) {
        btnCerrarTurno.addEventListener('click', () => {
            API.obtenerTipoCambio().then(tc => {
                        window.tipoCambioOficial = tc; })
                .catch(() => { window.tipoCambioOficial = 36.6243; });
            arqueoModal.classList.remove('hidden');
        });
    }

    const btnCerrarArqueo = document.getElementById('btn-cerrar-arqueo');
    if (btnCerrarArqueo) {
        btnCerrarArqueo.addEventListener('click', () => { arqueoModal.classList.add('hidden'); });
    }

    const btnConfirmarArqueo = document.getElementById('btn-confirmar-arqueo');
    if (btnConfirmarArqueo) {
        btnConfirmarArqueo.addEventListener('click', async () => {
            const ef = document.getElementById('arqueo-efectivo').value;
            const dol = document.getElementById('arqueo-dolares').value;
            const tr = document.getElementById('arqueo-transferencias').value;
            
            if (!ef || !dol || !tr) {
                showToast('Por favor ingrese todos los montos contados', true);
                return;
            }

            btnConfirmarArqueo.disabled = true;
            btnConfirmarArqueo.textContent = 'Cerrando...';

            try {
                const data = await API.cerrarTurno({
                        efectivo_contado: parseFloat(ef),
                        dolares_contados: parseFloat(dol),
                        transferencias_contadas: parseFloat(tr),
                        tipo_cambio: window.tipoCambioOficial || 36.6243,
                        observaciones: document.getElementById('arqueo-observaciones').value
                    });
                showToast('Turno cerrado exitosamente');
                setTimeout(() => window.location.href = '/', 1500);
            } catch (err) {
                showToast('Error de conexión', true);
                btnConfirmarArqueo.disabled = false;
                btnConfirmarArqueo.textContent = 'Cerrar Turno';
            }
        });
    }

    // Lógica del Modal de Ticket
    const facturaModal = document.getElementById('factura-modal');
    const btnCerrarTicket = document.getElementById('btn-cerrar-ticket');
    const btnImprimirTicket = document.getElementById('btn-imprimir-ticket');

    if (btnCerrarTicket) {
        btnCerrarTicket.addEventListener('click', () => {
            facturaModal.classList.add('hidden');
        });
    }

    if (btnImprimirTicket) {
        btnImprimirTicket.addEventListener('click', () => {
            window.print();
        });
    }
});

// Para llamadas globales desde botones en el DOM generado (como btn-qty)
window.modificarCantidad = function(id, delta) {
    const item = carrito.find(item => item.id === id);
    if (item) {
        item.cantidad += delta;
        if (item.cantidad <= 0) {
            carrito = carrito.filter(i => i.id !== id);
        } else {
            item.subtotal = item.cantidad * item.precio;
        }
        renderizarCarrito();
    }
};

function agregarAlCarrito(id, nombre, precio, categoria, detalleIngredientes = null) {
    const itemExistente = carrito.find(item => item.id === id);
    if (itemExistente) {
        itemExistente.cantidad++;
        itemExistente.subtotal = itemExistente.cantidad * itemExistente.precio;
    } else {
        carrito.push({
            id: id,
            nombre: nombre,
            precio: precio,
            categoria: categoria,
            cantidad: 1,
            subtotal: precio,
            detalle_ingredientes: detalleIngredientes
        });
    }
    renderizarCarrito();
}

function renderizarCarrito() {
    const cartItemsContainer = document.getElementById('cart-items');
    const subtotalDisplay = document.getElementById('subtotal-display');
    const ivaDisplay = document.getElementById('iva-display');
    const totalDisplay = document.getElementById('total-display');
    const btnFacturar = document.getElementById('btn-facturar');
    const btnRealizarPedido = document.getElementById('btn-realizar-pedido');

    if (carrito.length === 0) {
        cartItemsContainer.innerHTML = '<div class="empty-cart">Selecciona productos para comenzar</div>';
        subtotalDisplay.textContent = 'C$0.00';
        if (ivaDisplay) ivaDisplay.textContent = 'C$0.00';
        totalDisplay.textContent = 'C$0.00';
        if (btnFacturar) btnFacturar.disabled = true;
        if (btnRealizarPedido) btnRealizarPedido.disabled = true;
        return;
    }

    // Use DocumentFragment to minimize reflows
    const fragment = document.createDocumentFragment();

    carrito.forEach(item => {
        const itemEl = document.createElement('div');
        // Add a micro-animation class for visual feedback
        itemEl.className = 'cart-item fade-in-item';
        itemEl.innerHTML = `
            <div class="cart-item-info">
                <div class="cart-item-name" style="color: var(--text-main);">${item.nombre}</div>
                <div class="cart-item-price" style="color: var(--text-muted); font-size: 0.85rem;">C$${item.precio.toFixed(2)} x ${item.cantidad}</div>
            </div>
            <div class="cart-item-actions">
                <button type="button" class="btn-qty" onclick="modificarCantidad('${item.id}', -1)">-</button>
                <span style="min-width: 20px; text-align: center;">${item.cantidad}</span>
                <button type="button" class="btn-qty" onclick="modificarCantidad('${item.id}', 1)">+</button>
            </div>
            <div style="font-weight: 600; color: var(--primary-color);">C$${item.subtotal.toFixed(2)}</div>
        `;
        fragment.appendChild(itemEl);
    });

    // Clear and append in one operation
    cartItemsContainer.innerHTML = '';
    cartItemsContainer.appendChild(fragment);

    const { subtotal: subVal, iva, total } = calcularTotales();

    subtotalDisplay.textContent = `C$${subVal.toFixed(2)}`;
    if (ivaDisplay) ivaDisplay.textContent = `C$${iva.toFixed(2)}`;
    totalDisplay.textContent = `C$${total.toFixed(2)}`;
    if (btnFacturar) btnFacturar.disabled = false;
    if (btnRealizarPedido) btnRealizarPedido.disabled = false;
}

function calcularSubtotal() {
    return carrito.reduce((sum, item) => sum + item.subtotal, 0);
}

function calcularTotales() {
    let subtotal = 0;
    carrito.forEach(item => subtotal += item.subtotal);
    
    let ivaPorcentaje = 0.15;
    if (window.configuracionGlobal && window.configuracionGlobal.iva_porcentaje !== undefined) {
        ivaPorcentaje = parseFloat(window.configuracionGlobal.iva_porcentaje) / 100;
    }
    
    const iva = subtotal * ivaPorcentaje;
    return { subtotal, iva, total: subtotal + iva };
}

function calcularTotal() {
    const { total } = calcularTotales();
    return total;
}

async function procesarFactura(esEncargo = false, datosExtra = null) {
    showLoading(true);

    try {
        const { subtotal, iva, total } = calcularTotales();

        const payload = {
            carrito: carrito,
            subtotal: subtotal,
            iva: iva,
            total: total,
            es_encargo: esEncargo
        };

        if (datosExtra) {
            Object.assign(payload, datosExtra);
        } else {
            if (!esEncargo) {
                const metodo = document.getElementById('pago-metodo') ? document.getElementById('pago-metodo').value : 'Efectivo';
                payload.pagos_multiples = [{ metodo: metodo, monto: total }];
            }
        }

        const data = await API.procesarFactura(payload);
        
        // Mostrar el ticket de factura
        mostrarTicket(data.factura);
        
        showToast('¡Factura registrada exitosamente!');
        carrito = []; 
        renderizarCarrito();
    } catch (error) {
        console.error(error);
        showToast('❌ Error de conexión con el servidor', true);
    } finally {
        showLoading(false);
    }
}

// Algoritmo Greedy para calcular el vuelto en Córdoba Nicaragüense
function calcularDesgloseCambio(montoCambio) {
    if (montoCambio < 0) return "Monto insuficiente.";
    if (montoCambio === 0) return "✅ Pago exacto, no hay cambio.";
    
    const denominaciones = [
        { valor: 1000, tipo: 'billete' },
        { valor: 500, tipo: 'billete' },
        { valor: 200, tipo: 'billete' },
        { valor: 100, tipo: 'billete' },
        { valor: 50, tipo: 'billete' },
        { valor: 20, tipo: 'billete' },
        { valor: 10, tipo: 'billete' },
        { valor: 5, tipo: 'moneda' },
        { valor: 1, tipo: 'moneda' },
        { valor: 0.50, tipo: 'moneda' },
        { valor: 0.25, tipo: 'moneda' },
        { valor: 0.10, tipo: 'moneda' }
    ];
    
    let restante = Math.round(montoCambio * 100);
    let resultado = [];
    
    for (let denom of denominaciones) {
        let valorCentavos = Math.round(denom.valor * 100);
        if (restante >= valorCentavos) {
            let cantidad = Math.floor(restante / valorCentavos);
            restante -= cantidad * valorCentavos;
            
            let denominacionStr = denom.valor < 1 ? `${denom.valor * 100} centavos` : `C$${denom.valor}`;
            resultado.push(`<strong>${cantidad}</strong> ${denom.tipo}(s) de ${denominacionStr}`);
        }
    }
    
    if (resultado.length === 0) return "✅ Pago exacto, no hay cambio.";
    
    return "<strong>Entregar:</strong><br>" + resultado.join('<br>');
}
function mostrarTicket(factura) {
    // Llenar datos del ticket
    document.getElementById('ticket-numero').textContent = factura.numero_factura;
    document.getElementById('ticket-fecha').textContent = factura.fecha;
    document.getElementById('ticket-hora').textContent = factura.hora;
    
    // Productos
    const productosContainer = document.getElementById('ticket-productos');
    productosContainer.innerHTML = '';
    factura.productos.forEach(item => {
        const row = document.createElement('div');
        row.className = 'ticket-product-row';
        
        // Nombre sin los ingredientes en paréntesis
        const nombreBase = item.nombre.split(' (')[0];
        row.innerHTML = `
            <span class="ticket-product-name">${nombreBase}</span>
            <span class="ticket-product-qty">x${item.cantidad}</span>
            <span class="ticket-product-price">C$${item.subtotal.toFixed(2)}</span>
        `;
        productosContainer.appendChild(row);

        // Si tiene ingredientes, mostrarlos debajo
        if (item.detalle_ingredientes && item.detalle_ingredientes.ingredientes && item.detalle_ingredientes.ingredientes.length > 0) {
            // Precio base
            const baseRow = document.createElement('div');
            baseRow.style.cssText = 'font-size: 0.75rem; color: #6b7280; padding-left: 0.75rem; padding-top: 0.1rem;';
            baseRow.textContent = `  Base: C$${item.detalle_ingredientes.precio_base.toFixed(2)}`;
            productosContainer.appendChild(baseRow);

            item.detalle_ingredientes.ingredientes.forEach(ing => {
                const ingRow = document.createElement('div');
                ingRow.style.cssText = 'display: flex; justify-content: space-between; font-size: 0.75rem; color: #10b981; padding-left: 0.75rem;';
                ingRow.innerHTML = `<span>  + ${ing.nombre}</span><span>+C$${ing.precio.toFixed(2)}</span>`;
                productosContainer.appendChild(ingRow);
            });
        }
    });

    // Totales
    document.getElementById('ticket-subtotal').textContent = `C$${factura.subtotal.toFixed(2)}`;
    document.getElementById('ticket-iva').textContent = `C$${factura.iva.toFixed(2)}`;
    document.getElementById('ticket-total').textContent = `C$${factura.total.toFixed(2)}`;

    // Sección de encargo
    const encargoSection = document.getElementById('ticket-encargo-section');
    if (factura.es_encargo && factura.encargo_detalles) {
        encargoSection.classList.remove('hidden');
        document.getElementById('ticket-cliente').textContent = factura.encargo_detalles.nombre_cliente || 'N/A';
        document.getElementById('ticket-adelanto').textContent = `C$${factura.encargo_detalles.adelanto.toFixed(2)}`;
        document.getElementById('ticket-saldo').textContent = `C$${factura.encargo_detalles.saldo.toFixed(2)}`;
        document.getElementById('ticket-fecha-entrega').textContent = factura.encargo_detalles.fecha_entrega;
    } else {
        encargoSection.classList.add('hidden');
    }

    // QR
    document.getElementById('ticket-qr-img').src = factura.qr_image;

    // Mostrar modal
    document.getElementById('factura-modal').classList.remove('hidden');
}

function showLoading(show) {
    const overlay = document.getElementById('loading-overlay');
    if (show) overlay.classList.remove('hidden');
    else overlay.classList.add('hidden');
}

function showToast(message, isError = false) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${isError ? 'error' : ''}`;
    toast.textContent = message;
    
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ==========================================
// LÓGICA DE COTIZACIONES
// ==========================================

document.addEventListener('DOMContentLoaded', () => {
    // Modal Cliente: Mis Cotizaciones
    const btnMisCotizaciones = document.getElementById('btn-mis-cotizaciones');
    const modalMisCotizaciones = document.getElementById('mis-cotizaciones-modal');
    const btnCerrarMisCot = document.getElementById('btn-cerrar-mis-cotizaciones');
    const listaMisCot = document.getElementById('cotizaciones-cliente-list');

    if (btnMisCotizaciones) {
        btnMisCotizaciones.addEventListener('click', async () => {
            modalMisCotizaciones.classList.remove('hidden');
            await cargarMisCotizaciones();
        });

        btnCerrarMisCot.addEventListener('click', () => {
            modalMisCotizaciones.classList.add('hidden');
        });
    }

    async function cargarMisCotizaciones() {
        listaMisCot.innerHTML = '<p style="text-align: center; color: var(--text-muted);">Cargando...</p>';
        try {
            const data = await API.obtenerCotizacionesCliente();
            
            if (data.length === 0) {
                listaMisCot.innerHTML = '<p style="text-align: center; color: var(--text-muted);">No tienes cotizaciones activas.</p>';
                return;
            }

            listaMisCot.innerHTML = data.map(cot => `
                <div style="background: var(--background); padding: 1rem; border-radius: var(--radius-sm); border: 1px solid var(--border); margin-bottom: 1rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <strong>Para: ${escapeHTML(cot.fecha_entrega)}</strong>
                        <span class="badge" style="background: ${cot.estado === 'Cotizada' ? 'var(--success)' : (cot.estado === 'Rechazada' ? 'var(--danger)' : 'var(--warning)')}; color: white; padding: 0.25rem 0.5rem; border-radius: var(--radius-sm); font-size: 0.8rem;">
                            ${escapeHTML(cot.estado)}
                        </span>
                    </div>
                    <p style="font-size: 0.9rem; margin-bottom: 0.5rem; color: var(--text-main);">${escapeHTML(cot.especificaciones).replace(/\n/g, '<br>')}</p>
                    ${cot.ruta_imagen ? `<a href="${escapeHTML(cot.ruta_imagen.startsWith('http') ? cot.ruta_imagen : '/static/' + cot.ruta_imagen)}" target="_blank" style="font-size: 0.85rem; color: var(--primary);">Ver foto de referencia</a>` : ''}
                    
                    ${cot.estado === 'Cotizada' ? `
                        <div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--border);">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                                <span>Precio Asignado:</span>
                                <strong style="font-size: 1.2rem; color: var(--success);">C$${cot.precio_cotizado.toFixed(2)}</strong>
                            </div>
                            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                                <button class="btn btn-primary btn-aceptar-cot" data-id="${cot.id}" data-precio="${cot.precio_cotizado}" data-specs="${escapeHTML(cot.especificaciones)}" data-img="${escapeHTML(cot.ruta_imagen || '')}" data-fecha="${escapeHTML(cot.fecha_entrega)}" style="flex: 1;">Aceptar y Pagar Adelanto</button>
                                <button class="btn btn-outline btn-rechazar-cot" data-id="${cot.id}" style="color: var(--danger); border-color: rgba(239, 68, 68, 0.3);">Rechazar</button>
                                <a href="https://wa.me/50588888888?text=Hola, tengo una duda sobre la cotización de mi pastel para el ${escapeHTML(cot.fecha_entrega)}" target="_blank" class="btn btn-outline" style="border-color: #25D366; color: #25D366;">WhatsApp</a>
                            </div>
                        </div>
                    ` : ''}
                </div>
            `).join('');

            // Event listeners para los botones de aceptar/rechazar
            document.querySelectorAll('.btn-aceptar-cot').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const id = e.target.dataset.id;
                    const precio = parseFloat(e.target.dataset.precio);
                    const specs = e.target.dataset.specs;
                    const img = e.target.dataset.img;
                    const fecha = e.target.dataset.fecha;
                    
                    // Agregar al carrito
                    const itemPersonalizado = {
                        id: 'custom_' + id,
                        nombre: 'Pastel Personalizado',
                        precio: precio,
                        categoria: 'Reposteria',
                        cantidad: 1,
                        subtotal: precio,
                        detalle_ingredientes: { ingredientes: [], notas_especiales: '' },
                        encargo_detalles: {
                            fecha_entrega: fecha,
                            especificaciones: specs,
                            ruta_imagen_referencia: img || null,
                            telefono: null
                        },
                        es_custom: true
                    };
                    carrito.push(itemPersonalizado);
                    renderizarCarrito();
                    modalMisCotizaciones.classList.add('hidden');
                    showToast('Pastel agregado al carrito. Procede a facturar el pago del 50% mínimo.');
                });
            });

            document.querySelectorAll('.btn-rechazar-cot').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    if (confirm('¿Seguro que deseas rechazar y cancelar esta cotización?')) {
                        const id = e.target.dataset.id;
                        await fetch(`/api/cotizaciones/${id}/rechazar`, { method: 'POST' });
                        showToast('Cotización rechazada');
                        cargarMisCotizaciones();
                    }
                });
            });

        } catch (error) {
            listaMisCot.innerHTML = '<p style="text-align: center; color: var(--danger);">Error al cargar las cotizaciones.</p>';
        }
    }

    // Modal Recepción: Pedidos Clientes
    const btnPedidosClientes = document.getElementById('btn-pedidos-clientes');
    const modalPedidos = document.getElementById('pedidos-clientes-modal');
    const btnCerrarPedidos = document.getElementById('btn-cerrar-pedidos-clientes');
    const listaPedidos = document.getElementById('cotizaciones-pendientes-list');

    if (btnPedidosClientes) {
        btnPedidosClientes.addEventListener('click', async () => {
            modalPedidos.classList.remove('hidden');
            await cargarPedidosPendientes();
        });

        btnCerrarPedidos.addEventListener('click', () => {
            modalPedidos.classList.add('hidden');
        });
    }

    async function cargarPedidosPendientes() {
        listaPedidos.innerHTML = '<p style="text-align: center; color: var(--text-muted);">Cargando...</p>';
        try {
            const data = await API.obtenerCotizacionesPendientes();
            
            if (data.length === 0) {
                listaPedidos.innerHTML = '<p style="text-align: center; color: var(--text-muted);">No hay pedidos pendientes por cotizar.</p>';
                return;
            }

            listaPedidos.innerHTML = data.map(cot => `
                <div style="background: var(--background); padding: 1.25rem; border-radius: var(--radius-sm); border: 1px solid var(--border); margin-bottom: 1rem; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1rem;">
                        <div>
                            <h4 style="margin-bottom: 0.25rem;">Pedido #${cot.id}</h4>
                            <div style="color: var(--text-muted); font-size: 0.85rem;">
                                <div><strong>Cliente:</strong> ${escapeHTML(cot.cliente_nombre || cot.cliente)}</div>
                                <div><strong>Para entregar:</strong> ${escapeHTML(cot.fecha_entrega)}</div>
                            </div>
                        </div>
                        <span class="badge" style="background: var(--warning); color: white; padding: 0.35rem 0.75rem; border-radius: var(--radius-sm); font-size: 0.85rem; font-weight: 600;">
                            Nueva
                        </span>
                    </div>
                    
                    <div style="background: rgba(107, 58, 42, 0.03); padding: 1rem; border-radius: var(--radius-sm); margin-bottom: 1rem; border-left: 3px solid var(--brand-dorado);">
                        <strong style="display: block; margin-bottom: 0.5rem; color: var(--brand-cafe-dark); font-size: 0.85rem; text-transform: uppercase;">Especificaciones del Cliente:</strong>
                        <p style="font-size: 0.95rem; margin: 0; line-height: 1.5; color: var(--text-main);">${escapeHTML(cot.especificaciones).replace(/\n/g, '<br>')}</p>
                    </div>

                    ${cot.ruta_imagen ? `
                        <div style="margin-bottom: 1rem;">
                            <a href="${escapeHTML(cot.ruta_imagen.startsWith('http') ? cot.ruta_imagen : '/static/' + cot.ruta_imagen)}" target="_blank" class="btn btn-outline" style="font-size: 0.85rem; padding: 0.4rem 0.8rem; display: inline-flex; align-items: center; gap: 0.5rem;">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                                Ver Imagen de Referencia
                            </a>
                        </div>
                    ` : ''}
                    
                    <div style="margin-top: 1rem; display: flex; gap: 0.5rem; align-items: center;">
                        <input type="number" id="precio-cot-${cot.id}" class="form-control" placeholder="Precio (C$)" min="0" step="0.01" style="width: 150px;">
                        <button class="btn btn-primary btn-enviar-cot" data-id="${cot.id}">Fijar Precio</button>
                        ${cot.telefono ? `<a href="https://wa.me/505${cot.telefono.replace(/[^0-9]/g, '')}?text=Hola ${escapeHTML(cot.cliente_nombre || cot.cliente)}, te escribimos de Panadería Amada sobre tu encargo para el ${escapeHTML(cot.fecha_entrega)}..." target="_blank" class="btn btn-outline" style="border-color: #25D366; color: #25D366;">WhatsApp Cliente</a>` : ''}
                    </div>
                </div>
            `).join('');

            document.querySelectorAll('.btn-enviar-cot').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const id = e.target.dataset.id;
                    const precioInput = document.getElementById(`precio-cot-${id}`);
                    const precio = parseFloat(precioInput.value);
                    
                    if (isNaN(precio) || precio <= 0) {
                        showToast('Ingresa un precio válido', true);
                        return;
                    }

                    try {
                        const res = await fetch(`/api/cotizaciones/${id}/cotizar`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ precio: precio })
                        });
                        
                        if (res.ok) {
                            showToast('Cotización enviada al cliente');
                            cargarPedidosPendientes();
                        } else {
                            showToast('Error al enviar cotización', true);
                        }
                    } catch (error) {
                        showToast('Error de conexión', true);
                    }
                });
            });

        } catch (error) {
            listaPedidos.innerHTML = '<p style="text-align: center; color: var(--danger);">Error al cargar pedidos.</p>';
        }
    }
});
