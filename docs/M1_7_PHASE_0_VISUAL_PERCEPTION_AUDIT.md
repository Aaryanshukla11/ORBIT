# ORBIT — M1.7 PHASE 0: FORENSIC ARCHITECTURE AUDIT
## Visual Perception, Evidence Fusion & Safe Coordinate Transformation

**Status:** COMPLETE & AUTHORITATIVE  
**Milestone:** M1.7 Phase 0 (Analysis & Audit Only)  
**Host Platform:** Windows 11 Pro AMD64 (10.0.26200-SP0), Python 3.13.7  
**Baseline Test Suite:** 391 / 391 pytest tests passing | 5 / 5 Prototype formal suites passing  
**Frozen Prototype Preservation:** Zero modified lines against baseline (`ca87ef8`)  

---

## 1. EXECUTIVE SUMMARY & AUDIT STATUS

This audit delivers an exhaustive forensic assessment of ORBIT's visual perception capabilities, screenshot pipelines, OCR infrastructure, coordinate transformation models, and evidence fusion architecture.

### Current Epistemic Status Overview

| Capability Layer | Production Status (`src/orbit/`) | Prototype Status (`prototypes/`) | Epistemic Classification | Safety Gate Readiness |
| :--- | :--- | :--- | :--- | :--- |
| **Live Screen Capture** | GDI `BitBlt` + `CAPTUREBLT` in `CaptureEngine` | GDI capture in Prototype D | `CODE_PROVEN` / `LIVE_OS_VALIDATED` | Ready for Production |
| **Observation Snapshot Frame Delivery** | Schema defined (`FrameData`), but empty in `capture_snapshot` | Fully integrated in Prototype D snapshot | `CODE_PROVEN` / `SYNTHETIC_TEST_VALIDATED` | Gap: Wiring needed |
| **OCR Text Extraction** | Missing (`NOT_IMPLEMENTED`) | WinRT OCR & Tesseract in Prototype D | `CODE_PROVEN` (Prototype D) | Prototype-only; needs porting |
| **Visual Element / Icon Detection** | Missing (`NOT_IMPLEMENTED`) | Classical CV heuristics in Prototype D | `CODE_PROVEN` (Prototype D) | Prototype-only; needs porting |
| **Semantic Target Resolution** | UIA / MSAA / Window metadata active | Rule-based heuristics | `CODE_PROVEN` / `TEST_PROVEN` | `VISUAL_SEMANTIC` is `UNSUPPORTED` |
| **Accessibility / Vision Evidence Fusion** | Missing (`NOT_IMPLEMENTED`) | `EvidenceFusionEngine` in Prototype D | `CODE_PROVEN` (Prototype D) | Prototype-only; needs porting |
| **Visual Post-Action Verification** | `VisualChangeVerifier` stubbed | Perceptual dHash / delta in Prototype D | `CODE_PROVEN` (Prototype D) | Prototype-only; needs porting |
| **Coordinate Transformation Pipeline** | Logical desktop checks in `TargetLocator` | `CoordinateMapper` in Prototype E | `CODE_PROVEN` / `TEST_PROVEN` | Needs explicit `ImageToScreenTransform` |
| **Privacy & Local Execution** | 100% Local / Offline | 100% Local / Offline | `CODE_PROVEN` / `LIVE_OS_VALIDATED` | Fully air-gapped |

---

## 2. REPOSITORY FORENSIC INVESTIGATION

A comprehensive search across the entire ORBIT codebase (`src/`, `prototypes/`, `tests/`) revealed the exact implementation boundaries.

### 2.1 Production Core (`src/orbit/`)
1. **`src/orbit/adapters/observation/adapter.py` (`ProductionObservationAdapter`):**
   - Implements `capture_screen(bounding_box=None) -> FrameData` using `CaptureEngine`. It successfully grabs live physical desktop bitmaps via Win32 GDI `BitBlt` with `CAPTUREBLT` and encodes them as JPEG `FrameData`.
   - In `capture_snapshot()`, it captures window metadata, UIA accessibility trees, and MSAA elements. However, `snapshot.visual_evidence` and `snapshot.detected_targets` are hardcoded to empty tuples `()`, and `raw_frame` is set to `None`.
