"""SKILL 加载器与渐进披露。

仓库里的 ``skills/`` 只作为种子目录，启动时同步到运行时目录的
``.system/``；真正加载从运行时根目录（默认 ``~/.geass/.skill``）
读取。自动进化生成的技能直接放在运行时根目录，和 ``.system/`` 并列。

每个技能是 ``<skill_root>/<name>/SKILL.md`` 一个目录；文件使用标准的 YAML
frontmatter（`name` / `description` / 可选元数据）+ Markdown 正文：

    ---
    name: echo-hello
    description: 在可见终端中输出 hello world
    ---

    # 步骤
    ...

加载时只把「技能清单」注入系统提示；Agent 需要完整说明时再调用
`read_skill`，实现渐进披露，避免把全部技能正文塞进上下文。
"""
# 包化后的对外入口：保持 from geass.skills import load_skills 等兼容。
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SYSTEM_DIR = ".system"

FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL
)


@dataclass
class Skill:
    name: str
    description: str
    path: Path
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def files(self) -> list[str]:
        """返回技能目录内除 SKILL.md 外的相对文件路径。"""
        if not self.path.is_dir():
            return []
        files: list[str] = []
        for item in sorted(self.path.rglob("*")):
            if item.is_file() and item.name != "SKILL.md":
                files.append(item.relative_to(self.path).as_posix())
        return files

    def catalog_entry(self) -> str:
        return f"- `{self.name}`: {self.description}"


def _simple_kv(text: str) -> dict[str, str]:
    """PyYAML 不可用时的 frontmatter 兜底解析（仅支持标量键值）。"""
    result: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip("\"'")
    return result


def _parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw
    header = match.group(1)
    try:
        import yaml

        data = yaml.safe_load(header)
    except Exception:
        data = _simple_kv(header)
    if not isinstance(data, dict):
        data = {}
    return data, raw[match.end() :]


def _first_paragraph(text: str) -> str:
    for line in text.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped:
            return stripped
    return ""


def resolve_skills_dir(value: str | Path, config_path: str | Path | None = None) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() and config_path is not None:
        path = (Path(config_path).resolve().parent / path).resolve()
    return path


def resolve_skill_root(
    value: str | Path | None, config_path: str | Path | None = None
) -> Path:
    """解析运行时 SKILL 根目录；留空时默认 ``~/.geass/.skill``。"""
    if value is None or str(value).strip() == "":
        home = Path(os.environ.get("GEASS_HOME", str(Path.home())))
        return (home / ".geass" / ".skill").resolve()
    return resolve_skills_dir(value, config_path)


def _load_skill_dir(skill_dir: Path) -> Skill | None:
    skill_file = skill_dir / "SKILL.md"
    if not skill_dir.is_dir() or not skill_file.is_file():
        return None
    try:
        raw = skill_file.read_text(encoding="utf-8")
    except OSError:
        return None
    metadata, body = _parse_frontmatter(raw)
    name = str(metadata.get("name") or skill_dir.name).strip()
    description = str(
        metadata.get("description") or _first_paragraph(body) or name
    ).strip()
    return Skill(
        name=name,
        description=description,
        path=skill_dir.resolve(),
        body=body.strip(),
        metadata=metadata,
    )


def sync_system_skills(
    source_dir: str | Path,
    skill_root: str | Path | None,
    config_path: str | Path | None = None,
) -> Path:
    """把仓库种子目录镜像到运行时 ``<skill_root>/.system``。

    只会改写 ``.system/`` 内部内容；根目录下自动进化的技能不受影响。
    源目录中已删除的技能也会从镜像中移除。
    """
    source = resolve_skills_dir(source_dir, config_path)
    root = resolve_skill_root(skill_root, config_path)
    system_dir = root / SYSTEM_DIR
    system_dir.mkdir(parents=True, exist_ok=True)

    if source.is_dir():
        for skill_dir in sorted(source.iterdir()):
            if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").is_file():
                continue
            target = system_dir / skill_dir.name
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(skill_dir, target)

        for target in sorted(system_dir.iterdir()):
            if target.is_dir() and not (source / target.name).is_dir():
                shutil.rmtree(target, ignore_errors=True)
    return root


def load_skills(
    skill_root: str | Path | None,
    config_path: str | Path | None = None,
) -> list[Skill]:
    """从运行时根目录加载 SKILL（先系统、后自动进化；同名后者覆盖）。"""
    root = resolve_skill_root(skill_root, config_path)
    if not root.is_dir():
        return []

    system_dir = root / SYSTEM_DIR
    directories: list[Path] = []
    if system_dir.is_dir():
        directories.extend(
            item
            for item in sorted(system_dir.iterdir())
            if item.is_dir()
        )
    directories.extend(
        item
        for item in sorted(root.iterdir())
        if item.is_dir() and item.name != SYSTEM_DIR
    )

    by_name: dict[str, Skill] = {}
    for skill_dir in directories:
        skill = _load_skill_dir(skill_dir)
        if skill is not None:
            by_name[skill.name] = skill
    return sorted(by_name.values(), key=lambda skill: skill.name)


def catalog_text(skills: list[Skill]) -> str:
    if not skills:
        return "当前没有可用 SKILL。"
    lines = ["可用 SKILL 清单（任务相关时先调用 read_skill 获取完整说明）："]
    lines.extend(skill.catalog_entry() for skill in skills)
    return "\n".join(lines)


def find_skill(skills: list[Skill], name: str) -> Skill | None:
    target = name.strip()
    for skill in skills:
        if skill.name == target:
            return skill
    return None
