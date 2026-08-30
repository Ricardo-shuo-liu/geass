"""环境自检：判断当前配置能否启动并驱动 Agent。

用法：``python -m geass.check``

只展示非敏感信息；API Key、PaddleOCR Token、访问 Token 等密钥仅显示
「已配置/未配置」，绝不打印具体值。最后输出结论并以退出码表示结果
（0 = 可运行，1 = 存在缺失项）。
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import load_config

PYTHON_MIN = (3, 10)


@dataclass
class CheckItem:
    name: str
    ok: bool
    warn: bool = False
    detail: str = ""


def _vision_enabled(config) -> bool:
    whitelist = {name.strip().casefold() for name in config.agent.vision_whitelist if name.strip()}
    if whitelist:
        return config.agent.model.strip().casefold() in whitelist
    return config.agent.vision


def collect_checks(config) -> list[CheckItem]:
    checks: list[CheckItem] = []
    agent = config.agent

    version = sys.version_info
    version_ok = version >= PYTHON_MIN
    checks.append(
        CheckItem(
            "Python 版本",
            version_ok,
            detail=(
                f"{version.major}.{version.minor}.{version.micro}"
                f"（需要 >= {PYTHON_MIN[0]}.{PYTHON_MIN[1]}）"
                if version_ok
                else f"{version.major}.{version.minor}.{version.micro}（版本过低）"
            ),
        )
    )

    display = os.environ.get("DISPLAY")
    wayland = os.environ.get("WAYLAND_DISPLAY")
    if display:
        checks.append(CheckItem("图形环境", True, detail=f"DISPLAY={display}（X11）"))
    elif wayland:
        checks.append(
            CheckItem(
                "图形环境",
                False,
                warn=True,
                detail=f"仅检测到 WAYLAND_DISPLAY={wayland}，pyautogui 不支持 Wayland",
            )
        )
    else:
        checks.append(
            CheckItem(
                "图形环境",
                False,
                warn=True,
                detail="未设置 DISPLAY/WAYLAND_DISPLAY，键鼠与可见终端不可用",
            )
        )

    checks.append(
        CheckItem(
            "Agent 模型",
            bool(agent.model),
            detail=agent.model or "未配置",
        )
    )

    vision = _vision_enabled(config)
    if vision:
        mode = "视觉模式（模型在白名单内）" if agent.vision_whitelist else "视觉模式（vision=true）"
    elif agent.ocr:
        mode = "非视觉模型，将自动与 PaddleOCR 配对"
    else:
        mode = "文本模式（OCR 已关闭，仅键盘操作）"
    checks.append(CheckItem("模型模式", True, detail=mode))

    api_ready = bool(config.api_key or agent.base_url)
    checks.append(
        CheckItem(
            "API 访问",
            api_ready,
            detail=("已配置" if api_ready else "未配置 API Key，也未设置 base_url"),
        )
    )
    checks.append(
        CheckItem(
            "API Key",
            True,
            detail="已配置（值不显示）" if config.api_key else "未配置",
        )
    )
    checks.append(
        CheckItem(
            "Base URL",
            True,
            detail=agent.base_url or "（默认 OpenAI 端点）",
        )
    )

    if agent.ocr_token:
        ocr_detail = "已配置（值不显示）"
        ocr_ok = True
        ocr_warn = False
    elif vision:
        ocr_detail = "未配置（视觉模式无需配对，可选）"
        ocr_ok = True
        ocr_warn = False
    else:
        ocr_detail = "未配置，非视觉模型将退化为键盘-only"
        ocr_ok = False
        ocr_warn = True
    checks.append(CheckItem("PaddleOCR Token", ocr_ok, ocr_warn, ocr_detail))
    checks.append(
        CheckItem(
            "OCR 模型",
            True,
            detail=f"{agent.ocr_model} @ {agent.ocr_base_url}",
        )
    )

    from .screen import ScreenCapture

    monitor_count = ScreenCapture().monitor_count()
    if monitor_count > 1:
        checks.append(
            CheckItem(
                "多显示器",
                True,
                warn=True,
                detail=f"检测到 {monitor_count} 块物理屏，当前只操作主屏，其他屏幕请手动直控",
            )
        )
    else:
        checks.append(CheckItem("多显示器", True, detail="未检测到多屏，无限制"))

    from .io.accessibility import is_available

    atspi_ok = is_available()
    if atspi_ok:
        checks.append(CheckItem("控件查找", True, detail="pyatspi 可用（find_element）"))
    else:
        checks.append(
            CheckItem(
                "控件查找",
                False,
                warn=True,
                detail=(
                    "未安装 pyatspi，find_element 不可用"
                    "（Ubuntu/Debian: sudo apt install python3-pyatspi；"
                    "Fedora: sudo dnf install python3-pyatspi）"
                ),
            )
        )

    token_detail = (
        "已通过 GEASS_TOKEN 固定（值不显示）"
        if os.environ.get("GEASS_TOKEN")
        else "每次启动随机生成（值不显示，可用 GEASS_TOKEN 固定）"
    )
    checks.append(CheckItem("访问 Token", True, detail=token_detail))

    checks.append(
        CheckItem(
            "安全边界",
            True,
            detail=(
                f"已启用（审核超时 {config.security.approval_timeout:.0f}s）"
                if config.security.enabled
                else "已关闭"
            ),
        )
    )

    if shutil.which("script"):
        checks.append(CheckItem("终端输出捕获", True, detail="script 已安装"))
    else:
        checks.append(
            CheckItem(
                "终端输出捕获",
                False,
                warn=True,
                detail="未安装 script，一键执行命令的输出捕获会降级",
            )
        )

    checks.append(
        CheckItem(
            "配置文件",
            True,
            detail=(
                f"项目配置：{'存在' if config.config_path.exists() else '缺失'}，"
                "用户配置："
                + (
                    "存在"
                    if Path(os.environ.get("GEASS_HOME", os.path.expanduser("~")))
                    .joinpath(".geass", "env.toml")
                    .exists()
                    else "缺失（使用默认值）"
                )
            ),
        )
    )
    return checks


def summarize(checks: list[CheckItem]) -> str:
    fails = [item.name for item in checks if not item.ok and not item.warn]
    warns = [item.name for item in checks if not item.ok and item.warn]
    if fails:
        return f"环境未就绪，缺少：{', '.join(fails)}。补齐后重新运行 python -m geass.check。"
    if warns:
        return f"环境可以运行，但存在注意项：{', '.join(warns)}。"
    return "环境完整，可以运行 Geass。"


def render(checks: list[CheckItem]) -> str:
    lines = ["Geass 环境自检", "=" * 56]
    for item in checks:
        symbol = "✓" if item.ok else ("⚠" if item.warn else "✗")
        lines.append(f"[{symbol}] {item.name:<14} {item.detail}")
    lines.append("")
    lines.append(f"结论：{summarize(checks)}")
    return "\n".join(lines)


def main() -> None:
    config = load_config(persist=False)
    checks = collect_checks(config)
    print(render(checks))
    failed = any(not item.ok and not item.warn for item in checks)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
