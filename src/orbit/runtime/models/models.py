"""Provider-independent AI Model runtime contracts and data models (Milestone M1.9 Step 1).

Defines strongly-typed, immutable representations of:
- Model providers and categories
- Model status and runtime states
- Model capabilities (text, chat, vision, tool calling, reasoning, embeddings)
- Model descriptors with genuine, un-fabricated metadata
- Provider health reports with true latency measurements
- Generation and Chat request/response envelopes
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field, field_validator


class ModelProviderKind(str, Enum):
    """Enumeration of supported and recognized AI model provider runtime kinds."""

    OLLAMA = "OLLAMA"
    LM_STUDIO = "LM_STUDIO"
    OPENAI_COMPATIBLE = "OPENAI_COMPATIBLE"
    CLOUD = "CLOUD"
    CLOUD_OPENAI = "CLOUD_OPENAI"
    CLOUD_ANTHROPIC = "CLOUD_ANTHROPIC"
    CLOUD_GEMINI = "CLOUD_GEMINI"
    LOCAL_FILE = "LOCAL_FILE"


class ModelSourceType(str, Enum):
    """Origin and hosting type of an AI model."""

    LOCAL_RUNTIME = "LOCAL_RUNTIME"  # Managed by local server daemon (Ollama, LM Studio, etc.)
    LOCAL_FILE = "LOCAL_FILE"        # Raw model weights file on local storage (GGUF, ONNX, etc.)
    CLOUD_PROVIDER = "CLOUD_PROVIDER"# Remote cloud API provider (OpenAI, Anthropic, Gemini, etc.)


class CloudProviderKind(str, Enum):
    """Supported cloud AI API provider platforms."""

    OPENAI = "OPENAI"
    ANTHROPIC = "ANTHROPIC"
    GEMINI = "GEMINI"
    CUSTOM_OPENAI_COMPATIBLE = "CUSTOM_OPENAI_COMPATIBLE"


class CloudAuthStatus(str, Enum):
    """Authentication and connectivity state of a cloud model provider."""

    NOT_CONFIGURED = "NOT_CONFIGURED"                # No API key or credentials provided
    CONFIGURED_UNVERIFIED = "CONFIGURED_UNVERIFIED"   # Key present in memory, not yet validated
    AUTHENTICATING = "AUTHENTICATING"                # Active validation probe in progress
    AUTHENTICATED = "AUTHENTICATED"                  # Valid credentials configured and verified
    AUTH_FAILED = "AUTH_FAILED"                      # Authentication rejected by provider (HTTP 401/403)
    UNREACHABLE = "UNREACHABLE"                      # Remote endpoint unreachable or timeout
    UNAVAILABLE = "UNAVAILABLE"                      # Provider unavailable / server error
    ERROR = "ERROR"                                  # General error or exception


class ModelFileFormat(str, Enum):
    """File format of a local model weight artifact."""

    GGUF = "GGUF"
    ONNX = "ONNX"
    SAFETENSORS = "SAFETENSORS"
    BIN = "BIN"
    UNKNOWN = "UNKNOWN"


class ModelStatus(str, Enum):
    """Current operational and deployment lifecycle status of an AI model."""

    DISCOVERED = "DISCOVERED"      # Discovered in provider registry or filesystem, not yet loaded/installed
    INSTALLING = "INSTALLING"      # Currently downloading or installing weights
    INSTALLED = "INSTALLED"        # Weights downloaded and verified locally
    LOADING = "LOADING"            # Currently loading weights into GPU/VRAM or memory
    READY = "READY"                # Initialized and ready for immediate inference
    ACTIVE = "ACTIVE"              # Currently selected as ORBIT's primary active model
    AVAILABLE = "AVAILABLE"        # Ready for inference (synonym for READY)
    LOADED = "LOADED"              # Resident in memory/VRAM (synonym for ACTIVE)
    UNAVAILABLE = "UNAVAILABLE"    # Known model but currently unavailable (e.g. missing weights, daemon off)
    UNREACHABLE = "UNREACHABLE"    # Remote endpoint unreachable
    INCOMPATIBLE = "INCOMPATIBLE"  # File or model architecture incompatible with current hardware/runtime
    FAILED = "FAILED"              # Encountered an unrecoverable failure state
    OFFLINE = "OFFLINE"            # Provider or daemon is offline
    UNKNOWN = "UNKNOWN"            # Status could not be determined


class ModelCapability(str, Enum):
    """Specific functional capabilities supported by an AI model."""

    TEXT_GENERATION = "TEXT_GENERATION"  # Raw text completion / generation
    CHAT = "CHAT"                        # Multi-turn conversational chat
    VISION = "VISION"                    # Multimodal visual image understanding
    TOOL_CALLING = "TOOL_CALLING"        # Structured function/tool calling
    REASONING = "REASONING"              # Explicit reasoning / thinking tokens (e.g. DeepSeek-R1)
    EMBEDDINGS = "EMBEDDINGS"            # Vector representation / text embeddings
    CODE = "CODE"                        # Specialized source code synthesis and infilling
    CODE_GENERATION = "CODE"             # Alias for CODE capability


class ProviderHealthStatus(str, Enum):
    """Operational health state of a model provider backend."""

    HEALTHY = "HEALTHY"        # Reachable, responsive, low latency
    DEGRADED = "DEGRADED"      # Reachable with elevated latency or partial capability
    UNAVAILABLE = "UNAVAILABLE"# Connection refused or host unreachable
    ERROR = "ERROR"            # Runtime threw unhandled error during probe


class ProviderHealth(BaseModel):
    """Health check outcome and latency diagnostic for a model provider."""

    provider: ModelProviderKind = Field(..., description="Provider category")
    status: ProviderHealthStatus = Field(..., description="Health status classification")
    endpoint: str = Field(..., description="Target network endpoint or socket")
    checked_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when health probe was completed",
    )
    latency_ms: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Measured network roundtrip latency in milliseconds. None if unreachable.",
    )
    diagnostic_message: Optional[str] = Field(
        default=None,
        description="Human-readable status or error explanation",
    )
    version_info: Optional[str] = Field(
        default=None,
        description="Provider daemon / engine version string if reported",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional provider-specific health metrics",
    )


class ModelDescriptor(BaseModel):
    """Provider-independent descriptor of an installed or available AI model.

    Contains genuine metadata reported by the underlying runtime without fabrication.
    """

    model_id: str = Field(
        ...,
        description="Stable provider-aware unique identifier (e.g. 'ollama:qwen2.5:latest')",
    )
    provider: ModelProviderKind = Field(
        ...,
        description="Provider runtime kind managing this model",
    )
    provider_model_name: str = Field(
        ...,
        description="Exact model identifier returned by provider runtime (e.g. 'qwen2.5:latest')",
    )
    display_name: str = Field(
        default="",
        description="Human-readable display name for presentation and logging",
    )
    model_name: Optional[str] = Field(
        default=None,
        description="Alias for display_name or provider_model_name",
    )
    source_type: ModelSourceType = Field(
        default=ModelSourceType.LOCAL_RUNTIME,
        description="Origin source type (LOCAL_RUNTIME, LOCAL_FILE, CLOUD_PROVIDER)",
    )
    source_path: Optional[str] = Field(
        default=None,
        description="Local filesystem path if discovered from file, or None",
    )
    file_format: Optional[ModelFileFormat] = Field(
        default=None,
        description="File format if discovered from local file (GGUF, ONNX, etc.)",
    )
    status: ModelStatus = Field(
        default=ModelStatus.DISCOVERED,
        description="Current operational lifecycle status of this model",
    )
    capabilities: Set[ModelCapability] = Field(
        default_factory=set,
        description="Set of verified capabilities supported by this model",
    )
    context_window: Optional[int] = Field(
        default=None,
        ge=0,
        description="Maximum context window size in tokens, or None if unknown",
    )
    parameter_size: Optional[str] = Field(
        default=None,
        description="Parameter scale string (e.g. '7.6B', '14.8B'), or None if unknown",
    )
    quantization_level: Optional[str] = Field(
        default=None,
        description="Quantization format (e.g. 'Q4_K_M', 'F16'), or None if unknown",
    )
    quantization: Optional[str] = Field(
        default=None,
        description="Alias for quantization_level",
    )
    family: Optional[str] = Field(
        default=None,
        description="Model architecture family (e.g. 'qwen2', 'llama'), or None if unknown",
    )
    size_bytes: Optional[int] = Field(
        default=None,
        ge=0,
        description="Model disk size in bytes if reported, or None if unknown",
    )

    def model_post_init(self, __context: Any) -> None:
        if self.model_name and not self.display_name:
            self.display_name = self.model_name
        elif not self.model_name:
            self.model_name = self.display_name or self.provider_model_name
        if not self.display_name:
            self.display_name = self.model_name or self.provider_model_name

        if self.quantization and not self.quantization_level:
            self.quantization_level = self.quantization
        elif not self.quantization:
            self.quantization = self.quantization_level
    digest: Optional[str] = Field(
        default=None,
        description="Cryptographic checksum / sha256 digest of weights if reported",
    )
    local_or_remote: str = Field(
        default="local",
        description="Whether the model executes on local hardware ('local') or cloud ('remote')",
    )
    endpoint: Optional[str] = Field(
        default=None,
        description="Provider API endpoint hosting this model",
    )
    discovered_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when model was initially discovered",
    )
    last_health: Optional[ProviderHealth] = Field(
        default=None,
        description="Latest health probe result for this model's provider",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific raw attributes",
    )

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, v: str) -> str:
        if not v or ":" not in v:
            raise ValueError(f"model_id must be formatted as '<provider>:<name>', got '{v}'")
        return v


class ModelGenerateRequest(BaseModel):
    """Typed request envelope for text completion / generation."""

    prompt: str = Field(..., description="Prompt string to send to model")
    system_prompt: Optional[str] = Field(default=None, description="Optional system instruction")
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: Optional[int] = Field(default=None, gt=0, description="Max tokens to generate")
    stop: Optional[List[str]] = Field(default=None, description="Stop sequence strings")
    expected_generation: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional expected generation counter to guard against stale inference dispatch",
    )
    options: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific generation parameters")


class ModelRole(str, Enum):
    """Enumeration of message roles in a structured multi-turn conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ModelChatMessage(BaseModel):
    """Single turn in a structured multi-turn conversation."""

    role: str = Field(..., description="Message role: 'system', 'user', 'assistant', or 'tool'")
    content: str = Field(..., description="Text content of the message")
    images: Optional[List[str]] = Field(
        default=None,
        description="Optional list of base64-encoded images for vision-capable models",
    )


