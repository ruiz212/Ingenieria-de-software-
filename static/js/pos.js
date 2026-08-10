let carrito = [];

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
            currentCategoryTitle.textContent = `Mostrador - ${filter}`;
            
            filterableProducts.forEach(product => {
                if (filter === 'Todos' || product.dataset.categoria === filter) {
                    product.style.display = 'block';
                } else {
                    product.style.display = 'none';
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
        inputIngredientesTotal.value = `$${total.toFixed(2)}`;
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
                <span class="ing-precio">+$${precio.toFixed(2)}</span>
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

    btnFacturar.addEventListener('click', () => {
        const tieneEncargos = carrito.some(item => item.categoria === 'Reposteria');
        
        if (tieneEncargos) {
            inputTotalModal.value = `$${calcularTotal().toFixed(2)}`;
            inputAdelanto.value = '';
            inputSaldo.value = `$${calcularTotal().toFixed(2)}`;
            document.getElementById('modal-efectivo-encargo').value = '';
            document.getElementById('modal-cambio-encargo').value = '';
            document.getElementById('desglose-cambio-encargo').innerHTML = '';
            // Limpiar campos de cliente
            document.getElementById('modal-nombre-cliente').value = '';
            document.getElementById('modal-telefono-cliente').value = '';
            modal.classList.remove('hidden');
        } else {
            // Abrir Modal de Pago Normal
            const pagoModal = document.getElementById('pago-modal');
            document.getElementById('pago-total').value = `$${calcularTotal().toFixed(2)}`;
            document.getElementById('pago-efectivo').value = '';
            document.getElementById('pago-cambio').value = '';
            document.getElementById('desglose-cambio-normal').innerHTML = 'Ingrese efectivo para ver el desglose del cambio...';
            pagoModal.classList.remove('hidden');
        }
    });

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

    inputAdelanto.addEventListener('input', (e) => {
        const adelanto = parseFloat(e.target.value) || 0;
        const total = calcularTotal();
        const saldo = total - adelanto;
        inputSaldo.value = `$${saldo.toFixed(2)}`;
        
        // Colorear en rojo si es inválido
        if (adelanto > total) {
            inputSaldo.style.color = 'var(--danger)';
        } else {
            inputSaldo.style.color = 'var(--text)';
        }
        actualizarCambioEncargo();
    });

    document.getElementById('modal-efectivo-encargo').addEventListener('input', actualizarCambioEncargo);

    function cerrarModal() {
        modal.classList.add('hidden');
    }

    if(btnCerrarModal) {
        btnCerrarModal.addEventListener('click', cerrarModal);
    }

    btnConfirmarEncargo.addEventListener('click', () => {
        const adelanto = parseFloat(inputAdelanto.value);
        const fecha = document.getElementById('modal-fecha').value;
        const nombreCliente = document.getElementById('modal-nombre-cliente').value.trim();
        const telefonoCliente = document.getElementById('modal-telefono-cliente').value.trim();
        const total = calcularTotal();
        
        if (isNaN(adelanto) || !fecha) {
            showToast('Por favor, ingresa el adelanto y la fecha de entrega', true);
            return;
        }
        
        if (adelanto > total) {
            showToast('El adelanto no puede ser mayor al total ($' + total.toFixed(2) + ')', true);
            return;
        }
        
        const efectivo = parseFloat(document.getElementById('modal-efectivo-encargo').value) || 0;
        if (efectivo < adelanto && adelanto > 0) {
            showToast('El efectivo recibido es menor al adelanto', true);
            return;
        }
        
        cerrarModal();
        procesarFactura(true, {
            adelanto: adelanto,
            saldo: total - adelanto,
            fecha_entrega: fecha,
            nombre_cliente: nombreCliente,
            telefono: telefonoCliente
        });
    });

    // Lógica del Modal de Pago Normal
    const pagoModal = document.getElementById('pago-modal');
    const inputPagoEfectivo = document.getElementById('pago-efectivo');
    
    document.getElementById('btn-cerrar-pago').addEventListener('click', () => {
        pagoModal.classList.add('hidden');
    });

    inputPagoEfectivo.addEventListener('input', (e) => {
        const efectivo = parseFloat(e.target.value) || 0;
        const total = calcularTotal();
        const cambio = efectivo - total;
        
        if (efectivo >= total) {
            document.getElementById('pago-cambio').value = `C$${cambio.toFixed(2)}`;
            document.getElementById('desglose-cambio-normal').innerHTML = calcularDesgloseCambio(cambio);
        } else {
            document.getElementById('pago-cambio').value = '';
            document.getElementById('desglose-cambio-normal').innerHTML = 'Efectivo insuficiente...';
        }
    });

    document.getElementById('btn-confirmar-pago').addEventListener('click', () => {
        const efectivo = parseFloat(inputPagoEfectivo.value) || 0;
        const total = calcularTotal();
        
        if (efectivo < total) {
            showToast('El efectivo recibido es menor al total a pagar', true);
            return;
        }
        
        pagoModal.classList.add('hidden');
        procesarFactura(false);
    });

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

    cartItemsContainer.innerHTML = '';

    if (carrito.length === 0) {
        cartItemsContainer.innerHTML = '<div class="empty-cart">Selecciona productos para comenzar</div>';
        subtotalDisplay.textContent = '$0.00';
        if (ivaDisplay) ivaDisplay.textContent = '$0.00';
        totalDisplay.textContent = '$0.00';
        btnFacturar.disabled = true;
        return;
    }

    let subtotal = 0;

    carrito.forEach(item => {
        subtotal += item.subtotal;
        const itemEl = document.createElement('div');
        itemEl.className = 'cart-item';
        itemEl.innerHTML = `
            <div class="cart-item-info">
                <div class="cart-item-name">${item.nombre}</div>
                <div class="cart-item-price">$${item.precio.toFixed(2)} x ${item.cantidad}</div>
            </div>
            <div class="cart-item-actions">
                <button type="button" class="btn-qty" onclick="modificarCantidad('${item.id}', -1)">-</button>
                <span>${item.cantidad}</span>
                <button type="button" class="btn-qty" onclick="modificarCantidad('${item.id}', 1)">+</button>
            </div>
            <div style="font-weight: 600;">$${item.subtotal.toFixed(2)}</div>
        `;
        cartItemsContainer.appendChild(itemEl);
    });

    const iva = subtotal * 0.15;
    const total = subtotal + iva;

    subtotalDisplay.textContent = `$${subtotal.toFixed(2)}`;
    if (ivaDisplay) ivaDisplay.textContent = `$${iva.toFixed(2)}`;
    totalDisplay.textContent = `$${total.toFixed(2)}`;
    btnFacturar.disabled = false;
}

function calcularSubtotal() {
    return carrito.reduce((sum, item) => sum + item.subtotal, 0);
}

function calcularTotal() {
    const subtotal = calcularSubtotal();
    const iva = subtotal * 0.15;
    return subtotal + iva;
}

async function procesarFactura(esEncargo, encargoDetalles = null) {
    showLoading(true);

    try {
        const subtotal = calcularSubtotal();
        const iva = subtotal * 0.15;
        const total = subtotal + iva;

        const payload = {
            carrito: carrito,
            subtotal: subtotal,
            iva: iva,
            total: total,
            es_encargo: esEncargo,
            encargo_detalles: encargoDetalles
        };

        const response = await fetch('/api/factura', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) throw new Error('Error al facturar');
        
        const data = await response.json();
        
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
            <span class="ticket-product-price">$${item.subtotal.toFixed(2)}</span>
        `;
        productosContainer.appendChild(row);

        // Si tiene ingredientes, mostrarlos debajo
        if (item.detalle_ingredientes && item.detalle_ingredientes.ingredientes && item.detalle_ingredientes.ingredientes.length > 0) {
            // Precio base
            const baseRow = document.createElement('div');
            baseRow.style.cssText = 'font-size: 0.75rem; color: #6b7280; padding-left: 0.75rem; padding-top: 0.1rem;';
            baseRow.textContent = `  Base: $${item.detalle_ingredientes.precio_base.toFixed(2)}`;
            productosContainer.appendChild(baseRow);

            item.detalle_ingredientes.ingredientes.forEach(ing => {
                const ingRow = document.createElement('div');
                ingRow.style.cssText = 'display: flex; justify-content: space-between; font-size: 0.75rem; color: #10b981; padding-left: 0.75rem;';
                ingRow.innerHTML = `<span>  + ${ing.nombre}</span><span>+$${ing.precio.toFixed(2)}</span>`;
                productosContainer.appendChild(ingRow);
            });
        }
    });

    // Totales
    document.getElementById('ticket-subtotal').textContent = `$${factura.subtotal.toFixed(2)}`;
    document.getElementById('ticket-iva').textContent = `$${factura.iva.toFixed(2)}`;
    document.getElementById('ticket-total').textContent = `$${factura.total.toFixed(2)}`;

    // Sección de encargo
    const encargoSection = document.getElementById('ticket-encargo-section');
    if (factura.es_encargo && factura.encargo_detalles) {
        encargoSection.classList.remove('hidden');
        document.getElementById('ticket-cliente').textContent = factura.encargo_detalles.nombre_cliente || 'N/A';
        document.getElementById('ticket-adelanto').textContent = `$${factura.encargo_detalles.adelanto.toFixed(2)}`;
        document.getElementById('ticket-saldo').textContent = `$${factura.encargo_detalles.saldo.toFixed(2)}`;
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
