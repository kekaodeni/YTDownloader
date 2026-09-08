"""Bounded compressed-image cache; Qt decodes images on its loading thread."""
from collections import OrderedDict
import hashlib
import threading

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider


class ImageStore(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image, QQuickImageProvider.Flag.ForceAsynchronousImageLoading)
        self._data = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    def add(self, data):
        if not data:
            return ''
        data = bytes(data)
        # Header validation uses QImageReader, without creating a GUI-thread pixmap.
        from PySide6.QtCore import QByteArray, QBuffer, QIODevice
        from PySide6.QtGui import QImageReader
        buffer = QBuffer()
        buffer.setData(QByteArray(data))
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        reader = QImageReader(buffer)
        if not reader.canRead() or reader.size().width() * reader.size().height() > 40_000_000:
            return ''
        key = hashlib.sha256(data).hexdigest()
        with self._lock:
            if key not in self._data:
                self._data[key] = data
                self._bytes += len(data)
            self._data.move_to_end(key)
            while self._bytes > 24 * 1024 * 1024 and len(self._data) > 1:
                _, old = self._data.popitem(last=False)
                self._bytes -= len(old)
        return f'image://thumbnails/{key}'

    def requestImage(self, key, size, requestedSize):
        with self._lock:
            data = self._data.get(key, b'')
        image = QImage.fromData(data)
        if not image.isNull() and requestedSize.isValid():
            image = image.scaled(requestedSize, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if size is not None:
            size.setWidth(image.width())
            size.setHeight(image.height())
        return image
