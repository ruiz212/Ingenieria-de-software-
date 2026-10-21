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
        document.documentElement.classList.add('has-navigation-js');
        const button = document.querySelector('.mobile-menu-toggle');
        const backdrop = document.querySelector('.nav-backdrop');
        const main = document.querySelector('.main-content');
        const mobile = window.matchMedia('(max-width: 900px)');
        const search = document.getElementById('module-search');
        const clear = document.getElementById('module-search-clear');
        const menu = nav.querySelector('.dock-menu');
        const noResults = nav.querySelector('.dock-no-results');
        const scrollHint = nav.querySelector('.dock-scroll-hint');
        const updateScrollHint = () => {
            if (scrollHint) scrollHint.hidden = menu.scrollTop + menu.clientHeight >= menu.scrollHeight - 4;
        };
        const revealCurrentSection = () => {
            const current = menu.querySelector('.dock-item.active:not([hidden])');
            if (!current) return;
            const itemBounds = current.getBoundingClientRect();
            const menuBounds = menu.getBoundingClientRect();
            if (itemBounds.top < menuBounds.top || itemBounds.bottom > menuBounds.bottom) {
                menu.scrollTop += itemBounds.top - menuBounds.top - (menu.clientHeight - itemBounds.height) / 2;
            }
            updateScrollHint();
        };
        const normal = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
        const filterMenu = () => {
            const query = normal(search.value);
            let count = 0;
            menu.querySelectorAll('.dock-item').forEach(link => {
                link.hidden = !normal(link.textContent).includes(query);
                if (!link.hidden) count++;
            });
            menu.querySelectorAll('.menu-label').forEach(label => {
                let item = label.nextElementSibling;
                let visible = false;
                while (item && !item.classList.contains('menu-label')) {
                    if (item.classList.contains('dock-item') && !item.hidden) visible = true;
                    item = item.nextElementSibling;
                }
                label.hidden = !visible;
            });
            clear.hidden = !search.value;
            noResults.hidden = count !== 0;
            menu.scrollTop = 0;
            updateScrollHint();
        };
        search?.addEventListener('input', filterMenu);
        clear?.addEventListener('click', () => { search.value = ''; filterMenu(); search.focus(); });
        const setOpen = (open, restoreFocus = false) => {
            open = mobile.matches && open;
            nav.classList.toggle('mobile-open', open);
            nav.inert = mobile.matches && !open;
            main.inert = open;
            document.body.classList.toggle('navigation-open', open);
            button.setAttribute('aria-expanded', String(open));
            backdrop.hidden = !open;
            if (open) {
                (search || nav.querySelector('a')).focus();
                revealCurrentSection();
            }
            else if (restoreFocus) button.focus();
        };
        const close = (restoreFocus = false) => setOpen(false, restoreFocus);
        button.addEventListener('click', () => {
            setOpen(!nav.classList.contains('mobile-open'), true);
        });
        nav.querySelector('.dock-close')?.addEventListener('click', () => close(true));
        backdrop.addEventListener('click', () => close(true));
        mobile.addEventListener('change', () => { close(); revealCurrentSection(); });
        menu.addEventListener('scroll', updateScrollHint, {passive:true});
        window.addEventListener('resize', updateScrollHint, {passive:true});
        setOpen(false);
        revealCurrentSection();
        document.addEventListener('keydown', event => {
            if (!mobile.matches || !nav.classList.contains('mobile-open')) return;
            if (event.key === 'Escape') { event.preventDefault(); close(true); }
            if (event.key === 'Tab') {
                const controls = [...nav.querySelectorAll('a[href], button, input')]
                    .filter(element => !element.disabled && !element.closest('[hidden]') && element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden');
                const first = controls[0], last = controls[controls.length - 1];
                if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
                else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
            }
        });
        nav.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', () => close());
            if (link.classList.contains('active')) link.setAttribute('aria-current','page');
        });
        nav.querySelectorAll('svg').forEach(icon => icon.setAttribute('aria-hidden', 'true'));
    }
})();
