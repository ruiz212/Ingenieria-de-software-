"""Keyboard contract of the rendered catalog dialog; no server or database."""

from pathlib import Path
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_admin_table_accessibility import ENV  # noqa: E402


root = Path(__file__).resolve().parents[2]
styles = (root / "static/css/dist/app.css").read_text(encoding="utf-8")
styles += (root / "static/css/dist/pages/admin/catalogo.css").read_text(encoding="utf-8")
html = f"<style>{styles}.hidden,.catalogo-np-imagen-file{{display:none!important}}</style><main class='page-catalogo'>" + ENV.get_template(
    "admin/catalogo.html"
).render(productos=[{"id": 7, "nombre": "Pan integral", "imagen_url": "", "categoria": "Pan",
                    "categoria_id": 1, "precio": 20, "descuento": 0, "activo": True}],
         categorias=[]) + "</main>"

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="msedge", headless=True)
    try:
        page = browser.new_page()
        page.set_content(html)
        trigger = page.get_by_role("button", name="Nuevo Producto")
        trigger.click()
        assert page.evaluate("document.activeElement.id") == "np-nombre"
        assert page.evaluate("document.querySelector('.page-header').inert")
        page.locator("#btn-guardar-producto").focus()
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.textContent.trim()") == "Elegir o cambiar imagen"
        page.keyboard.press("Shift+Tab")
        assert page.evaluate("document.activeElement.id") == "btn-guardar-producto"
        page.locator("#np-nombre").focus()
        page.keyboard.press("Escape")
        assert not page.locator("#modal-nuevo-producto").is_visible()
        assert page.evaluate("document.activeElement.textContent.trim()") == "Nuevo Producto"
        assert not page.evaluate("document.querySelector('.page-header').inert")
        for width in (320, 390, 768, 1024, 1366):
            page.set_viewport_size({"width": width, "height": 936})
            action = page.locator("tbody .catalogo-action-column")
            assert action.bounding_box()["x"] + action.bounding_box()["width"] <= width + 1, width
    finally:
        browser.close()
