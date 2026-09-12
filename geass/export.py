"""``geass export``：把运行时 SKILL / COT / ROT 导出到指定目录。

导出结果是一个可直接浏览或备份的目录：

    <destination>/
    ├── manifest.json          # 导出清单（支持多次导出追加合并）
    ├── skills/<name>/**       # SKILL.md 与附带文件
    └── pot/
        ├── cot.md             # Global-COT（若有）
        └── rot/<name>.md      # ROT 原文（含 frontmatter）
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .config import Config, load_config
from .evolution.pot import ROT, POTStore
from .skills import Skill, load_skills, resolve_skill_root

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1


class ExportError(RuntimeError):
    """导出参数或目标状态非法。"""


def _prepare_target(path: Path, force: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return
    if not force:
        raise ExportError(f"目标已存在：{path}（如需覆盖请加 --force）")
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _export_skill(skill: Skill, destination: Path, force: bool) -> dict[str, Any]:
    target = destination / "skills" / skill.name
    _prepare_target(target, force)
    shutil.copytree(skill.path, target)
    return {
        "type": "skill",
        "name": skill.name,
        "path": target.relative_to(destination).as_posix(),
        "source": str(skill.path),
        "files": [
            item.relative_to(target).as_posix()
            for item in sorted(target.rglob("*"))
            if item.is_file()
        ],
    }


def _export_cot(store: POTStore, destination: Path, force: bool) -> dict[str, Any] | None:
    text = store.get_cot()
    if not text:
        return None
    target = destination / "pot" / "cot.md"
    _prepare_target(target, force)
    target.write_text(text.rstrip() + "\n", encoding="utf-8")
    return {
        "type": "cot",
        "name": "global-cot",
        "path": target.relative_to(destination).as_posix(),
        "source": str(store.cot_path),
        "files": [],
    }


def _export_rot(
    store: POTStore,
    rot: ROT,
    destination: Path,
    force: bool,
) -> dict[str, Any]:
    source = store.rot_path(rot.name)
    target = destination / "pot" / "rot" / source.name
    _prepare_target(target, force)
    shutil.copy2(source, target)
    return {
        "type": "rot",
        "name": rot.name,
        "path": target.relative_to(destination).as_posix(),
        "source": str(source),
        "enabled": rot.enabled,
        "files": [],
    }


def _write_manifest(
    destination: Path,
    source_roots: dict[str, str],
    items: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    path = destination / MANIFEST_NAME
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, json.JSONDecodeError):
            existing = {}
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for item in list(existing.get("items") or []) + items:
        if not isinstance(item, dict):
            continue
        merged[(str(item.get("type")), str(item.get("name")))] = item
    manifest = {
        "version": MANIFEST_VERSION,
        "exported_at": time.time(),
        "source": {**dict(existing.get("source") or {}), **source_roots},
        "items": list(merged.values()),
        "warnings": list(warnings),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return manifest


def export_assets(
    config: Config,
    destination: str | Path,
    *,
    skill_names: Sequence[str] = (),
    all_skills: bool = False,
    rot_names: Sequence[str] = (),
    all_rots: bool = False,
    include_cot: bool = False,
    enabled_rots_only: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """导出选中的资产并返回写入后的 manifest。"""
    if not str(destination).strip():
        raise ExportError("导出目录不能为空")
    root = Path(destination).expanduser()
    root.mkdir(parents=True, exist_ok=True)

    skills = load_skills(config.agent.skill_root, config.config_path)
    by_name = {skill.name: skill for skill in skills}
    if all_skills:
        selected_skills = skills
    else:
        selected_skills = []
        missing = []
        for name in skill_names:
            skill = by_name.get(str(name))
            if skill is None:
                missing.append(str(name))
            else:
                selected_skills.append(skill)
        if missing:
            available = "、".join(sorted(by_name)) or "无"
            raise ExportError(f"SKILL 不存在：{'、'.join(missing)}（可用：{available}）")

    store = POTStore(config.agent.pot_path or None)
    rots = store.list_rots(include_disabled=not enabled_rots_only)
    rot_by_name = {rot.name: rot for rot in rots}
    if all_rots:
        selected_rots = rots
    else:
        selected_rots = []
        missing_rots = []
        for name in rot_names:
            rot = rot_by_name.get(str(name))
            if rot is None:
                missing_rots.append(str(name))
            else:
                selected_rots.append(rot)
        if missing_rots:
            available = "、".join(sorted(rot_by_name)) or "无"
            raise ExportError(f"ROT 不存在：{'、'.join(missing_rots)}（可用：{available}）")

    if not selected_skills and not selected_rots and not include_cot:
        raise ExportError("请至少选择 SKILL、ROT 或 COT 中的一项")

    items: list[dict[str, Any]] = []
    for skill in selected_skills:
        items.append(_export_skill(skill, root, force))
    warnings: list[str] = []
    if include_cot:
        cot_item = _export_cot(store, root, force)
        if cot_item is None:
            warnings.append("当前没有 Global-COT，已跳过")
        else:
            items.append(cot_item)
    for rot in selected_rots:
        items.append(_export_rot(store, rot, root, force))

    return _write_manifest(
        root,
        {
            "skill_root": str(resolve_skill_root(config.agent.skill_root, config.config_path)),
            "pot_root": str(store.root),
        },
        items,
        warnings,
    )


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--to", required=True, dest="destination", help="导出目标目录")
    parser.add_argument("--force", action="store_true", help="覆盖同名目标")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="geass export",
        description="导出运行时 SKILL / COT / ROT 资产到指定目录",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    skill = sub.add_parser("skill", help="导出指定 SKILL（或 --all）")
    skill.add_argument("names", nargs="*", metavar="NAME")
    skill.add_argument("--all", action="store_true", dest="all_items", help="导出全部 SKILL")
    _add_common(skill)

    rot = sub.add_parser("rot", help="导出指定 ROT（或 --all）")
    rot.add_argument("names", nargs="*", metavar="NAME")
    rot.add_argument("--all", action="store_true", dest="all_items", help="导出全部 ROT")
    rot.add_argument("--enabled-only", action="store_true", help="只导出启用中的 ROT")
    _add_common(rot)

    cot = sub.add_parser("cot", help="导出 Global-COT")
    _add_common(cot)

    everything = sub.add_parser("all", help="导出全部 SKILL + COT + ROT")
    everything.add_argument("--enabled-only", action="store_true", help="只导出启用中的 ROT")
    _add_common(everything)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command in ("skill", "rot") and not args.names and not args.all_items:
        raise SystemExit(f"请指定名称，或使用 --all 导出全部 {args.command.upper()}")
    config = load_config(persist=False)
    try:
        manifest = export_assets(
            config,
            args.destination,
            skill_names=args.names if args.command == "skill" else (),
            all_skills=args.command == "all" or (args.command == "skill" and args.all_items),
            rot_names=args.names if args.command == "rot" else (),
            all_rots=args.command == "all" or (args.command == "rot" and args.all_items),
            include_cot=args.command in ("cot", "all"),
            enabled_rots_only=bool(getattr(args, "enabled_only", False)),
            force=bool(args.force),
        )
    except ExportError as exc:
        raise SystemExit(str(exc)) from exc
    for item in manifest.get("items", []):
        print(f"- [{item.get('type')}] {item.get('name')} -> {item.get('path')}")
    for warning in manifest.get("warnings", []):
        print(f"警告：{warning}")
    print(f"已导出 {len(manifest.get('items', []))} 项到 {Path(args.destination).expanduser()}")
    print(f"导出清单：{MANIFEST_NAME}")


if __name__ == "__main__":
    main()
