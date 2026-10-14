/* Contrato común para formularios y APIs del mismo origen. */
(() => {
    const token = document.querySelector('meta[name="csrf-token"]')?.content;
    const originalFetch = window.fetch.bind(window);
    window.fetch = (input, options = {}) => {
        const url = new URL(input instanceof Request ? input.url : input, location.href);
        const method = (options.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
        if (url.origin === location.origin && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
            const headers = new Headers(options.headers || (input instanceof Request ? input.headers : {}));
            if (token) headers.set('X-CSRFToken', token);
            options = {...options, headers};
        }
        return originalFetch(input, options);
    };
    document.addEventListener('submit', event => {
        const form = event.target;
        if (form.method.toLowerCase() === 'post' && new URL(form.action).origin === location.origin && !form.querySelector('[name="csrf_token"]')) {
            const hidden = document.createElement('input');
            hidden.type = 'hidden'; hidden.name = 'csrf_token'; hidden.value = token || '';
            form.append(hidden);
        }
    }, true);
    document.querySelectorAll('table').forEach(table => {
        if (!table.closest('.table-responsive, .table-scroll')) {
            const wrapper = document.createElement('div'); wrapper.className = 'table-responsive';
            table.before(wrapper); wrapper.append(table);
        }
    });
    document.querySelectorAll('.table-responsive').forEach(element => {
        element.tabIndex = 0; element.setAttribute('role', 'region');
        element.setAttribute('aria-label', 'Tabla de datos; desplácese horizontalmente para ver todas las columnas');
    });
    document.querySelectorAll('#toast-container').forEach(element => element.setAttribute('aria-live', 'polite'));
    const nav = document.getElementById('glass-dock');
    if (nav) {
        const button = document.createElement('button'); button.type='button';
        button.className='mobile-menu-toggle'; button.textContent='☰ Menú';
        button.setAttribute('aria-controls','glass-dock'); button.setAttribute('aria-expanded','false');
        document.body.prepend(button);
        const close = () => { nav.classList.remove('mobile-open'); button.setAttribute('aria-expanded','false'); };
        button.addEventListener('click', () => {
            const open=nav.classList.toggle('mobile-open'); button.setAttribute('aria-expanded',String(open));
        });
        document.addEventListener('keydown',event => { if (event.key === 'Escape') close(); });
        nav.querySelectorAll('a').forEach(link => {
            link.addEventListener('click',close);
            if (link.classList.contains('active')) link.setAttribute('aria-current','page');
        });
    }
})();
