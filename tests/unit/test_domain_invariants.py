from datetime import UTC, datetime

import pytest

from src.domain.models.project import Project
from src.domain.value_objects.geometry import Rect


def test_rect_zero_area_valid():
    r = Rect(x0=10, y0=10, x1=10, y1=10)
    assert r.width == 0
    assert r.height == 0
    assert r.area == 0


def test_rect_negative_area_invalid():
    with pytest.raises(ValueError):
        Rect(x0=20, y0=10, x1=10, y1=20)


def test_project_invariants():
    now = datetime.now(UTC)

    with pytest.raises(ValueError, match="pdf_size no puede ser negativo"):
        Project("p1", "n1", "path", "sha", -1, 10, 1, now, now)

    with pytest.raises(ValueError, match="pdf_page_count no puede ser negativo"):
        Project("p1", "n1", "path", "sha", 100, -1, 1, now, now)

    with pytest.raises(ValueError, match="last_viewed_page no puede ser negativo"):
        Project("p1", "n1", "path", "sha", 100, 10, -1, now, now)
