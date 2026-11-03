/* Recomendaciones efímeras del carrito; no guarda identidad ni actividad del invitado. */
(() => {
    const section = document.querySelector('.store-recs');
    const grid = document.querySelector('.store-recs-grid');
    const count = document.querySelector('.store-recs-count');
    if (!section || !grid || !count) return;

    let timer;
    let pending;
    let revision = 0;

    function card(product) {
        const id = Number(product.id);
        const price = Number(product.precio);
        const discount = Math.min(100, Math.max(0, Number(product.descuento) || 0));
        if (!Number.isSafeInteger(id) || id <= 0 || !Number.isFinite(price) || price < 0) return null;

        const article = document.createElement('article');
        article.className = 'product-card store-recs-card';
        article.dataset.id = String(id);
        article.dataset.nombre = String(product.nombre || 'Producto');
        article.dataset.precio = String(price);
        article.dataset.categoria = String(product.categoria || '');
        article.dataset.descuento = String(discount);

        const reason = document.createElement('span');
        reason.className = 'store-recs-reason';
        reason.textContent = String(product.motivo || 'Sugerencia de la tienda');
        article.appendChild(reason);

        const main = document.createElement('div');
        main.className = 'store-recs-card-main';
        const details = document.createElement('div');
        const category = document.createElement('p');
        category.className = 'store-recs-category';
        category.textContent = article.dataset.categoria;
        const title = document.createElement('h3');
        title.textContent = article.dataset.nombre;
        details.append(category, title);
        main.appendChild(details);
        if (product.imagen_url) {
            const picture = document.createElement('img');
            picture.className = 'store-recs-image';
            picture.src = String(product.imagen_url);
            picture.alt = '';
            picture.loading = 'lazy';
            main.appendChild(picture);
        }
        article.appendChild(main);

        const footer = document.createElement('div');
        footer.className = 'store-recs-card-footer';
        const amount = document.createElement('span');
        amount.textContent = `C$${(price * (1 - discount / 100)).toFixed(2)}`;
        if (discount > 0) {
            const badge = document.createElement('small');
            badge.textContent = ` −${Math.round(discount)}%`;
            amount.appendChild(badge);
        }
        const add = document.createElement('button');
        add.type = 'button';
        add.className = 'store-recs-add';
        add.textContent = article.dataset.categoria === 'Reposteria' ? 'Personalizar' : 'Agregar';
        add.setAttribute('aria-label', `${add.textContent} ${article.dataset.nombre} al pedido`);
        footer.append(amount, add);
        article.appendChild(footer);
        return article;
    }

    window.addEventListener('carritoActualizado', event => {
        const items = Array.isArray(event.detail?.carrito) ? event.detail.carrito : [];
        const ids = [...new Set(items.map(item => Number(item.id))
            .filter(id => Number.isSafeInteger(id) && id > 0))].slice(0, 10);
        clearTimeout(timer);
        if (pending) pending.abort();
        const current = ++revision;
        timer = setTimeout(async () => {
            pending = new AbortController();
            try {
                const response = await fetch(`/api/mercadotecnia/recomendaciones?carrito=${ids.join(',')}`,
                    { signal: pending.signal, credentials: 'same-origin' });
                if (!response.ok) return;
                const data = await response.json();
                if (current !== revision || !Array.isArray(data.productos)) return;
                const nodes = data.productos.map(card).filter(Boolean);
                grid.replaceChildren(...nodes);
                count.textContent = `${nodes.length} sugerencia${nodes.length === 1 ? '' : 's'}`;
                section.hidden = nodes.length === 0;
            } catch (error) {
                if (error.name !== 'AbortError') console.warn('Sugerencias no disponibles');
            }
        }, 300);
    });
})();
