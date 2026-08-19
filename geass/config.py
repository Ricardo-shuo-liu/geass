"""配置加载：config.toml + 环境变量覆盖。"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8765
    token: str = ""


@dataclass
class ScreenConfig:
    fps: int = 15
    jpeg_quality: int = 70
    max_width: int = 1920


@dataclass
class AgentConfig:
    model: str = "gpt-5.6-terra"
    max_steps: int = 30
    image_max_edge: int = 1568
    base_url: str = ""


@dataclass
class VoiceConfig:
    fallback_model: str = "whisper-1"


@dataclass
class Config:
    server: ServerConfig = field(default_factory=ServerConfig)
    screen: ScreenConfig = field(default_factory=ScreenConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    config_path: Path = field(default=DEFAULT_CONFIG_PATH)
    openai_api_key: str = ""
    openai_base_url: str = ""


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    section = data.get(name)
    return section if isinstance(section, dict) else {}


def load_config(path: str | Path | None = None) -> Config:
    config_path = Path(
        path or os.environ.get("GEASS_CONFIG", DEFAULT_CONFIG_PATH)
    ).expanduser().resolve()

    data: dict[str, Any] = {}
    if config_path.exists():
        with config_path.open("rb") as fh:
            data = tomli.load(fh)

    server = _section(data, "server")
    screen = _section(data, "screen")
    agent = _section(data, "agent")
    voice = _section(data, "voice")

    token = os.environ.get("GEASS_TOKEN") or str(server.get("token") or "")
    if not token:
        token = secrets.token_urlsafe(9)

    # API 兼容层：支持 OpenAI / DeepSeek / 任意 OpenAI 兼容端点。
    base_url = (
        os.environ.get("GEASS_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or str(agent.get("base_url") or "")
    )
    api_key = (
        os.environ.get("GEASS_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or ""
    )

    return Config(
        server=ServerConfig(
            host=str(server.get("host", "0.0.0.0")),
            port=int(server.get("port", 8765)),
            token=token,
        ),
        screen=ScreenConfig(
            fps=max(1, int(screen.get("fps", 15))),
            jpeg_quality=min(95, max(1, int(screen.get("jpeg_quality", 70)))),
            max_width=max(1, int(screen.get("max_width", 1920))),
        ),
        agent=AgentConfig(
            model=str(agent.get("model", "gpt-5.6-terra")),
            max_steps=max(1, int(agent.get("max_steps", 30))),
            image_max_edge=max(1, int(agent.get("image_max_edge", 1568))),
            base_url=base_url,
        ),
        voice=VoiceConfig(
            fallback_model=str(voice.get("fallback_model", "whisper-1")),
        ),
        config_path=config_path,
        openai_api_key=api_key,
        openai_base_url=base_url,
    )
