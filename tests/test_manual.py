from __future__ import annotations

import asyncio

from geass.server.app import create_app
from geass.server.manual import execute_manual_input
from geass.server.state import broadcast_control

from .conftest import FakeBackend, make_config, make_state
from .ws_harness import WSClient


def test_move_normalizes_coordinates():
    backend = FakeBackend(size=(1000, 500))

    result = execute_manual_input(
        backend, {"action": "move", "x": 0.25, "y": 0.5}
    )

    assert result["ok"] is True
    assert ("move", (250, 250), {}) in backend.calls


def test_click_passes_button_and_coordinates():
    backend = FakeBackend(size=(1000, 500))

    execute_manual_input(
        backend, {"action": "click", "x": 0.1, "y": 0.2, "button": "right"}
    )

    assert ("click", (100, 100, "right"), {}) in backend.calls


def test_drag_uses_start_and_end_points():
    backend = FakeBackend(size=(1000, 1000))

    execute_manual_input(
        backend,
        {
            "action": "drag",
            "x1": 0.1,
            "y1": 0.2,
            "x2": 0.5,
            "y2": 0.6,
        },
    )

    assert ("drag", (100, 200, 500, 600), {}) in backend.calls


def test_scroll_clamps_large_values():
    backend = FakeBackend()

    execute_manual_input(backend, {"action": "scroll", "dx": 999, "dy": -999})

    assert ("scroll", (50, -50), {}) in backend.calls


def test_key_and_type_actions():
    backend = FakeBackend()

    execute_manual_input(backend, {"action": "key", "combo": "ctrl+c"})
    execute_manual_input(backend, {"action": "type", "text": "hi"})

    assert ("key_press", ("ctrl+c",), {}) in backend.calls
    assert ("type_text", ("hi",), {}) in backend.calls


def test_invalid_action_and_button_return_errors():
    backend = FakeBackend()

    assert execute_manual_input(backend, {"action": "nope"})["ok"] is False
    assert (
        execute_manual_input(
            backend, {"action": "click", "x": 0.5, "y": 0.5, "button": "bad"}
        )["ok"]
        is False
    )


def test_manual_input_ws_drives_backend():
    async def run():
        config = make_config()
        config.server.token = "test-token"
        state = make_state(config=config)
        state.approval_manager.broadcast = lambda message: broadcast_control(
            state, message
        )
        app = create_app(state)
        headers = [(b"sec-websocket-protocol", b"geass, test-token")]

        async with WSClient(app, "/ws/control", headers=headers) as ws:
            await ws.send_json(
                {
                    "type": "manual_input",
                    "action": "click",
                    "x": 0.5,
                    "y": 0.5,
                }
            )
            await ws.send_json(
                {"type": "manual_input", "action": "type", "text": "hi"}
            )
            await asyncio.sleep(0.01)

        assert ("click", (960, 540, "left"), {}) in state.backend.calls
        assert ("type_text", ("hi",), {}) in state.backend.calls

    asyncio.run(run())
