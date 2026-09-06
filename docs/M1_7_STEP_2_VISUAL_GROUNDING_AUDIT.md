# ORBIT — MILESTONE M1.7 STEP 2 FORENSIC ARCHITECTURE AUDIT
# VISUAL TARGET MATCHING & ICON GROUNDING

**Document Version:** 1.0.0  
**Date:** September 6, 2026  
**Audited Baseline:** M1.5 + M1.6 + M1.7 Step 1 (461 / 461 Tests Passing)  
**Security / Epistemic Boundary:** Fail-Closed, Zero Fake AI, DPI-Aware, Trust-Boundary Aware  

---

## 1. Existing Architecture Analysis

### Current Autonomy Pipeline
ORBIT currently operates on a closed-loop perception and execution pipeline:
```
OBSERVE (ObservationSnapshot + Desktop Generation)
   ↓
PERCEIVE (MSAA / UI Automation / Win32 / Native OCR Text)
   ↓
TARGET RESOLUTION (EvidenceBasedTargetLocator)
   ↓
SAFE ACTION POINT (Deterministic interior centroid calculation)
   ↓
WORKSPACE VALIDATION (ProductionWorkspaceAdapter + Usable Canvas + AppBar boundary)
   ↓
AUTONOMOUS DISPATCH GATE (Preemption checks + Human takeover monitor)
   ↓
ACT (ProductionPointerAdapter / ProductionKeyboardAdapter)
   ↓
RE-OBSERVE & POST-ACTION VERIFICATION
```

### Current Perception Baseline
- **Accessibility Elements:** Resolves MSAA, UI Automation, and Win32 controls from `detected_elements`.
- **Window Metadata:** Resolves top-level windows from `windows` collection.
- **OCR Text:** Resolves visible on-screen text regions using Windows Native OCR (`Windows.Media.Ocr.OcrEngine`).
- **Limitation:** Non-textual graphical UI targets—such as application icons, toolbar glyphs without accessibility names, custom canvas controls, Flutter buttons, and Electron image controls—currently cannot be resolved without explicit hardcoded coordinate regions.

---

## 2. Available Image Evidence & Screenshot Acquisition Path

### Screenshot Source & Pipeline
1. **`ProductionObservationAdapter.capture_screen()`**:
   - Queries `CoordinateMapper` for virtual desktop bounds.
   - Invokes Win32 GDI `BitBlt` via `CaptureEngine.capture_full_desktop()`.
   - Returns a `FrameData` record with JPEG-compressed bytes and virtual desktop ROI.
2. **`ProductionObservationAdapter.capture_snapshot()`**:
   - Acquires multi-source telemetry including window lists and accessibility trees.
   - Attaches screenshot image telemetry (`snapshot.telemetry["screenshot"]` / `snapshot.telemetry["image"]`).
3. **Pixel Format & Ownership**:
   - Screenshots are represented as in-memory PIL `Image.Image` instances in `RGB` / `L` (Grayscale) formats.
   - Lifetime is bound to the immutable `ObservationSnapshot` instance.

---

## 3. Coordinate Systems & DPI Hazards

### Active Coordinate Spaces
1. **`VIRTUAL_DESKTOP_SPACE`**:
   - Canonical multi-monitor physical pixel space spanning `[SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN]`.
   - Origin may be negative on secondary monitors.
2. **`SCREENSHOT_PIXEL_SPACE`**:
   - Top-left $(0, 0)$ pixel array of the captured image buffer.
   - Offset from virtual desktop space by `(screenshot_offset_x, screenshot_offset_y)`.
3. **`WINDOW_CLIENT_SPACE`**:
   - Relative to client area $(0, 0)$ of target HWND.
4. **`LOGICAL_DPI_SPACE`**:
   - Scaled by host DPI ratio (e.g. 1.25x, 1.5x, 2.0x).

### DPI & Scale Hazards
- Display scaling mismatches: If an icon template was captured at 100% scale (96 DPI) and the host runs at 150% scale (144 DPI), the icon on screen is 1.5x larger.
- Single-scale template matching will fail to correlate unless multi-scale candidate search is executed.
- Sub-pixel rounding: Integer pixel truncation in coordinate transformation must strictly preserve boundary safety.

---

## 4. Template Matching Options & Algorithm Selection

| Approach | Feasibility in ORBIT | Dependencies | Performance | Safety / Determinism |
| :--- | :--- | :--- | :--- | :--- |
| **2D FFT Normalized Cross-Correlation (NCC)** | **HIGH (Selected)** | `numpy` (built-in `np.fft`) | $O(N \log N)$ (~180ms on 800x400) | **100% Deterministic & Exact** |
| **OpenCV `matchTemplate`** | Medium | `opencv-python` (New dep) | High | Adds C-extension dependency |
| **Deep Learning Object Detector (YOLO/CLIP)** | Low / Rejected | PyTorch, ONNX, Heavy weights | Slow / Non-deterministic | Non-deterministic, hallucination risk |
| **Naive Sliding Window Pixel Difference** | High | Pure Python / NumPy | $O(W \cdot H \cdot w \cdot h)$ (Very slow) | Deterministic but too slow for production |

