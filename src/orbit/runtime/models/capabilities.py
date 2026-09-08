"""Model capability analysis, normalization, and filtering helpers (Milestone M1.9 Step 2).

Provides capability inference from runtime tags, model architecture families,
and model names, as well as filtering utilities for registry queries.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Set
from pydantic import BaseModel, Field

from orbit.runtime.models.models import (
    ModelCapability,
    ModelDescriptor,
    ModelProviderKind,
)


class ModelCapabilityProfile(BaseModel):
    """Canonical profile describing model identity, capabilities, and hosting topology."""

    model_id: str
    provider: ModelProviderKind
    model_name: str
    capabilities: Set[ModelCapability] = Field(default_factory=set)
    is_local: bool = True
    context_window: Optional[int] = None
    description: str = ""

    @property
    def supports_vision(self) -> bool:
        """Whether this model can natively accept and process images / screenshots."""
        return ModelCapability.VISION in self.capabilities

    @property
    def supports_reasoning(self) -> bool:
        """Whether this model produces explicit deep reasoning / chain-of-thought tokens."""
        return ModelCapability.REASONING in self.capabilities

    @property
    def supports_tools(self) -> bool:
        """Whether this model supports structured tool / function calling."""
        return ModelCapability.TOOL_CALLING in self.capabilities

    @classmethod
    def from_descriptor(cls, descriptor: ModelDescriptor) -> ModelCapabilityProfile:
        """Create a profile from an active or discovered ModelDescriptor."""
        is_local = descriptor.provider in {
            ModelProviderKind.OLLAMA,
            ModelProviderKind.LM_STUDIO,
            ModelProviderKind.LOCAL_FILE,
        }
        caps = set(descriptor.capabilities)
        if not caps:
            caps = infer_capabilities(
                provider=descriptor.provider,
                model_name=descriptor.provider_model_name,
                family=descriptor.family or "",
            )
        return cls(
            model_id=descriptor.model_id,
            provider=descriptor.provider,
            model_name=descriptor.provider_model_name,
            capabilities=caps,
            is_local=is_local,
            context_window=descriptor.context_window,
            description=descriptor.display_name or descriptor.provider_model_name,
        )


# Known canonical model capability profiles
CANONICAL_MODEL_PROFILES: Dict[str, ModelCapabilityProfile] = {
    # Local Vision Models
    "ollama:llava:latest": ModelCapabilityProfile(
        model_id="ollama:llava:latest",
        provider=ModelProviderKind.OLLAMA,
        model_name="llava:latest",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION},
        is_local=True,
        context_window=4096,
        description="Local multimodal LLaVA vision-language model",
    ),
    "ollama:llama3.2-vision:latest": ModelCapabilityProfile(
        model_id="ollama:llama3.2-vision:latest",
        provider=ModelProviderKind.OLLAMA,
        model_name="llama3.2-vision:latest",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION},
        is_local=True,
        context_window=8192,
        description="Local Llama 3.2 multimodal vision model",
    ),
    "ollama:qwen2-vl:latest": ModelCapabilityProfile(
        model_id="ollama:qwen2-vl:latest",
        provider=ModelProviderKind.OLLAMA,
        model_name="qwen2-vl:latest",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION},
        is_local=True,
        context_window=8192,
        description="Local Qwen 2 VL vision model",
    ),
    # Local Text / Reasoning Models
    "ollama:qwen2.5:latest": ModelCapabilityProfile(
        model_id="ollama:qwen2.5:latest",
        provider=ModelProviderKind.OLLAMA,
        model_name="qwen2.5:latest",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.TOOL_CALLING},
        is_local=True,
        context_window=32768,
        description="Local Qwen 2.5 general reasoning and tool-calling model",
    ),
    "ollama:deepseek-r1:latest": ModelCapabilityProfile(
        model_id="ollama:deepseek-r1:latest",
        provider=ModelProviderKind.OLLAMA,
        model_name="deepseek-r1:latest",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.REASONING},
        is_local=True,
        context_window=65536,
        description="Local DeepSeek R1 reasoning model with thinking tokens",
    ),
    # Cloud Vision & Reasoning Models
    "cloud:gpt-4o": ModelCapabilityProfile(
        model_id="cloud:gpt-4o",
        provider=ModelProviderKind.CLOUD_OPENAI,
        model_name="gpt-4o",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING},
        is_local=False,
        context_window=128000,
        description="Cloud OpenAI flagship multimodal model",
    ),
    "cloud:gpt-4o-mini": ModelCapabilityProfile(
        model_id="cloud:gpt-4o-mini",
        provider=ModelProviderKind.CLOUD_OPENAI,
        model_name="gpt-4o-mini",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING},
        is_local=False,
        context_window=128000,
        description="Cloud OpenAI fast lightweight multimodal model",
    ),
    "cloud:claude-3-5-sonnet": ModelCapabilityProfile(
        model_id="cloud:claude-3-5-sonnet",
        provider=ModelProviderKind.CLOUD_ANTHROPIC,
        model_name="claude-3-5-sonnet",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING},
        is_local=False,
        context_window=200000,
        description="Cloud Anthropic Claude 3.5 Sonnet multimodal model",
    ),
    "cloud:gemini-2.0-flash": ModelCapabilityProfile(
        model_id="cloud:gemini-2.0-flash",
        provider=ModelProviderKind.CLOUD_GEMINI,
        model_name="gemini-2.0-flash",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING},
        is_local=False,
        context_window=1000000,
        description="Cloud Google Gemini 2.0 Flash high-speed multimodal model",
    ),
}


def get_model_capability_profile(
    model_id: str,
    descriptor: Optional[ModelDescriptor] = None,
) -> ModelCapabilityProfile:
    """Retrieve or build a capability profile for a model identifier."""
    if model_id in CANONICAL_MODEL_PROFILES:
        return CANONICAL_MODEL_PROFILES[model_id]

    if descriptor is not None:
        return ModelCapabilityProfile.from_descriptor(descriptor)

    # Infer on the fly
    provider_str, _, name = model_id.partition(":")
    is_local = provider_str.lower() in {"ollama", "lm_studio", "local_file", "local"}
    caps = infer_capabilities(provider=provider_str, model_name=name or model_id)
    return ModelCapabilityProfile(
        model_id=model_id,
        provider=ModelProviderKind.OLLAMA if is_local else ModelProviderKind.CLOUD,
        model_name=name or model_id,
        capabilities=caps,
        is_local=is_local,
    )


def infer_capabilities(
    provider: Optional[ModelProviderKind | str] = None,
    raw_capabilities: Iterable[str] | None = None,
    model_name: str = "",
    family: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Set[ModelCapability]:
    """Deterministically infer standardized ModelCapability flags from runtime attributes."""
    if isinstance(provider, str) and not model_name:
        model_name = provider
        provider = None

    caps: Set[ModelCapability] = set()
    raw_caps_lower = {str(c).lower().strip() for c in (raw_capabilities or [])}
    name_lower = (model_name or "").lower()
    fam_lower = (family or "").lower()

    # 1. Check Embeddings
    if "embedding" in raw_caps_lower or "embed" in name_lower or "bert" in fam_lower:
        caps.add(ModelCapability.EMBEDDINGS)
        if len(raw_caps_lower) == 1 and "embedding" in raw_caps_lower:
            return caps

    # 2. Check Text Generation & Chat
    if "completion" in raw_caps_lower or "chat" in raw_caps_lower or not caps:
        caps.add(ModelCapability.TEXT_GENERATION)
        caps.add(ModelCapability.CHAT)

    # 3. Check Vision
    if "vision" in raw_caps_lower or "vision" in name_lower or "mllama" in fam_lower or "vl" in name_lower or "llava" in name_lower:
        caps.add(ModelCapability.VISION)

    # 4. Check Tool Calling / Function Calling
    if "tools" in raw_caps_lower or "tool" in raw_caps_lower or "function_calling" in raw_caps_lower:
        caps.add(ModelCapability.TOOL_CALLING)
    elif any(k in name_lower for k in ("hermes", "gorilla", "functionary", "command-r", "tool")):
        caps.add(ModelCapability.TOOL_CALLING)

    # 5. Check Explicit Reasoning / Thinking Tokens
    if any(k in name_lower for k in ("-r1", "deepseek-r1", "qwq", "reasoner", "o1-", "o3-", "o1", "o3")):
        caps.add(ModelCapability.REASONING)

    # 6. Check Code Synthesis
    if any(k in name_lower for k in ("coder", "code", "starcoder", "deepseek-coder", "codellama")):
        caps.add(ModelCapability.CODE)

    return caps


def matches_capabilities(
    descriptor: ModelDescriptor,
    required_capabilities: Iterable[ModelCapability] | None = None,
) -> bool:
    """Check whether a model descriptor satisfies all required capabilities."""
    if not required_capabilities:
        return True
    req_set = set(required_capabilities)
    return req_set.issubset(descriptor.capabilities)


