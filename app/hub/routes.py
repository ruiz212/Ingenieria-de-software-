# app/hub/routes.py
# Ruta del Hub Principal del sistema y endpoints públicos de indexación SEO (robots.txt, sitemap.xml, manifest)

from datetime import date
from flask import redirect, url_for, request, Response, jsonify
from flask_login import login_required, current_user

from app.hub import hub_bp


@hub_bp.route('/')
@login_required
def main_hub():
    """Redirige al módulo correspondiente según el rol del usuario."""
    rol = current_user.rol_nombre

    if rol in ['SuperAdmin', 'Admin']:
        return redirect(url_for('admin.dashboard'))
    elif rol == 'Operativo':
        return redirect(url_for('monitor.monitor_pedidos'))
    elif rol == 'Kiosco':
        return redirect(url_for('kiosco.kiosco_vista'))
    elif rol in ['Estandar', 'Cliente', 'Invitado']:
        return redirect(url_for('pos.index'))

    # Fallback por si acaso
    return redirect(url_for('pos.index'))


@hub_bp.route('/robots.txt')
def robots_txt():
    """Directivas de rastreo para Googlebot y buscadores web."""
    base_url = request.url_root.rstrip('/')
    lines = [
        'User-agent: *',
        'Allow: /tienda',
        'Allow: /cliente/bienvenida',
        'Allow: /cliente/registro',
        'Allow: /login',
        'Disallow: /admin/',
        'Disallow: /api/',
        'Disallow: /kiosco/',
        'Disallow: /monitor',
        f'Sitemap: {base_url}/sitemap.xml',
    ]
    return Response('\n'.join(lines) + '\n', mimetype='text/plain; charset=utf-8')


@hub_bp.route('/sitemap.xml')
def sitemap_xml():
    """Mapa del sitio XML canónico para posicionamiento en Google Search."""
    base_url = request.url_root.rstrip('/')
    hoy = date.today().isoformat()
    urls = [
        (f'{base_url}/tienda', 'daily', '1.0'),
        (f'{base_url}/cliente/bienvenida', 'weekly', '0.9'),
        (f'{base_url}/cliente/registro', 'monthly', '0.8'),
        (f'{base_url}/login', 'monthly', '0.6'),
    ]
    items_xml = '\n'.join(
        f'  <url>\n'
        f'    <loc>{loc}</loc>\n'
        f'    <lastmod>{hoy}</lastmod>\n'
        f'    <changefreq>{freq}</changefreq>\n'
        f'    <priority>{prio}</priority>\n'
        f'  </url>'
        for loc, freq, prio in urls
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'{items_xml}\n'
        '</urlset>\n'
    )
    return Response(xml, mimetype='application/xml; charset=utf-8')


@hub_bp.route('/manifest.webmanifest')
def web_manifest():
    """Web App Manifest con metadatos de marca para buscadores y dispositivos móviles."""
    return jsonify({
        'name': "Brajher's Cake — Panadería Amada",
        'short_name': "Brajher's Cake",
        'description': "Panadería artesanal y pastelería de autor en Managua, Nicaragua. Pasteles personalizados, pan recién horneado y encargos en línea.",
        'start_url': '/tienda',
        'display': 'standalone',
        'background_color': '#F5F0EA',
        'theme_color': '#6B3A2A',
        'lang': 'es-NI',
    })
