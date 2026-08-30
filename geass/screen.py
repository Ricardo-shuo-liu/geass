"""屏幕抓取与实时帧流。"""

from __future__ import annotations

import asyncio
import io
import logging
import threading
from typing import Any, cast

from PIL import Image

logger = logging.getLogger(__name__)


def image_difference(before: Image.Image, after: Image.Image, size: int = 64) -> float:
    """返回两张图的像素差异率（0~1），用于判断动作是否让屏幕发生变化。

    先把图像转成灰度并缩放到 ``size x size``，再逐像素比较。阈值由调用方
    决定：不同内容的截图通常差异率明显高于纯鼠标悬停造成的细微变化。
    """
    left = before.convert("L").resize((size, size), Image.Resampling.BILINEAR)
    right = after.convert("L").resize((size, size), Image.Resampling.BILINEAR)
    left_px = left.load()
    right_px = right.load()
    assert left_px is not None and right_px is not None
    total = 0.0
    for y in range(size):
        for x in range(size):
            total += abs(cast(int, left_px[x, y]) - cast(int, right_px[x, y]))
    return total / (size * size * 255.0)


class ScreenCapture:
    def __init__(self, max_width: int = 1920, jpeg_quality: int = 70) -> None:
        self.max_width = max_width
        self.jpeg_quality = jpeg_quality
        self._sct: Any = None
        self._lock = threading.Lock()

    def _ensure_sct(self):
        if self._sct is None:
            import mss

            self._sct = mss.MSS()
        return self._sct

    def monitor_count(self) -> int:
        """物理显示器数量；mss 不可用时返回 0（未知）。"""
        try:
            sct = self._ensure_sct()
            return max(0, len(sct.monitors) - 1)
        except Exception:
            return 0

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
            (round(width * scale), round(height * scale)), Image.Resampling.BILINEAR
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
