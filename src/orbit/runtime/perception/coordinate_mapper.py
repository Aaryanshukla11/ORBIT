"""Coordinate space transformation and validation engine for OCR bounding boxes."""

from __future__ import annotations

import logging
from typing import Optional, Tuple
from pydantic import BaseModel, Field

from orbit.models.common import BoundingBox
from orbit.runtime.perception.models import (
    OCRBoundingBox,
    OCRCoordinateSpace,
    OCRStatus,
)

logger = logging.getLogger(__name__)


class CoordinateMappingResult(BaseModel):
    """Outcome of a coordinate space transformation."""

    is_valid: bool = Field(..., description="True if mapping succeeded and resulting box is geometrically valid")
    status: OCRStatus = Field(..., description="Outcome status (SUCCESS or COORDINATE_MAPPING_FAILED)")
    mapped_box: Optional[OCRBoundingBox] = Field(default=None, description="Transformed bounding box if valid")
    diagnostic_message: Optional[str] = Field(default=None, description="Diagnostic error reason if mapping failed")


class OCRCoordinateMapper:
    """Deterministic, fail-closed coordinate mapper across OCR coordinate spaces."""

    def __init__(
        self,
        virtual_origin_x: int = 0,
        virtual_origin_y: int = 0,
        virtual_width: int = 32767,
        virtual_height: int = 32767,
    ) -> None:
        self._virtual_origin_x = virtual_origin_x
        self._virtual_origin_y = virtual_origin_y
        self._virtual_width = virtual_width
        self._virtual_height = virtual_height

    def map_to_virtual_desktop(
        self,
        box: OCRBoundingBox,
        screenshot_offset_x: int = 0,
        screenshot_offset_y: int = 0,
        dpi_scale_factor: float = 1.0,
        window_origin_x: Optional[int] = None,
        window_origin_y: Optional[int] = None,
    ) -> CoordinateMappingResult:
        """Transform an OCR bounding box from its declared space into VIRTUAL_DESKTOP_SPACE."""
        # 1. Base geometric sanity check
        if not box.is_valid or box.width <= 0 or box.height <= 0:
            return CoordinateMappingResult(
                is_valid=False,
                status=OCRStatus.COORDINATE_MAPPING_FAILED,
                diagnostic_message=(
                    f"Invalid input bounding box geometry: left={box.left}, right={box.right}, "
                    f"top={box.top}, bottom={box.bottom} (width={box.width}, height={box.height})"
                ),
            )

        source_space = box.coordinate_space

        try:
            if source_space == OCRCoordinateSpace.VIRTUAL_DESKTOP_SPACE:
                # Already in virtual desktop space
                mapped_left = box.left
                mapped_top = box.top
                mapped_right = box.right
                mapped_bottom = box.bottom

            elif source_space == OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE:
                # Add screenshot offset in virtual space
                mapped_left = box.left + screenshot_offset_x
                mapped_top = box.top + screenshot_offset_y
                mapped_right = box.right + screenshot_offset_x
                mapped_bottom = box.bottom + screenshot_offset_y

            elif source_space == OCRCoordinateSpace.WINDOW_CLIENT_SPACE:
                if window_origin_x is None or window_origin_y is None:
                    return CoordinateMappingResult(
                        is_valid=False,
                        status=OCRStatus.COORDINATE_MAPPING_FAILED,
                        diagnostic_message="WINDOW_CLIENT_SPACE mapping requires non-null window_origin coordinates",
                    )
                mapped_left = box.left + window_origin_x
                mapped_top = box.top + window_origin_y
                mapped_right = box.right + window_origin_x
                mapped_bottom = box.bottom + window_origin_y

            elif source_space == OCRCoordinateSpace.LOGICAL_DPI_SPACE:
                if dpi_scale_factor <= 0.0:
                    return CoordinateMappingResult(
                        is_valid=False,
                        status=OCRStatus.COORDINATE_MAPPING_FAILED,
                        diagnostic_message=f"Invalid DPI scale factor: {dpi_scale_factor}",
                    )
                mapped_left = int(round(box.left * dpi_scale_factor)) + screenshot_offset_x
                mapped_top = int(round(box.top * dpi_scale_factor)) + screenshot_offset_y
                mapped_right = int(round(box.right * dpi_scale_factor)) + screenshot_offset_x
                mapped_bottom = int(round(box.bottom * dpi_scale_factor)) + screenshot_offset_y

            else:
                return CoordinateMappingResult(
                    is_valid=False,
                    status=OCRStatus.COORDINATE_MAPPING_FAILED,
                    diagnostic_message=f"Unknown coordinate space: {source_space}",
                )

            mapped_box = OCRBoundingBox(
                left=mapped_left,
                top=mapped_top,
                right=mapped_right,
                bottom=mapped_bottom,
                coordinate_space=OCRCoordinateSpace.VIRTUAL_DESKTOP_SPACE,
            )

            # 2. Validate output geometry
            if not mapped_box.is_valid or mapped_box.width <= 0 or mapped_box.height <= 0:
                return CoordinateMappingResult(
                    is_valid=False,
                    status=OCRStatus.COORDINATE_MAPPING_FAILED,
                    diagnostic_message=f"Transformed bounding box is geometrically invalid: {mapped_box}",
                )

            return CoordinateMappingResult(
                is_valid=True,
                status=OCRStatus.SUCCESS,
                mapped_box=mapped_box,
            )

        except Exception as ex:
            logger.error("Coordinate mapping failed with exception: %s", ex, exc_info=True)
            return CoordinateMappingResult(
                is_valid=False,
                status=OCRStatus.COORDINATE_MAPPING_FAILED,
                diagnostic_message=f"Coordinate transformation error: {ex}",
            )
