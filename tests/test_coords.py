from __future__ import annotations

from geass.agent import Agent
from geass.config import AgentConfig

from .conftest import FakeBackend, FakeCapture


def build_agent(backend: FakeBackend | None = None) -> Agent:
    backend = backend or FakeBackend(size=(1920, 1080))
    return Agent(
        client=None,
        backend=backend,
        capture=FakeCapture(),
        config=AgentConfig(model="x"),
    )


def test_norm_to_px_center():
    assert build_agent().norm_to_px(0.5, 0.5) == (960, 540)


def test_norm_clamped():
    agent = build_agent(FakeBackend(size=(1000, 500)))
    assert agent.norm_to_px(-1, 2) == (0, 500)


def test_norm_independent_of_capture_scale():
    agent = build_agent(FakeBackend(size=(3840, 2160)))
    assert agent.norm_to_px(0.25, 0.25) == (960, 540)

