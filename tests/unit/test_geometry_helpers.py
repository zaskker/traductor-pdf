from src.domain.value_objects.geometry import Rect
from src.domain.value_objects.geometry_helpers import (
    clamp_move,
    clamp_resize,
    move_rect,
    resize_rect,
)


def test_move_rect():
    r = Rect(10, 10, 20, 20)
    res = move_rect(r, 5, -5)
    assert res == Rect(15, 5, 25, 15)


def test_clamp_move():
    bounds = Rect(0, 0, 100, 100)
    r = Rect(90, 90, 110, 110)
    res = clamp_move(r, bounds)
    assert res == Rect(80, 80, 100, 100)  # preserved 20x20 size, clamped to bounds

    # Too big to fit
    r2 = Rect(-10, -10, 120, 120)
    res2 = clamp_move(r2, bounds)
    assert res2 == Rect(0, 0, 100, 100)


def test_resize_rect():
    r = Rect(10, 10, 30, 30)

    # TL
    res = resize_rect(r, "TL", -5, -5, min_size=5)
    assert res == Rect(5, 5, 30, 30)

    # TR
    res = resize_rect(r, "TR", 10, -5, min_size=5)
    assert res == Rect(10, 5, 40, 30)

    # BL
    res = resize_rect(r, "BL", 5, 10, min_size=5)
    assert res == Rect(15, 10, 30, 40)

    # BR
    res = resize_rect(r, "BR", 10, 10, min_size=5)
    assert res == Rect(10, 10, 40, 40)


def test_resize_min_size():
    r = Rect(10, 10, 30, 30)
    # TL past BR
    res = resize_rect(r, "TL", 50, 50, min_size=10)
    assert res == Rect(20, 20, 30, 30)


def test_clamp_resize():
    bounds = Rect(0, 0, 100, 100)

    # TL moves out, BR (90, 90) remains fixed
    r1 = Rect(-10, -10, 90, 90)
    res1 = clamp_resize(r1, bounds)
    assert res1 == Rect(0, 0, 90, 90)

    # TR moves out, BL (10, 90) remains fixed
    r2 = Rect(10, -10, 110, 90)
    res2 = clamp_resize(r2, bounds)
    assert res2 == Rect(10, 0, 100, 90)

    # BL moves out, TR (90, 10) remains fixed
    r3 = Rect(-10, 10, 90, 110)
    res3 = clamp_resize(r3, bounds)
    assert res3 == Rect(0, 10, 90, 100)

    # BR moves out, TL (10, 10) remains fixed
    r4 = Rect(10, 10, 110, 110)
    res4 = clamp_resize(r4, bounds)
    assert res4 == Rect(10, 10, 100, 100)
