from typing import Protocol

from src.domain.value_objects.layout import LayoutRequest, LayoutResult


class ITextLayoutEngine(Protocol):
    def calculate_layout(self, request: LayoutRequest) -> LayoutResult: ...
