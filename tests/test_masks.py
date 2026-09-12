from __future__ import annotations

import json
import os

import pytest
from PIL import Image

from geass.server.masks import MAX_MASKS, MaskManager


def test_defaults_to_disabled(tmp_path):
    manager = MaskManager(tmp_path / ".masks.json")

    assert manager.snapshot() == {"enabled": False, "masks": []}


def test_add_enables_and_persists(tmp_path):
    path = tmp_path / ".masks.json"
    manager = MaskManager(path)

    mask = manager.add({"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4})

    assert mask["id"]
    snapshot = MaskManager(path).snapshot()
    assert snapshot["enabled"] is True
    assert snapshot["masks"][0]["w"] == pytest.approx(0.3)
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_remove_and_toggle(tmp_path):
    manager = MaskManager(tmp_path / ".masks.json")
    mask = manager.add({"x": 0.0, "y": 0.0, "w": 0.5, "h": 0.5})

    assert manager.set_enabled(False) is False
    assert manager.enabled is False
    assert manager.remove(mask["id"]) is True
    assert manager.remove(mask["id"]) is False
    assert manager.snapshot()["masks"] == []


def test_invalid_rect_is_rejected(tmp_path):
    manager = MaskManager(tmp_path / ".masks.json")

    with pytest.raises(ValueError):
        manager.add({"x": 0.5, "y": 0.5, "w": 0.001, "h": 0.001})


def test_mask_limit(tmp_path):
    manager = MaskManager(tmp_path / ".masks.json")
    for index in range(MAX_MASKS):
        manager.add({"x": 0.01 * index, "y": 0.0, "w": 0.02, "h": 0.02})

    with pytest.raises(ValueError):
        manager.add({"x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2})


def test_apply_paints_black_only_when_enabled(tmp_path):
    manager = MaskManager(tmp_path / ".masks.json")
    mask = manager.add({"x": 0.0, "y": 0.0, "w": 0.5, "h": 0.5})
    image = Image.new("RGB", (100, 100), (255, 255, 255))

    painted = manager.apply(image.copy())
    assert painted.getpixel((10, 10)) == (0, 0, 0)
    assert painted.getpixel((80, 80)) == (255, 255, 255)

    manager.set_enabled(False)
    untouched = manager.apply(image.copy())
    assert untouched.getpixel((10, 10)) == (255, 255, 255)
    manager.remove(mask["id"])


def test_corrupt_store_resets(tmp_path):
    path = tmp_path / ".masks.json"
    path.write_text("{broken", encoding="utf-8")

    manager = MaskManager(path)

    assert manager.snapshot() == {"enabled": False, "masks": []}
    assert json.dumps(manager.snapshot())


def test_clear_removes_all(tmp_path):
    manager = MaskManager(tmp_path / ".masks.json")
    manager.add({"x": 0.0, "y": 0.0, "w": 0.2, "h": 0.2})
    manager.add({"x": 0.3, "y": 0.3, "w": 0.2, "h": 0.2})

    assert manager.clear() == 2
    assert manager.snapshot()["masks"] == []
