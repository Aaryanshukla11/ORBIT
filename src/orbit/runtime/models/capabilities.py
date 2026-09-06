"""Model capability analysis, normalization, and filtering helpers (Milestone M1.9 Step 2).

Provides capability inference from runtime tags, model architecture families,
and model names, as well as filtering utilities for registry queries.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Set

from orbit.runtime.models.models import (
    ModelCapability,
    ModelDescriptor,
    ModelProviderKind,
)


def infer_capabilities(
    provider: Optional[ModelProviderKind | str] = None,
    raw_capabilities: Iterable[str] | None = None,
    model_name: str = "",
    family: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Set[ModelCapability]:
    """Deterministically infer standardized ModelCapability flags from runtime attributes."""
    # Allow calling as infer_capabilities("model-name-string")
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
        # Dedicated embedding models typically do not perform open-ended text chat
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
    """Check whether a model descriptor satisfies all required capabilities.

    Returns True if required_capabilities is None, empty, or a subset of descriptor.capabilities.
    """
    if not required_capabilities:
        return True
    req_set = set(required_capabilities)
    return req_set.issubset(descriptor.capabilities)
