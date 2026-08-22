from __future__ import annotations

import sys
import types
from pathlib import Path

from geass.check import collect_checks, render, summarize
from geass.config import AgentConfig, Config, SecurityConfig


def build_config(**overrides) -> Config:
    config = Config()
    config.config_path = Path("/tmp/geass-test-config.toml")
    params = dict(
        model="gpt-5.6-terra",
        vision=True,
        vision_whitelist=("gpt-5.6-terra",),
        ocr=True,
        ocr_token="ocr-secret",
    )
    params.update(overrides)
    config.agent = AgentConfig(**params)
    config.security = SecurityConfig(enabled=True, approval_timeout=30.0)
    return config


def test_render_hides_secrets(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":1")
    monkeypatch.setenv("GEASS_TOKEN", "fixed-secret-token")
    config = build_config()
    config.api_key = "sk-secret-value"

    output = render(collect_checks(config))

    assert "已配置" in output
    assert "sk-secret-value" not in output
    assert "ocr-secret" not in output
    assert "fixed-secret-token" not in output


def test_fully_configured_vision_mode_is_ready(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":1")
    monkeypatch.setitem(sys.modules, "pyatspi", types.SimpleNamespace())
    config = build_config()
    config.api_key = "sk-test"

    checks = collect_checks(config)

    assert all(item.ok for item in checks)
    assert "视觉模式" in next(
        item.detail for item in checks if item.name == "模型模式"
    )
    assert summarize(checks) == "环境完整，可以运行 Geass。"


def test_missing_api_access_fails():
    config = build_config(ocr_token="")

    checks = collect_checks(config)
    failed = [item.name for item in checks if not item.ok and not item.warn]

    assert "API 访问" in failed
    assert "API 访问" in summarize(checks)


def test_non_vision_model_without_ocr_token_warns():
    config = build_config(
        model="deepseek-v4-flash",
        vision_whitelist=("gpt-5.6-terra",),
        vision=True,
        ocr_token="",
    )
    config.api_key = "sk-test"

    checks = collect_checks(config)
    ocr_item = next(item for item in checks if item.name == "PaddleOCR Token")

    assert ocr_item.ok is False
    assert ocr_item.warn is True
    assert "PaddleOCR Token" in summarize(checks)


def test_whitelist_non_member_uses_ocr_pairing():
    config = build_config(
        model="deepseek-v4-flash",
        vision_whitelist=("gpt-5.6-terra",),
        ocr_token="ocr-secret",
    )

    mode = next(item.detail for item in collect_checks(config) if item.name == "模型模式")

    assert "PaddleOCR 配对" in mode
