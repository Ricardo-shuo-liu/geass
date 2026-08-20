"""SKILL 加载器与渐进披露。

每个技能是 `skills/<name>/SKILL.md` 一个目录；文件使用标准的 YAML
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
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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


def load_skills(
    skills_dir: str | Path, config_path: str | Path | None = None
) -> list[Skill]:
    root = resolve_skills_dir(skills_dir, config_path)
    if not root.is_dir():
        return []

    skills: list[Skill] = []
    for skill_dir in sorted(root.iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_dir.is_dir() or not skill_file.is_file():
            continue
        try:
            raw = skill_file.read_text(encoding="utf-8")
        except OSError:
            continue
        metadata, body = _parse_frontmatter(raw)
        name = str(metadata.get("name") or skill_dir.name).strip()
        description = str(
            metadata.get("description") or _first_paragraph(body) or name
        ).strip()
        skills.append(
            Skill(
                name=name,
                description=description,
                path=skill_dir.resolve(),
                body=body.strip(),
                metadata=metadata,
            )
        )
    return skills


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
