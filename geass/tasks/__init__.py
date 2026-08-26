"""任务计划：Agent 自行判断难度，并为困难任务生成、跟踪执行计划。

计划不是强制的调度器，而是给模型自己用的"外置工作记忆"：模型在任务
开始时判断简单/困难，困难任务调用 ``plan`` 工具记录目标与步骤；执行
循环随后把计划作为上下文持续注入，帮助模型保持主线并逐步验证。
"""
# 包化后的对外入口：保持 from geass.tasks import TaskPlan 兼容。
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

VALID_DIFFICULTY = ("easy", "hard")
MAX_STEPS = 20


@dataclass
class TaskPlan:
    difficulty: str
    goal: str
    steps: list[str]
    current_step: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def from_args(cls, args: dict[str, Any]) -> "TaskPlan":
        difficulty = str(args.get("difficulty") or "").strip().lower()
        if difficulty not in VALID_DIFFICULTY:
            raise ValueError(f"difficulty 必须是 {VALID_DIFFICULTY} 之一")

        goal = str(args.get("goal") or "").strip()
        if not goal:
            raise ValueError("goal 不能为空")

        raw_steps = args.get("steps")
        if not isinstance(raw_steps, list):
            raise ValueError("steps 必须是字符串数组")
        steps = [str(step).strip() for step in raw_steps]
        steps = [step for step in steps if step]
        if not steps:
            raise ValueError("steps 至少需要一步")
        if len(steps) > MAX_STEPS:
            raise ValueError(f"steps 最多 {MAX_STEPS} 步")

        current_step = args.get("current_step")
        if current_step is None:
            current_step = 1
        try:
            current_step = int(current_step)
        except (TypeError, ValueError) as exc:
            raise ValueError("current_step 必须是整数") from exc
        if not 1 <= current_step <= len(steps) + 1:
            raise ValueError(
                f"current_step 应在 1~{len(steps) + 1} 之间"
            )

        return cls(
            difficulty=difficulty,
            goal=goal[:500],
            steps=[step[:500] for step in steps],
            current_step=current_step,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "difficulty": self.difficulty,
            "goal": self.goal,
            "steps": list(self.steps),
            "current_step": self.current_step,
        }

    def render(self) -> str:
        label = "困难任务" if self.difficulty == "hard" else "简单任务"
        lines = [f"任务计划（{label}）：{self.goal}"]
        for index, step in enumerate(self.steps, start=1):
            if index < self.current_step:
                marker = "✓"
            elif index == self.current_step:
                marker = "▶"
            else:
                marker = "·"
            lines.append(f"{marker} {index}. {step}")
        return "\n".join(lines)
