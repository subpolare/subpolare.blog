"""Bounded cover snapshots. Public views only read the prepared bytes."""
import http.client
import io
import ipaddress
import socket
import ssl
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import urlsplit

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 24_000_000
MAX_SIDE = 12000
MAX_PREVIEW_BYTES = 20_000
_RESOLVER = ThreadPoolExecutor(max_workers=2, thread_name_prefix="map-dns")
_DNS_SLOTS = BoundedSemaphore(2)


class PreviewError(ValueError):
    pass


def public_addresses(host):
    # DNS itself can block. Bound both its wait time and the number of resolver
    # jobs; a timed-out resolver cannot create an unbounded thread/queue backlog.
    if not _DNS_SLOTS.acquire(blocking=False):
        raise PreviewError("Определение адреса временно недоступно.")
    future = _RESOLVER.submit(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
    future.add_done_callback(lambda result: _DNS_SLOTS.release())
    addresses = future.result(timeout=3)
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global or ip.is_multicast or ip.is_reserved:
            raise PreviewError("Адрес обложки не является публичным.")
    if not addresses:
        raise PreviewError("У хоста обложки нет публичного адреса.")
    return addresses


@lru_cache(maxsize=1)
def placeholder():
    return (Path(__file__).parent / "placeholder.webp").read_bytes()


def prepare_preview(data):
    if not data or len(data) > MAX_SOURCE_BYTES:
        raise PreviewError("Изображение пустое или больше 8 МиБ.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP", "GIF"}:
                    raise PreviewError("Допустимы только JPEG, PNG, WebP и GIF.")
                width, height = source.size
                if width * height > MAX_PIXELS or max(width, height) > MAX_SIDE:
                    raise PreviewError("Изображение слишком большое: максимум 24 Мп и 12000 px по стороне.")
                source.verify()
            with Image.open(io.BytesIO(data)) as source:
                source.seek(0)
                image = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"), (128, 128), method=Image.Resampling.LANCZOS)
                for quality in (82, 65, 45, 25):
                    output = io.BytesIO()
                    image.save(output, format="WEBP", quality=quality, method=6)
                    if output.tell() <= MAX_PREVIEW_BYTES:
                        return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, EOFError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise PreviewError("Не удалось прочитать изображение.") from error
    raise PreviewError("Не удалось уменьшить превью до 20 КБ.")


class _DeadlineReader(io.RawIOBase):
    """Apply a wall-clock deadline to every header/body socket read, including trickles."""
    def __init__(self, sock, deadline):
        self.sock = sock
        self.deadline = deadline
        # Preserve the socket's file reference. HTTPConnection closes its socket
        # immediately for Connection: close; the response must still own the fd.
        self.stream = sock.makefile("rb", buffering=0)

    def readable(self):
        return True

    def readinto(self, buffer):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Cover deadline exceeded")
        self.sock.settimeout(min(3, remaining))
        return self.stream.readinto(buffer)

    def close(self):
        try:
            self.stream.close()
        finally:
            super().close()


class _DeadlineSocket:
    def __init__(self, sock, deadline):
        self.sock = sock
        self.deadline = deadline

    def makefile(self, mode):
        return io.BufferedReader(_DeadlineReader(self.sock, self.deadline))

    def __getattr__(self, name):
        return getattr(self.sock, name)


def fetch_cover(url):
    try:
        parsed = urlsplit(url or "")
        host = parsed.hostname
        if (parsed.scheme != "https" or host not in settings.MAP_IMAGE_ALLOWED_HOSTS
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or parsed.fragment or any(ord(c) <= 32 for c in (url or "")) or "\\" in (url or "")):
            raise PreviewError("Обложка должна использовать HTTPS и разрешённый хост.")
        addresses = public_addresses(host)
        # Connect to the vetted IP, never resolve the hostname a second time. TLS
        # still verifies the original hostname. Environment proxies are not used.
        deadline = time.monotonic() + 8
        family, socktype, proto, _, address = addresses[0]
        connection = http.client.HTTPSConnection(host, timeout=3)
        raw_socket = socket.socket(family, socktype, proto)
        response = None
        try:
            raw_socket.settimeout(3)
            raw_socket.connect(address)
            tls_socket = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=host)
            connection.sock = _DeadlineSocket(tls_socket, deadline)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Cover deadline exceeded")
            tls_socket.settimeout(min(3, remaining))
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            connection.request("GET", path, headers={"Accept": "image/*", "Accept-Encoding": "identity", "User-Agent": "SubpolareMap/1.0"})
            response = connection.getresponse()
            if response.status != 200 or response.getheader("Content-Encoding", "identity") != "identity":
                raise PreviewError("Хост не отдал изображение (перенаправления запрещены).")
            length = response.getheader("Content-Length")
            if length and int(length) > MAX_SOURCE_BYTES:
                raise PreviewError("Обложка больше 8 МиБ.")
            data = response.read(MAX_SOURCE_BYTES + 1)
            if len(data) > MAX_SOURCE_BYTES:
                raise PreviewError("Обложка больше 8 МиБ.")
            return data
        finally:
            if response is not None:
                response.close()
            connection.close()
            raw_socket.close()
    except (OSError, ValueError, http.client.HTTPException) as error:
        raise PreviewError("Не удалось безопасно загрузить обложку.") from error


def update_preview(marker, upload=None):
    """Return an admin warning on failure; never retain the original image."""
    if marker.preview_mode == marker.PreviewMode.CUSTOM and upload is None and marker.preview:
        return None
    try:
        if marker.preview_mode == marker.PreviewMode.CUSTOM:
            data = upload.read(MAX_SOURCE_BYTES + 1) if upload else b""
        else:
            data = fetch_cover(marker.post.main_image())
        marker.preview = prepare_preview(data)
        return None
    except PreviewError as error:
        marker.preview = placeholder()
        return f"{error} Сохранена нейтральная заглушка."
