"""Decode and rewrite untrusted profile photographs before public serving."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import warnings

from PIL import Image, UnidentifiedImageError

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000


def save_profile_image(upload, static_folder):
    data = upload.stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('La foto no puede superar 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP'} or source.width * source.height > MAX_PIXELS:
                    raise ValueError('La foto debe ser una imagen JPEG, PNG o WebP válida.')
                source.load()
                image = source.convert('RGB')
                image.thumbnail((1600, 1600))
                # A new pixel-only image discards metadata, trailing HTML and scripts.
                clean = Image.new('RGB', image.size)
                clean.paste(image)
                output = BytesIO()
                clean.save(output, format='JPEG', quality=88)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('La foto debe ser una imagen JPEG, PNG o WebP válida.') from exc
    folder = Path(static_folder) / 'uploads' / 'perfiles'
    folder.mkdir(parents=True, exist_ok=True)
    name = uuid4().hex + '.jpg'
    path = folder / name
    with path.open('xb') as target:
        target.write(output.getvalue())
    return f'uploads/perfiles/{name}'
