from __future__ import annotations

import inspect

from geass.agent import STATE_CHANGING_TOOLS, TEXT_ONLY_TOOLS, TOOLS
from geass.tools import TOOL_REGISTRY


def test_every_registered_tool_has_handler_and_schema():
    for tool in TOOL_REGISTRY.values():
        assert callable(tool.handler)
        assert inspect.iscoroutinefunction(tool.handler)
        assert tool.parameters["type"] == "object"


def test_tools_list_matches_registry():
    assert [tool["name"] for tool in TOOLS] == [name for name in TOOL_REGISTRY]


def test_mode_sets_are_derived_from_registry():
    assert TEXT_ONLY_TOOLS == {name for name, tool in TOOL_REGISTRY.items() if tool.text_only}
    assert STATE_CHANGING_TOOLS == {
        name for name, tool in TOOL_REGISTRY.items() if tool.state_changing
    }


def test_schema_matches_registry_parameters():
    by_name = {tool["name"]: tool for tool in TOOLS}
    for name, tool in TOOL_REGISTRY.items():
        assert by_name[name]["parameters"] == tool.parameters
        assert by_name[name]["description"] == tool.description
