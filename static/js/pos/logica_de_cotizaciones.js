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
