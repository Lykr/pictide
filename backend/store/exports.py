"""Build temporary archives of explicitly selected original images."""
from pathlib import Path
import tempfile
import zipfile


def export_images(paths, images):
    with tempfile.NamedTemporaryFile(prefix='liked-', suffix='.zip', dir=paths.tmp, delete=False) as stream:
        target = Path(stream.name)
    try:
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_STORED) as archive:
            for identifier, image in images:
                archive.write(image, f'{identifier}{image.suffix}')
        return target
    except BaseException:
        target.unlink(missing_ok=True)
        raise
