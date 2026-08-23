from __future__ import annotations

from PIL import Image

from geass.screen import ScreenCapture, image_difference


def test_resize_by_width():
    capture = ScreenCapture(max_width=100, jpeg_quality=70)
    image = Image.new("RGB", (400, 200), (255, 0, 0))
    resized = capture._resize(image, None)
    assert resized.size == (100, 50)


def test_resize_by_max_edge():
    capture = ScreenCapture(max_width=100)
    image = Image.new("RGB", (400, 200))
    resized = capture._resize(image, 160)
    assert resized.size == (160, 80)


def test_encode_jpeg_magic_bytes():
    capture = ScreenCapture(max_width=100)
    image = Image.new("RGB", (10, 10))
    data = capture.encode_jpeg(image)
    assert data[:2] == b"\xff\xd8"


def test_image_difference_identical_is_zero():
    image = Image.new("RGB", (100, 80), (120, 130, 140))
    assert image_difference(image, image.copy()) == 0.0


def test_image_difference_opposite_is_large():
    black = Image.new("RGB", (100, 80), (0, 0, 0))
    white = Image.new("RGB", (100, 80), (255, 255, 255))
    assert image_difference(black, white) > 0.9
