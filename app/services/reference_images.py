"""References are public local uploads or images on ImgBB's exact HTTPS origin."""
from pathlib import Path
import re

from flask import current_app


_LOCAL = re.compile(r'uploads/referencias/[A-Za-z0-9_-][A-Za-z0-9_.-]*\.(?:jpg|jpeg|png|webp)', re.I)
_IMGBB = re.compile(r'https://i\.ibb\.co/[A-Za-z0-9_-]+/[A-Za-z0-9_-][A-Za-z0-9_.-]*\.(?:jpg|jpeg|png|webp)', re.I)


def validate_reference_image(value):
    """Normalize approved references; reject markup, schemes and paths outside uploads."""
    if value is None or value == '':
        return None
    message = 'La referencia debe ser una imagen subida o una URL HTTPS de i.ibb.co.'
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError(message)
    if _IMGBB.fullmatch(value):
        return value
    relative = value
    for prefix in ('/static/', 'static/'):
        if relative.startswith(prefix):
            relative = relative[len(prefix):]
            break
    if not _LOCAL.fullmatch(relative):
        raise ValueError(message)
    folder = (Path(current_app.static_folder) / 'uploads' / 'referencias').resolve()
    candidate = (Path(current_app.static_folder) / relative).resolve()
    if not candidate.is_relative_to(folder) or not candidate.is_file():
        raise ValueError(message)
    return relative