class ModelChatRequest(BaseModel):
    """Typed request envelope for structured conversational chat."""

    messages: List[ModelChatMessage] = Field(..., min_length=1, description="List of chat turns")
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: Optional[int] = Field(default=None, gt=0, description="Max tokens to generate")
    stop: Optional[List[str]] = Field(default=None, description="Stop sequence strings")
    expected_generation: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional expected generation counter to guard against stale inference dispatch",
    )
    options: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific chat parameters")


class ModelGenerateResponse(BaseModel):
    """Standardized response from an AI model generation or chat operation."""

    model_id: str = Field(..., description="ID of the model that produced this response")
    content: str = Field(..., description="Generated text content")
    done: bool = Field(default=True, description="Whether generation reached completion")
    total_duration_ms: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Total duration in milliseconds spent on generation",
    )
    prompt_tokens: Optional[int] = Field(default=None, ge=0, description="Number of tokens in prompt")
    completion_tokens: Optional[int] = Field(default=None, ge=0, description="Number of tokens generated")
    raw_response: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw untransformed provider response dictionary",
    )

    @property
    def text(self) -> str:
        """Alias for content."""
        return self.content


# Canonical alias for chat response envelopes
ModelChatResponse = ModelGenerateResponse



class LocalModelFileDescriptor(BaseModel):
    """Safe metadata collected from candidate local model files without loading weights."""

    path: str = Field(..., description="Absolute filesystem path to candidate model file")
    filename: str = Field(..., description="Base filename")
    file_name: Optional[str] = Field(default=None, description="Alias for filename")
    format: ModelFileFormat = Field(..., description="File format classification")
    format_metadata: Dict[str, Any] = Field(default_factory=dict, description="Parsed header details")
    size_bytes: int = Field(..., ge=0, description="Size in bytes on disk")
    last_modified_utc: datetime = Field(..., description="File modification timestamp")
    model_family: Optional[str] = Field(default=None, description="Inferred model family if determinable")
    quantization: Optional[str] = Field(default=None, description="Inferred quantization string if determinable")
    is_compatible: bool = Field(default=True, description="Whether the file format is supported by ORBIT runtime")
    incompatibility_reason: Optional[str] = Field(default=None, description="Reason if marked incompatible")

    def model_post_init(self, __context: Any) -> None:
        if self.file_name is not None:
            self.filename = self.file_name
        else:
            self.file_name = self.filename


