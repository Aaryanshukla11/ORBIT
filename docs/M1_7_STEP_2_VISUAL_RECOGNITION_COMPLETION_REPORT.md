# ORBIT — MILESTONE M1.7 STEP 2 COMPLETION REPORT
# VISUAL TEMPLATE, ICON & NON-TEXT UI TARGET RECOGNITION

**Date:** September 6, 2026  
**Status:** COMPLETE AND VALIDATED  
**Architecture Layer:** Semantic Perception & Multimodal Target Grounding  
**Authoritative Validation Result:** 461 / 461 Pytest Tests Passing (100% GREEN)  
**Frozen Prototype Boundary:** 0 Modifications (Strict Ca87ef8 Boundary Preserved)  

---

## 1. Exact Architecture Implemented

Milestone M1.7 Step 2 introduces a deterministic, evidence-backed visual perception subsystem enabling ORBIT to resolve non-text graphical UI targets (icons, toolbar buttons without accessible names, logos, custom canvas buttons) without relying on accessibility names or raw coordinate hardcoding.

The subsystem integrates directly into ORBIT's closed-loop autonomy pipeline:

```
ObservationSnapshot (Desktop Capture + Generation ID)
        ↓
VisualPerceptionEngine
        ↓
TemplateVisualMatcher (Deterministic FFT NCC + Float64 Variance)
        ↓
VisualMatchResult (Evidence, BoundingBox, Peak Scores)
        ↓
OCRCoordinateMapper (DPI Scaling & Virtual Desktop Space Transformation)
        ↓
EvidenceBasedTargetLocator (_resolve_visual_template)
        ↓
SafeActionPoint (Deterministic Center Point Clamping)
        ↓
Workspace Validation Gate (Usable Canvas + Reserved AppBar Boundary)
        ↓
AutonomousDispatchGate (Preemption, Takeover & Generation Checks)
        ↓
Pointer / Keyboard Action Execution
```

---

## 2. Visual Matching Approach Actually Used

- **Algorithm:** 2D Normalized Cross-Correlation (NCC) executed via Fast Fourier Transform (`np.fft.rfft2` / `np.fft.irfft2`) for exact pixel-level correlation surface computation.
- **Local Window Variance:** 2D double-integral images (`cumsum` in `float64`) compute local image patch variance in $O(1)$ time per pixel while preventing single-precision floating-point cancellation.
- **Zero-Variance Protection:** Flat/solid-color image areas (`std_i <= 1e-4` or `tpl_std <= 1e-4`) are strictly masked to $0.0$ to prevent division by epsilon and false correlation spikes.
- **Local Maxima Peak Extraction:** Fully vectorized 8-neighborhood local maximum detection extracts discrete candidate locations $\ge \text{minimum\_confidence}$.
- **Non-Maximum Suppression (NMS):** Spatial IoU suppression (threshold $0.3$) eliminates overlapping duplicate bounding boxes across candidate locations and multi-scale sweeps.
- **Execution Threading:** All matching computations execute in an asynchronous worker thread pool (`asyncio.to_thread`) to ensure the runtime event loop never stalls.

---

## 3. Dependencies Actually Added

- **New External Dependencies Added:** **0**
- **Existing Approved Dependencies Utilized:**
  - `numpy==2.2.6` (for vectorized array operations, 2D FFT, and integral image variance)
  - `Pillow==12.2.0` (for image loading, format conversion, and grayscale representation)
- **Dependency Policy Compliance:** 100% compliant with `pyproject.toml`. No ML frameworks, heavy computer vision blobs, or cloud vision APIs added.

---

## 4. Template Trust & Provenance Model

Visual templates are never treated as anonymous byte arrays. Every `VisualTemplate` requires:
- **`template_id`**: Strongly typed unique template identifier.
- **`source`**: Explicit provenance classification:
  - `TRUSTED_REGISTERED_TEMPLATE` (audited, registered application icons).
  - `UNTRUSTED_RUNTIME_IMAGE` (dynamic runtime captures requiring explicit validation).
- **`checksum`**: SHA-256 cryptographic hash computed over raw RGBA image bytes upon template construction to guarantee byte-level immutability and tamper resistance.
- **`dimensions` & `is_valid`**: Enforces strictly positive dimensions ($w > 0, h > 0$).
- **Registry**: `VisualPerceptionEngine` manages a thread-safe registry of registered trusted templates with collision detection.

---

## 5. Confidence Policy

- **Configurable `VisualMatchPolicy`**:
  - `minimum_confidence` (default: 0.85).
  - `ambiguity_margin` (default: 0.05).
  - `allow_multi_scale` (default: True, scale factors: `[0.8, 0.9, 1.0, 1.1, 1.2]`).
  - `max_candidates` (default: 10).
- **Fail-Closed Threshold Enforcement:**
  - Matches with correlation $< \text{minimum\_confidence}$ return `VisualMatchStatus.NOT_FOUND` or `LOW_CONFIDENCE`.
  - Confidence scores are never hardcoded to 1.0; they reflect the exact mathematical cross-correlation score.

---

## 6. Ambiguity Policy

- When multiple candidate regions meet `minimum_confidence`:
  - The top match and second-best match are compared:
    $$\Delta = \text{confidence}_{\text{top}} - \text{confidence}_{\text{second}}$$
  - If $\Delta < \text{ambiguity\_margin}$, the matcher triggers `VisualMatchStatus.AMBIGUOUS`.
  - In ambiguous state, `best_match` is set to `None`, and all candidate regions are preserved in `matches` for auditability.
  - `EvidenceBasedTargetLocator` immediately returns `TargetResolutionStatus.AMBIGUOUS`, resulting in **ZERO pointer dispatches**.

