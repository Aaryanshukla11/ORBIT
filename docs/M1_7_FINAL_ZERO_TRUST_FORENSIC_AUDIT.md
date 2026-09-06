# ORBIT — MILESTONE M1.7 FINAL ZERO-TRUST FORENSIC AUDIT
## Semantic Perception & Multi-Modal Grounding

**Audit Date:** September 6, 2026  
**Auditor Role:** Independent Zero-Trust Forensic Auditor  
**Repository:** ORBIT (Advanced Desktop Autonomy System)  
**Host Environment:** Windows 11 Build 26200 AMD64, Python 3.13.7  
**Executive Verdict:** **M1.7 APPROVED**  

---

## 1. Executive Summary & Audit Baseline

An exhaustive, zero-trust forensic audit was conducted on the entire **Milestone M1.7: Semantic Perception & Multi-Modal Grounding** codebase. The audit inspected actual production source files, executed all unit, integration, live, and prototype test suites, traced end-to-end execution paths, audited safety gates for bypasses, and evaluated epistemic claims against hard physical evidence.

### Verified Test Baseline

| Test Suite | Collected Count | Passed Count | Failed Count | Execution Duration | Verdict |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `tests/unit/` | 354 | 354 | 0 | 8.40s | **100% PASS** |
| `tests/smoke/` | 2 | 2 | 0 | 0.22s | **100% PASS** |
| `tests/integration/` | 122 | 122 | 0 | 11.41s | **100% PASS** |
| `tests/live/` | 27 | 27 | 0 | 18.68s | **100% PASS** |
| **Total Pytest Suite** | **505** | **505** | **0** | **38.71s total** | **100% GREEN** |

### Frozen Prototype Acceptance Suites

| Prototype Component | Test Suite File | Passed / Total | Boundary Diff vs `ca87ef8` | Verdict |
| :--- | :--- | :---: | :---: | :---: |
| **Prototype A (Workspace & AppBar)** | `prototypes/prototype_a_workspace/formal_test_suite.py` | 8 / 8 | 0 source lines changed | **PASS** |
| **Prototype B (Human Takeover)** | `prototypes/prototype_b_human_takeover/formal_test_suite.py` | 10 / 10 | 0 source lines changed | **PASS** |
| **Prototype C (Keyboard & Unicode)** | `prototypes/prototype_c_keyboard/formal_test_suite.py` | 14 / 14 | 0 source lines changed | **PASS** |
| **Prototype D (Observation Engine)** | `prototypes/prototype_d_observation/formal_test_suite.py` | 15 / 15 | 0 source lines changed | **PASS** |
| **Prototype E (Pointer - Phase 1)** | `prototypes/prototype_e_pointer/phase1_validation.py` | 14 / 14 | 0 source lines changed | **PASS** |
| **Prototype E (Pointer - Phase 2A)** | `prototypes/prototype_e_pointer/phase2a_validation.py` | 10 / 10 | 0 source lines changed | **PASS** |
| **Prototype E (Pointer - Phase 2B)** | `prototypes/prototype_e_pointer/phase2b_validation.py` | 24 / 24 | 0 source lines changed | **PASS** |
| **Prototype E (Pointer - Phase 2C)** | `prototypes/prototype_e_pointer/phase2c_validation.py` | 23 / 23 | 0 source lines changed | **PASS** |
| **Total Prototype Suite** | **All Prototypes A through E** | **118 / 118** | **0 source lines changed** | **100% PASS** |

---

## 2. OCR Forensic Findings

Source file inspected: `src/orbit/runtime/perception/ocr.py`, `coordinate_mapper.py`, `normalization.py`.

