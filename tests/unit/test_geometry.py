import pytest

from src.domain.value_objects.geometry import Rect


def test_rect_creation():
    r = Rect(x0=10, y0=20, x1=100, y1=200)
    assert r.x0 == 10
    assert r.y0 == 20
    assert r.x1 == 100
    assert r.y1 == 200


def test_rect_dimensions():
    r = Rect(x0=0, y0=0, x1=50, y1=80)
    assert r.width == 50
    assert r.height == 80


def test_rect_invalid_coordinates():
    with pytest.raises(ValueError, match="Coordenadas inválidas"):
        Rect(x0=100, y0=0, x1=50, y1=80)

    with pytest.raises(ValueError, match="Coordenadas inválidas"):
        Rect(x0=0, y0=100, x1=50, y1=80)
