from collections import OrderedDict
import hashlib
from pathlib import Path
import uuid

from PySide6.QtCore import QObject, QRunnable, QSize, QThreadPool, Signal, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPixmap


class ThumbnailSignals(QObject):
    ready = Signal(str, QImage)


class ThumbnailJob(QRunnable):
    def __init__(self, key: str, source: Path, target: Path, signals: ThumbnailSignals, image_size=None):
        super().__init__()
        self.key, self.source, self.target, self.signals = key, source, target, signals
        self.image_size=image_size or QSize(88,104)

    def run(self):
        image = QImage()
        try:
            image = QImage(str(self.target))
            if image.isNull():
                reader = QImageReader(str(self.source))
                reader.setAutoTransform(True)
                size = reader.size()
                if size.isValid():
                    reader.setScaledSize(size.scaled(self.image_size, Qt.AspectRatioMode.KeepAspectRatio))
                image = reader.read()
                if not image.isNull():
                    image = image.scaled(self.image_size, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
                    temporary = self.target.with_name(f"{self.key}.{uuid.uuid4().hex}.tmp")
                    try:
                        self.target.parent.mkdir(parents=True, exist_ok=True)
                        if image.save(str(temporary), "PNG"):
                            temporary.replace(self.target)
                    finally:
                        temporary.unlink(missing_ok=True)
        except (OSError, RuntimeError, ValueError):
            pass  # Unreadable photos/cache directories must not prevent roster use.
        self.signals.ready.emit(self.key, image)


class ThumbnailCache(QObject):
    changed = Signal()

    def __init__(self, root: Path, cache_dir: Path, parent=None, *, image_size=None):
        super().__init__(parent)
        self.root, self.cache_dir = root, cache_dir
        self.image_size=image_size or QSize(88,104)
        self.memory = OrderedDict()
        self.pending = set()
        # An icon refresh visits the whole table. Re-queuing evicted thumbnails
        # from that callback creates an endless decode/changed/evict cycle once
        # the table exceeds the memory cache. Completed tiny PNGs can be read
        # without scheduling another completion notification.
        self.completed = set()
        self.signals = ThumbnailSignals(self)
        self.signals.ready.connect(self._ready)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.placeholder = QPixmap(44, 52)
        self.placeholder.fill(QColor("#e8edf4"))
        painter = QPainter(self.placeholder)
        painter.setPen(QColor("#8493a5"))
        painter.drawText(self.placeholder.rect(), Qt.AlignmentFlag.AlignCenter, "사진\n없음")
        painter.end()

    def get(self, relative_path: str) -> QPixmap:
        source = self.root / relative_path
        try:
            stat = source.stat()
        except OSError:
            return self.placeholder
        size_key='' if self.image_size==QSize(88,104) else f'|{self.image_size.width()}x{self.image_size.height()}'
        key = hashlib.sha256(f"v1{size_key}|{relative_path}|{stat.st_mtime_ns}|{stat.st_size}".encode()).hexdigest()
        if key in self.memory:
            self.memory.move_to_end(key)
            return self.memory[key]
        if key in self.completed:
            pixmap=QPixmap(str(self.cache_dir / f"{key}.png"))
            if pixmap.isNull():return self.placeholder
            pixmap.setDevicePixelRatio(2.0)
            self.memory[key]=pixmap
            while len(self.memory)>256:self.memory.popitem(last=False)
            return pixmap
        if key not in self.pending:
            self.pending.add(key)
            self.pool.start(ThumbnailJob(key, source, self.cache_dir / f"{key}.png", self.signals,self.image_size))
        return self.placeholder

    def _ready(self, key: str, image: QImage):
        self.pending.discard(key)
        self.completed.add(key)
        pixmap = self.placeholder
        if not image.isNull():
            pixmap = QPixmap.fromImage(image)
            pixmap.setDevicePixelRatio(2.0)
        self.memory[key] = pixmap
        while len(self.memory) > 256:
            self.memory.popitem(last=False)
        self.changed.emit()

    def close(self):
        self.pool.waitForDone()
