export let carrito = [];

export function agregarAlCarrito(id, nombre, precio, categoria, detalleIngredientes = null) {
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
}

export function modificarCantidad(id, delta) {
    const item = carrito.find(i => i.id === id);
    if (!item) return;

    item.cantidad += delta;
    if (item.cantidad <= 0) {
        eliminarDelCarrito(id);
    } else {
        item.subtotal = item.cantidad * item.precio;
    }
}

export function eliminarDelCarrito(id) {
    carrito = carrito.filter(item => item.id !== id);
}

export function calcularSubtotal() {
    return carrito.reduce((sum, item) => sum + item.subtotal, 0);
}

export function calcularTotales(ivaPorcentaje = 0.15) {
    let subtotal = 0;
    carrito.forEach(item => subtotal += item.subtotal);
    const iva = subtotal * ivaPorcentaje;
    return { subtotal, iva, total: subtotal + iva };
}

export function vaciarCarrito() {
    carrito = [];
}

export function setCarrito(newCarrito) {
    carrito = newCarrito;
}

export function calcularDesgloseCambio(montoCambio) {
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
