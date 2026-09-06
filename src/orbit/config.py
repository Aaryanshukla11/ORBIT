"""Runtime configuration and adapter mode selection for ORBIT."""

from __future__ import annotations

import os
from typing import Dict, Optional
from pydantic import BaseModel, Field

from orbit.contracts.capabilities import AdapterMode, CapabilityType


class RuntimeConfig(BaseModel):
    """Configuration model for ORBIT runtime and capability subsystems."""

    adapter_mode: AdapterMode = Field(
        default=AdapterMode.PRODUCTION,
        description="Global adapter mode: MOCK or PRODUCTION",
    )
    capability_overrides: Dict[CapabilityType, AdapterMode] = Field(
        default_factory=dict,
        description="Per-capability adapter mode overrides",
    )
    host: str = Field(default="127.0.0.1", description="Gateway bind host")
    port: int = Field(default=8765, description="Gateway port")
    log_level: str = Field(default="info", description="Application log level")

    def get_mode_for(self, cap_type: CapabilityType) -> AdapterMode:
        """Resolve adapter mode for a specific capability type."""
        return self.capability_overrides.get(cap_type, self.adapter_mode)

    @classmethod
    def from_env(cls) -> RuntimeConfig:
        """Create configuration from environment variables."""
        mode_str = os.getenv("ORBIT_ADAPTER_MODE", "PRODUCTION").upper()
        mode = AdapterMode.PRODUCTION if mode_str == "PRODUCTION" else AdapterMode.MOCK
        host = os.getenv("ORBIT_HOST", "127.0.0.1")
        port = int(os.getenv("ORBIT_PORT", "8765"))
        log_level = os.getenv("ORBIT_LOG_LEVEL", "info")

        return cls(
            adapter_mode=mode,
            host=host,
            port=port,
            log_level=log_level,
        )