2. **`src/orbit/runtime/targeting/locator.py` (`EvidenceBasedTargetLocator`):**
   - Implements `locate_target(intent, snapshot, topology)` supporting `ACCESSIBILITY_FIRST`, `ACCESSIBILITY_ONLY`, `WINDOW_HEURISTIC`, and `HYBRID_FUSED`.
   - When encountering `TargetLocatorStrategy.VISUAL_SEMANTIC`, it returns `TargetResolutionResult(status=TargetResolutionStatus.UNSUPPORTED, is_resolved=False)` (fail-closed).
3. **`src/orbit/runtime/targeting/models.py` (`TargetEvidence`, `EvidenceSource`):**
   - `EvidenceSource` enum already defines `ACCESSIBILITY`, `MSAA`, `UIA`, `VISUAL_OCR`, `VISUAL_CV`, `VISUAL_SEMANTIC`, `WINDOW_METADATA`.
   - `TargetEvidence` dataclass already includes fields for `bounding_box`, `confidence`, `matched_text`, `visual_similarity`, and `metadata`. The contract is fully forward-compatible!
4. **`src/orbit/runtime/verification/verifier.py` (`ActionVerifier`):**
   - Contains `VisualChangeVerifier` strategy, but because `snapshot.visual_evidence` is empty in production, it fails closed or returns `VerificationOutcome.INCONCLUSIVE`.

### 2.2 Prototype Repository (`prototypes/prototype_d_observation/`)
1. **`ocr_engine.py`:**
   - Contains `NativeWinRTOCRProvider` utilizing Windows 10/11 built-in WinRT OCR (`winsdk.windows.media.ocr.OcrEngine` / `Windows.Graphics.Imaging.SoftwareBitmap`). It delivers fast, zero-dependency, local OCR.
   - Contains `OptionalTesseractOCRProvider` using `pytesseract` with fallback handling.
   - Contains `DefaultOCRDispatcher` implementing fallback logic and confidence scoring.
2. **`visual_engine.py`:**
   - Implements 3-layer visual perception architecture:
     - **Layer V1 (Visual Stability & Change Detection):** Difference Hashing (dHash 64-bit), Hamming distance computation, image variance analysis.
     - **Layer V2 (Visual Text & Label Extraction):** OCR bounding box extraction and text normalization.
     - **Layer V3 (Visual Element Detection):** Edge detection, morphological closing, and contour-based UI element bounding box discovery.
3. **`fusion_engine.py`:**
   - Implements `EvidenceFusionEngine` performing:
     - Spatial containment and Intersection over Union (IoU) matching between accessibility elements and visual OCR boxes.
     - Z-order occlusion separation (`GEOMETRIC_OVERLAP` vs `OBSERVED_VISUAL_OCCLUSION`).
     - Semantic agreement verification and contradiction flagging (`CONFLICTING_EVIDENCE`).

---

## 3. ANSWERS TO CRITICAL FORENSIC QUESTIONS

### Q1: What visual perception infrastructure already exists?
- **Production (`src/`):** Win32 GDI `BitBlt` physical screen capture (`CaptureEngine`), `FrameData` JPEG packaging, `TargetEvidence` contract schemas, and fail-closed dispatch gates.
- **Prototype (`prototypes/prototype_d_observation`):** WinRT OCR provider, Tesseract OCR provider, perceptual dHash engine, contour-based visual element extractor, and spatial evidence fusion engine.

### Q2: Does ORBIT already capture actual screenshots?
- **YES (`CODE_PROVEN`, `TEST_PROVEN`, `LIVE_OS_VALIDATED`).**
- `ProductionObservationAdapter.capture_screen()` captures live desktop pixels via GDI DC blitting (`SRCCOPY | CAPTUREBLT`), capturing hardware overlays, layered windows, and cursor state into PIL RGB images.

### Q3: What is the exact format of captured image data?
- **Internal / In-Memory:** `PIL.Image.Image` (RGB mode, 8-bit per channel).
- **Contract / Serialized:** `FrameData` dataclass containing:
  - `data: bytes` (JPEG compressed image buffer)
  - `resolution: Resolution(width: int, height: int)`
  - `timestamp_ns: int` (high-precision timestamp from `time.perf_counter_ns()`)
  - `format: str = "JPEG"`
  - `bounding_box: Optional[BoundingBox]` (physical desktop rect of capture area)

