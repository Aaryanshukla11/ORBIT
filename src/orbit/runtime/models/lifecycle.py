"""Model Lifecycle Management and State Transition Validator (Milestone M1.9 Step 2).

Enforces strict lifecycle invariants:
- Prevents illegal direct state transitions (e.g. UNAVAILABLE -> ACTIVE).
- Records transition history and reasons for auditability.
- Provides atomic state mutation guards.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field

from orbit.runtime.models.models import ModelStatus

logger = logging.getLogger(__name__)


class InvalidStateTransitionError(Exception):
    """Raised when attempting an invalid or unauthorized model state transition."""

    def __init__(self, model_id: str, current_state: ModelStatus, requested_state: ModelStatus, reason: str = "") -> None:
        self.model_id = model_id
        self.current_state = current_state
        self.requested_state = requested_state
        msg = f"Illegal state transition for model '{model_id}': cannot transition from {current_state.value} to {requested_state.value}."
        if reason:
            msg += f" Reason: {reason}"
        super().__init__(msg)


class ModelLifecycleTransition(BaseModel):
    """Audit record of a validated model lifecycle status transition."""

    model_id: str
    from_status: Optional[ModelStatus] = None
    to_status: ModelStatus
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: Optional[str] = None


class ModelLifecycleManager:
    """Manages and validates operational state transitions for AI models."""

    # Explicit whitelist of permitted state transitions
    VALID_TRANSITIONS: Dict[ModelStatus, Set[ModelStatus]] = {
        ModelStatus.DISCOVERED: {
            ModelStatus.DISCOVERED,  # Idempotent
            ModelStatus.INSTALLING,
            ModelStatus.INSTALLED,
            ModelStatus.LOADING,
            ModelStatus.READY,
            ModelStatus.AVAILABLE,
            ModelStatus.UNAVAILABLE,
            ModelStatus.UNREACHABLE,
            ModelStatus.INCOMPATIBLE,
            ModelStatus.FAILED,
            ModelStatus.OFFLINE,
        },
        ModelStatus.INSTALLING: {
            ModelStatus.INSTALLING,  # Idempotent
            ModelStatus.INSTALLED,
            ModelStatus.FAILED,
            ModelStatus.DISCOVERED,
            ModelStatus.UNAVAILABLE,
        },
        ModelStatus.INSTALLED: {
            ModelStatus.INSTALLED,   # Idempotent
            ModelStatus.LOADING,
            ModelStatus.READY,
            ModelStatus.AVAILABLE,
            ModelStatus.UNAVAILABLE,
            ModelStatus.INCOMPATIBLE,
            ModelStatus.FAILED,
        },
        ModelStatus.LOADING: {
            ModelStatus.LOADING,     # Idempotent
            ModelStatus.LOADED,
            ModelStatus.ACTIVE,
            ModelStatus.READY,
            ModelStatus.AVAILABLE,
            ModelStatus.FAILED,
            ModelStatus.UNAVAILABLE,
        },
        ModelStatus.READY: {
            ModelStatus.READY,       # Idempotent
            ModelStatus.AVAILABLE,
            ModelStatus.LOADING,
            ModelStatus.LOADED,
            ModelStatus.ACTIVE,
            ModelStatus.UNAVAILABLE,
            ModelStatus.UNREACHABLE,
            ModelStatus.OFFLINE,
            ModelStatus.FAILED,
        },
        ModelStatus.AVAILABLE: {
            ModelStatus.AVAILABLE,   # Idempotent
            ModelStatus.READY,
            ModelStatus.LOADING,
            ModelStatus.LOADED,
            ModelStatus.ACTIVE,
            ModelStatus.UNAVAILABLE,
            ModelStatus.UNREACHABLE,
            ModelStatus.OFFLINE,
            ModelStatus.FAILED,
        },
        ModelStatus.ACTIVE: {
            ModelStatus.ACTIVE,      # Idempotent
            ModelStatus.LOADED,
            ModelStatus.READY,
            ModelStatus.AVAILABLE,
            ModelStatus.UNAVAILABLE,
            ModelStatus.UNREACHABLE,
            ModelStatus.OFFLINE,
            ModelStatus.FAILED,
        },
        ModelStatus.LOADED: {
            ModelStatus.LOADED,      # Idempotent
            ModelStatus.ACTIVE,
            ModelStatus.READY,
            ModelStatus.AVAILABLE,
            ModelStatus.UNAVAILABLE,
            ModelStatus.UNREACHABLE,
            ModelStatus.OFFLINE,
            ModelStatus.FAILED,
        },
        ModelStatus.UNAVAILABLE: {
            ModelStatus.UNAVAILABLE, # Idempotent
            ModelStatus.DISCOVERED,
            ModelStatus.INSTALLING,
            ModelStatus.LOADING,
            ModelStatus.READY,
            ModelStatus.AVAILABLE,
            ModelStatus.OFFLINE,
            ModelStatus.UNREACHABLE,
            ModelStatus.FAILED,
            # Note: UNAVAILABLE -> ACTIVE is strictly prohibited!
        },
        ModelStatus.UNREACHABLE: {
            ModelStatus.UNREACHABLE, # Idempotent
            ModelStatus.DISCOVERED,
            ModelStatus.UNAVAILABLE,
            ModelStatus.READY,
            ModelStatus.AVAILABLE,
            ModelStatus.OFFLINE,
            ModelStatus.FAILED,
        },
        ModelStatus.INCOMPATIBLE: {
            ModelStatus.INCOMPATIBLE,# Idempotent
            ModelStatus.DISCOVERED,
            ModelStatus.FAILED,
            ModelStatus.UNAVAILABLE,
        },
        ModelStatus.FAILED: {
            ModelStatus.FAILED,      # Idempotent
            ModelStatus.DISCOVERED,
            ModelStatus.INSTALLING,
            ModelStatus.LOADING,
            ModelStatus.UNAVAILABLE,
            ModelStatus.READY,
            ModelStatus.AVAILABLE,
        },
        ModelStatus.OFFLINE: {
            ModelStatus.OFFLINE,     # Idempotent
            ModelStatus.DISCOVERED,
            ModelStatus.UNAVAILABLE,
            ModelStatus.UNREACHABLE,
            ModelStatus.READY,
            ModelStatus.AVAILABLE,
            ModelStatus.FAILED,
        },
        ModelStatus.UNKNOWN: {
            ModelStatus.UNKNOWN,     # Idempotent
            ModelStatus.DISCOVERED,
            ModelStatus.UNAVAILABLE,
            ModelStatus.READY,
            ModelStatus.AVAILABLE,
            ModelStatus.FAILED,
        },
    }

    def __init__(self) -> None:
        self._history: List[ModelLifecycleTransition] = []
        self._current_statuses: Dict[str, ModelStatus] = {}

    def get_current_status(self, model_id: str) -> Optional[ModelStatus]:
        """Return current status of model or None if untracked."""
        return self._current_statuses.get(model_id)

    def can_transition(self, from_status: ModelStatus, to_status: ModelStatus) -> bool:
        """Check whether a transition between two statuses is permissible."""
        allowed = self.VALID_TRANSITIONS.get(from_status, set())
        return to_status in allowed

    def record_transition(
        self,
        model_id: str,
        to_status: ModelStatus,
        reason: Optional[str] = None,
    ) -> ModelLifecycleTransition:
        """Record status transition without validation check (used during initial discovery)."""
        from_status = self._current_statuses.get(model_id)
        transition = ModelLifecycleTransition(
            model_id=model_id,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
        )
        self._current_statuses[model_id] = to_status
        self._history.append(transition)
        return transition

    def transition(
        self,
        model_id: str,
        target_status: ModelStatus,
        reason: Optional[str] = None,
    ) -> ModelLifecycleTransition:
        """Validate and commit a model state transition, raising InvalidStateTransitionError if illegal."""
        current_status = self._current_statuses.get(model_id, ModelStatus.DISCOVERED)
        if not self.can_transition(current_status, target_status):
            msg = f"Direct transition from {current_status.value} to {target_status.value} violates lifecycle contract."
            logger.warning("Rejected invalid lifecycle transition for %s: %s -> %s (%s)", model_id, current_status.value, target_status.value, reason)
            raise InvalidStateTransitionError(
                model_id=model_id,
                current_state=current_status,
                requested_state=target_status,
                reason=msg,
            )
        return self.record_transition(model_id, target_status, reason=reason)

    def validate_transition(
        self,
        model_id: str,
        current_status: ModelStatus,
        target_status: ModelStatus,
        reason: Optional[str] = None,
    ) -> ModelLifecycleTransition:
        """Validate and record a model state transition from explicit current_status."""
        if not self.can_transition(current_status, target_status):
            msg = f"Direct transition from {current_status.value} to {target_status.value} violates lifecycle contract."
            logger.warning("Rejected invalid lifecycle transition for %s: %s -> %s (%s)", model_id, current_status.value, target_status.value, reason)
            raise InvalidStateTransitionError(
                model_id=model_id,
                current_state=current_status,
                requested_state=target_status,
                reason=msg,
            )
        return self.record_transition(model_id, target_status, reason=reason)

    def get_history(self, model_id: Optional[str] = None) -> List[ModelLifecycleTransition]:
        """Retrieve full transition history or filter by model_id."""
        if model_id is None:
            return list(self._history)
        return [t for t in self._history if t.model_id == model_id]