class InstallationStage(str, Enum):
    """Lifecycle stages during model weight download and installation."""

    INITIALIZING = "INITIALIZING"
    QUEUED = "QUEUED"
    DOWNLOADING = "DOWNLOADING"
    VERIFYING = "VERIFYING"
    WRITING = "WRITING"
    COMPLETED = "COMPLETED"
    COMPLETE = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class InstallationRequest(BaseModel):
    """Request payload to install / pull a model through a local runtime."""

    model_name: str = Field(..., description="Model identifier to install (e.g. 'qwen2.5:0.5b')")
    provider_kind: ModelProviderKind = Field(
        default=ModelProviderKind.OLLAMA,
        description="Target provider runtime to execute the pull",
    )
    target_runtime: Optional[ModelProviderKind] = Field(
        default=None,
        description="Alias for provider_kind",
    )
    source_uri: Optional[str] = Field(default=None, description="Optional remote repository or registry URI")
    tag: Optional[str] = Field(default="latest", description="Version / revision tag")
    insecure: bool = Field(default=False, description="Allow HTTP connections for custom registries")

    def model_post_init(self, __context: Any) -> None:
        if self.target_runtime is not None:
            self.provider_kind = self.target_runtime
        else:
            self.target_runtime = self.provider_kind


class InstallationProgress(BaseModel):
    """Point-in-time progress snapshot during model installation."""

    model_name: str = Field(..., description="Model identifier being installed")
    stage: InstallationStage = Field(default=InstallationStage.QUEUED, description="Current installation stage")
    percent: float = Field(default=0.0, ge=0.0, le=100.0, description="Percentage completed [0.0..100.0]")
    percent_complete: Optional[float] = Field(default=None, description="Alias for percent")
    downloaded_bytes: int = Field(default=0, ge=0, description="Bytes downloaded so far")
    bytes_completed: Optional[int] = Field(default=None, description="Alias for downloaded_bytes")
    total_bytes: Optional[int] = Field(default=None, ge=0, description="Total expected size in bytes")
    speed_bps: Optional[float] = Field(default=None, ge=0.0, description="Current download speed in bytes per second")
    status_message: str = Field(default="", description="Human-readable progress detail")
    error_message: Optional[str] = Field(default=None, description="Error detail if failed")
    target_runtime: Optional[ModelProviderKind] = Field(default=None, description="Runtime kind")

    def model_post_init(self, __context: Any) -> None:
        if self.percent_complete is not None:
            self.percent = self.percent_complete
        else:
            self.percent_complete = self.percent
        if self.bytes_completed is not None:
            self.downloaded_bytes = self.bytes_completed
        else:
            self.bytes_completed = self.downloaded_bytes


