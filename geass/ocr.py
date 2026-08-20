"""PaddleOCR AI Studio 远程屏幕文本识别后端。

`paddleocr` 本地库已不再跟进新模型（PaddleOCR-VL-1.6 / PP-StructureV3），
因此这里直接调用 AI Studio 官方 HTTP jobs API：提交截图 -> 轮询任务状态 ->
下载 JSONL 结果 -> 解析为「文本 + 归一化坐标」的转写，让非视觉模型仍能
看懂界面并基于文本框中心坐标调用鼠标工具。

Token / 模型 / 端点与 LLM API Key 的配置方式一致：

    python -m geass.config set --ocr-token YOUR_TOKEN --ocr-model PaddleOCR-VL-1.6

或使用环境变量 `GEASS_PADDLEOCR_TOKEN` 等；默认写入 `~/.geass/env.toml`。
"""
from __future__ import annotations

import io
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests
from PIL import Image

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://paddleocr.aistudio-app.com"
JOBS_PATH = "/api/v2/ocr/jobs"
DEFAULT_OPTIONAL_PAYLOAD = {
    "useDocOrientationClassify": False,
    "useDocUnwarping": False,
    "useChartRecognition": False,
}


@dataclass
class OCRBox:
    text: str
    confidence: float
    x: float
    y: float


@dataclass
class OCRResult:
    ok: bool
    boxes: list[OCRBox] = field(default_factory=list)
    error: str = ""

    def transcript(self, width: int, height: int) -> str:
        if not self.ok:
            return f"PaddleOCR 识别失败：{self.error or '未知错误'}"
        if not self.boxes:
            return f"屏幕分辨率 {width}x{height}，未检测到文本。"
        lines = [
            f"屏幕分辨率 {width}x{height}。以下是 PaddleOCR 检测到的文本，"
            "坐标是文本包围盒中心（归一化 0~1，可传给 move/click 等工具）："
        ]
        # 按视觉阅读顺序排序：先按 y 近似分行，再按 x。
        for box in sorted(self.boxes, key=lambda b: (round(b.y, 2), b.x)):
            lines.append(f"[{box.x:.3f},{box.y:.3f}] {box.text}")
        return "\n".join(lines)


class OCRRemoteError(RuntimeError):
    """远程 OCR 服务调用失败。"""


