from typing import Protocol

from src.application.dtos.export import (
    BackgroundAnalysis,
    BackgroundAnalysisRequest,
)


class IRegionBackgroundAnalyzer(Protocol):
    def analyze_many(
        self,
        source_path: str,
        requests: tuple[BackgroundAnalysisRequest, ...],
    ) -> tuple[BackgroundAnalysis, ...]: ...
