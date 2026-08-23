"""配置加载与持久化。

生效优先级（从高到低）：
    环境变量 > ~/.geass/env.toml > 项目 config.toml > 内置默认值

统一环境变量：
    GEASS_API_KEY / GEASS_BASE_URL / GEASS_MODEL / GEASS_VISION_WHITELIST
    / GEASS_TOKEN / GEASS_CONFIG / GEASS_HOME
    GEASS_PADDLEOCR_TOKEN / GEASS_PADDLEOCR_MODEL / GEASS_PADDLEOCR_BASE_URL

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

from .memory import default_memory_path
from .skills import resolve_skill_root

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
    vision_whitelist: tuple[str, ...] = ()
    ocr: bool = True
    ocr_token: str = ""
    ocr_model: str = "PaddleOCR-VL-1.6"
    ocr_base_url: str = "https://paddleocr.aistudio-app.com"
    ocr_timeout: float = 90.0
    terminal_timeout: float = 15.0
    skills_dir: str = "skills"
    memory_enabled: bool = True
    memory_path: str = ""
    memory_max_entries: int = 200
    memory_context_entries: int = 8
    skill_root: str = ""
    evolution_enabled: bool = True
    evolution_idle_seconds: float = 300.0
    evolution_interval: float = 1800.0
    evolution_max_skills: int = 20


@dataclass
class SecurityConfig:
    enabled: bool = True
    patterns: tuple[str, ...] = ()
    approval_timeout: float = 30.0


@dataclass
class VoiceConfig:
    fallback_model: str = "whisper-1"


@dataclass
class Config:
    server: ServerConfig = field(default_factory=ServerConfig)
    screen: ScreenConfig = field(default_factory=ScreenConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
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
    for section in ("server", "screen", "agent", "security", "voice"):
        items = data.get(section)
        if not isinstance(items, dict) or not items:
            continue
        lines.append(f"[{section}]")
        for key, value in items.items():
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif isinstance(value, (int, float)):
                rendered = str(value)
            elif isinstance(value, (list, tuple)):
                items_ = ", ".join(json.dumps(str(item)) for item in value)
                rendered = f"[{items_}]"
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
    p_security = _section(project, "security")
    p_voice = _section(project, "voice")
    u_agent = _section(user, "agent")
    u_security = _section(user, "security")

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
    vision_whitelist_value = os.environ.get("GEASS_VISION_WHITELIST")
    if not vision_whitelist_value:
        vision_whitelist_value = pick(
            u_agent, "vision_whitelist", pick(p_agent, "vision_whitelist", [])
        )
    if isinstance(vision_whitelist_value, str):
        vision_whitelist = tuple(
            item.strip()
            for item in str(vision_whitelist_value).split(",")
            if item.strip()
        )
    elif isinstance(vision_whitelist_value, (list, tuple)):
        vision_whitelist = tuple(
            str(item).strip()
            for item in vision_whitelist_value
            if str(item).strip()
        )
    else:
        vision_whitelist = ()
    ocr = bool(pick(u_agent, "ocr", pick(p_agent, "ocr", True)))
    ocr_token = (
        os.environ.get("GEASS_PADDLEOCR_TOKEN")
        or os.environ.get("PADDLEOCR_MCP_AISTUDIO_ACCESS_TOKEN")
        or str(pick(u_agent, "ocr_token", pick(p_agent, "ocr_token", "")) or "")
    )
    ocr_model = os.environ.get(
        "GEASS_PADDLEOCR_MODEL",
        str(
            pick(
                u_agent,
                "ocr_model",
                pick(p_agent, "ocr_model", "PaddleOCR-VL-1.6"),
            )
        ),
    )
    ocr_base_url = os.environ.get(
        "GEASS_PADDLEOCR_BASE_URL",
        str(
            pick(
                u_agent,
                "ocr_base_url",
                pick(
                    p_agent,
                    "ocr_base_url",
                    "https://paddleocr.aistudio-app.com",
                ),
            )
            or ""
        ),
    )
    ocr_timeout = max(
        5.0,
        float(pick(u_agent, "ocr_timeout", pick(p_agent, "ocr_timeout", 90.0))),
    )
    terminal_timeout = max(
        0.5,
        float(
            pick(
                u_agent,
                "terminal_timeout",
                pick(p_agent, "terminal_timeout", 15.0),
            )
        ),
    )
    skills_dir = str(pick(u_agent, "skills_dir", pick(p_agent, "skills_dir", "skills")))
    memory_enabled = bool(
        pick(u_agent, "memory_enabled", pick(p_agent, "memory_enabled", True))
    )
    memory_path = str(
        pick(u_agent, "memory_path", pick(p_agent, "memory_path", "")) or ""
    )
    memory_max_entries = max(
        1,
        int(
            pick(
                u_agent,
                "memory_max_entries",
                pick(p_agent, "memory_max_entries", 200),
            )
        ),
    )
    memory_context_entries = max(
        1,
        int(
            pick(
                u_agent,
                "memory_context_entries",
                pick(p_agent, "memory_context_entries", 8),
            )
        ),
    )
    skill_root = str(
        pick(u_agent, "skill_root", pick(p_agent, "skill_root", "")) or ""
    )
    evolution_enabled = bool(
        pick(
            u_agent,
            "evolution_enabled",
            pick(p_agent, "evolution_enabled", True),
        )
    )
    evolution_idle_seconds = max(
        30.0,
        float(
            pick(
                u_agent,
                "evolution_idle_seconds",
                pick(p_agent, "evolution_idle_seconds", 300.0),
            )
        ),
    )
    evolution_interval = max(
        60.0,
        float(
            pick(
                u_agent,
                "evolution_interval",
                pick(p_agent, "evolution_interval", 1800.0),
            )
        ),
    )
    evolution_max_skills = max(
        1,
        min(
            100,
            int(
                pick(
                    u_agent,
                    "evolution_max_skills",
                    pick(p_agent, "evolution_max_skills", 20),
                )
            ),
        ),
    )
    security_enabled = bool(
        pick(u_security, "enabled", pick(p_security, "enabled", True))
    )
    security_timeout = max(
        5.0,
        float(
            pick(
                u_security,
                "approval_timeout",
                pick(p_security, "approval_timeout", 30.0),
            )
        ),
    )
    security_patterns_value = pick(
        u_security, "patterns", pick(p_security, "patterns", [])
    )
    if isinstance(security_patterns_value, (list, tuple)):
        security_patterns = tuple(
            str(item) for item in security_patterns_value if str(item).strip()
        )
    else:
        security_patterns = ()

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
            vision_whitelist=vision_whitelist,
            ocr=ocr,
            ocr_token=ocr_token,
            ocr_model=ocr_model,
            ocr_base_url=ocr_base_url,
            ocr_timeout=ocr_timeout,
            terminal_timeout=terminal_timeout,
            skills_dir=skills_dir,
            memory_enabled=memory_enabled,
            memory_path=memory_path,
            memory_max_entries=memory_max_entries,
            memory_context_entries=memory_context_entries,
            skill_root=skill_root,
            evolution_enabled=evolution_enabled,
            evolution_idle_seconds=evolution_idle_seconds,
            evolution_interval=evolution_interval,
            evolution_max_skills=evolution_max_skills,
        ),
        security=SecurityConfig(
            enabled=security_enabled,
            patterns=security_patterns,
            approval_timeout=security_timeout,
        ),
        voice=VoiceConfig(
            fallback_model=str(pick(p_voice, "fallback_model", "whisper-1")),
        ),
        config_path=config_path,
        api_key=api_key,
    )

    if persist:
        _persist_runtime_values(
            model,
            base_url,
            api_key,
            ocr_token,
            ocr_model,
            ocr_base_url,
            vision_whitelist,
        )

    return config


def _persist_runtime_values(
    model: str,
    base_url: str,
    api_key: str,
    ocr_token: str = "",
    ocr_model: str = "",
    ocr_base_url: str = "",
    vision_whitelist: tuple[str, ...] = (),
) -> None:
    """启动时把环境变量沉淀到用户级配置，避免重复配置（访问 token 除外）。"""
    updates: dict[str, dict[str, Any]] = {"agent": {}}
    if "GEASS_MODEL" in os.environ and model:
        updates["agent"]["model"] = model
    if "GEASS_BASE_URL" in os.environ and base_url:
        updates["agent"]["base_url"] = base_url
    if "GEASS_API_KEY" in os.environ and api_key:
        updates["agent"]["api_key"] = api_key
    if "GEASS_PADDLEOCR_TOKEN" in os.environ and ocr_token:
        updates["agent"]["ocr_token"] = ocr_token
    if "GEASS_PADDLEOCR_MODEL" in os.environ and ocr_model:
        updates["agent"]["ocr_model"] = ocr_model
    if "GEASS_PADDLEOCR_BASE_URL" in os.environ and ocr_base_url:
        updates["agent"]["ocr_base_url"] = ocr_base_url
    if "GEASS_VISION_WHITELIST" in os.environ and vision_whitelist:
        updates["agent"]["vision_whitelist"] = list(vision_whitelist)
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
    set_parser.add_argument(
        "--ocr", choices=["true", "false"], help="是否启用 PaddleOCR 屏幕识别"
    )
    set_parser.add_argument("--ocr-token", help="PaddleOCR AI Studio 访问 Token")
    set_parser.add_argument(
        "--ocr-model", help="PaddleOCR 模型，如 PaddleOCR-VL-1.6 / PP-StructureV3"
    )
    set_parser.add_argument(
        "--ocr-base-url",
        help="PaddleOCR 服务端点（默认 https://paddleocr.aistudio-app.com）",
    )
    set_parser.add_argument(
        "--vision-whitelist",
        help="支持图像输入的模型白名单（逗号分隔；留空则按 --vision 决定）",
    )
    set_parser.add_argument("--skills-dir", help="SKILL 目录（默认项目下 skills）")
    set_parser.add_argument(
        "--memory-enabled",
        choices=["true", "false"],
        help="是否启用持久记忆（默认 true）",
    )
    set_parser.add_argument(
        "--memory-path", help="记忆目录路径（默认 ~/.geass/.memory）"
    )
    set_parser.add_argument(
        "--skill-root", help="运行时 SKILL 根目录（默认 ~/.geass/.skill）"
    )
    set_parser.add_argument(
        "--evolution-enabled",
        choices=["true", "false"],
        help="是否启用空闲进化系统（默认 true）",
    )
    set_parser.add_argument(
        "--evolution-idle-seconds",
        type=float,
        help="空闲多少秒后触发进化（最低 30 秒）",
    )
    set_parser.add_argument(
        "--evolution-interval",
        type=float,
        help="两次进化的最小间隔秒数（最低 60 秒）",
    )
    set_parser.add_argument(
        "--evolution-max-skills",
        type=int,
        help="运行时自动生成 SKILL 的数量上限（1~100）",
    )
    set_parser.add_argument(
        "--security-enabled",
        choices=["true", "false"],
        help="是否启用高危 shell 命令审核",
    )
    set_parser.add_argument(
        "--approval-timeout", type=float, help="命令审核超时秒数（最低 5 秒）"
    )

    args = parser.parse_args()
    if args.command == "show":
        config = load_config(persist=False)
        print(f"config    = {user_env_path()}")
        print(f"model     = {config.agent.model}")
        print(f"base_url  = {config.agent.base_url or '（OpenAI 默认）'}")
        print(f"vision    = {config.agent.vision}")
        print(f"vision_whitelist = {', '.join(config.agent.vision_whitelist) or '（未设置）'}")
        print(f"ocr       = {config.agent.ocr}（model={config.agent.ocr_model}）")
        print(f"ocr_url   = {config.agent.ocr_base_url}")
        print(f"skills    = {config.agent.skills_dir}")
        print(
            "memory    = "
            f"enabled={config.agent.memory_enabled}, "
            f"path={config.agent.memory_path or default_memory_path()}"
        )
        print(
            "evolution = "
            f"enabled={config.agent.evolution_enabled}, "
            f"idle={config.agent.evolution_idle_seconds:.0f}s, "
            f"interval={config.agent.evolution_interval:.0f}s, "
            f"max={config.agent.evolution_max_skills}, "
            f"root={config.agent.skill_root or resolve_skill_root(None)}"
        )
        print(f"api_key   = {mask_secret(config.api_key) or '（未设置）'}")
        print(f"ocr_token = {mask_secret(config.agent.ocr_token) or '（未设置）'}")
        print(
            "security  = "
            f"enabled={config.security.enabled}, "
            f"timeout={config.security.approval_timeout:.0f}s, "
            f"patterns={len(config.security.patterns)}"
        )
        print("token     = 每次启动随机生成（启动时在控制台打印）")
        return

    updates: dict[str, dict[str, Any]] = {"agent": {}, "security": {}}
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
    if args.ocr is not None:
        updates["agent"]["ocr"] = args.ocr == "true"
    if args.ocr_token:
        updates["agent"]["ocr_token"] = args.ocr_token
    if args.ocr_model:
        updates["agent"]["ocr_model"] = args.ocr_model
    if args.ocr_base_url:
        updates["agent"]["ocr_base_url"] = args.ocr_base_url
    if args.vision_whitelist is not None:
        updates["agent"]["vision_whitelist"] = [
            item.strip()
            for item in args.vision_whitelist.split(",")
            if item.strip()
        ]
    if args.skills_dir:
        updates["agent"]["skills_dir"] = args.skills_dir
    if args.memory_enabled is not None:
        updates["agent"]["memory_enabled"] = args.memory_enabled == "true"
    if args.memory_path:
        updates["agent"]["memory_path"] = args.memory_path
    if args.skill_root:
        updates["agent"]["skill_root"] = args.skill_root
    if args.evolution_enabled is not None:
        updates["agent"]["evolution_enabled"] = args.evolution_enabled == "true"
    if args.evolution_idle_seconds is not None:
        updates["agent"]["evolution_idle_seconds"] = max(
            30.0, float(args.evolution_idle_seconds)
        )
    if args.evolution_interval is not None:
        updates["agent"]["evolution_interval"] = max(
            60.0, float(args.evolution_interval)
        )
    if args.evolution_max_skills is not None:
        updates["agent"]["evolution_max_skills"] = max(
            1, min(100, int(args.evolution_max_skills))
        )
    if args.security_enabled is not None:
        updates["security"]["enabled"] = args.security_enabled == "true"
    if args.approval_timeout is not None:
        updates["security"]["approval_timeout"] = max(
            5.0, float(args.approval_timeout)
        )
    if not updates["agent"] and not updates["security"]:
        parser.error("请至少提供一个 --xxx 参数")
    path = save_user_env(updates)
    print(f"已写入 {path}")


if __name__ == "__main__":
    main()
