"""Unified Layered WorldState Architecture (Phase 2D).

Defines the 4-tier perception and world model pipeline:
Tier 1: Raw Evidence (Screenshot buffer, raw UIA hierarchy, OCR stream, Win32 table)
Tier 2: Perception & Fusion Engine (Spatial clustering, coordinate mapping, settle status)
Tier 3: Canonical WorldState Snapshot (Active application, visible controls, modal state, observation ID)
Tier 4: Compact Model Context (Token-efficient representation for fast LLM inference)

INVARIANT: WorldState is perception/grounding only; never a secondary decision brain.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.perception.settle import SettleResult


class RawEvidenceLayer(BaseModel):
    """Tier 1: Raw sensory evidence captured directly from OS adapters."""

    observation_id: str = Field(default_factory=lambda: f"obs_{uuid4().hex[:8]}")
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    screen_width: int = 1920
    screen_height: int = 1080
    raw_screenshot_shape: Tuple[int, int, int] = (1080, 1920, 3)
    dpi_scale: float = 1.0
    active_hwnd: Optional[int] = None
    active_window_hwnd: Optional[int] = None
    raw_window_list: List[Dict[str, Any]] = Field(default_factory=list)
    raw_uia_tree: List[Any] = Field(default_factory=list)
    raw_ocr_tokens: List[Any] = Field(default_factory=list)
    raw_uia_count: int = 0
    raw_ocr_count: int = 0
    raw_screenshot_bytes_len: int = 0





class PerceivedControl(BaseModel):
    """A fused, localized UI element with bounding box and multimodal evidence."""

    control_id: str = Field(default_factory=lambda: f"ctl_{uuid4().hex[:8]}")
    name: str = ""
    role: str = ""
    automation_id: Optional[str] = None
    bounds: List[int] = Field(default_factory=list, description="[ymin, xmin, ymax, xmax] 0-1000 normalized")
    pixel_bounds: Optional[Tuple[int, int, int, int]] = None
    is_interactive: bool = True
    ocr_text: Optional[str] = None
    evidence_source: str = "UIA"
    confidence: float = 1.0


class PerceptionFusionLayer(BaseModel):
    """Tier 2: Fused perceptual layer combining UIA, OCR, and Visual signals."""

    settle_result: Optional[SettleResult] = None
    fused_controls: List[PerceivedControl] = Field(default_factory=list)
    detected_modals: List[Dict[str, Any]] = Field(default_factory=list)
    text_clusters_count: int = 0
    visual_icons_count: int = 0

    @property
    def detected_ui_nodes(self) -> List[PerceivedControl]:
        return self.fused_controls

    @property
    def ocr_spatial_clusters(self) -> List[PerceivedControl]:
        return [c for c in self.fused_controls if c.evidence_source == "OCR" or c.ocr_text]



CanonicalUIElement = PerceivedControl


class CanonicalWorldState(BaseModel):
    """Tier 3: Canonical, consistent state of the desktop environment."""

    observation_id: str
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    active_process_name: str = ""
    active_window_title: str = ""
    active_window_hwnd: Optional[int] = None
    active_window_bounds: Optional[List[int]] = None
    visible_windows: List[Dict[str, Any]] = Field(default_factory=list)
    interactive_elements: List[PerceivedControl] = Field(default_factory=list)
    active_modal: Optional[Dict[str, Any]] = None
    canvas_status: str = "UNKNOWN"
    filesystem_snapshot: Dict[str, Any] = Field(default_factory=dict)
    generation_id: int = 0


class CompactContext(BaseModel):
    """Tier 4: Compact, token-efficient serialization for LLM prompt context."""

    observation_id: str
    active_app_summary: str = ""
    foreground_window_title: str = ""
    active_process_name: str = ""
    screen_resolution: str = "1920x1080"
    app_context: str = "Desktop"
    interactive_summary: List[Dict[str, Any]] = Field(default_factory=list)
    visible_controls_text: str = ""
    active_modal_warning: Optional[str] = None
    estimated_tokens: int = 0


class UnifiedWorldState(BaseModel):
    """Encapsulates all 4 tiers of the WorldState architecture."""

    raw_evidence: RawEvidenceLayer
    perception_fusion: PerceptionFusionLayer
    canonical_state: CanonicalWorldState
    compact_context: CompactContext

    @property
    def observation_id(self) -> str:
        return self.canonical_state.observation_id

    @property
    def timestamp(self) -> float:
        return self.canonical_state.timestamp_utc.timestamp()

    @property
    def is_fresh(self) -> bool:
        """Check whether observation timestamp is within acceptable freshness window (<5.0s)."""
        age = (datetime.now(timezone.utc) - self.canonical_state.timestamp_utc).total_seconds()
        return age < 5.0


class WorldStateBuilder:
    """Constructs UnifiedWorldState from live desktop perception and adapter outputs."""

    @staticmethod
    def build_world_state(
        observation: Any = None,
        settle_result: Optional[SettleResult] = None,
        max_compact_controls: int = 30,
        observation_id: Optional[str] = None,
        screenshot: Optional[Any] = None,
        uia_elements: Optional[List[Any]] = None,
        ocr_tokens: Optional[List[Any]] = None,
        active_window_title: Optional[str] = None,
        active_process_name: Optional[str] = None,
        active_hwnd: Optional[int] = None,
        visible_windows: Optional[List[Any]] = None,
    ) -> UnifiedWorldState:
        """Transform raw observation or explicit parameters into layered UnifiedWorldState."""
        obs_id = (
            observation_id
            or getattr(observation, "observation_id", None)
            or f"obs_{uuid4().hex[:8]}"
        )
        now = datetime.now(timezone.utc)

        # 1. Tier 1: Raw Evidence Extraction
        d_obs = getattr(observation, "desktop_observation", None) if observation else None
        
        act_title = active_window_title or (getattr(observation, "active_window_title", "") if observation else "")
        act_proc = active_process_name or (getattr(observation, "active_process_name", "") if observation else "")
        act_hwnd = active_hwnd if active_hwnd is not None else (getattr(observation, "active_window_hwnd", None) if observation else None)
        vis_windows = visible_windows if visible_windows is not None else (getattr(observation, "visible_windows", []) if observation else [])
        
        raw_uia = uia_elements if uia_elements is not None else ((getattr(d_obs, "uia_elements", []) or []) if d_obs else [])
        raw_ocr = ocr_tokens if ocr_tokens is not None else (getattr(observation, "ocr_tokens", []) if observation else [])
        sc_obj = screenshot if screenshot is not None else (getattr(observation, "screenshot", None) if observation else None)

        sc_shape = (1080, 1920, 3)
        if sc_obj is not None:
            if hasattr(sc_obj, "size"):
                sc_shape = (sc_obj.size[1], sc_obj.size[0], 3)
            elif hasattr(sc_obj, "shape"):
                sc_shape = tuple(sc_obj.shape)

        raw_layer = RawEvidenceLayer(
            observation_id=obs_id,
            timestamp_utc=now,
            screen_width=sc_shape[1],
            screen_height=sc_shape[0],
            raw_screenshot_shape=sc_shape,
            active_hwnd=act_hwnd,
            active_window_hwnd=act_hwnd,
            raw_window_list=vis_windows if isinstance(vis_windows, list) else [],
            raw_uia_tree=raw_uia,
            raw_ocr_tokens=raw_ocr,
            raw_uia_count=len(raw_uia),
            raw_ocr_count=len(raw_ocr),
        )

        # 2. Tier 2: Perception & Fusion
        fused_controls: List[PerceivedControl] = []
        
        # Combine UIA elements
        all_raw_elements = list(raw_uia)
        if d_obs and getattr(d_obs, "perceived_elements", None):
            all_raw_elements.extend(d_obs.perceived_elements)
        elif observation and hasattr(observation, "perceived_elements"):
            all_raw_elements.extend(getattr(observation, "perceived_elements", []))

        for el in all_raw_elements:
            if isinstance(el, dict):
                name = el.get("name", "")
                role = el.get("role", el.get("control_type", ""))
                bounds = el.get("bounds", [0, 0, 0, 0])
                conf = el.get("confidence", 1.0)
                src = el.get("source", "UIA")
                ocr_t = el.get("ocr_text", None)
            else:
                name = getattr(el, "name", "") or ""
                role = getattr(el, "role", getattr(el, "control_type", "")) or ""
                bounds = getattr(el, "bounds", getattr(el, "bounding_box", None))
                conf = getattr(el, "confidence", 1.0)
                src = getattr(el, "source", "UIA")
                ocr_t = getattr(el, "ocr_text", None)

            norm_bounds = [0, 0, 0, 0]
            if bounds and isinstance(bounds, (list, tuple)) and len(bounds) == 4:
                norm_bounds = [int(b) for b in bounds]
            elif hasattr(bounds, "top"):
                norm_bounds = [int(bounds.top), int(bounds.left), int(bounds.top + bounds.height), int(bounds.left + bounds.width)]

            if name or role or ocr_t:
                fused_controls.append(
                    PerceivedControl(
                        name=str(name),
                        role=str(role),
                        bounds=norm_bounds,
                        confidence=float(conf or 1.0),
                        evidence_source=str(src),
                        ocr_text=ocr_t,
                    )
                )

        # Merge OCR tokens into fused controls if not already represented
        for tok in raw_ocr:
            tok_txt = tok.get("text", "") if isinstance(tok, dict) else getattr(tok, "text", "")
            tok_bounds = tok.get("bounds", [0, 0, 0, 0]) if isinstance(tok, dict) else getattr(tok, "bounds", [0, 0, 0, 0])
            tok_conf = tok.get("confidence", 0.85) if isinstance(tok, dict) else getattr(tok, "confidence", 0.85)
            if tok_txt:
                fused_controls.append(
                    PerceivedControl(
                        name=tok_txt,
                        role="text",
                        bounds=list(tok_bounds) if isinstance(tok_bounds, (list, tuple)) else [0, 0, 0, 0],
                        confidence=float(tok_conf or 0.85),
                        evidence_source="OCR",
                        ocr_text=tok_txt,
                    )
                )

        # Detect active modals
        modals = []
        for w in vis_windows:
            title = (w.get("title", "") if isinstance(w, dict) else getattr(w, "title", str(w))) or ""
            if any(kw in title.lower() for kw in ("save as", "confirm", "dialog", "warning", "error", "unsaved", "replace")):
                modals.append(w if isinstance(w, dict) else {"title": title})

        fusion_layer = PerceptionFusionLayer(
            settle_result=settle_result,
            fused_controls=fused_controls,
            detected_modals=modals,
            text_clusters_count=len(raw_ocr),
        )

        # 3. Tier 3: Canonical State
        canonical_state = CanonicalWorldState(
            observation_id=obs_id,
            timestamp_utc=now,
            active_process_name=act_proc,
            active_window_title=act_title,
            active_window_hwnd=act_hwnd,
            visible_windows=vis_windows if isinstance(vis_windows, list) else [],
            interactive_elements=fused_controls,
            active_modal=modals[0] if modals else None,
            canvas_status=getattr(observation, "canvas_status", "UNKNOWN") if observation else "UNKNOWN",
        )

        # 4. Tier 4: Compact Context for Model Prompting
        control_lines = []
        interactive_sum = []
        for c in fused_controls[:max_compact_controls]:
            control_lines.append(f"- [{c.role}] \"{c.name}\" at {c.bounds}")
            interactive_sum.append({
                "name": c.name,
                "role": c.role,
                "bounds": c.bounds,
                "source": c.evidence_source,
            })
        ctrl_text = "\n".join(control_lines) if control_lines else "None detected"

        modal_warning = f"MODAL ACTIVE: \"{modals[0].get('title', '')}\"" if modals else None
        app_sum = f"Window: \"{act_title}\" | Process: {act_proc} (HWND: {act_hwnd})"

        # App context deduction for prompting
        app_context = "Desktop"
        if "paint" in act_proc.lower() or "paint" in act_title.lower():
            app_context = "Paint"
        elif "notepad" in act_proc.lower() or "notepad" in act_title.lower():
            app_context = "Notepad"
        elif "edge" in act_proc.lower() or "chrome" in act_proc.lower():
            app_context = "Browser"

        compact = CompactContext(
            observation_id=obs_id,
            active_app_summary=app_sum,
            foreground_window_title=act_title,
            active_process_name=act_proc,
            screen_resolution=f"{sc_shape[1]}x{sc_shape[0]}",
            app_context=app_context,
            interactive_summary=interactive_sum,
            visible_controls_text=ctrl_text,
            active_modal_warning=modal_warning,
            estimated_tokens=len(app_sum) // 4 + len(ctrl_text) // 4,
        )

        return UnifiedWorldState(
            raw_evidence=raw_layer,
            perception_fusion=fusion_layer,
            canonical_state=canonical_state,
            compact_context=compact,
        )

