from typing import Any, Protocol

from src.domain.models.region import TranslationRegion


class IRegionReplacementStrategy(Protocol):
    def apply(self, region: TranslationRegion, page_context: Any) -> None: ...