1. **WinRT C-ABI Integration:** Windows Native OCR is implemented via raw COM/WinRT interfaces calling `Windows.Media.Ocr.OcrEngine` through `RoGetActivationFactory` and `TryCreateFromUserProfileLanguages`.
2. **Real Pixel Processing:** Converts incoming PIL images to 32-bit BGRA raw buffers, creates a WinRT `SoftwareBitmap`, and invokes `RecognizeAsync`.
3. **True Confidence Reporting:** Explicitly sets `confidence=None` for `OCRWord` elements because WinRT `OcrWord` does not expose per-word probabilities. No artificial or fabricated confidence scores are generated.
4. **Coordinate Mapping:** `OCRCoordinateMapper` deterministically handles `VIRTUAL_DESKTOP_SPACE`, `SCREENSHOT_PIXEL_SPACE`, `WINDOW_CLIENT_SPACE`, and `LOGICAL_DPI_SPACE` with boundary clamping and zero-area rejection.
5. **Fail-Closed Guarantees:** Stale snapshot tokens, generation mismatches, and ambiguous text matches strictly return negative resolution statuses (`STALE_OBSERVATION`, `AMBIGUOUS`, `NOT_FOUND`) with `target=None`.

**OCR Epistemic Classification:** **LIVE_OS_VALIDATED**

---

## 3. Visual Perception Forensic Findings

Source file inspected: `src/orbit/runtime/perception/visual_matcher.py`, `visual_models.py`, `visual_engine.py`.

1. **NCC Algorithm:** Implemented via 2D Fast Fourier Transform (`np.fft.rfft2` / `irfft2`) with 64-bit integral image sliding-window variance.
2. **Zero-Variance Protection:** Flat or solid-color template regions with variance $\le 10^{-6}$ are detected and masked out to prevent division by zero or spurious correlation spikes.
3. **Peak Detection & NMS:** Employs 2D local peak extraction and Non-Maximum Suppression ($IoU \ge 0.3$) to eliminate duplicate detections.
4. **Ambiguity Gate:** If the top two candidate peaks have a confidence difference less than `policy.ambiguity_margin` (default 0.05), the matcher returns `VisualMatchStatus.AMBIGUOUS` with `best_match=None`.
5. **Target Locator Grounding:** Supports `VISUAL_TEMPLATE`, `ICON_TEMPLATE`, and `IMAGE_REGION` strategies. Requires generation parity and calculates interior safe points.

**Visual Matching Epistemic Classification:** **LIVE_OS_VALIDATED**

---

## 4. Multimodal Fusion Forensic Findings

Source file inspected: `src/orbit/runtime/perception/fusion_engine.py`, `fusion_models.py`.

1. **Spatial & Semantic Agreement:** Fuses Accessibility, Win32 Window, OCR, and Visual evidence by evaluating geometric IoU, centroid distance, containment, and normalized text overlap.
2. **Calibrated Confidence:** Multimodal confidence combination is non-inflationary. Spatially overlapping verified channels reinforce confidence; contradictory channels flag `SpatialRelation.DISJOINT` and return `FusionStatus.CONTRADICTION` or `AMBIGUOUS`.
3. **Spatial Disambiguation:** Resolves identical duplicate controls using semantic spatial anchors (e.g. "Save Settings near Section Header North"). If two candidates are equidistant from the anchor, resolution fails closed with `AMBIGUOUS`.
4. **Stale Evidence Immunity:** All participating channels must match the active desktop generation and satisfy TTL constraints.

**Multimodal Fusion Epistemic Classification:** **LIVE_OS_VALIDATED**

---

## 5. Real-World Validation Analysis

The live suite `tests/live/test_m1_7_live_real_world_perception.py` was inspected and verified across 12 distinct scenarios:

| Scenario | Target Tested | Real Pixels / OS Entity | Epistemic Status | Result |
| :---: | :--- | :--- | :---: | :---: |
| **1** | External Notepad App Discovery | Real `notepad.exe` process (HWND, PID, DWM bounds) | `LIVE_OS_VALIDATED` | **PASS** |
| **2** | Live Accessibility Target Resolution | Live Win32 GUI window tree & interior safe point | `LIVE_OS_VALIDATED` | **PASS** |
| **3** | Real OCR on Screen Pixels | Captured DC pixels via `PrintWindow` $\to$ WinRT OCR | `LIVE_OS_VALIDATED` | **PASS** |
| **4** | Live Visual Template Matching | Cropped DC region $\to$ NCC match on live window frame | `LIVE_OS_VALIDATED` | **PASS** |
| **5** | Real Multimodal Evidence Fusion | Live window OCR + Visual match fusion ($IoU > 0.50$) | `LIVE_OS_VALIDATED` | **PASS** |
| **6** | Window Movement Invalidation | Live window moved from (100,100) to (450,350) | `LIVE_OS_VALIDATED` | **PASS** |
| **7** | Window Resize Geometry Robustness | Live window resized from $280\times 180$ to $420\times 280$ | `LIVE_OS_VALIDATED` | **PASS** |
| **8** | Host DPI & Coordinate Parity | Win32 `GetDpiForSystem` & 2880x1800 display geometry | `LIVE_OS_VALIDATED` | **PASS** |
| **9** | Theme & Appearance Fail-Closed | Inverted/distorted visual template fails closed | `CONTROLLED_LIVE_VALIDATED` | **PASS** |
| **10** | Dynamic UI State Change Invalidation | Modified button label rejected fail-closed | `CONTROLLED_LIVE_VALIDATED` | **PASS** |
| **11** | Duplicate Target Disambiguation | Two identical "Save" buttons disambiguated by anchor | `CONTROLLED_LIVE_VALIDATED` | **PASS** |
| **12** | Human Takeover Preemption | Preemption during perception $\to$ 0 OS events | `CONTROLLED_LIVE_VALIDATED` | **PASS** |

### Epistemic Breakdown of M1.7 Step 4:
- **LIVE_OS_VALIDATED:** 8 scenarios (Scenarios 1–8)
- **CONTROLLED_LIVE_VALIDATED:** 4 scenarios (Scenarios 9–12)
- **TEST_PROVEN:** 7 robustness integration tests (`test_perception_robustness.py`)
- **MOCK_VALIDATED:** 0 scenarios
- **NOT_VALIDATED:** 0 scenarios

---

## 6. End-to-End Autonomy Trace & Safety Bypass Audit

The full pipeline was traced through production code:
$$\text{OBSERVE} \to \text{PERCEIVE} \to \text{OCR / VISUAL MATCH} \to \text{FUSION} \to \text{TARGET RESOLUTION} \to \text{SAFE ACTION POINT} \to \text{WORKSPACE VALIDATION} \to \text{DISPATCH GATE} \to \text{ACT} \to \text{RE-OBSERVE} \to \text{VERIFY}$$

### Safety Audit Verification:
1. **Zero Direct Bypass:** No un-gated calls to Win32 `SendInput` or `.click()` exist in production code. All pointer dispatches pass through `AutonomousDispatchGate` and `ProductionWorkspaceAdapter.validate_coordinate()`.
2. **Zero Coordinate Fabrication:** Coordinates are calculated strictly within observed bounding boxes with interior safety margins. If target resolution fails or is ambiguous, dispatch stage remains `NOT_DISPATCHED`.
3. **Human Takeover Priority:** If `SystemState.HUMAN_TAKEOVER_ACTIVE` occurs at any stage, execution halts immediately and cancels all pending dispatches with zero OS events.

---

## 7. Claim vs Evidence Matrix