class InstallationResult(BaseModel):
    """Final outcome of a model installation / pull operation."""

    is_success: bool = Field(..., description="Whether the installation completed successfully")
    model_name: str = Field(..., description="Requested model name")
    model_id: Optional[str] = Field(default=None, description="Stable model_id if installed, else None")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Total elapsed installation time in milliseconds")
    error_message: Optional[str] = Field(default=None, description="Diagnostic error message on failure")
    descriptor: Optional[ModelDescriptor] = Field(default=None, description="Discovered descriptor after install")


# =============================================================================
# Milestone M1.9 Step 3: Selection, Activation, Session, and Switching Models
# =============================================================================


class ModelSelectionStatus(str, Enum):
    """Outcome classification for a model selection validation request."""

    SELECTED = "SELECTED"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    RUNTIME_UNREACHABLE = "RUNTIME_UNREACHABLE"
    AUTH_NOT_CONFIGURED = "AUTH_NOT_CONFIGURED"
    MODEL_INCOMPATIBLE = "MODEL_INCOMPATIBLE"
    MODEL_NOT_READY = "MODEL_NOT_READY"
    CAPABILITY_MISMATCH = "CAPABILITY_MISMATCH"
    FAILED = "FAILED"


class ModelSelectionRequest(BaseModel):
    """Request envelope to validate and select a candidate model for future activation."""

    model_id: str = Field(..., description="Target model identifier (e.g. 'ollama:qwen2.5:latest')")
    required_capabilities: Set[ModelCapability] = Field(
        default_factory=set,
        description="Optional capability constraints that the model must satisfy",
    )
    caller_id: Optional[str] = Field(
        default=None,
        description="Subsystem or caller component requesting model selection",
    )
    options: Dict[str, Any] = Field(
        default_factory=dict,
        description="Selection tuning options",
    )


class ModelSelectionResult(BaseModel):
    """Outcome of model selection validation."""

    is_successful: bool = Field(..., description="Whether the requested model is valid and selectable")
    model_id: str = Field(..., description="Target model ID")
    status: ModelSelectionStatus = Field(..., description="Selection outcome status code")
    failure_reason: Optional[str] = Field(
        default=None,
        description="Typed failure code if selection rejected",
    )
    diagnostic_message: Optional[str] = Field(
        default=None,
        description="Human-readable explanation of selection result or failure",
    )
    descriptor: Optional[ModelDescriptor] = Field(
        default=None,
        description="Full descriptor of selected model if successful",
    )
    validated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when selection validation was evaluated",
    )