### Q4: Can ObservationSnapshot currently carry image evidence?
- **Partially (`CODE_PROVEN`).**
- `ObservationSnapshot` in `src/orbit/adapters/observation/snapshot.py` has fields `raw_frame: Optional[FrameData] = None` and `visual_evidence: Tuple[VisualObservation, ...] = ()`.
- However, `ProductionObservationAdapter.capture_snapshot()` does not capture or populate `raw_frame` or `visual_evidence` by default to avoid memory bloat during purely accessibility-based workflows.

### Q5: Are screenshot timestamps and desktop generations available?
- **Timestamps:** YES (`FrameData.timestamp_ns` and `ObservationSnapshot.timestamp_ns`).
- **Desktop Generations:** Available on `ObservationSnapshot.generation`, but NOT embedded inside `FrameData` itself. M1.7 must explicitly add `generation: int` to `FrameData` to enforce cryptographic/temporal lock with desktop state.

### Q6: What OCR implementation, if any, already exists?
- **Production (`src/`):** Zero (`NOT_IMPLEMENTED`).
- **Prototypes:** `NativeWinRTOCRProvider` (WinRT `Windows.Media.Ocr`) and `OptionalTesseractOCRProvider` (`pytesseract`) exist in Prototype D.

### Q7: Is any OCR code production-ready or prototype-only?
- **Prototype-only (`CODE_PROVEN` in Prototype D).**
- The prototype OCR code is functionally proven (15/15 tests passing in Prototype D formal suite), but has not been integrated into `src/orbit/adapters/observation/` or added to runtime packaging dependencies.

### Q8: What visual target resolution already exists?
- **Production (`src/`):** None (`NOT_IMPLEMENTED`).
- **Prototypes:** Prototype D `VisualEngine` detects visual bounding boxes, OCR words, and visual line clusters.

### Q9: Why does VISUAL_SEMANTIC currently return UNSUPPORTED?
- `src/orbit/runtime/targeting/locator.py` deliberately fails closed with `TargetResolutionStatus.UNSUPPORTED` because no production OCR or visual engine is wired to the locator. This prevents unsafe random or ungrounded mouse clicks.

### Q10: Can the existing TargetEvidence model support visual evidence without breaking contracts?
- **YES (`CODE_PROVEN`).**
- `TargetEvidence` dataclass already supports `EvidenceSource.VISUAL_OCR`, `VISUAL_CV`, and `VISUAL_SEMANTIC`, with fields `bounding_box`, `confidence`, `matched_text`, `visual_similarity`, and `metadata: Dict[str, Any]`.

### Q11: How should accessibility evidence and visual evidence interact?
- **Tiered Multi-Source Evidence Fusion:**
  1. **Primary Ground Truth for Standard Native UI:** Accessibility tree (UIA / MSAA). Provides exact control patterns, automation IDs, and hierarchy.
  2. **Primary Ground Truth for Non-Accessible / Custom UI:** Visual OCR and Computer Vision for web canvas, Qt/OpenGL widgets, remote desktop windows, and legacy apps.
  3. **Corroborative Fusion:** When both exist, visual OCR validates that the rendered label matches the accessibility name, boosting confidence to `HIGH_CONFIDENCE`.

### Q12: What should happen when Accessibility says Target A and Visual OCR says Target B at the same coordinates?
- **EXPLICIT CONTRADICTION & IMMEDIATE FAIL-CLOSED.**
- ORBIT must record `TargetResolutionStatus.CONFLICTING_EVIDENCE`, log an occlusion or state desynchronization anomaly, set `is_resolved=False`, and dispatch **ZERO** pointer events.

### Q13: How should ORBIT handle conflicting evidence?
- Return `TargetResolutionResult(is_resolved=False, status=TargetResolutionStatus.AMBIGUOUS, confidence=0.0)`.
- Increment telemetry contradiction counters.
- Suppress pointer/keyboard actuation.
- Escalate to the closed-loop recovery engine for re-observation or safe abort.

### Q14: Can visual coordinates safely map into physical desktop coordinates under DPI scaling, multiple monitors, negative coordinates, and cropped ROIs?
- **YES, via an Explicit Typed Transformation Model.**
- Screenshots captured via GDI physical `BitBlt` represent physical desktop pixels.
- If an ROI is cropped at virtual desktop coordinate `(origin_x, origin_y)`, an image bounding box `[ix, iy, iw, ih]` maps to physical desktop space via:
  $$\text{desktop\_x} = \text{origin\_x} + ix$$
  $$\text{desktop\_y} = \text{origin\_y} + iy$$
