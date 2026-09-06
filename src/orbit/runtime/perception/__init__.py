"""Semantic and visual perception package for ORBIT."""

from orbit.runtime.perception.coordinate_mapper import (
    CoordinateMappingResult,
    OCRCoordinateMapper,
)
from orbit.runtime.perception.engine import SemanticPerceptionEngine
from orbit.runtime.perception.models import (
    OCRBoundingBox,
    OCRCoordinateSpace,
    OCRProviderKind,
    OCRResult,
    OCRStatus,
    OCRTextRegion,
    OCRWord,
)
from orbit.runtime.perception.normalization import (
    matches_text,
    normalize_text,
    tokenize_text,
)
from orbit.runtime.perception.ocr import (
    MockOCRProvider,
    OCRProvider,
    WindowsNativeOCRProvider,
)
from orbit.runtime.perception.fusion_engine import MultiModalPerceptionFusionEngine
from orbit.runtime.perception.fusion_models import (
    EvidenceChannel,
    FusedEvidence,
    FusedTargetMatch,
    FusionPolicy,
    FusionStatus,
    MultiModalFusionResult,
    PerceptionEvidence,
    SemanticAgreement,
    SpatialAgreement,
    SpatialRelation,
)
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

__all__ = [
    "OCRBoundingBox",
    "OCRCoordinateSpace",
    "OCRCoordinateMapper",
    "CoordinateMappingResult",
    "OCRProviderKind",
    "OCRResult",
    "OCRStatus",
    "OCRTextRegion",
    "OCRWord",
    "OCRProvider",
    "WindowsNativeOCRProvider",
    "MockOCRProvider",
    "SemanticPerceptionEngine",
    "VisualPerceptionEngine",
    "VisualMatcher",
    "TemplateVisualMatcher",
    "MockVisualMatcher",
    "VisualTemplate",
    "VisualTemplateSource",
    "VisualMatchRegion",
    "VisualMatchResult",
    "VisualMatchStatus",
    "VisualMatcherKind",
    "VisualMatchPolicy",
    "MultiModalPerceptionFusionEngine",
    "EvidenceChannel",
    "SpatialRelation",
    "FusionStatus",
    "PerceptionEvidence",
    "SpatialAgreement",
    "SemanticAgreement",
    "FusionPolicy",
    "FusedEvidence",
    "FusedTargetMatch",
    "MultiModalFusionResult",
    "normalize_text",
    "matches_text",
    "tokenize_text",
]

