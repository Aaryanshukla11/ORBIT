"""
Provenance & Architectural Attribution:
======================================
Windows-Use Source:   windows_use/agent/tree/service.py
ORBIT Destination:    src/orbit/runtime/perception/uia.py
Integration Paradigm: Transduced Perception Gateway (Brain-Body Separation)

Adaptations Applied:
- Removed legacy pywinauto fallback and external dependencies.
- Delegated 100% of UIA observation to authoritative UIAElementTreeExtractor.
- Retained fail-closed error handling and thread desktop attachment.
- Enforced strict invariant: Sensory element observation only, zero target selection.
======================================
"""

from __future__ import annotations

import logging
import sys
from typing import List, Optional, Tuple

from orbit.adapters.uia.tree_extractor import UIAElementTreeExtractor
from orbit.runtime.perception.models import UIElementObservation

logger = logging.getLogger(__name__)


class UIAElementObserver:
    """Authoritative UI Automation accessibility tree walker and element observer."""

    def __init__(self) -> None:
        self._is_win32 = sys.platform == "win32"
        self._tree_extractor = UIAElementTreeExtractor()

    def observe_elements(
        self,
        target_hwnd: Optional[int] = None,
        max_elements: int = 50,
    ) -> Tuple[Optional[UIElementObservation], List[UIElementObservation]]:
        """Interrogate UI Automation tree scoped to target HWND or foreground window."""
        if not self._is_win32:
            return None, []

        try:
            return self._tree_extractor.observe_elements(
                target_hwnd=target_hwnd,
                max_elements=max_elements,
            )
        except Exception as ex:
            logger.debug("Authoritative UIA tree observation notice: %s", ex)
            return None, []
