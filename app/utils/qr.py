# app/utils/qr.py
# Generador de códigos QR

import qrcode
import io
import base64


def generar_qr_base64(data_url):
    """Genera un código QR y lo devuelve como imagen base64 para embeber en HTML."""
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(data_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{img_base64}"
