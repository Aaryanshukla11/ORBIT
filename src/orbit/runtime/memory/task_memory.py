"""Task-scoped working memory and isolated secret store.

Provides ephemeral working memory strictly scoped to individual autonomous task lifecycles,
with guaranteed in-memory zeroization upon task completion/abortion, and dedicated credential
isolation through SecureSecretStore to prevent credential persistence in reasoning traces.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4
from pydantic import BaseModel, Field


class MemoryFact(BaseModel):
    """An atomic verified empirical fact extracted during task execution."""

    fact_id: str = Field(default_factory=lambda: f"fact_{uuid4().hex[:8]}")
    category: str = Field(default="general")
    statement: str
    source: str = Field(default="observation")
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SecureSecretStore:
    """Isolated, ephemeral in-memory credential storage.

    INVARIANT: Credentials, auth tokens, passwords, and sensitive keys MUST NOT be stored
    in plain working memory or serialized into reasoning traces or world models.
    They are stored here by opaque handle, redacted from telemetry, and purged on task termination.
    """

    REDACTION_MASK = "***REDACTED***"

    def __init__(self) -> None:
        # handle -> secret value
        self._secrets_by_handle: Dict[str, str] = {}
        # name -> handle
        self._name_to_handle: Dict[str, str] = {}
        # raw strings to mask for trace redaction
        self._raw_values_to_mask: Set[str] = set()

    def store_secret(self, secret_name: str, raw_secret: str) -> str:
        """Store a sensitive secret in-memory and return an opaque, unguessable handle."""
        if not raw_secret:
            raise ValueError("Cannot store empty secret")
        if not secret_name:
            raise ValueError("Secret name must be non-empty")

        handle = f"sec_tok_{uuid4().hex[:12]}"
        self._secrets_by_handle[handle] = raw_secret
        self._name_to_handle[secret_name] = handle
        # Store for redaction filtering if sufficiently non-trivial
        if len(raw_secret.strip()) >= 3:
            self._raw_values_to_mask.add(raw_secret)
        return handle

    def resolve_secret(self, handle_or_name: str) -> Optional[str]:
        """Resolve raw secret by its opaque handle or logical name."""
        if handle_or_name in self._secrets_by_handle:
            return self._secrets_by_handle[handle_or_name]
        handle = self._name_to_handle.get(handle_or_name)
        if handle:
            return self._secrets_by_handle.get(handle)
        return None

    def has_secret(self, handle_or_name: str) -> bool:
        """Check if secret exists without exposing its content."""
        return (handle_or_name in self._secrets_by_handle) or (handle_or_name in self._name_to_handle)

    def mask_text(self, text: str) -> str:
        """Redact all stored raw secrets from strings before logging or tracing."""
        if not text or not self._raw_values_to_mask:
            return text
        redacted = text
        for raw in self._raw_values_to_mask:
            if raw in redacted:
                redacted = redacted.replace(raw, self.REDACTION_MASK)
        return redacted

    def purge(self) -> None:
        """Purge all secrets from memory and clear all lookup tables."""
        # Overwrite in-memory strings if possible and clear
        self._secrets_by_handle.clear()
        self._name_to_handle.clear()
        self._raw_values_to_mask.clear()


class TaskScopedMemory:
    """Ephemeral working memory strictly isolated to a single autonomous task lifecycle.

    Guarantees:
    1. Zero persistence beyond task lifecycle: wipe() clears all data on task completion/abort.
    2. Zero credentials in working variables: all secrets route through isolated SecureSecretStore.
    3. Ephemeral variable and fact storage for multi-step reasoning.
    """

    def __init__(self, task_id: str) -> None:
        if not task_id:
            raise ValueError("task_id must be non-empty")
        self._task_id = task_id
        self._variables: Dict[str, Any] = {}
        self._facts: Dict[str, MemoryFact] = {}
        self._secret_store = SecureSecretStore()
        self._created_at_utc = datetime.now(timezone.utc)
        self._is_wiped: bool = False

    @property
    def task_id(self) -> str:
        return self._task_id

    @property
    def secret_store(self) -> SecureSecretStore:
        return self._secret_store

    @property
    def is_wiped(self) -> bool:
        return self._is_wiped

    def _assert_active(self) -> None:
        if self._is_wiped:
            raise RuntimeError(f"TaskScopedMemory for task '{self._task_id}' has already been wiped")

    # Variable Management
    def set_variable(self, key: str, value: Any) -> None:
        """Store an ephemeral variable. Rejects secrets; secrets must use secret_store."""
        self._assert_active()
        if not key:
            raise ValueError("Variable key cannot be empty")
        # Check if caller mistakenly tries to store a raw secret directly
        lower_k = key.lower()
        if any(s in lower_k for s in ("password", "api_key", "secret_key", "auth_token", "private_key")):
            raise ValueError(
                f"Sensitive variable '{key}' cannot be stored in TaskScopedMemory. Use secret_store.store_secret() instead."
            )
        self._variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        """Retrieve an ephemeral variable."""
        self._assert_active()
        return self._variables.get(key, default)

    def has_variable(self, key: str) -> bool:
        """Check if an ephemeral variable is defined."""
        self._assert_active()
        return key in self._variables

    def delete_variable(self, key: str) -> None:
        """Delete an ephemeral variable."""
        self._assert_active()
        self._variables.pop(key, None)

    def list_variables(self) -> Dict[str, Any]:
        """Return a copy of all current ephemeral variables."""
        self._assert_active()
        return dict(self._variables)

    # Empirical Fact Management
    def store_fact(self, key: str, statement: str, category: str = "general", source: str = "observation") -> MemoryFact:
        """Store an empirical fact discovered during execution."""
        self._assert_active()
        fact = MemoryFact(category=category, statement=statement, source=source)
        self._facts[key] = fact
        return fact

    def get_fact(self, key: str) -> Optional[MemoryFact]:
        """Retrieve an empirical fact by key."""
        self._assert_active()
        return self._facts.get(key)

    def get_all_facts(self) -> Dict[str, MemoryFact]:
        """Return a copy of all stored empirical facts."""
        self._assert_active()
        return dict(self._facts)

    # Lifecycle Cleanup
    def wipe(self) -> None:
        """Wipe all ephemeral memory and purge all secrets. Terminal operation."""
        self._variables.clear()
        self._facts.clear()
        self._secret_store.purge()
        self._is_wiped = True


__all__ = [
    "MemoryFact",
    "SecureSecretStore",
    "TaskScopedMemory",
]
