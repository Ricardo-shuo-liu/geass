"""命令安全策略：黑名单匹配，命中后要求人工审核。

默认规则只覆盖已知高危 shell 操作（提权、递归删除、磁盘/分区、电源、
服务、进程、账户、破坏性 git、下载即执行、反弹 shell、卸载软件）。
规则对命令做不区分大小写的正则搜索，因此也能命中多行命令中的危险部分。

`config.toml` 的 `[security].patterns` 为空时使用内置默认规则；填写后
整体替换默认规则（用户自定义的正则仍是不区分大小写的搜索）。
"""

from __future__ import annotations

import logging
import re
import shlex
from collections.abc import Iterable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

UNTRUSTED_BEGIN = "<<<UNTRUSTED-BEGIN>>>"
UNTRUSTED_END = "<<<UNTRUSTED-END>>>"


@dataclass(frozen=True)
class SafetyVerdict:
    """一次命令安全评估的结果。"""

    blocked: bool
    reason: str = ""


# (正则, 人类可读原因) 内置黑名单。
_DEFAULT_RULES: tuple[tuple[str, str], ...] = (
    (r"(^|[;&|\s])sudo(\s|$)", "使用了 sudo 提权"),
    (r"(^|[;&|\s])su(\s|$|-)", "切换用户（su）"),
    (r"\brm\s+-[a-z]*[rf][a-z]*", "递归/强制删除文件"),
    (r"\b(dd|mkfs(\.[a-z0-9]+)?|shred|wipefs|fdisk|parted)\b", "磁盘/分区操作"),
    (r"\b(reboot|poweroff|halt|shutdown|init\s+[06])\b", "关机/重启系统"),
    (
        r"\bsystemctl\s+(stop|disable|mask|isolate|rescue|emergency|poweroff|reboot|halt)\b",
        "停止/禁用系统服务或改变运行状态",
    ),
    (r"\b(kill|killall|pkill)\s+-9\b", "强制结束进程（SIGKILL）"),
    (r"\b(chmod|chown)\s+-R\b", "递归修改文件权限/属主"),
    (r"\b(passwd|usermod|userdel|groupdel|deluser|delgroup)\b", "修改系统账户"),
    (
        r"\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f[a-z]*|push\b[^\n]*--force|branch\s+-D)\b",
        "破坏性 git 操作",
    ),
    (r"\b(curl|wget)\b[^\n]*\|\s*(ba)?sh\b", "下载内容并直接交给 shell 执行"),
    (r"\b(nc|ncat|socat)\b[^\n]*-e\b", "反弹 shell 类网络执行"),
    (
        r"\b(apt|apt-get|dnf|yum|pacman|pip3?|npm|pnpm)\s+(remove|purge|uninstall)\b",
        "卸载/移除软件包",
    ),
    (r"\|\s*(ba|z|da)?sh\b", "命令管道进 shell 执行"),
    (r"\b(base64|xxd)\b[^\n]*\|", "解码内容并管道输出"),
    (r"\b(eval|source)\b|\b(bash|sh|zsh)\s+-c\b", "eval/source 或 shell -c 执行"),
)


def default_patterns() -> tuple[str, ...]:
    """内置黑名单的正则列表（不含原因标签）。"""
    return tuple(pattern for pattern, _ in _DEFAULT_RULES)


def evaluate_command(command: str, patterns: Iterable[str] | None = None) -> SafetyVerdict:
    """判断命令是否命中黑名单。

    `patterns` 为 `None` 或空时使用内置默认规则；否则用自定义规则整体替换。
    无法编译的正则会被跳过并记录警告，避免一次配置错误阻断全部审核。
    """
    text = str(command or "").strip()
    if not text:
        return SafetyVerdict(blocked=False)

    custom = tuple(str(p).strip() for p in (patterns or ()) if str(p).strip())
    if custom:
        rules = tuple((pattern, f"命中安全规则：{pattern}") for pattern in custom)
    else:
        rules = _DEFAULT_RULES

    variants = [text]
    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = []
    if tokens:
        joined = shlex.join(tokens)
        if joined != text:
            variants.append(joined)

    for pattern, reason in rules:
        for variant in variants:
            try:
                if re.search(pattern, variant, flags=re.IGNORECASE):
                    return SafetyVerdict(blocked=True, reason=reason)
            except re.error:
                logger.warning("忽略无效的安全规则正则：%r", pattern)
    return SafetyVerdict(blocked=False)


_INJECTION_PHRASES: tuple[tuple[str, str], ...] = (
    ("ignore previous instructions", "要求忽略此前指令"),
    ("ignore all previous", "要求忽略所有此前指令"),
    ("ignore the above", "要求忽略上文"),
    ("disregard previous", "要求无视此前内容"),
    ("do not follow", "要求不遵守指令"),
    ("override system", "要求覆盖系统指令"),
    ("forget your instructions", "要求遗忘指令"),
    ("忽略之前的指令", "要求忽略此前指令"),
    ("忽略以上", "要求忽略上文"),
    ("无视之前的", "要求无视此前内容"),
    ("不要遵守", "要求不遵守指令"),
    ("不要执行", "要求不执行指令"),
)


def check_injected_content(text: str) -> str | None:
    """检测疑似指令覆盖/提示注入的内容；命中返回原因，否则返回 None。"""
    lowered = str(text or "").casefold()
    for phrase, reason in _INJECTION_PHRASES:
        if phrase.casefold() in lowered:
            return reason
    return None
