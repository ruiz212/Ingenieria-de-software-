let carrito = [];

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

function modificarCantidad(id, delta) {
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
}

function renderizarCarrito() {
    const cartItemsContainer = document.getElementById('cart-items');
    const subtotalDisplay = document.getElementById('subtotal-display');
    const totalDisplay = document.getElementById('total-display');
    const btnFacturar = document.getElementById('btn-facturar');

    cartItemsContainer.innerHTML = '';

    if (carrito.length === 0) {
        cartItemsContainer.innerHTML = '<div class="empty-cart">Selecciona productos para comenzar</div>';
        subtotalDisplay.textContent = '$0.00';
        totalDisplay.textContent = '$0.00';
        btnFacturar.disabled = true;
        return;
    }

    let total = 0;

    carrito.forEach(item => {
        total += item.subtotal;
        const itemEl = document.createElement('div');
        itemEl.className = 'cart-item';
        itemEl.innerHTML = `
            <div class="cart-item-info">
                <div class="cart-item-name">${item.nombre}</div>
                <div class="cart-item-price">$${item.precio.toFixed(2)} x ${item.cantidad}</div>
            </div>
            <div class="cart-item-actions">
                <button class="btn-qty" onclick="modificarCantidad(${item.id}, -1)">-</button>
                <span>${item.cantidad}</span>
                <button class="btn-qty" onclick="modificarCantidad(${item.id}, 1)">+</button>
            </div>
            <div style="font-weight: 600;">$${item.subtotal.toFixed(2)}</div>
        `;
        cartItemsContainer.appendChild(itemEl);
    });

    subtotalDisplay.textContent = `$${total.toFixed(2)}`;
    totalDisplay.textContent = `$${total.toFixed(2)}`;
    btnFacturar.disabled = false;
}

function calcularTotal() {
    return carrito.reduce((sum, item) => sum + item.subtotal, 0);
}

// Lógica de Facturación y Modal de Encargos
const btnFacturar = document.getElementById('btn-facturar');
const modal = document.getElementById('encargo-modal');
const btnConfirmarEncargo = document.getElementById('btn-confirmar-encargo');

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
