from __future__ import annotations

import requests
from PIL import Image

from geass import ocr as ocr_module
from geass.ocr import OCRBox, OCRResult, PaddleOCRBackend


class FakeResponse:
    def __init__(self, status_code: int = 200, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeRequests:
    """post 固定返回提交响应；get 先按顺序返回轮询响应，最后返回结果文件。"""

    def __init__(self, post_response, poll_responses, result_response):
        self.post_calls: list[tuple[str, dict]] = []
        self.get_calls: list[tuple[str, dict]] = []
        self._post_response = post_response
        self._poll_responses = list(poll_responses)
        self._result_response = result_response

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self._post_response

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        if self._poll_responses:
            return self._poll_responses.pop(0)
        return self._result_response


def make_fake_requests(jsonl_text: str) -> FakeRequests:
    return FakeRequests(
        post_response=FakeResponse(200, {"data": {"jobId": "job-1"}}),
        poll_responses=[
            FakeResponse(200, {"data": {"state": "pending"}}),
            FakeResponse(200, {"data": {"state": "running"}}),
            FakeResponse(
                200,
                {
                    "data": {
                        "state": "done",
                        "resultUrl": {"jsonUrl": "https://cdn.test/result.jsonl"},
                    }
                },
            ),
        ],
        result_response=FakeResponse(200, text=jsonl_text),
    )


def test_remote_vl_roundtrip(monkeypatch):
    jsonl_text = (
        '{"result": {"layoutParsingResults": [{"prunedResult": '
        '{"parsing_res_list": [{"block_label": "ocr", '
        '"block_content": "hello", "block_bbox": [10, 10, 70, 30]}]}}]}}\n'
    )
    fake = make_fake_requests(jsonl_text)
    monkeypatch.setattr("geass.ocr.requests", fake)
    backend = PaddleOCRBackend(
        token="tok",
        model="PaddleOCR-VL-1.6",
        base_url="https://ocr.test",
    )
    image = Image.new("RGB", (100, 80))

    result = backend.read(image)

    assert result.ok is True
    assert len(result.boxes) == 1
    assert result.boxes[0].text == "hello"
    assert result.boxes[0].x == 40 / 100
    assert result.boxes[0].y == 20 / 80

    url, kwargs = fake.post_calls[0]
    assert url == "https://ocr.test/api/v2/ocr/jobs"
    assert kwargs["headers"] == {"Authorization": "bearer tok"}
    assert kwargs["data"]["model"] == "PaddleOCR-VL-1.6"
    assert "optionalPayload" in kwargs["data"]
    assert "file" in kwargs["files"]
    assert fake.get_calls[0][0] == "https://ocr.test/api/v2/ocr/jobs/job-1"
    assert fake.get_calls[-1][0] == "https://cdn.test/result.jsonl"
    # 预签名下载地址按官方示例不带 Authorization 头，否则 CDN 返回 400
    assert "headers" not in fake.get_calls[-1][1]


def test_structure_v3_overall_ocr_res():
    backend = PaddleOCRBackend(token="tok", model="PP-StructureV3")
    page = {
        "overall_ocr_res": {
            "rec_texts": ["world"],
            "rec_scores": [0.9],
            "rec_boxes": [[[5, 5], [45, 5], [45, 25], [5, 25]]],
        }
    }

    boxes = backend._parse_page(page, 50, 30)

    assert len(boxes) == 1
    assert boxes[0].text == "world"
    assert boxes[0].confidence == 0.9
    assert boxes[0].x == 25 / 50
    assert boxes[0].y == 15 / 30


def test_markdown_fallback_when_no_boxes():
    backend = PaddleOCRBackend(token="tok")
    lines = [
        {
            "result": {
                "layoutParsingResults": [
                    {"markdown": {"text": "plain page", "images": {}}}
                ]
            }
        }
    ]

    boxes = backend._parse_response(lines, (100, 100))

    assert len(boxes) == 1
    assert boxes[0].text == "plain page"
    assert boxes[0].x == 0.5
    assert boxes[0].y == 0.5


def test_missing_token_fails_fast():
    backend = PaddleOCRBackend(token="")

    result = backend.read(Image.new("RGB", (10, 10)))

    assert result.ok is False
    assert "token" in result.error


def test_failed_job_reports_error(monkeypatch):
    fake = FakeRequests(
        post_response=FakeResponse(200, {"data": {"jobId": "job-1"}}),
        poll_responses=[
            FakeResponse(200, {"data": {"state": "failed", "errorMsg": "boom"}})
        ],
        result_response=FakeResponse(200, text=""),
    )
    monkeypatch.setattr("geass.ocr.requests", fake)
    backend = PaddleOCRBackend(token="tok", base_url="https://ocr.test")

    result = backend.read(Image.new("RGB", (10, 10)))

    assert result.ok is False
    assert "boom" in result.error


def test_submit_http_error_is_reported(monkeypatch):
    fake = FakeRequests(
        post_response=FakeResponse(500, text="server exploded"),
        poll_responses=[],
        result_response=FakeResponse(200, text=""),
    )
    monkeypatch.setattr("geass.ocr.requests", fake)
    backend = PaddleOCRBackend(token="tok", base_url="https://ocr.test")

    result = backend.read(Image.new("RGB", (10, 10)))

    assert result.ok is False
    assert "提交 OCR 任务失败" in result.error


def test_network_error_is_reported(monkeypatch):
    def broken(*args, **kwargs):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(requests, "post", broken)
    monkeypatch.setattr(requests, "get", broken)
    backend = PaddleOCRBackend(token="tok", base_url="https://ocr.test")

    result = backend.read(Image.new("RGB", (10, 10)))

    assert result.ok is False
    assert "提交 OCR 任务失败" in result.error


def test_poll_timeout(monkeypatch):
    fake = FakeRequests(
        post_response=FakeResponse(200, {"data": {"jobId": "job-1"}}),
        poll_responses=[
            FakeResponse(200, {"data": {"state": "pending"}})
        ]
        * 10,
        result_response=FakeResponse(200, text=""),
    )
    monkeypatch.setattr("geass.ocr.requests", fake)
    backend = PaddleOCRBackend(
        token="tok",
        base_url="https://ocr.test",
        timeout=0.15,
        poll_interval=0.1,
    )

    result = backend.read(Image.new("RGB", (10, 10)))

    assert result.ok is False
    assert "超时" in result.error


def test_flatten_points_variants():
    assert ocr_module._flatten_points([1, 2, 3, 4]) == [
        (1.0, 2.0),
        (3.0, 4.0),
    ]
    assert ocr_module._flatten_points([1, 2, 3, 4, 5, 6, 7, 8]) == [
        (1.0, 2.0),
        (3.0, 4.0),
        (5.0, 6.0),
        (7.0, 8.0),
    ]
    assert ocr_module._flatten_points([[1, 2], [3, 4]]) == [
        (1.0, 2.0),
        (3.0, 4.0),
    ]
    assert ocr_module._flatten_points(None) == []


def test_transcript_includes_coordinates():
    result = OCRResult(
        ok=True,
        boxes=[
            OCRBox("second", 0.9, 0.2, 0.5),
            OCRBox("first", 0.9, 0.1, 0.5),
        ],
    )

    text = result.transcript(100, 100)

    assert "100x100" in text
    assert "[0.100,0.500] first" in text
    assert "[0.200,0.500] second" in text
    assert text.index("first") < text.index("second")
