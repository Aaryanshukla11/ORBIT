# ORBIT — MILESTONE M1.7 STEP 3 FORENSIC ARCHITECTURE AUDIT
# MULTI-MODAL PERCEPTION FUSION & CONFIDENCE GROUNDING

**Document Version:** 1.0.0  
**Date:** September 6, 2026  
**Audited Baseline:** M1.5 + M1.6 + M1.7 Step 1 (OCR) + M1.7 Step 2 (Visual Matching) — 463 / 463 Tests Passing  
**Epistemic Standard:** Strict Deterministic Fusion, No Synthetic Hallucination, Zero-Dispatch Fail-Closed Guarantee  

---

## 1. Executive Summary & Problem Formulation

ORBIT currently provides four distinct, verified perception channels:
1. **Accessibility / UI Automation (UIA & MSAA):** Discovers named controls, roles, automation IDs, and accessibility bounding boxes from the OS element tree.
2. **Win32 Window Subsystem:** Enumerate visible top-level windows, HWND handles, window titles, and extended frame bounds.
3. **Windows Native OCR (`Windows.Media.Ocr.OcrEngine`):** Extracts textual words, normalized phrases, line regions, and pixel bounding boxes from on-screen image captures.
4. **Visual Template Grounding (2D FFT NCC):** Matches non-textual graphical UI elements, application icons, and toolbar buttons against reference templates with exact mathematical correlation surfaces.

### Current Architectural Limitation
Prior to Step 3, `EvidenceBasedTargetLocator` operates in isolated silos:
- If `TargetStrategy.ACCESSIBILITY_ELEMENT` is selected, the locator queries only `snapshot.detected_elements`. If accessibility is disabled or missing labels (e.g. Electron/Flutter canvas), resolution fails.
- If `TargetStrategy.OCR_TEXT` is selected, the locator queries only OCR bounding boxes. If duplicate text labels exist (e.g. three "Cancel" buttons on a multi-pane dialog), resolution returns `AMBIGUOUS`.
- If `TargetStrategy.VISUAL_TEMPLATE` is selected, the locator queries only template cross-correlation peaks. If duplicate icons exist (e.g. multiple "Settings" gear icons), resolution returns `AMBIGUOUS`.

There is no formal layer that evaluates **cross-channel spatial, semantic, and temporal agreement** to resolve ambiguous single-channel queries, corroborate confidence, or detect dangerous contradictions between perception channels.

---

## 2. Multi-Modal Evidence Channels & Coordinate Models

Every perception channel in ORBIT produces candidate evidence that can be projected into canonical **Virtual Desktop Coordinate Space**:

| Channel | Coordinate Space at Source | Transformation Path to Virtual Desktop | Confidence Metric | Failure Modes |
| :--- | :--- | :--- | :--- | :--- |
| **Accessibility (UIA/MSAA)** | Virtual Desktop Physical Pixels | Identity (Native OS screen coords) | Discrete (0.90 - 1.0) | Stale element tree, invisible elements, zero dimensions |
| **Win32 Windows** | Virtual Desktop Physical Pixels | Identity (Native OS window rect) | Discrete (1.0) | HWND recycling, minimized/obscured windows |
| **OCR Text** | Screenshot Pixel Space $(0,0)$ | `OCRCoordinateMapper.map_to_virtual_desktop` | Recognition score $[0.0, 1.0]$ | Sub-pixel blur, font rendering artifacts, duplicate text |
| **Visual Template** | Screenshot Pixel Space $(0,0)$ | `OCRCoordinateMapper.map_to_virtual_desktop` | Cross-correlation $[0.0, 1.0]$ | Repetitive icons, scaling mismatch, solid color regions |

---

## 3. Core Principles of Fail-Closed Multi-Modal Fusion

### Principle 1: Non-Inflationary Confidence Grounding
Combining multiple weak evidence sources must **NEVER** artificially boost confidence above individual verified bounds:
$$\text{FusedConfidence} \le \min\left(1.0, \max_{c \in \text{Sources}}(\text{Confidence}_c) \times \text{AgreementFactor}\right)$$
If evidence channel A has confidence $0.60$ and evidence channel B has confidence $0.55$, their fused result cannot be promoted to $0.95$. Weak evidence compounded remains weak.

### Principle 2: Spatial Agreement & Contradiction Detection
When two channels claim to identify the same target intent (e.g. UIA control named "Save" and OCR text "Save"):
- **Spatial Alignment:** If bounding box centroids are within `spatial_tolerance_px` (e.g. $\le 50\text{px}$) or have significant Intersection-over-Union ($\text{IoU} \ge 0.3$), they are marked **CORROBORATED**.
- **Spatial Contradiction:** If two primary channels claim to identify the same unique target but their centroids diverge by $> \text{contradiction_threshold_px}$ (e.g. $> 150\text{px}$), the fusion engine flags the state as **CONTRADICTORY** and fails closed with **ZERO pointer actions**.

### Principle 3: Semantic Consistency
When multimodal intent specifies both a textual query and a visual/accessible anchor, semantic agreement is evaluated:
- Normalized string matching between OCR text, accessible name, and template identifier.
- Disambiguation: When visual matching finds multiple identical icon candidates, the candidate spatially closest to the confirmed semantic text label is disambiguated deterministically.
- If multiple icon candidates are equidistant to the anchor text label ($|\Delta d| < \text{ambiguity\_margin}$), the result fails closed as **AMBIGUOUS**.