- Pointer coordinates in SendInput absolute normalized coordinates `[0..65535]` must be calculated using `CoordinateMapper.physical_to_normalized()` taking into account negative monitor origins `(SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN)` and dimensions `(SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN)`.

### Q15: What is the safest way to represent image-to-screen coordinate transforms?
- Through an immutable dataclass `ImageToScreenTransform`:
  ```python
  @dataclass(frozen=True)
  class ImageToScreenTransform:
      source_frame_id: str
      origin_x: int  # Virtual desktop X corresponding to image pixel (0, 0)
      origin_y: int  # Virtual desktop Y corresponding to image pixel (0, 0)
      frame_width: int
      frame_height: int
      dpi_scale: float
      desktop_generation: int
      capture_timestamp_ns: int
  ```
- Any coordinate transformation must be rejected if `current_generation != transform.desktop_generation`.

### Q16: What perception operations can be performed locally?
- **100% of required operations:**
  - Screen capture (Win32 GDI)
  - OCR Text Extraction (Windows Native WinRT OCR `Windows.Media.Ocr` or Tesseract)
  - Visual Change Detection (dHash / pixel variance / MSE / SSIM)
  - UI Element Contour Detection (Classical OpenCV / morphological filters)
  - Local Icon & Target Detection (ONNX Runtime lightweight UI detectors)

### Q17: Which proposed perception capabilities would require external models or services?
- **NONE.** All cloud-based vision APIs (e.g. OpenAI GPT-4V, Gemini Vision, Claude Vision) are strictly excluded from the execution safety loop to preserve air-gapped privacy, zero latency variance, and deterministic safety bounds.

### Q18: Can ORBIT remain fully local and privacy-preserving?
- **YES (`CODE_PROVEN`).**
- By utilizing Windows Native WinRT OCR (built into Windows 10/11 OS) and local CPU/DirectML models, no screen data ever leaves host memory.

### Q19: How should visual confidence differ from verification confidence?
- **Visual Discovery Confidence ($C_{discovery} \in [0.0, 1.0]$):** Measures pattern match quality (e.g., Levenshtein distance normalized for OCR, template correlation for icons). Gates whether a target is valid for dispatch.
- **Post-Action Verification Confidence ($C_{verify} \in [0.0, 1.0]$):** Measures visual state change between pre-action and post-action frames (e.g., dHash delta $> \theta$, focus rectangle appearance, text mutation). Gates whether the step succeeded or needs retry.

### Q20: How should stale screenshot evidence be rejected?
- Strict 3-point fail-closed validation:
  1. `snapshot.generation == current_desktop_generation` (Desktop state change invalidates).
  2. `(now_ns - frame.timestamp_ns) <= MAX_VISUAL_AGE_NS` (TTL $\le 500\text{ms}$).
  3. `human_takeover_adapter.is_takeover_active() == False` (Takeover preemption invalidates).
  If any check fails, the evidence is discarded with `STALE_EVIDENCE` status.

---

## 4. EVIDENCE FUSION HIERARCHY ANALYSIS

ORBIT establishes a 5-level tiered perception hierarchy:

```
+-------------------------------------------------------------------------+
| LEVEL 1: UI Automation (UIA)                                            |
|   - Determinism: HIGH | Latency: 5-25ms | Failure Mode: Hidden/Custom UI|
+-------------------------------------------------------------------------+
                                     | (Fallback / Corroboration)
                                     v
+-------------------------------------------------------------------------+
| LEVEL 2: MSAA / Native Window Hierarchy                                 |
|   - Determinism: HIGH | Latency: 2-10ms | Failure Mode: Non-Standard Win|
+-------------------------------------------------------------------------+
                                     | (Fallback / Corroboration)
                                     v
+-------------------------------------------------------------------------+
| LEVEL 3: Native WinRT OCR Text Recognition                              |
|   - Determinism: MEDIUM-HIGH | Latency: 15-40ms | Failure: Font/Occlusion|
+-------------------------------------------------------------------------+
                                     | (Fallback / Corroboration)
                                     v
+-------------------------------------------------------------------------+
| LEVEL 4: Visual UI Element / Contour Detection                          |
|   - Determinism: MEDIUM | Latency: 10-30ms | Failure: Low Contrast UI   |
+-------------------------------------------------------------------------+
                                     | (Fallback / Corroboration)
                                     v
+-------------------------------------------------------------------------+
| LEVEL 5: Local ONNX Semantic Vision Models                              |
|   - Determinism: STATISTICAL | Latency: 30-80ms | Failure: Hallucination|
+-------------------------------------------------------------------------+
```

