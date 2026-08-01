let carrito = [];

document.addEventListener('DOMContentLoaded', () => {
    // Escuchar clics en productos (event delegation)
    const catalogPanel = document.querySelector('.catalog-panel');
    catalogPanel.addEventListener('click', (e) => {
        const card = e.target.closest('.product-card');
        if (card) {
            const id = parseInt(card.dataset.id);
            const nombre = card.dataset.nombre;
            const precio = parseFloat(card.dataset.precio);
            const categoria = card.dataset.categoria;
            
            if (categoria === 'Encargo') {
                abrirModalIngredientes(id, nombre, precio, categoria);
            } else {
                agregarAlCarrito(id, nombre, precio, categoria);
            }
        }
    });

    // Lógica del Modal de Ingredientes
    let itemPendienteParaCarrito = null;
    const ingredientesModal = document.getElementById('ingredientes-modal');
    const btnConfirmarIngredientes = document.getElementById('btn-confirmar-ingredientes');
    const btnCerrarIngredientes = document.getElementById('btn-cerrar-ingredientes');
    const inputIngredientesTotal = document.getElementById('modal-ingredientes-total');
    const ingredientesCheckboxes = document.querySelectorAll('.ingrediente-cb');

    window.abrirModalIngredientes = function(id, nombre, precio, categoria) {
        itemPendienteParaCarrito = { id, nombre, precioBase: precio, categoria };
        
        // Resetear checkboxes
        ingredientesCheckboxes.forEach(cb => cb.checked = false);
        actualizarTotalIngredientes();
        
        document.getElementById('modal-ingredientes-title').textContent = `Personalizar ${nombre}`;
        ingredientesModal.classList.remove('hidden');
    }

    function actualizarTotalIngredientes() {
        if (!itemPendienteParaCarrito) return;
        let total = itemPendienteParaCarrito.precioBase;
        ingredientesCheckboxes.forEach(cb => {
            if (cb.checked) total += parseFloat(cb.value);
        });
        inputIngredientesTotal.value = `$${total.toFixed(2)}`;
    }

    ingredientesCheckboxes.forEach(cb => {
        cb.addEventListener('change', actualizarTotalIngredientes);
    });

    if (btnCerrarIngredientes) {
        btnCerrarIngredientes.addEventListener('click', () => {
            ingredientesModal.classList.add('hidden');
            itemPendienteParaCarrito = null;
        });
    }

    if (btnConfirmarIngredientes) {
        btnConfirmarIngredientes.addEventListener('click', () => {
            if (!itemPendienteParaCarrito) return;
            
            let ingredientesNombres = [];
            let total = itemPendienteParaCarrito.precioBase;
            
            ingredientesCheckboxes.forEach(cb => {
                if (cb.checked) {
                    total += parseFloat(cb.value);
                    ingredientesNombres.push(cb.dataset.nombre);
                }
            });

            let nombreFinal = itemPendienteParaCarrito.nombre;
            if (ingredientesNombres.length > 0) {
                nombreFinal += ` (${ingredientesNombres.join(', ')})`;
            }

            // Usamos un ID único si tiene ingredientes para no agruparlo con otro distinto
            let idFinal = itemPendienteParaCarrito.id;
            if (ingredientesNombres.length > 0) {
                idFinal = idFinal + "_" + Date.now();
            }

            agregarAlCarrito(idFinal, nombreFinal, total, itemPendienteParaCarrito.categoria);
            
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
        const tieneEncargos = carrito.some(item => item.categoria === 'Encargo');
        
        if (tieneEncargos) {
            inputTotalModal.value = `$${calcularTotal().toFixed(2)}`;
            inputAdelanto.value = '';
            inputSaldo.value = `$${calcularTotal().toFixed(2)}`;
            modal.classList.remove('hidden');
        } else {
            procesarFactura(false);
        }
    });

    inputAdelanto.addEventListener('input', (e) => {
        const adelanto = parseFloat(e.target.value) || 0;
        const total = calcularTotal();
        const saldo = total - adelanto;
        inputSaldo.value = `$${saldo.toFixed(2)}`;
    });

    function cerrarModal() {
        modal.classList.add('hidden');
    }

    if(btnCerrarModal) {
        btnCerrarModal.addEventListener('click', cerrarModal);
    }

    btnConfirmarEncargo.addEventListener('click', () => {
        const adelanto = parseFloat(inputAdelanto.value);
        const fecha = document.getElementById('modal-fecha').value;
        
        if (isNaN(adelanto) || !fecha) {
            showToast('Por favor, ingresa el adelanto y la fecha de entrega', true);
            return;
        }
        
        cerrarModal();
        procesarFactura(true, {
            adelanto: adelanto,
            saldo: calcularTotal() - adelanto,
            fecha_entrega: fecha
        });
    });
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

function agregarAlCarrito(id, nombre, precio, categoria) {
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
            subtotal: precio
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
                <button type="button" class="btn-qty" onclick="modificarCantidad(${item.id}, -1)">-</button>
                <span>${item.cantidad}</span>
                <button type="button" class="btn-qty" onclick="modificarCantidad(${item.id}, 1)">+</button>
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

function calcularTotal() {
    const subtotal = carrito.reduce((sum, item) => sum + item.subtotal, 0);
    const iva = subtotal * 0.15;
    return subtotal + iva;
}

async function procesarFactura(esEncargo, encargoDetalles = null) {
    showLoading(true);

    try {
        const payload = {
            carrito: carrito,
            total: calcularTotal(),
            es_encargo: esEncargo,
            encargo_detalles: encargoDetalles
        };

        const response = await fetch('/api/factura', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) throw new Error('Error al facturar');
        
        showToast('¡Factura registrada exitosamente!');
        carrito = []; 
        renderizarCarrito();
    } catch (error) {
        console.error(error);
        showToast('Error de conexión al servidor', true);
    } finally {
        showLoading(false);
    }
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
