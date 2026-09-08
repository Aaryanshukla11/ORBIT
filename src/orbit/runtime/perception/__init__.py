"""Multimodal Desktop Perception Subsystem (Step 3).

Exports the canonical DesktopObservation, individual modality observers (Win32, UIA, Screenshot, OCR),
and the DesktopPerceptionEngine with multi-modal evidence fusion.
"""

from __future__ import annotations

from orbit.runtime.perception.coordinate_mapper import (
    CoordinateMappingResult,
    OCRCoordinateMapper,
)
from orbit.runtime.perception.engine import (
    DesktopPerceptionEngine,
    SemanticPerceptionEngine,
)
from orbit.runtime.perception.fusion_engine import MultiModalPerceptionFusionEngine
from orbit.runtime.perception.fusion_models import (
    EvidenceChannel,
    FusedEvidence,
    FusedTargetMatch,
    FusionPolicy,
    FusionStatus,
    MultiModalFusionResult,
    PerceptionEvidence as LegacyPerceptionEvidence,
    SemanticAgreement,
    SpatialAgreement,
    SpatialRelation,
)
from orbit.runtime.perception.models import (
    DesktopObservation,
    OCRBoundingBox,
    OCRCoordinateSpace,
    OCRProviderKind,
    OCRResult,
    OCRStatus,
    OCRTextRegion,
    OCRToken,
    OCRWord,
    PerceivedElement,
    PerceptionEvidence,
    ScreenshotObservation,
    UIElementObservation,
    VisualRegion,
    VisualRegionType,
    WindowObservation,
)
from orbit.runtime.perception.normalization import (
    matches_text,
    normalize_text,
    tokenize_text,
)
from orbit.runtime.perception.observer import DesktopObserver
from orbit.runtime.perception.ocr import (
    MockOCRProvider,
    OCRProvider,
    WindowsNativeOCRProvider,
)
from orbit.runtime.perception.screenshot import DesktopScreenshotObserver
from orbit.runtime.perception.uia import UIAElementObserver
from orbit.runtime.perception.visual_engine import VisualPerceptionEngine
from orbit.runtime.perception.visual_matcher import (
    MockVisualMatcher,
    TemplateVisualMatcher,
    VisualMatcher,
)
from orbit.runtime.perception.visual_models import (
    VisualMatchPolicy,
    VisualMatchRegion,
    VisualMatchResult,
    VisualMatchStatus,
    VisualMatcherKind,
    VisualTemplate,
    VisualTemplateSource,
)
from orbit.runtime.perception.windows import Win32WindowObserver

__all__ = [
    # Canonical Step 3 Models
    "DesktopObservation",
    "DesktopObserver",
    "DesktopPerceptionEngine",
    "DesktopScreenshotObserver",
    "OCRToken",
    "PerceivedElement",
    "PerceptionEvidence",
    "ScreenshotObservation",
    "UIAElementObserver",
    "UIElementObservation",
    "VisualRegion",
    "VisualRegionType",
    "Win32WindowObserver",
    "WindowObservation",
    # Legacy and Modality Components
    "CoordinateMappingResult",
    "EvidenceChannel",
    "FusedEvidence",
    "FusedTargetMatch",
    "FusionPolicy",
    "FusionStatus",
    "LegacyPerceptionEvidence",
    "MockOCRProvider",
    "MockVisualMatcher",
    "MultiModalFusionResult",
    "MultiModalPerceptionFusionEngine",
    "OCRBoundingBox",
    "OCRCoordinateMapper",
    "OCRCoordinateSpace",
    "OCRProvider",
    "OCRProviderKind",
    "OCRResult",
    "OCRStatus",
    "OCRTextRegion",
    "OCRWord",
    "SemanticAgreement",
    "SemanticPerceptionEngine",
    "SpatialAgreement",
    "SpatialRelation",
    "TemplateVisualMatcher",
    "VisualMatchPolicy",
    "VisualMatchRegion",
    "VisualMatchResult",
    "VisualMatchStatus",
    "VisualMatcher",
    "VisualMatcherKind",
    "VisualPerceptionEngine",
    "VisualTemplate",
    "VisualTemplateSource",
    "WindowsNativeOCRProvider",
    "matches_text",
    "normalize_text",
    "tokenize_text",
]