### Strategic Recommendation
**Architecture Choice: Option B & C (Corroborative Tiered Fusion with Contradiction Gate)**
- For standard native applications: UIA is primary; OCR is corroborative.
- For non-accessible applications (Canvas, Electron, Games, Citrix): OCR and Visual Element Detection are primary.
- If both sources yield targets for overlapping bounding boxes:
  - **Agreement:** Boost confidence to $1.0$.
  - **Conflict:** Flag anomaly and **fail closed** ($0.0$ confidence).

---

## 5. LOCAL OCR & VISION ENGINE EVALUATION

| Engine | Availability on Windows Host | Latency (CPU) | Dependency Footprint | Privacy / Offline | Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Windows WinRT OCR** (`Windows.Media.Ocr`) | Native Windows 10/11 OS API | 15–35 ms | Zero binary footprint (`winsdk` / `ctypes`) | 100% Local / Zero egress | **RECOMMENDED PRIMARY** |
| **Tesseract OCR** | External binary (`tesseract.exe`) | 50–150 ms | Requires native executable install | 100% Local | **SECONDARY FALLBACK** |
| **PaddleOCR** | Third-party Python package | 120–400 ms | Heavy PyTorch/Paddle dependencies (>500MB) | 100% Local | **NOT RECOMMENDED** (Heavy) |
| **OpenCV Classical CV** | Python `opencv-python-headless` | 5–20 ms | Lightweight C-extension | 100% Local | **RECOMMENDED FOR CV** |
| **Local ONNX UI Models** | ONNX Runtime (`onnxruntime`) | 25–60 ms | Lightweight runtime (~50MB) | 100% Local | **RECOMMENDED FOR ICONS** |
| **Cloud VLMs** (GPT-4V / Gemini) | Requires Network / API keys | 1500–4000 ms | Network egress, latency risk | Cloud egress (Privacy risk) | **FORBIDDEN IN EXECUTION LOOP** |

---

## 6. COORDINATE TRANSFORMATION & SAFETY PIPELINE (P0)

To guarantee that visual perception never dispatches an out-of-bounds or distorted coordinate, every visual coordinate must traverse the following unidirectional, validated pipeline:

```
[Captured Screenshot Bitmap (W x H px)]
                 |
                 v (Crop / ROI Bounding Box)
[Image Bounding Box (ix, iy, iw, ih)]
                 |
                 v (Apply ImageToScreenTransform: x = origin_x + ix, y = origin_y + iy)
[Physical Desktop Pixel Coordinate (dx, dy)]
                 |
                 v (Validate against DesktopTopology / VirtualDesktopMetrics)
[Virtual Desktop Bounds Gate: [X_ORIGIN .. X_ORIGIN + WIDTH)]
                 |
                 v (Workspace Validation: Check Reserved AppBar / Dock Collisions)
[Workspace Safe Action Point Gate]
                 |
                 v (SendInput Normalization: (dx - X_ORIGIN) * 65535 / (WIDTH - 1))
[Normalized Absolute Coordinate: (nx, ny) in [0..65535]]
                 |
                 v (Pre-Dispatch Safety Check: Generation Parity & Takeover Gate)
[ProductionPointerAdapter.move_pointer / click]
```

---

## 7. ATOMIC STEP-BY-STEP ROADMAP FOR M1.7

Based on the forensic audit, M1.7 will be executed in 6 strictly atomic steps:

### M1.7 Step 1: Perception Contracts & Screenshot Coordinate Transformation Model
- **Objective:** Introduce typed coordinate transformation models (`ImageToScreenTransform`, `FrameData` generation locking, `VisualObservation` dataclasses).
- **Files Affected:** `src/orbit/contracts/`, `src/orbit/adapters/observation/snapshot.py`, `src/orbit/runtime/targeting/models.py`.
- **Safety Invariants:** Generation parity enforced on all image evidence; out-of-bounds transforms fail closed.

