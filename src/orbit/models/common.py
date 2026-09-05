"""Common geometric, temporal, and error domain models for ORBIT."""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class Point2D(BaseModel):
    """Normalized or floating-point coordinate pair (0.0 to 1.0 or custom unit)."""

    x: float = Field(..., description="X coordinate")
    y: float = Field(..., description="Y coordinate")


class ScreenPoint(BaseModel):
    """Physical pixel coordinate on the virtual desktop."""

    x: int = Field(..., description="Physical X coordinate in pixels")
    y: int = Field(..., description="Physical Y coordinate in pixels")


class BoundingBox(BaseModel):
    """Rectangular area in pixel space."""

    left: int = Field(..., description="Left pixel coordinate")
    top: int = Field(..., description="Top pixel coordinate")
    width: int = Field(..., gt=0, description="Width in pixels")
    height: int = Field(..., gt=0, description="Height in pixels")

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def center(self) -> ScreenPoint:
        return ScreenPoint(
            x=self.left + self.width // 2,
            y=self.top + self.height // 2,
        )

    def contains(self, pt: ScreenPoint) -> bool:
        return (
            self.left <= pt.x < self.right and
            self.top <= pt.y < self.bottom
        )


class Resolution(BaseModel):
    """Display or viewport resolution."""

    width: int = Field(..., gt=0, description="Width in physical pixels")
    height: int = Field(..., gt=0, description="Height in physical pixels")
    scale_factor: float = Field(1.0, gt=0.0, description="DPI scale factor (e.g. 1.0, 1.25, 1.5, 2.0)")


class ErrorDetail(BaseModel):
    """Structured error payload for events and exceptions."""

    code: str = Field(..., description="Machine-readable error classification code")
    message: str = Field(..., description="Human-readable error explanation")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Optional diagnostic details")
    recoverable: bool = Field(default=True, description="Whether the error state can be recovered or retried")