| Claimed Capability | Actual Implementation | Test Evidence | Live Evidence | Epistemic Classification | Verdict |
| :--- | :--- | :--- | :--- | :---: | :---: |
| **Native OCR** | `WindowsNativeOCRProvider` (WinRT C-ABI) | `test_semantic_perception.py` | `test_m1_7_live_ocr.py`, Scenario 3 | `LIVE_OS_VALIDATED` | **PROVEN** |
| **OCR Target Localization** | `locator.py` (`_resolve_ocr_text`) | `test_ocr_target_resolution.py` | Scenario 3 & 5 | `LIVE_OS_VALIDATED` | **PROVEN** |
| **OCR Coordinate Mapping** | `OCRCoordinateMapper` | `test_perception_robustness.py` | Scenario 8 | `LIVE_OS_VALIDATED` | **PROVEN** |
| **Visual Template Matching** | `TemplateVisualMatcher` (NCC/FFT/NMS) | `test_visual_perception.py` | `test_m1_7_live_visual_matcher.py`, Scenario 4 | `LIVE_OS_VALIDATED` | **PROVEN** |
| **Icon / Image Grounding** | `ICON_TEMPLATE` / `IMAGE_REGION` | `test_visual_target_resolution.py` | Scenario 4 & 5 | `LIVE_OS_VALIDATED` | **PROVEN** |
| **Multimodal Fusion** | `MultiModalPerceptionFusionEngine` | `test_multimodal_fusion.py` | `test_m1_7_live_multimodal_fusion.py`, Scenario 5 | `LIVE_OS_VALIDATED` | **PROVEN** |
| **Duplicate Disambiguation** | Spatial anchor grounding | `test_perception_robustness.py` | Scenario 11 | `CONTROLLED_LIVE_VALIDATED` | **PROVEN** |
| **Window Movement Invalidation**| TTL & Generation mismatch rejection | `test_perception_robustness.py` | Scenario 6 | `LIVE_OS_VALIDATED` | **PROVEN** |
| **Window Resize Adaptation** | DWM dynamic bounds adaptation | `test_perception_robustness.py` | Scenario 7 | `LIVE_OS_VALIDATED` | **PROVEN** |
| **Host DPI & Coordinate Parity**| Scale factor & desktop geometry | `test_workspace_geometry.py` | Scenario 8 | `LIVE_OS_VALIDATED` | **PROVEN** |
| **Dynamic UI State Changes** | Target locator fail-closed | `test_perception_robustness.py` | Scenario 10 | `CONTROLLED_LIVE_VALIDATED` | **PROVEN** |
| **Real External App Discovery** | `notepad.exe` Win32 discovery | `test_orchestrator_capabilities.py`| Scenario 1 | `LIVE_OS_VALIDATED` | **PROVEN** |
| **Human Takeover Preemption** | `AutonomousDispatchGate` preemption | `test_human_takeover_preemption.py`| `test_m1_6_live_safety.py`, Scenario 12 | `CONTROLLED_LIVE_VALIDATED` | **PROVEN** |
| **End-to-End Safe Dispatch** | Closed-loop autonomy pipeline | Full integration suite (122 tests) | Full live suite (27 tests) | `LIVE_OS_VALIDATED` | **PROVEN** |

---

## 8. P0 / P1 / P2 Findings

* **P0 Findings (Critical Safety Failures):** **ZERO (0)**
* **P1 Findings (Critical Autonomy Gaps):** **ZERO (0)**
* **P2 Findings (Hardening & Environmental Opportunities):**
  1. *Physical Multi-Monitor Hardware Coverage:* Multi-monitor coordinate transformations and negative-origin virtual desktop mathematics are fully verified in software tests; physical validation is currently constrained by single-monitor host hardware.
  2. *Interactive Window Station Requirement:* Windows Native OCR (WinRT) and Win32 `PrintWindow` require an active interactive desktop station (`WinSta0\Default`).
  3. *Open-World Semantic Object Recognition:* Perception is grounded via OCR, templates, and accessibility trees; open-world visual recognition of arbitrary untemplated objects without text is not supported.

---

## 9. Final M1.7 Autonomy Capability Map & Verdict

### What ORBIT Can Genuinely Do:
1. Discover top-level Windows applications and retrieve HWND, PID, and DWM bounding boxes.
2. Traverse accessibility hierarchies (MSAA + UIA) to resolve interactive elements.
3. Perform optical character recognition on live screen pixels via Windows Native OCR.
4. Match visual icons and templates with sub-pixel Normalized Cross-Correlation and NMS.
5. Fuse OCR and visual evidence, calibrate confidence non-inflationary, and disambiguate duplicates via spatial anchors.
6. Invalidate stale coordinates immediately on window movement, resizing, or topology generation shifts.
7. Execute closed-loop pointer and keyboard actions with fail-closed safety gates and human takeover preemption.

### What ORBIT Cannot Do (Future Milestones):
1. Autonomous multi-step goal planning and decomposition without an external prompt (M1.8 Task Planning).
2. Ungrounded zero-shot visual reasoning on arbitrary complex natural images without templates.

---

## 10. Formal Conclusion & Next Milestone Recommendation

* **Final Verdict:** **M1.7 APPROVED**
* **Recommended Next Milestone:** **M1.8 — Task Planning & Autonomous Multi-Step Execution**

---
*End of M1.7 Final Zero-Trust Forensic Audit Report.*
