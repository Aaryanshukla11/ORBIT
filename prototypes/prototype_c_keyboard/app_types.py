"""
Type definitions, enums, and data models for ORBIT Prototype C (Keyboard Interaction & Unicode Engine).
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any
import time


class KeyOwner(Enum):
    ORBIT_INJECTED_TRACKED = "ORBIT_INJECTED_TRACKED"  # Injected by ORBIT in active session
    USER_PHYSICAL_OBSERVED = "USER_PHYSICAL_OBSERVED"  # Physical input observed via hook/sensor
    UNKNOWN = "UNKNOWN"                                # Unproven or untracked state (NEVER RELEASE)


class KeyActionType(Enum):
    ASCII_TEXT = "ASCII_TEXT"
    UNICODE_TEXT = "UNICODE_TEXT"
    SHORTCUT = "SHORTCUT"
    SPECIAL_KEY = "SPECIAL_KEY"
    STREAMING_TEXT = "STREAMING_TEXT"


class ExecutionState(Enum):
    IDLE = "IDLE"
    TYPING = "TYPING"
    EXECUTING_SHORTCUT = "EXECUTING_SHORTCUT"
    CANCELLING = "CANCELLING"
    PAUSED_BY_USER = "PAUSED_BY_USER"
    SAFE_ABORT = "SAFE_ABORT"
    PARTIAL_INJECTION_UNCERTAIN = "PARTIAL_INJECTION_UNCERTAIN"
    SANITIZED = "SANITIZED"


class CancellationSource(Enum):
    HUMAN_TAKEOVER = "HUMAN_TAKEOVER"                 # External human takeover signal
    GLOBAL_EMERGENCY_STOP = "GLOBAL_EMERGENCY_STOP"   # Dedicated Win32 global hotkey (F12)
    GLOBAL_LOW_LEVEL_OBS = "GLOBAL_LOW_LEVEL_OBS"     # Contextual low-level hook observation (ESC)
    PROTOTYPE_LOCAL_UI = "PROTOTYPE_LOCAL_UI"         # UI-local button or testbed trigger
    FOCUS_LOSS = "FOCUS_LOSS"                         # Foreground focus shifted away from target
    TARGET_LOSS = "TARGET_LOSS"                       # Target window destroyed or closed
    INTERNAL_FAILURE = "INTERNAL_FAILURE"             # SendInput partial error or worker exception
    EXTERNAL_CONTROLLER = "EXTERNAL_CONTROLLER"       # High-level supervisor abort


class UnicodeMatchOutcome(Enum):
    EXACT_MATCH = "EXACT_MATCH"                               # Raw received codepoint sequence matches expected
    NORMALIZATION_EQUIVALENT = "NORMALIZATION_EQUIVALENT"     # Matches after canonical NFC normalization
    CHARACTER_CORRUPTION = "CHARACTER_CORRUPTION"             # Replacement character, dropped, or corrupted
    READBACK_UNAVAILABLE = "READBACK_UNAVAILABLE"             # Destination does not expose accessible readback


class ReadbackLevel(Enum):
    LEVEL_1_UI_AUTOMATION = "LEVEL_1_UI_AUTOMATION"           # Direct UI Automation value/text pattern
    LEVEL_2_CLIPBOARD = "LEVEL_2_CLIPBOARD"                   # Isolated select-all/copy with preservation
    LEVEL_3_NATIVE_MSG = "LEVEL_3_NATIVE_MSG"                 # WM_GETTEXT / standard Win32 edit buffer
    LEVEL_4_NOT_VALIDATED = "LEVEL_4_NOT_VALIDATED"           # No independent verification available


class ShortcutRiskLevel(Enum):
    ALLOWED = "ALLOWED"                                       # Standard safe editing shortcuts (Ctrl+C, Ctrl+V, etc.)
    RESTRICTED = "RESTRICTED"                                 # Destructive system shortcuts (Win+L, Alt+F4, etc.)
    MANUAL_CONTROLLED_ONLY = "MANUAL_CONTROLLED_ONLY"         # Context-disruptive shortcuts (Alt+Tab, Win+Tab)


class ValidationTier(Enum):
    TIER_1_WIDGET = "TIER_1_WIDGET"                           # Controlled local test widget (Tkinter)
    TIER_2_NATIVE_APP = "TIER_2_NATIVE_APP"                   # Real native Windows app (Notepad)
    TIER_3_BROWSER = "TIER_3_BROWSER"                         # Controlled local HTML test page in browser


@dataclass
class PressedKey:
    vk_code: int
    scan_code: int
    is_extended: bool
    is_unicode: bool
    owner: KeyOwner
    timestamp_ns: int
    session_id: str


@dataclass
class TargetContext:
    target_hwnd: int = 0
    process_id: int = 0
    process_name: str = ""
    window_title: str = ""
    is_valid: bool = False


@dataclass
class CancellationRequest:
    source: CancellationSource
    timestamp_ns: int
    reason: str
    session_id: str


@dataclass
class ShortcutSequence:
    modifiers: List[str]
    action_key: str
    repeat_count: int = 1


@dataclass
class StageLatencyRecord:
    t1_action_requested_ns: int = 0
    t2_worker_started_ns: int = 0
    t3_first_sendinput_ns: int = 0
    t4_cancel_requested_ns: int = 0
    t5_cancel_observed_ns: int = 0
    t6_final_key_released_ns: int = 0
    t7_worker_exited_ns: int = 0

    @property
    def signal_to_observation_us(self) -> float:
        if self.t4_cancel_requested_ns and self.t5_cancel_observed_ns:
            return max(0.0, (self.t5_cancel_observed_ns - self.t4_cancel_requested_ns) / 1000.0)
        return 0.0

    @property
    def sanitization_latency_us(self) -> float:
        if self.t5_cancel_observed_ns and self.t6_final_key_released_ns:
            return max(0.0, (self.t6_final_key_released_ns - self.t5_cancel_observed_ns) / 1000.0)
        return 0.0

    @property
    def worker_teardown_latency_us(self) -> float:
        if self.t6_final_key_released_ns and self.t7_worker_exited_ns:
            return max(0.0, (self.t7_worker_exited_ns - self.t6_final_key_released_ns) / 1000.0)
        return 0.0

    @property
    def true_cancellation_latency_us(self) -> float:
        if self.t4_cancel_requested_ns and self.t7_worker_exited_ns:
            return max(0.0, (self.t7_worker_exited_ns - self.t4_cancel_requested_ns) / 1000.0)
        return 0.0


@dataclass
class UnicodeValidationRecord:
    expected_text: str
    received_text: str
    expected_codepoints: List[int]
    received_codepoints: List[int]
    dispatched_utf16_units: List[str]
    outcome: UnicodeMatchOutcome
    exact_match: bool
    nfc_match: bool


@dataclass
class TelemetryRecord:
    session_id: str
    action_type: str
    state: str
    character_count: int
    duration_ms: float
    characters_per_second: float
    error_count: int
    cancellation_source: Optional[str] = None
    stage_latency: Optional[StageLatencyRecord] = None
    unicode_validation: Optional[UnicodeValidationRecord] = None
    in_flight_events_at_cancel: int = 0
    events_dispatched_after_cancel_observed: int = 0
    destination_events_after_cancel_request: int = 0
