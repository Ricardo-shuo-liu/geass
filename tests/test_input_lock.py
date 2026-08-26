from __future__ import annotations

import asyncio
import time

from geass.agent import Agent
from geass.config import AgentConfig

from .conftest import FakeBackend, FakeCapture, FakeOpenAI


class LockRecordingBackend(FakeBackend):
    def __init__(self):
        super().__init__()
        self.intervals: list[tuple[float, float]] = []

    def click(self, x, y, button="left"):
        start = time.monotonic()
        time.sleep(0.05)
        super().click(x, y, button=button)
        self.intervals.append((start, time.monotonic()))


def test_input_lock_serializes_state_changing_actions():
    backend = LockRecordingBackend()
    client = FakeOpenAI([])
    lock = asyncio.Lock()

    def make_agent() -> Agent:
        return Agent(
            client=client,
            backend=backend,
            capture=FakeCapture(),
            config=AgentConfig(model="gpt-test"),
            input_lock=lock,
        )

    agent_a = make_agent()
    agent_b = make_agent()

    async def run():
        await asyncio.gather(
            agent_a._guarded_action("click", {"x": 0.5, "y": 0.5}),
            agent_b._guarded_action("click", {"x": 0.2, "y": 0.2}),
        )

    asyncio.run(run())

    intervals = sorted(backend.intervals)
    assert len(intervals) == 2
    assert intervals[0][1] <= intervals[1][0]
