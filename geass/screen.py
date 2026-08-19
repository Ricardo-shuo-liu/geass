"""屏幕抓取与实时帧流。"""
from __future__ import annotations

import asyncio
import io
import logging
import threading
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)


class ScreenCapture:
    def __init__(self, max_width: int = 1920, jpeg_quality: int = 70) -> None:
        self.max_width = max_width
        self.jpeg_quality = jpeg_quality
        self._sct: Any = None
        self._lock = threading.Lock()

    def _ensure_sct(self):
        if self._sct is None:
            import mss

            self._sct = mss.mss()
        return self._sct

    def capture_image(self, max_edge: int | None = None) -> Image.Image:
        with self._lock:
            sct = self._ensure_sct()
            # monitors[0] 是所有显示器拼合的虚拟屏幕；优先抓第一块物理屏，
            # 与 pyautogui.size()（主屏）保持一致，保证归一化坐标映射正确。
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.rgb)
        return self._resize(image, max_edge)

    def _resize(self, image: Image.Image, max_edge: int | None) -> Image.Image:
        width, height = image.size
        if max_edge is not None:
            long_side = max(width, height)
            if long_side <= max_edge:
                return image
            scale = max_edge / long_side
        else:
            if width <= self.max_width:
                return image
            scale = self.max_width / width
        return image.resize(
            (round(width * scale), round(height * scale)), Image.BILINEAR
        )

    def capture_jpeg(self, max_edge: int | None = None) -> bytes:
        image = self.capture_image(max_edge=max_edge)
        return self.encode_jpeg(image)

    def encode_jpeg(self, image: Image.Image) -> bytes:
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=self.jpeg_quality)
        return buffer.getvalue()


class ScreenStreamer:
    """以固定帧率抓屏并广播给所有订阅者；订阅队列容量为 1，自动丢弃旧帧。"""

    def __init__(self, capture: ScreenCapture, fps: int = 15) -> None:
        self.capture = capture
        self.interval = 1.0 / max(1, fps)
        self._clients: set[asyncio.Queue[bytes]] = set()

    def subscribe(self) -> asyncio.Queue[bytes]:
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
        self._clients.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[bytes]) -> None:
        self._clients.discard(queue)

    async def run(self) -> None:
        while True:
            try:
                frame = self.capture.capture_jpeg()
            except Exception:
                logger.exception("抓屏失败")
                await asyncio.sleep(self.interval)
                continue

            for queue in list(self._clients):
                if queue.full():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                try:
                    queue.put_nowait(frame)
                except asyncio.QueueFull:
                    pass

            await asyncio.sleep(self.interval)
