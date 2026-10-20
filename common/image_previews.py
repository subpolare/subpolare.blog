"""Prepare homepage derivatives through Pepic, without writing original files."""
from django.conf import settings

from common.images import (
    PREVIEW_LENGTHS, PREVIEW_VERSION, file_dimensions, image_dimensions,
    pepic_filename, storage_path,
)


class PreviewPreparationError(Exception):
    pass


def prepare_previews(url, session):
    """Generate only missing derivatives; external covers remain unchanged."""
    name = pepic_filename(url)
    if not name:
        return 0
    dimensions = image_dimensions(url)
    if not dimensions:
        raise PreviewPreparationError(f"Cannot read cover dimensions: {url}")

    prepared = 0
    for length in PREVIEW_LENGTHS:
        if length >= max(dimensions):
            continue
        path = storage_path(name, f"resize/{length}")
        actual = file_dimensions(path)
        if actual and max(actual) == length:
            continue
        preview_url = f"{settings.PEPIC_MEDIA_ORIGIN}/{length}/{name}?v={PREVIEW_VERSION}"
        with session.get(
            preview_url, timeout=(5, 20), stream=True, allow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise PreviewPreparationError(f"Preview returned {response.status_code}: {preview_url}")
            for _ in response.iter_content(65536):
                pass
        actual = file_dimensions(path)
        if not actual or max(actual) != length:
            raise PreviewPreparationError(f"Invalid or missing prepared preview: {preview_url}")
        prepared += 1
    return prepared
