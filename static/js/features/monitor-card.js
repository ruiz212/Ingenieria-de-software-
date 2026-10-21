/** Production cards: customer content is always text, never executable markup. */
(() => {
    function add(parent, tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = String(text);
        parent.append(node);
        return node;
    }

    function referenceURL(value) {
        if (typeof value !== 'string' || !value.trim()) return null;
        const raw = value.trim();
        if (raw.startsWith('//') || (/^[a-z][a-z0-9+.-]*:/i.test(raw) && !/^https?:\/\//i.test(raw))) return null;
        try {
            const path = /^https?:\/\//i.test(raw) ? raw : '/' + (raw.replace(/^\//, '').startsWith('static/') ? raw.replace(/^\//, '') : 'static/' + raw.replace(/^\//, ''));
            const url = new URL(path, window.location.href);
            return ['http:', 'https:'].includes(url.protocol) ? url.href : null;
        } catch { return null; }
    }

    function action(parent, code, state, label, className) {
        const button = add(parent, 'button', className, label);
        button.type = 'button';
        button.dataset.nextState = state;
        button.addEventListener('click', () => window.cambiarEstado(code, state));
    }

    window.createCard = function createCard(encargo) {
        const details = encargo.encargo_detalles || {};
        const state = ['Pendiente', 'En Proceso', 'Listo', 'Entregado'].includes(details.estado) ? details.estado : 'Pendiente';
        const code = String(encargo.codigo_seguimiento || '');
        const card = document.createElement('div');
        card.className = `kds-card card-${state.replace(' ', '_')}`;
        card.id = `card-${code}`;
        card.dataset.code = code;
        const header = add(card, 'div', 'kds-card-header');
        add(header, 'span', 'kds-invoice', '#' + (encargo.numero_factura || ''));
        add(header, 'span', 'kds-time', encargo.hora || '');
        const customer = add(card, 'div', 'kds-customer');
        const customerRow = add(customer, 'div', 'kds-customer-row');
        add(customerRow, 'strong', '', details.nombre_cliente || 'Cliente');
        if (details.telefono) {
            const phone = String(details.telefono);
            const link = add(customerRow, 'a', 'kds-tel-link', '📞 ' + phone);
            link.href = 'tel:' + phone.replace(/[^\d+() -]/g, '');
        }
        const delivery = add(customer, 'div', 'monitor-div-text', 'Para entregar: ');
        add(delivery, 'span', 'monitor-span-text', details.fecha_entrega || 'Sin fecha');

        const imageURL = referenceURL(details.ruta_imagen_referencia);
        if (imageURL) {
            const container = add(card, 'div', 'kds-image-container');
            const link = add(container, 'a', '');
            link.href = imageURL;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.title = 'Clic para ampliar foto de referencia';
            const image = add(link, 'img', '');
            image.src = imageURL;
            image.alt = 'Foto de referencia';
            image.loading = 'lazy';
            add(link, 'span', 'kds-image-badge', '🔍 Foto de referencia');
        }
        for (const [value, label, className] of [
            [details.especificaciones, '✨ Personalizado: ', 'kds-alert'],
            [details.notas, '📝 Nota: ', 'kds-notes']
        ]) {
            if (value) {
                const block = add(card, 'div', className);
                add(block, 'strong', '', label);
                block.append(document.createTextNode(String(value)));
            }
        }

        const products = add(card, 'div', 'kds-products');
        for (const item of encargo.productos || []) {
            const row = add(products, 'div', 'kds-product-row');
            add(row, 'span', 'kds-qty', 'x' + (item.cantidad || 1));
            const info = add(row, 'div', 'monitor-div-spacing');
            add(info, 'span', 'kds-name', String(item.nombre || 'Producto').split(' (')[0]);
            const ingredients = item.detalle_ingredientes?.ingredientes || [];
            if (ingredients.length) {
                const extras = add(info, 'div', 'kds-addons');
                ingredients.forEach((ingredient, index) => {
                    if (index) extras.append(document.createElement('br'));
                    extras.append(document.createTextNode('+ ' + (ingredient.nombre || 'Extra')));
                });
            }
        }
        if (!products.children.length) add(products, 'div', 'kds-empty-products', 'Sin líneas de producto registradas');
        const actions = add(card, 'div', 'kds-actions');
        const status = add(actions, 'div', 'kds-status-line');
        add(status, 'span', '', 'Estado actual');
        add(status, 'strong', '', state);
        const buttons = add(actions, 'div', 'kds-action-buttons');
        if (state === 'Pendiente') {
            action(buttons, code, 'En Proceso', '▶ Iniciar Preparación', 'btn btn-warning w-100 kds-state-button');
        } else if (state === 'En Proceso') {
            action(buttons, code, 'Listo', '✓ Marcar como Listo', 'btn btn-success w-100 kds-state-button');
            action(buttons, code, 'Pendiente', '↩ Devolver a Pendiente', 'kds-btn-revert');
        } else if (state === 'Listo') {
            action(buttons, code, 'Entregado', '📦 Marcar como Entregado', 'btn btn-primary w-100 kds-state-button monitor-btn-primary');
            action(buttons, code, 'En Proceso', '↩ Regresar a Preparación', 'kds-btn-revert');
        }
        return card;
    };
})();