---

## 7. Coordinate Mapping Model

- **Space Transformations:**
  - `SCREENSHOT_PIXEL_SPACE` $\to$ `VIRTUAL_DESKTOP_SPACE` using snapshot monitor offsets (`screenshot_offset_x`, `screenshot_offset_y`).
  - `LOGICAL_DPI_SPACE` $\to$ `VIRTUAL_DESKTOP_SPACE` using host DPI scaling factor.
- **Coordinate Transformation Verification:**
  - All visual bounding boxes are mapped through `OCRCoordinateMapper.map_to_virtual_desktop`.
  - Invalid geometry or negative dimensions fail closed with `TargetResolutionStatus.INVALID_REQUEST`.

---

## 8. Safety & Autonomy Integration

- **Generation Parity Gate:** Visual evidence captures desktop generation `desktop_generation_id`. If active generation differs, `TargetResolutionStatus.STALE_OBSERVATION` is triggered.
- **Workspace Canvas Validation:** Safe action point $(x, y)$ is validated against `ProductionWorkspaceAdapter.validate_coordinate()`. If the point falls into a docked AppBar or outside the usable canvas, execution is rejected.
- **Human Takeover Preemption:** If physical human input is detected, active visual task execution is immediately cancelled and hardware sanitized.
- **Zero Stale Coordinate Reuse:** Closed-loop retries require fresh observation snapshots and fresh visual matching.

---

## 9. Zero-Dispatch Evidence Matrix

The following conditions provably produce **ZERO** pointer events:

| Condition | Perception Status | Locator Status | Action Dispatched |
| :--- | :--- | :--- | :--- |
| Template Not Found | `NOT_FOUND` | `NOT_FOUND` | **0 Pointer Events** |
| Low Confidence ($<0.85$) | `LOW_CONFIDENCE` | `NOT_FOUND` | **0 Pointer Events** |
| Duplicate / Ambiguous Matches | `AMBIGUOUS` | `AMBIGUOUS` | **0 Pointer Events** |
| Near-Tied Matches ($\Delta < 0.05$) | `AMBIGUOUS` | `AMBIGUOUS` | **0 Pointer Events** |
| Stale Snapshot / Expired TTL | `STALE_OBSERVATION` | `STALE_OBSERVATION` | **0 Pointer Events** |
| Desktop Generation Mismatch | `MATCHED` (Old Gen) | `STALE_OBSERVATION` | **0 Pointer Events** |
| Reserved AppBar Collision | `MATCHED` | `RESERVED_COLLISION` | **0 Pointer Events** |
| Human Takeover Active | `CANCELLED` | `CANCELLED` | **0 Pointer Events** |
| Coordinate Mapping Failure | `MAPPING_FAILED` | `INVALID_REQUEST` | **0 Pointer Events** |

---

## 10. Test Count & Verification Summary

### Comprehensive Test Metrics:
- **Total Pytest Tests:** **461 / 461 PASSING** (100% GREEN)
  - Unit Tests: 14 Visual Perception Unit Tests (`tests/unit/test_visual_perception.py`)
  - Integration Tests: 8 Visual Target Resolution Integration Tests (`tests/integration/test_visual_target_resolution.py`)
  - Live OS Tests: 2 Live Windows Visual Matcher Tests (`tests/live/test_m1_7_live_visual_matcher.py`)
  - Full Regression Baseline: All 437 pre-existing tests preserved with 0 regressions.

### Formal Prototype Validation Suites:
1. `prototypes/prototype_a_workspace/formal_test_suite.py`: **PASS (8/8 Tests)**
2. `prototypes/prototype_b_human_takeover/formal_test_suite.py`: **PASS (10/10 Tests)**
3. `prototypes/prototype_c_keyboard/formal_test_suite.py`: **PASS (14/14 Tests)**
4. `prototypes/prototype_d_observation/formal_test_suite.py`: **PASS (15/15 Tests)**
5. `prototypes/prototype_e_pointer/phase2c_validation.py`: **PASS (23/23 Tests)**

### Frozen Prototype Boundary Diff:
`git diff ca87ef8 -- prototypes/`: **0 lines modified** (100% frozen boundary preserved).

---

## 11. Epistemic Classification

### LIVE_OS_VALIDATED Capabilities:
1. Live Windows desktop snapshot capture via `ProductionObservationAdapter`.
2. Live visual template extraction and deterministic matching against desktop pixels on Windows 11 host.
3. Live coordinate validation against active `ProductionWorkspaceAdapter` AppBar work areas.
4. Fail-closed rejection of non-existent visual templates against live desktop observations.

### TEST_PROVEN Capabilities:
1. Multi-scale template matching across varied UI scaling ratios.
2. Near-equal score ambiguity detection and zero-dispatch enforcement.
3. Closed-loop retry with fresh observation generation updates.
4. Human takeover preemption during visual perception and target resolution.

---

## 12. Remaining Limitations & Non-Claims

- **No Generic AI Vision:** ORBIT does not claim broad visual reasoning, open-vocabulary object detection, or captioning.
- **Template Specificity:** Targets must have distinct visual contrast and non-zero pixel variance; matching solid/featureless surfaces fails closed honestly.
- **Deformation & 3D Rotation:** Visual template matching relies on 2D affine scale and cross-correlation; it does not match arbitrarily distorted, skewed, or 3D-rotated graphical controls.

---

## 13. Next Recommended Milestone Step

Proceed to **Milestone M1.7 Step 3: Multimodal Evidence Fusion & Semantic Target Resolution** to unify Accessibility, OCR, and Visual Template evidence into a prioritized multimodal target resolution policy.
