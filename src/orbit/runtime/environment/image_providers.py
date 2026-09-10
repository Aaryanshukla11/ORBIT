"""Artifact-Only Image Generation Environment Provider.

INVARIANT:
Artifact-Only Execution. Generates real image files on disk. Zero physical desktop
execution authority, zero mouse/keyboard manipulation, zero window spawning.
All physical actions (e.g. launching Paint, pasting image) must route through
PrimitiveExecutionController via canonical primitives.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import AbstractAction
from orbit.runtime.environment.registry import EnvironmentProvider, ProviderExecutionResult

logger = logging.getLogger(__name__)


class GeneratedImageResult(BaseModel):
    """Artifact result produced by an image generation provider."""

    success: bool = Field(..., description="Whether generation succeeded")
    image_path: Optional[str] = Field(default=None, description="Path to generated image on disk")
    image_bytes: Optional[bytes] = Field(default=None, description="Raw image bytes if in memory")
    width: Optional[int] = Field(default=None)
    height: Optional[int] = Field(default=None)
    mime_type: str = Field(default="image/png")
    model_id: Optional[str] = Field(default=None)
    error: Optional[str] = Field(default=None)


class ImageGenerationProvider(ABC):
    """Abstract interface for generative image backends."""

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if model backend is operational."""
        ...

    @abstractmethod
    async def generate_image(
        self,
        prompt: str,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> GeneratedImageResult:
        """Synthesize image from prompt."""
        ...


class NullImageGenerationProvider(ImageGenerationProvider):
    """No-op / unavailable image generation provider."""

    async def is_available(self) -> bool:
        return False

    async def generate_image(
        self,
        prompt: str,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> GeneratedImageResult:
        return GeneratedImageResult(
            success=False,
            error="No image generation backend configured",
        )


class ArtifactImageGenProvider(EnvironmentProvider):
    """Environment provider delivering image synthesis as a verified file artifact."""

    def __init__(
        self,
        image_gen_backend: Optional[ImageGenerationProvider] = None,
        default_output_dir: Optional[str] = None,
    ) -> None:
        self._backend = image_gen_backend or NullImageGenerationProvider()
        self._default_output_dir = default_output_dir or os.path.abspath("./artifacts/generated_images")

    @property
    def provider_id(self) -> str:
        return "artifact_image_gen_provider"

    @property
    def supported_features(self) -> List[str]:
        return ["image_artifact", "file_output", "non_physical", "zero_desktop_authority"]

    async def is_available(self) -> bool:
        """Check if backend generative model is operational."""
        return await self._backend.is_available()

    async def check_permissions(self, action: AbstractAction) -> bool:
        """Verify prompt is provided."""
        params = action.parameters or {}
        prompt = params.get("prompt") or params.get("description")
        return bool(prompt and str(prompt).strip())

    async def execute(self, action: AbstractAction) -> ProviderExecutionResult:
        """Generate image artifact on disk without any physical OS interaction."""
        params = action.parameters or {}
        prompt = str(params.get("prompt") or params.get("description") or "").strip()
        if not prompt:
            return ProviderExecutionResult(
                success=False,
                error="IMAGE_GEN_FAILED: Missing required 'prompt' parameter",
            )

        output_path = params.get("output_path") or params.get("path")
        constraints = params.get("constraints", {})

        logger.info("[IMAGE ARTIFACT PROVIDER] Synthesizing image artifact for prompt: '%s'", prompt)

        try:
            gen_result: GeneratedImageResult = await self._backend.generate_image(
                prompt=prompt,
                constraints=constraints,
            )

            if not gen_result.success:
                return ProviderExecutionResult(
                    success=False,
                    error=gen_result.error or "Image generation backend failed",
                    metadata={"provider": self.provider_id, "prompt": prompt},
                )

            # If image bytes were returned without path, save them to disk
            saved_path = gen_result.image_path
            if not saved_path and gen_result.image_bytes:
                os.makedirs(self._default_output_dir, exist_ok=True)
                import uuid
                filename = f"gen_{uuid.uuid4().hex[:8]}.png"
                saved_path = os.path.join(self._default_output_dir, filename)
                Path(saved_path).write_bytes(gen_result.image_bytes)

            return ProviderExecutionResult(
                success=True,
                output={
                    "prompt": prompt,
                    "image_path": saved_path,
                    "width": gen_result.width,
                    "height": gen_result.height,
                    "model_id": gen_result.model_id,
                    "mime_type": gen_result.mime_type,
                    "artifact_exists": os.path.exists(saved_path) if saved_path else False,
                },
                metadata={
                    "provider": self.provider_id,
                    "zero_physical_authority": True,
                },
            )

        except Exception as exc:
            logger.error("[IMAGE ARTIFACT PROVIDER] Image generation failed: %s", exc, exc_info=True)
            return ProviderExecutionResult(
                success=False,
                error=f"IMAGE_GEN_EXCEPTION: {str(exc)}",
                metadata={"provider": self.provider_id, "prompt": prompt},
            )
