from __future__ import annotations

import pytest

from geass.tasks import TaskPlan


def test_plan_from_args_defaults():
    plan = TaskPlan.from_args(
        {
            "difficulty": "hard",
            "goal": "打开浏览器并新建页面",
            "steps": ["启动浏览器", "新建标签页", "验证页面"],
        }
    )

    assert plan.difficulty == "hard"
    assert plan.current_step == 1
    assert plan.to_dict()["goal"] == "打开浏览器并新建页面"


def test_plan_render_shows_progress():
    plan = TaskPlan.from_args(
        {
            "difficulty": "hard",
            "goal": "g",
            "steps": ["a", "b", "c"],
            "current_step": 2,
        }
    )
    rendered = plan.render()
    assert "✓ 1. a" in rendered
    assert "▶ 2. b" in rendered
    assert "· 3. c" in rendered


@pytest.mark.parametrize(
    "args",
    [
        {"difficulty": "medium", "goal": "g", "steps": ["a"]},
        {"difficulty": "easy", "goal": "", "steps": ["a"]},
        {"difficulty": "easy", "goal": "g", "steps": []},
        {"difficulty": "easy", "goal": "g", "steps": ["a"], "current_step": 3},
        {"difficulty": "easy", "goal": "g", "steps": "a"},
    ],
)
def test_plan_from_args_rejects_invalid(args):
    with pytest.raises(ValueError):
        TaskPlan.from_args(args)
