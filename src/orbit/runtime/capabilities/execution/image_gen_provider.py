"""Image Generation Provider Interface and Runtime Contracts (M1.9 Component 8).

INVARIANT:
A text-only language model or non-generative provider MUST NOT be registered as
an ImageGenerationProvider. If no genuine image generation provider is operational,
IMAGE_GENERATE capabilities are honestly reported as unavailable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class GeneratedImageResult(BaseModel):
    """Output artifact produced by an image generation provider."""

    success: bool = Field(..., description="Whether image generation succeeded")
    image_path: Optional[str] = Field(default=None, description="Absolute file path to saved image artifact")
    image_bytes: Optional[bytes] = Field(default=None, description="Raw image bytes if held in memory")
    width: Optional[int] = Field(default=None, description="Image width in pixels")
    height: Optional[int] = Field(default=None, description="Image height in pixels")
    model_id: str = Field(default="unknown", description="Model identifier that produced this artifact")
    mime_type: str = Field(default="image/png", description="Image MIME type")
    error: Optional[str] = Field(default=None, description="Error message if generation failed")


class ImageGenerationProvider(ABC): 
    """Interface for generative AI providers capable of synthesizing real image artifacts."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True only if a real image generation model is reachable and configured."""
        ...

    @abstractmethod 
    async def generate_image(
        self,
        prompt: str,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> GeneratedImageResult:
        """Synthesize an image based on semantic prompt and return a verified artifact."""
        ...


class NullImageGenerationProvider(ImageGenerationProvider):
    """Default honest null provider when no image generation model is connected to ORBIT."""

    def is_available(self) -> bool:
        return False

    async def generate_image(
        self,
        prompt: str,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> GeneratedImageResult:
        return GeneratedImageResult(
            success=False,
            error="No active ImageGenerationProvider configured. Text-only models cannot generate images.",
        )