**Selected Architecture:** 2D Normalized Cross-Correlation (NCC) via NumPy Fast Fourier Transform (`np.fft.rfft2` / `np.fft.irfft2`) with 64-bit double-integral image variance computation.

---

## 5. Icon Matching Limitations, False Positives & Ambiguity

### False-Positive Risks
- Solid/flat color regions: Constant background patches have zero local variance. Mathematical NCC division by near-zero variance produces artificial 1.0 spikes if not masked.
  - **Mitigation:** Zero-variance mask: `valid_mask = (std_i > 1e-4) & (tpl_std > 1e-4)`. Unmasked regions evaluate to $0.0$.
- High-frequency noise: Tiny single-pixel artifacts may generate spurious peaks.
  - **Mitigation:** Minimum template dimension gate ($w \ge 8, h \ge 8$) and minimum confidence threshold ($0.85$).

### Duplicate & Near-Tied Ambiguity
- When identical or near-identical icons exist (e.g. 3 "Close" or "Settings" icons on screen):
  - **Fail-Closed Rule:** If $\text{confidence}_{\text{top}} - \text{confidence}_{\text{second}} < \text{ambiguity\_margin}$ (0.05), the matcher returns `VisualMatchStatus.AMBIGUOUS`.
  - In ambiguous state, `best_match` is set to `None` and locator produces `TargetResolutionStatus.AMBIGUOUS` with **ZERO pointer dispatches**.

---

## 6. Multi-Modal Evidence Fusion Strategy (Visual + OCR + Window Context)

When visual matching alone is ambiguous or needs contextual anchoring:
1. **Visual Match + Window Scoping:**
   - Scope visual search ROI to the client bounds of target window HWND.
2. **Visual Match + Nearby OCR Text Label:**
   - Anchor an icon target by requiring spatial proximity (e.g. within 150px) to a confirmed OCR text region (e.g. "Save" icon next to "Save" text label).
3. **Visual Match + Explicit Bounding Box ROI:**
   - Narrow candidate search to declared operational workspace canvas.
4. **Conflict Policy:**
   - If visual evidence and OCR evidence point to divergent coordinates ($> 50\text{px}$ discrepancy), fail closed with `TargetResolutionStatus.AMBIGUOUS`.

---

## 7. Safety Implications & Zero-Dispatch Guarantees

Every visual perception path must enforce:
1. **Freshness Gate:** Snapshot must not be stale (`is_stale=False`, `FreshnessState.FRESH`).
2. **Generation Parity:** `desktop_generation_id` of visual match must equal `snapshot.generation_id`.
3. **Workspace Canvas Validation:** Target $(x, y)$ coordinate must be inside usable canvas and not collide with docked AppBar areas.
4. **Preemption Gate:** Human takeover or runtime cancellation immediately aborts execution.
5. **No Coordinate Fabrication:** If template is not found, low confidence, or ambiguous, return structured failure with **0 pointer events**.

---

## 8. Implementation Plan

1. **Domain Models (`src/orbit/runtime/perception/visual_models.py`):**
   - Provide `VisualTemplate`, `VisualTemplateSource`, `VisualMatchRegion`, `VisualMatchPolicy`, `VisualMatchResult`, `VisualMatchStatus`, `VisualMatcherKind`, `VisualEvidence`.
2. **Matching Engine (`src/orbit/runtime/perception/visual_matcher.py`):**
   - Implement `TemplateVisualMatcher` with 2D FFT NCC, float64 integral variance, zero-variance masking, NMS, and ambiguity margin gating.
   - Implement `MockVisualMatcher` for deterministic mock scenarios.
3. **Perception Engine Integration (`src/orbit/runtime/perception/visual_engine.py` & `engine.py`):**
   - Template registry with SHA-256 checksum verification.
   - Structured multimodal fusion methods (`fuse_visual_and_ocr`, `find_template_near_text`).
4. **Target Locator (`src/orbit/runtime/targeting/locator.py`):**
   - Integrate `TargetStrategy.VISUAL_TEMPLATE`, `ICON_TEMPLATE`, and `IMAGE_REGION`.
   - Unsupported or un-backed strategies fail closed with `UNSUPPORTED`.
5. **Testing & Live Validation:**
   - Unit tests for all edge cases, integration tests for full autonomy loops, and live tests on Windows host.