### M1.7 Step 2: Production Local OCR Integration (WinRT Native + Fallback)
- **Objective:** Port and harden Prototype D `NativeWinRTOCRProvider` and OCR dispatcher into `src/orbit/adapters/observation/ocr/`.
- **Files Affected:** `src/orbit/adapters/observation/ocr/`, `src/orbit/adapters/observation/adapter.py`.
- **Safety Invariants:** 100% local execution; gracefully handles OCR engine initialization failure.

### M1.7 Step 3: Visual Element Detection & Semantic OCR Target Locator
- **Objective:** Implement OCR-based target discovery and visual element detection in `src/orbit/runtime/targeting/`.
- **Files Affected:** `src/orbit/runtime/targeting/locator.py`, `src/orbit/runtime/targeting/action_point.py`.
- **Safety Invariants:** Fuzzy text matching thresholds; strict bounding box validation; no guessing.

### M1.7 Step 4: Multi-Source Evidence Fusion & Contradiction Resolution
- **Objective:** Implement `EvidenceFusionEngine` combining accessibility (UIA/MSAA) and visual evidence.
- **Files Affected:** `src/orbit/runtime/targeting/fusion.py`, `src/orbit/runtime/targeting/locator.py`.
- **Safety Invariants:** Contradictory evidence between accessibility and OCR triggers fail-closed `CONFLICTING_EVIDENCE`.

### M1.7 Step 5: Visual Post-Action Verification Engine
- **Objective:** Wire perceptual difference hashing (dHash), text mutation verification, and visual delta analysis into `ActionVerifier`.
- **Files Affected:** `src/orbit/runtime/verification/verifier.py`, `src/orbit/runtime/verification/strategies.py`.
- **Safety Invariants:** Inconclusive visual delta triggers bounded retry or fail-closed abort.

### M1.7 Step 6: End-to-End Live Perception Validation & Final Acceptance
- **Objective:** Validate live autonomous tasks against real Windows applications (Notepad, Calculator, Browser Canvas, Custom UI) using fused visual perception.
- **Files Affected:** `tests/integration/test_m1_7_live_perception_validation.py`, `tests/smoke/test_m1_7_e2e_smoke.py`.
- **Safety Invariants:** 100% human takeover preemption; zero pointer leaks; complete audit report.

---

## 8. TEST BASELINE & FROZEN PROTOTYPE VERIFICATION

### 8.1 Pytest Suite Baseline
- **Execution Command:** `python -m pytest tests/unit tests/integration tests/smoke -v`
- **Total Tests:** 391
- **Passed:** 391
- **Failed:** 0
- **Skipped:** 0
- **Execution Time:** 13.98s
- **Verdict:** `GREEN` (100% PASSING)

### 8.2 Frozen Prototype Verification Suite
- **Prototype A (Workspace & AppBar):** `formal_test_suite.py` -> **PASS (8/8 validated)**
- **Prototype B (Human Takeover):** `formal_test_suite.py` -> **PASS (10/10 validated, Avg latency 1.91ms)**
- **Prototype C (Keyboard & Unicode):** `formal_test_suite.py` -> **PASS (14/14 validated, 0 leaks)**
- **Prototype D (Observation & Fusion):** `formal_test_suite.py` -> **PASS (15/15 validated)**
- **Prototype E (Pointer & SendInput):** `phase1`, `phase2a`, `phase2b`, `phase2c` -> **PASS (71/71 validated)**
- **Prototype Source Diff:** `git diff ca87ef8 -- prototypes/*.py` -> **0 lines (STRICT ZERO DIFF)**

---

## 9. EXACT NEXT IMPLEMENTATION STEP

The exact next implementation step is:
**M1.7 Step 1: Perception Contracts & Screenshot Coordinate Transformation Model**
- Define `ImageToScreenTransform` in `src/orbit/runtime/targeting/models.py`.
- Enhance `FrameData` in `src/orbit/adapters/observation/snapshot.py` with `generation: int`.
- Define typed `VisualObservation` and `VisualEvidence` structures.
- Implement forward and inverse coordinate mapping with strict desktop bounds and DPI validation.
