"""Windows Shell thumbnail verification and cache refresh helpers."""

from __future__ import annotations

from io import BytesIO
import ctypes
from ctypes import wintypes
import logging
import os
from pathlib import Path
import uuid

from PIL import Image, ImageChops, ImageStat
from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QImage


logger = logging.getLogger(__name__)
_ISHELL_ITEM_IMAGE_FACTORY = "bcc18b79-ba16-442f-80c4-8a59c30c463b"
_SIIGBF_BIGGERSIZEOK = 0x00000001
_SIIGBF_THUMBNAILONLY = 0x00000008
_SHCNE_UPDATEITEM = 0x00002000
_SHCNF_PATHW = 0x0005
_RPC_E_CHANGED_MODE = -2147417850


class _GUID(ctypes.Structure):
    _fields_ = (
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    )

    @classmethod
    def parse(cls, value: str) -> "_GUID":
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


class _SIZE(ctypes.Structure):
    _fields_ = (("cx", ctypes.c_long), ("cy", ctypes.c_long))


def _shell_image(path: Path, size: int = 256) -> QImage | None:
    if os.name != "nt" or not path.is_file():
        return None
    ole32 = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32
    gdi32 = ctypes.windll.gdi32
    initialized = int(ole32.CoInitializeEx(None, 0x2))
    should_uninitialize = initialized in {0, 1}
    if initialized < 0 and initialized != _RPC_E_CHANGED_MODE:
        logger.warning("CoInitializeEx failed with HRESULT 0x%08X", initialized & 0xFFFFFFFF)
        return None
    factory = ctypes.c_void_p()
    iid = _GUID.parse(_ISHELL_ITEM_IMAGE_FACTORY)
    shell32.SHCreateItemFromParsingName.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    )
    shell32.SHCreateItemFromParsingName.restype = ctypes.c_long
    try:
        result = int(shell32.SHCreateItemFromParsingName(str(path), None, ctypes.byref(iid), ctypes.byref(factory)))
        if result < 0 or not factory.value:
            logger.info("Shell thumbnail factory unavailable for %s (HRESULT 0x%08X)", path.suffix, result & 0xFFFFFFFF)
            return None
        vtable = ctypes.cast(factory, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        get_image_type = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            _SIZE,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_void_p),
        )
        release_type = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
        get_image = get_image_type(vtable[3])
        release = release_type(vtable[2])
        bitmap = ctypes.c_void_p()
        try:
            result = int(get_image(
                factory,
                _SIZE(size, size),
                _SIIGBF_THUMBNAILONLY | _SIIGBF_BIGGERSIZEOK,
                ctypes.byref(bitmap),
            ))
            if result < 0 or not bitmap.value:
                logger.info("Shell provider did not return a thumbnail (HRESULT 0x%08X)", result & 0xFFFFFFFF)
                return None
            try:
                image = QImage.fromHBITMAP(int(bitmap.value))
                return image.copy() if not image.isNull() else None
            finally:
                gdi32.DeleteObject(bitmap)
        finally:
            release(factory)
    finally:
        if should_uninitialize:
            ole32.CoUninitialize()


def _qimage_png(image: QImage) -> bytes:
    encoded = QByteArray()
    buffer = QBuffer(encoded)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        return b""
    return bytes(encoded)


def _content_crop(image: Image.Image) -> Image.Image:
    converted = image.convert("RGBA")
    alpha = converted.getchannel("A")
    bounds = alpha.getbbox()
    return converted.crop(bounds) if bounds else converted


def _difference_hash(image: Image.Image) -> int:
    small = _content_crop(image).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(small.get_flattened_data())
    value = 0
    for row in range(8):
        offset = row * 9
        for column in range(8):
            value = (value << 1) | int(pixels[offset + column] > pixels[offset + column + 1])
    return value


def images_visually_similar(first: Image.Image, second: Image.Image) -> bool:
    hash_distance = (_difference_hash(first) ^ _difference_hash(second)).bit_count()
    first_small = _content_crop(first).convert("RGB").resize((32, 32), Image.Resampling.LANCZOS)
    second_small = _content_crop(second).convert("RGB").resize((32, 32), Image.Resampling.LANCZOS)
    difference = ImageChops.difference(first_small, second_small)
    rms = sum(ImageStat.Stat(difference).rms) / (3 * 255)
    return rms <= 0.18 or (hash_distance <= 18 and rms <= 0.30)


def shell_thumbnail_matches(media_path: Path, reference_image: Path) -> bool | None:
    shell = _shell_image(media_path)
    if shell is None:
        return None
    encoded = _qimage_png(shell)
    if not encoded:
        return None
    with Image.open(BytesIO(encoded)) as shell_image, Image.open(reference_image) as reference:
        return images_visually_similar(shell_image, reference)


def notify_shell_updated(path: Path) -> None:
    if os.name != "nt":
        return
    shell32 = ctypes.windll.shell32
    shell32.SHChangeNotify(
        _SHCNE_UPDATEITEM,
        _SHCNF_PATHW,
        ctypes.c_wchar_p(str(path)),
        None,
    )