class PaddleOCRBackend:
    """PaddleOCR AI Studio 远程 jobs API 客户端。"""

    def __init__(
        self,
        token: str = "",
        model: str = "PaddleOCR-VL-1.6",
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 90.0,
        poll_interval: float = 1.5,
    ) -> None:
        self.token = (token or "").strip()
        self.model = (model or "PaddleOCR-VL-1.6").strip()
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = max(0.1, float(timeout))
        self.poll_interval = min(self.timeout, max(0.1, float(poll_interval)))
        self.optional_payload = dict(DEFAULT_OPTIONAL_PAYLOAD)

    def read(self, image: Image.Image) -> OCRResult:
        """识别一张 PIL 截图，返回文本 + 归一化文本框中心坐标。"""
        if not self.token:
            return OCRResult(
                ok=False,
                error=(
                    "未配置 PaddleOCR token；请执行 "
                    "`python -m geass.config set --ocr-token YOUR_TOKEN`，"
                    "或设置环境变量 GEASS_PADDLEOCR_TOKEN"
                ),
            )
        try:
            job_id = self._submit(image)
            jsonl_url = self._poll(job_id)
            lines = self._download(jsonl_url)
            boxes = self._parse_response(lines, image.size)
            return OCRResult(ok=True, boxes=boxes)
        except OCRRemoteError as exc:
            logger.warning("PaddleOCR 远程识别失败：%s", exc)
            return OCRResult(ok=False, error=str(exc))
        except Exception as exc:
            logger.warning("PaddleOCR 远程识别失败：%s", exc)
            return OCRResult(ok=False, error=str(exc))

    def _jobs_url(self) -> str:
        return f"{self.base_url}{JOBS_PATH}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"bearer {self.token}"}

    def _submit(self, image: Image.Image) -> str:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG")
        buffer.seek(0)
        data = {
            "model": self.model,
            "optionalPayload": json.dumps(self.optional_payload),
        }
        try:
            response = requests.post(
                self._jobs_url(),
                headers=self._headers(),
                data=data,
                files={"file": ("screen.jpg", buffer, "image/jpeg")},
                timeout=60,
            )
        except requests.RequestException as exc:
            raise OCRRemoteError(f"提交 OCR 任务失败：{exc}") from exc
        try:
            payload = response.json()
            job_id = str(payload["data"]["jobId"]).strip()
        except (ValueError, KeyError, TypeError) as exc:
            raise OCRRemoteError(
                f"提交 OCR 任务失败（HTTP {response.status_code}）："
                f"{_short(response.text)}"
            ) from exc
        if response.status_code != 200 or not job_id:
            raise OCRRemoteError(
                f"提交 OCR 任务失败（HTTP {response.status_code}）："
                f"{_short(response.text)}"
            )
        return job_id

    def _poll(self, job_id: str) -> str:
        url = f"{self._jobs_url()}/{job_id}"
        deadline = time.monotonic() + self.timeout
        state = "unknown"
        while True:
            if time.monotonic() >= deadline:
                raise OCRRemoteError(
                    f"OCR 任务超时（>{self.timeout:.0f}s），最后状态：{state}"
                )
            try:
                response = requests.get(
                    url, headers=self._headers(), timeout=30
                )
            except requests.RequestException as exc:
                raise OCRRemoteError(f"查询 OCR 任务失败：{exc}") from exc
            payload = self._json_or_raise(response, "查询 OCR 任务")
            data = payload.get("data")
            if not isinstance(data, dict):
                raise OCRRemoteError(
                    f"查询 OCR 任务返回异常：{_short(response.text)}"
                )
            state = str(data.get("state") or "unknown")
            if state == "done":
                try:
                    return str(data["resultUrl"]["jsonUrl"])
                except (KeyError, TypeError) as exc:
                    raise OCRRemoteError("OCR 任务完成但缺少结果地址") from exc
            if state == "failed":
                raise OCRRemoteError(
                    f"OCR 任务失败：{data.get('errorMsg') or '未知原因'}"
                )
            time.sleep(
                min(self.poll_interval, max(0.0, deadline - time.monotonic()))
            )

    def _download(self, jsonl_url: str) -> list[dict[str, Any]]:
        # resultUrl.jsonUrl 是预签名下载地址：按官方示例直接 GET，不带
        # Authorization 头（带上反而可能被 CDN 拒绝，表现为 HTTP 400）。
        try:
            response = requests.get(
                jsonl_url, timeout=60
            )
        except requests.RequestException as exc:
            raise OCRRemoteError(f"下载 OCR 结果失败：{exc}") from exc
        if response.status_code != 200:
            raise OCRRemoteError(
                f"下载 OCR 结果失败（HTTP {response.status_code}）"
            )
        lines: list[dict[str, Any]] = []
        for line in response.text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                lines.append(parsed)
        if not lines:
            raise OCRRemoteError("OCR 结果为空")
        return lines

    @staticmethod
    def _json_or_raise(response: Any, action: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise OCRRemoteError(
                f"{action}失败（HTTP {response.status_code}）："
                f"{_short(response.text)}"
            ) from exc
        if not isinstance(payload, dict):
            raise OCRRemoteError(
                f"{action}失败（HTTP {response.status_code}）："
                f"{_short(response.text)}"
            )
        return payload

    def _parse_response(
        self, lines: list[dict[str, Any]], size: tuple[int, int]
    ) -> list[OCRBox]:
        width, height = size
        boxes: list[OCRBox] = []
        for line in lines:
            result = line.get("result")
            if not isinstance(result, dict):
                continue
            layout = result.get("layoutParsingResults")
            pages = layout if isinstance(layout, list) else [result]
            for page in pages:
                if isinstance(page, dict):
                    boxes.extend(self._parse_page(page, width, height))
        if not boxes:
            text = _markdown_text(lines)
            if text:
                # 没有任何文本框坐标时，至少把整页文本提供给模型。
                boxes.append(OCRBox(text=text, confidence=1.0, x=0.5, y=0.5))
        return boxes

    def _parse_page(
        self, page: dict[str, Any], width: int, height: int
    ) -> list[OCRBox]:
        boxes: list[OCRBox] = []
        # PaddleOCR-VL-1.6：prunedResult.parsing_res_list
        #   {"block_label": "ocr", "block_content": "hello", "block_bbox": [...]}
        for container in _find_containers(page, "parsing_res_list"):
            for item in container["parsing_res_list"]:
                if not isinstance(item, dict):
                    continue
                text = (
                    item.get("block_content")
                    or item.get("content")
                    or item.get("text")
                    or ""
                )
                bbox = item.get("block_bbox") or item.get("bbox")
                score = item.get("block_score", item.get("score", 1.0))
                if text:
                    boxes.append(
                        self._make_box(str(text), score, bbox, width, height)
                    )
        # PP-StructureV3：overall_ocr_res / ocr_res 等 rec_texts 结构
        for container in _find_containers(page, "rec_texts"):
            texts = container.get("rec_texts") or []
            scores = container.get("rec_scores") or []
            polys = (
                container.get("rec_boxes")
                or container.get("rec_polys")
                or []
            )
            for text, score, poly in _zip_padded(texts, scores, polys):
                if text:
                    boxes.append(
                        self._make_box(str(text), score, poly, width, height)
                    )
        return boxes

    def _make_box(
        self,
        text: Any,
        score: Any,
        poly: Any,
        width: int,
        height: int,
    ) -> OCRBox:
        points = _flatten_points(poly)
        if not points:
            x = y = 0.0
        else:
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            x = (min(xs) + max(xs)) / 2.0
            y = (min(ys) + max(ys)) / 2.0
        try:
            confidence = float(score)
        except (TypeError, ValueError):
            confidence = 1.0
        return OCRBox(
            text=str(text or "").strip(),
            confidence=confidence,
            x=min(1.0, max(0.0, x / max(1, width))),
            y=min(1.0, max(0.0, y / max(1, height))),
        )


def _walk(node: Any):
    """递归遍历 JSON 结构，产出每一个 dict 节点。"""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _find_containers(node: Any, key: str):
    """递归找出所有含指定 key（值为列表）的 dict 节点。"""
    for container in _walk(node):
        value = container.get(key)
        if isinstance(value, list):
            yield container


def _markdown_text(lines: list[dict[str, Any]]) -> str:
    for line in lines:
        result = line.get("result")
        if not isinstance(result, dict):
            continue
        for node in _walk(result):
            markdown = node.get("markdown")
            if isinstance(markdown, dict):
                text = str(markdown.get("text") or "").strip()
                if text:
                    return text
    return ""


def _zip_padded(texts: list, scores: list, polys: list):
    length = max(len(texts), len(scores), len(polys))
    for index in range(length):
        text = texts[index] if index < len(texts) else ""
        score = scores[index] if index < len(scores) else 1.0
        poly = polys[index] if index < len(polys) else []
        yield text, score, poly


def _flatten_points(poly: Any) -> list[tuple[float, float]]:
    """把多种 bbox 写法统一成 [(x, y), ...]：
    [x1,y1,x2,y2]、8 个扁平坐标、[[x1,y1],...] 嵌套点。
    """
    if not isinstance(poly, (list, tuple)):
        return []
    points: list[tuple[float, float]] = []
    if len(poly) in (4, 8) and all(
        isinstance(value, (int, float)) for value in poly
    ):
        flat = [float(value) for value in poly]
        if len(poly) == 4:
            points.append((flat[0], flat[1]))
            points.append((flat[2], flat[3]))
            return points
        for index in range(0, 8, 2):
            points.append((flat[index], flat[index + 1]))
        return points
    for item in poly:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            try:
                points.append((float(item[0]), float(item[1])))
            except (TypeError, ValueError):
                continue
    return points


def _short(text: Any, limit: int = 300) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "…"
