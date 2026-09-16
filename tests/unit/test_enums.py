import pytest

from src.domain.models.enums import RegionStatus
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect


def create_dummy_region() -> TranslationRegion:
    return TranslationRegion(
        id="reg_1", project_id="proj_1", page_id=1, selection_rect=Rect(0, 0, 100, 100)
    )


def test_initial_status():
    r = create_dummy_region()
    assert r.status == RegionStatus.PENDING


def test_valid_status_transition():
    r = create_dummy_region()
    r.change_status(RegionStatus.TRANSLATED)
    assert r.status == RegionStatus.TRANSLATED

    r.change_status(RegionStatus.REVIEWED)
    assert r.status == RegionStatus.REVIEWED

    r.change_status(RegionStatus.READY_FOR_EXPORT)
    assert r.status == RegionStatus.READY_FOR_EXPORT


def test_invalid_status_transition():
    r = create_dummy_region()
    # PENDING -> READY_FOR_EXPORT no está permitido directamente
    with pytest.raises(ValueError, match="Transición de estado inválida"):
        r.change_status(RegionStatus.READY_FOR_EXPORT)
