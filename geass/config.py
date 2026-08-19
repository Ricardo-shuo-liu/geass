"""配置加载与持久化。

生效优先级（从高到低）：
    环境变量 > ~/.geass/env.toml > 项目 config.toml > 内置默认值

统一环境变量：
    GEASS_API_KEY / GEASS_BASE_URL / GEASS_MODEL / GEASS_TOKEN / GEASS_CONFIG / GEASS_HOME

`python -m geass.main` 启动时若检测到 GEASS_* 环境变量，会把它们写入
`~/.geass/env.toml`，下次运行无需重复配置；也可用
`python -m geass.config set ...` 手动管理。
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"


def user_env_path() -> Path:
    home = Path(os.environ.get("GEASS_HOME", str(Path.home())))
    return home / ".geass" / "env.toml"


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
    vision: bool = True


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
    api_key: str = ""


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as fh:
            data = tomli.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, tomli.TOMLDecodeError):
        return {}


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    section = data.get(name)
    return section if isinstance(section, dict) else {}


def _dump_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for section in ("server", "screen", "agent", "voice"):
        items = data.get(section)
        if not isinstance(items, dict) or not items:
            continue
        lines.append(f"[{section}]")
        for key, value in items.items():
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif isinstance(value, (int, float)):
                rendered = str(value)
            else:
                rendered = json.dumps(str(value))
            lines.append(f"{key} = {rendered}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def save_user_env(updates: dict[str, Any]) -> Path:
    """把配置项合并写入 ~/.geass/env.toml（密钥文件权限 0600）。"""
    path = user_env_path()
    data = _read_toml(path)
    for section, items in updates.items():
        if not isinstance(items, dict):
            continue
        bucket = data.setdefault(section, {})
        if not isinstance(bucket, dict):
            bucket = {}
            data[section] = bucket
        for key, value in items.items():
            if value is None or value == "":
                continue
            bucket[key] = value

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    path.write_text(_dump_toml(data), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def load_config(path: str | Path | None = None, persist: bool = False) -> Config:
    config_path = Path(
        path or os.environ.get("GEASS_CONFIG", DEFAULT_CONFIG_PATH)
    ).expanduser().resolve()

    project = _read_toml(config_path)
    user = _read_toml(user_env_path())
    p_server = _section(project, "server")
    p_screen = _section(project, "screen")
    p_agent = _section(project, "agent")
    p_voice = _section(project, "voice")
    u_agent = _section(user, "agent")

    def pick(section: dict[str, Any], key: str, default: Any) -> Any:
        return section.get(key, default)

    # Token 每次启动随机生成，不持久化；如需固定可显式设置
    # GEASS_TOKEN 环境变量或 config.toml 的 server.token。
    token = os.environ.get("GEASS_TOKEN") or str(
        pick(p_server, "token", "") or ""
    )
    if not token:
        token = secrets.token_urlsafe(9)

    model = os.environ.get(
        "GEASS_MODEL",
        str(pick(u_agent, "model", pick(p_agent, "model", "gpt-5.6-terra"))),
    )
    base_url = os.environ.get(
        "GEASS_BASE_URL",
        str(pick(u_agent, "base_url", pick(p_agent, "base_url", "")) or ""),
    )
    api_key = os.environ.get(
        "GEASS_API_KEY", str(pick(u_agent, "api_key", "") or "")
    )
    vision = bool(
        pick(u_agent, "vision", pick(p_agent, "vision", True))
    )

    config = Config(
        server=ServerConfig(
            host=str(pick(p_server, "host", "0.0.0.0")),
            port=int(pick(p_server, "port", 8765)),
            token=token,
        ),
        screen=ScreenConfig(
            fps=max(1, int(pick(p_screen, "fps", 15))),
            jpeg_quality=min(95, max(1, int(pick(p_screen, "jpeg_quality", 70)))),
            max_width=max(1, int(pick(p_screen, "max_width", 1920))),
        ),
        agent=AgentConfig(
            model=model,
            max_steps=max(1, int(pick(p_agent, "max_steps", 30))),
            image_max_edge=max(1, int(pick(p_agent, "image_max_edge", 1568))),
            base_url=base_url,
            vision=vision,
        ),
        voice=VoiceConfig(
            fallback_model=str(pick(p_voice, "fallback_model", "whisper-1")),
        ),
        config_path=config_path,
        api_key=api_key,
    )

    if persist:
        _persist_runtime_values(model, base_url, api_key)

    return config


def _persist_runtime_values(
    model: str, base_url: str, api_key: str
) -> None:
    """启动时把环境变量沉淀到用户级配置，避免重复配置（token 除外）。"""
    updates: dict[str, dict[str, Any]] = {"agent": {}}
    if "GEASS_MODEL" in os.environ and model:
        updates["agent"]["model"] = model
    if "GEASS_BASE_URL" in os.environ and base_url:
        updates["agent"]["base_url"] = base_url
    if "GEASS_API_KEY" in os.environ and api_key:
        updates["agent"]["api_key"] = api_key
    save_user_env(updates)


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m geass.config",
        description=f"管理用户级配置 {user_env_path()}",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="显示当前生效配置（密钥脱敏）")

    set_parser = sub.add_parser("set", help="写入用户级配置（下次运行生效）")
    set_parser.add_argument(
        "values",
        nargs="*",
        metavar="VALUE",
        help="按顺序：API_KEY [BASE_URL] [MODEL]",
    )
    set_parser.add_argument("--api-key", help="API Key")
    set_parser.add_argument("--base-url", help="OpenAI 兼容端点，如 https://api.deepseek.com")
    set_parser.add_argument("--model", help="模型名，如 deepseek-chat")
    set_parser.add_argument(
        "--vision", choices=["true", "false"], help="模型是否支持图像输入"
    )

    args = parser.parse_args()
    if args.command == "show":
        config = load_config(persist=False)
        print(f"config    = {user_env_path()}")
        print(f"model     = {config.agent.model}")
        print(f"base_url  = {config.agent.base_url or '（OpenAI 默认）'}")
        print(f"vision    = {config.agent.vision}")
        print(f"api_key   = {mask_secret(config.api_key) or '（未设置）'}")
        print("token     = 每次启动随机生成（启动时在控制台打印）")
        return

    updates: dict[str, dict[str, Any]] = {"agent": {}}
    positional_keys = ("api_key", "base_url", "model")
    for index, value in enumerate(args.values):
        if index < len(positional_keys) and value:
            updates["agent"][positional_keys[index]] = value
    if args.model:
        updates["agent"]["model"] = args.model
    if args.base_url:
        updates["agent"]["base_url"] = args.base_url
    if args.api_key:
        updates["agent"]["api_key"] = args.api_key
    if args.vision is not None:
        updates["agent"]["vision"] = args.vision == "true"
    if not updates["agent"]:
        parser.error("请至少提供一个 --xxx 参数")
    path = save_user_env(updates)
    print(f"已写入 {path}")


if __name__ == "__main__":
    main()