### Principle 4: Temporal & Generation Parity
All evidence items participating in a fusion decision must satisfy:
1. `desktop_generation_id` of every evidence source must strictly match `snapshot.generation_id`.
2. Snapshot `is_stale == False` and `freshness_state == FreshnessState.FRESH`.
3. If any participating channel possesses stale telemetry or mismatched generation ID, fusion triggers `STALE_OBSERVATION` with **ZERO pointer events**.

---

## 4. Multi-Modal Target Strategy & Fusion Architecture

### TargetStrategy Expansion
- Add `TargetStrategy.MULTIMODAL` to `TargetStrategy` enum.
- Add `TargetResolutionStatus.CONTRADICTORY` and `TargetResolutionStatus.LOW_CONFIDENCE` to `TargetResolutionStatus` enum.

### Pipeline Flow
```
[ ObservationSnapshot ]
    │
    ├─► Accessibility Extractor ──► [ PerceptionEvidence (UIA / MSAA) ]
    ├─► Window Extractor         ──► [ PerceptionEvidence (WIN32_WINDOW) ]
    ├─► OCR Engine               ──► [ PerceptionEvidence (OCR_TEXT) ]
    └─► Visual Engine            ──► [ PerceptionEvidence (VISUAL_TEMPLATE) ]
                                            │
                                            ▼
                        [ MultiModalPerceptionFusionEngine ]
                                            │
                        ├── Generation Parity Verification
                        ├── Spatial Agreement (IoU & Centroid Proximity)
                        ├── Semantic Consistency Evaluation
                        ├── Contradiction & Ambiguity Gating
                        └── Non-Inflationary Confidence Calibration
                                            │
                                            ▼
                               [ MultiModalFusionResult ]
                        (RESOLVED | AMBIGUOUS | CONTRADICTORY |
                         NOT_FOUND | STALE_OBSERVATION | LOW_CONFIDENCE)
                                            │
                                            ▼
                            [ SafeActionPoint Calculation ]
                                            │
                                            ▼
                            [ Workspace Validation Gate ]
                                            │
                                            ▼
                            [ AutonomousDispatchGate ]
                                            │
                                            ▼
                                  [ OS Action Execution ]
```

---

## 5. Risk Analysis & Mitigation Matrix

| Risk | Impact | Architectural Mitigation |
| :--- | :--- | :--- |
| **Phantom Consensus** | Two weak/spurious detections agree coincidentally | Minimum threshold per individual channel ($c \ge 0.70$) before participating in fusion. |
| **Coordinate Divergence** | UIA bounding box differs from rendered visual pixels | Contradiction gate: if spatial delta $> 150\text{px}$, fail closed with `CONTRADICTORY`. |
| **Generation Desync** | Visual evidence from generation $N$ fused with UIA from $N+1$ | Strict generation parity check across all evidence items; fail closed with `STALE_OBSERVATION`. |
| **Duplicate Disambiguation Failure** | Multiple identical icons near multiple identical text labels | Ambiguity margin check on spatial distances; if equidistant, return `AMBIGUOUS`. |
| **Coordinate Fabrication** | Fallback guessing when channels disagree | Zero guessing; fail closed with `NOT_FOUND` or `CONTRADICTORY`. |

---

## 6. Implementation Plan for Step 3

1. **`src/orbit/runtime/perception/fusion_models.py`:**
   - Define `EvidenceChannel`, `PerceptionEvidence`, `SpatialAgreement`, `SemanticAgreement`, `FusedEvidence`, `FusedTargetMatch`, `FusionPolicy`, `FusionStatus`, `MultiModalFusionResult`.
2. **`src/orbit/runtime/perception/fusion_engine.py`:**
   - Implement `MultiModalPerceptionFusionEngine` with deterministic spatial clustering, IoU/proximity evaluation, semantic matching, contradiction detection, and non-inflating confidence aggregation.
3. **`src/orbit/runtime/targeting/models.py` & `locator.py`:**
   - Integrate `TargetStrategy.MULTIMODAL` into `EvidenceBasedTargetLocator`.
   - Add explicit support for `CONTRADICTORY` and `LOW_CONFIDENCE` statuses.
4. **`src/orbit/runtime/perception/engine.py`:**
   - Expose `SemanticPerceptionEngine.fuse_multimodal_observation()` and integrate the fusion engine into the perception pipeline.
5. **Comprehensive Verification:**
   - Add unit test suite `tests/unit/test_multimodal_fusion.py` (15+ tests).
   - Add integration test suite `tests/integration/test_multimodal_target_resolution.py` (8+ tests).
   - Add live test suite `tests/live/test_m1_7_live_multimodal_fusion.py`.
   - Full regression suite validation (463+ tests).
   - Verify prototype boundary diff (`git diff ca87ef8 -- prototypes/`).
6. **Documentation:**
   - Generate `docs/M1_7_STEP_3_MULTIMODAL_FUSION_COMPLETION_REPORT.md`.