class ModelSessionStatus(str, Enum):
    """Operational session status of an active model."""

    INITIALIZING = "INITIALIZING"
    ACTIVATING = "ACTIVATING"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    DEACTIVATING = "DEACTIVATING"
    DEACTIVATED = "DEACTIVATED"
    FAILED = "FAILED"


class ActiveModelSession(BaseModel):
    """Immutable snapshot of the single primary active model session in ORBIT."""

    active_model_id: str = Field(..., description="Unique model identifier currently active")
    provider_id: ModelProviderKind = Field(..., description="Provider runtime kind managing this model")
    provider_model_name: str = Field(..., description="Runtime model name on provider")
    runtime_id: str = Field(..., description="Runtime backend or host instance identifier")
    activation_timestamp_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when model activation committed",
    )
    health_status: ProviderHealthStatus = Field(
        default=ProviderHealthStatus.HEALTHY,
        description="Health status at activation time",
    )
    session_status: ModelSessionStatus = Field(
        default=ModelSessionStatus.ACTIVE,
        description="Current session state",
    )
    generation: int = Field(
        default=1,
        ge=1,
        description="Monotonically increasing activation generation counter",
    )
    capabilities: Set[ModelCapability] = Field(
        default_factory=set,
        description="Verified capabilities of active model",
    )
    context_window: Optional[int] = Field(
        default=None,
        ge=0,
        description="Token context window size",
    )
    endpoint: Optional[str] = Field(
        default=None,
        description="Provider endpoint (safe address, no credentials)",
    )
    descriptor: Optional[ModelDescriptor] = Field(
        default=None,
        description="Underlying model descriptor",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Safe session metadata without credentials",
    )


class ModelActivationRequest(BaseModel):
    """Request envelope to perform runtime preparation and activate a model."""

    model_id: str = Field(..., description="Target model ID to activate")
    timeout_seconds: float = Field(
        default=60.0,
        gt=0.0,
        description="Activation timeout in seconds",
    )
    preload_weights: bool = Field(
        default=True,
        description="Whether to preload model weights into VRAM/memory if supported",
    )
    required_capabilities: Set[ModelCapability] = Field(
        default_factory=set,
        description="Optional capability constraints that must be verified before activation",
    )
    options: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific activation options",
    )


class ModelActivationResult(BaseModel):
    """Result of an explicit model activation attempt."""

    is_successful: bool = Field(..., description="Whether model activation succeeded and committed")
    model_id: str = Field(..., description="Target model ID")
    generation: int = Field(
        default=0,
        ge=0,
        description="Active generation counter if successful",
    )
    active_session: Optional[ActiveModelSession] = Field(
        default=None,
        description="Active session snapshot if successful",
    )
    failure_reason: Optional[str] = Field(
        default=None,
        description="Typed failure reason if activation failed",
    )
    diagnostic_message: Optional[str] = Field(
        default=None,
        description="Human-readable diagnostic error message on failure",
    )
    duration_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Total elapsed activation time in milliseconds",
    )


class ModelSwitchPolicy(str, Enum):
    """Policy governing model switching rollback behavior."""

    SAFE_ROLLBACK = "SAFE_ROLLBACK"  # If target activation fails, previous active model remains intact
    FORCE = "FORCE"                  # Attempt switch regardless


class ModelSwitchResult(BaseModel):
    """Result of a transactional model switch operation."""

    is_successful: bool = Field(..., description="Whether switch succeeded and new model is active")
    previous_model_id: Optional[str] = Field(
        default=None,
        description="Model ID active before switch",
    )
    active_model_id: Optional[str] = Field(
        default=None,
        description="Model ID active after switch attempt",
    )
    generation: int = Field(
        default=0,
        ge=0,
        description="Active generation counter after switch attempt",
    )
    switched: bool = Field(
        default=False,
        description="True if active model identity changed successfully",
    )
    active_session: Optional[ActiveModelSession] = Field(
        default=None,
        description="Current active session",
    )
    failure_reason: Optional[str] = Field(
        default=None,
        description="Failure reason if switch failed",
    )
    diagnostic_message: Optional[str] = Field(
        default=None,
        description="Diagnostic message on failure",
    )
    duration_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Elapsed time in milliseconds",
    )

