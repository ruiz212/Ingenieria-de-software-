from io import BytesIO
from pathlib import Path
from uuid import uuid4
from PIL import Image, UnidentifiedImageError


def save_image(content, directory):
    if not content or len(content) > 5 * 1024 * 1024:
        raise ValueError('La imagen debe pesar como máximo 5 MB.')
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > 16000000:
                raise ValueError('Formato o dimensiones de imagen no admitidos.')
            image.load()
            clean = image.convert('RGB')
            clean.thumbnail((2000, 2000))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('La imagen no es válida.') from exc
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    name = uuid4().hex + '.jpg'
    clean.save(directory / name, 'JPEG', quality=88)
    return name
