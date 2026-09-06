# ORBIT — MILESTONE M1.7 STEP 4 FORENSIC AUDIT
## REAL-WORLD MULTI-APPLICATION PERCEPTION VALIDATION & ROBUSTNESS HARDENING

**Document Version:** 1.0.0  
**Milestone:** M1.7 Step 4 — Real-World Multi-Application Perception Validation  
**Date:** September 6, 2026  
**Status:** AUDIT COMPLETE — BASELINE ESTABLISHED  
**Baseline Test Count:** 486 / 486 PASSING (100% GREEN)  

---

## 1. EXECUTIVE AUDIT SUMMARY

Milestone M1.7 Steps 1–3 implemented:
- Windows Native OCR screen text localization (`Windows.Media.Ocr.OcrEngine`)
- Visual template & icon matching (`TemplateVisualMatcher` NCC)
- Multi-modal evidence fusion & confidence grounding (`MultiModalPerceptionFusionEngine`)

This forensic audit investigates the **truthfulness of live perception claims** across the ORBIT runtime. Specifically, it audits how existing tests acquire visual and OCR evidence, distinguishes between controlled synthetic test fixtures and genuine independent Windows applications, identifies perception blind spots, and defines the exact live validation scenarios required for production readiness.

---

## 2. SECTION A — EXISTING PERCEPTION ARCHITECTURE MAP

```
+-----------------------------------------------------------------------------+
|                           ORBIT Perception Pipeline                          |
+-----------------------------------------------------------------------------+
                                       |
                     [ProductionObservationAdapter]
                                       |
       +-------------------------------+-------------------------------+
       |                               |                               |
[Win32 & DWM Window Tree]   [UI Automation (UIA/MSAA)]    [Display Screenshot Frame]
       |                               |                               |
       v                               v                               v
[Window Bounds & PIDs]     [Accessibility Elements]      [Raw Bitmap Image / BGR]
       |                               |                               |
       |                               |               +---------------+---------------+
       |                               |               |                               |
       |                               |               v                               v
       |                               |      [WindowsNativeOCR]           [TemplateVisualMatcher]
       |                               |     (WinRT OcrEngine API)            (2D Pixel NCC)
       |                               |               |                               |
       |                               |               v                               v
       |                               |       [OCRTextRegions]             [VisualMatchCandidates]
       |                               |               |                               |
       +-------------------------------+---------------+-------------------------------+
                                       |
                                       v
                     [MultiModalPerceptionFusionEngine]
                     - Generation Parity Gate
                     - 2D Spatial Clustering (IoU >= 0.30)
                     - Semantic & Fuzzy String Agreement
                     - Spatial Anchor Disambiguation
                     - Contradiction Separation Gate (>150px)
                     - Non-Inflationary Confidence Calibration
                                       |
                                       v
                      [EvidenceBasedTargetLocator]
                     - Interior Action Point Clamping
                     - Coordinate Space Mapping (Screen <-> Virtual Desktop)
                     - Workspace Canvas & Dock Boundary Check
                                       |
                                       v
                    [SafeActionPoint] / [FAIL_CLOSED]
```

---

## 3. SECTION B — EXISTING LIVE VALIDATION COVERAGE

Auditing all 6 test suites under `tests/live/`:

| Test File | Test Name | Target Under Test | Evidence Source | Honest Classification |
|:---|:---|:---|:---|:---:|
| `test_m1_6_live_autonomy.py` | `test_live_scenario_a_real_application_discovery` | Spawned Tkinter window | Win32 `FindWindowW` + DWM Rect | `CONTROLLED_LIVE_VALIDATED` |
| `test_m1_6_live_autonomy.py` | `test_live_scenario_b_real_target_resolution_and_safe_point` | Spawned Tkinter window | Window Title target resolution | `CONTROLLED_LIVE_VALIDATED` |
| `test_m1_6_live_autonomy.py` | `test_live_scenario_c_real_safe_action_dispatch` | Spawned Tkinter window | Live Pointer `SendInput` movement | `LIVE_OS_VALIDATED` |
| `test_m1_6_live_autonomy.py` | `test_live_scenario_d_human_takeover_preemption` | Mock takeover event | Injected event bus takeover | `TEST_PROVEN` |
| `test_m1_6_live_closed_loop.py` | `test_live_closed_loop_pointer_move_verification` | Spawned Tkinter window | Win32 cursor position readback | `CONTROLLED_LIVE_VALIDATED` |
| `test_m1_6_live_closed_loop.py` | `test_live_closed_loop_focus_click_verification` | Spawned Tkinter window | Win32 `GetForegroundWindow` | `CONTROLLED_LIVE_VALIDATED` |
| `test_m1_6_live_safety.py` | `test_live_safety_dock_collision_fails_closed` | Live workspace bounds | Production workspace geometry | `LIVE_OS_VALIDATED` |
| `test_m1_7_live_ocr.py` | `test_live_windows_native_ocr_execution_on_host` | In-memory PIL Image | WinRT `OcrEngine` on PIL Image | `LIVE_OS_VALIDATED` (Engine) / `SYNTHETIC_ONLY` (Target) |
| `test_m1_7_live_visual_matcher.py` | `test_live_windows_visual_template_matching_on_host` | Screen crop or in-memory drawn glyph | Live screenshot crop + NCC | `LIVE_OS_VALIDATED` (Matcher) / `SYNTHETIC_ONLY` (Target) |
| `test_m1_7_live_multimodal_fusion.py` | `test_live_windows_multimodal_perception_fusion` | Button drawn on screenshot in memory | WinRT OCR + NCC on composite image | `LIVE_OS_VALIDATED` (Pipeline) / `SYNTHETIC_ONLY` (Target) |

---

## 4. SECTION C — GENUINE EVIDENCE VERSUS SIMULATED EVIDENCE

1. **Genuinely Real & OS-Backed:**
   - The Windows WinRT OCR engine (`Windows.Media.Ocr.OcrEngine`) is genuinely invoked on the host.
   - Screen frames are genuinely captured via Windows Desktop Duplication / GDI bitblt (`ProductionObservationAdapter.capture_screen()`).
   - Win32 window handles (`HWND`), processes (`PID`), and bounds are genuinely retrieved via `user32.dll` and `dwmapi.dll`.
   - Cursor positions are genuinely moved and read back via `SendInput` and `GetCursorPos`.

2. **Simulated / In-Memory Artifacts in Current Tests:**
   - In `test_m1_7_live_ocr.py`, `test_m1_7_live_visual_matcher.py`, and `test_m1_7_live_multimodal_fusion.py`, the target text or icon was **drawn directly onto the PIL image in Python memory** (`ImageDraw.Draw(img).text(...)`) rather than being rendered on-screen by an external Windows process.
   - As a result, current perception tests have not yet proven target localization against **independently rendered Windows GUI applications** (e.g. standard Win32 controls, DirectWrite text, GDI fonts, Dark Mode UI elements, or browser web pages).

---

## 5. SECTION D — CURRENT REAL-WORLD APPLICATION COVERAGE

- **Independent External Applications Tested:** **0** (Zero external applications like Notepad, Calculator, Edge, or Explorer have been automated yet).
- **Controlled Test GUI Applications:** **1** (Tkinter test subprocess for M1.6 window discovery and focus verification).
- **In-Memory Composited Images:** **3** (OCR live test, Visual Matcher live test, Multimodal Fusion live test).

---

## 6. SECTION E — PERCEPTION BLIND SPOTS

1. **Sub-Pixel Antialiasing & Font Rendering Differences**: DirectWrite and ClearType font rendering produce subtle color fringes and anti-aliasing variations that differ from PIL's default GDI rasterizer.
2. **Window Frame Shadow & DWM Extended Bounds Offset**: Win32 `GetWindowRect` includes invisible DWM drop shadows (typically 7–8px on Windows 11), whereas visual OCR bounding boxes locate visible pixels. Mismatches must be clamped within the visible client area.
3. **Occlusion & Z-Order Disconnect**: A window may be partially occluded by another window or the taskbar. OCR extracts text from visible pixels, but UIA might report element bounds from the obscured window.
4. **Theme Variations**: Text rendered in Windows 11 Dark Mode (white text on dark background) vs Light Mode (dark text on white background) must be correctly segmented and matched.

---

## 7. SECTION F — DPI AND COORDINATE-SPACE RISKS

- Host virtual desktop layout: $2880 \times 1800$ physical pixels at $150\%$ DPI scaling.
- WinRT OCR returns coordinates in **physical bitmap pixel coordinates**.
- Win32 `SetProcessDPIAware` / `Per-Monitor V2` awareness must ensure that screen capture resolution matches the virtual desktop coordinate space $1:1$.
- Any non-integer scaling ($125\%, 150\%, 175\%$) introduces coordinate rounding risks if not strictly mapped in physical display space.

---

## 8. SECTION G — WINDOW LIFECYCLE RISKS

- **Window Move**: Moving an application window after target resolution shifts physical coordinates. Target locator must verify snapshot timestamp against active generation or detect stale observations.
- **Window Minimize / Hide**: Minimizing a window removes visible pixels. OCR and visual matching must fail-closed with `NOT_FOUND` instead of targeting stale coordinates.
- **Window Destroy**: Closing an application invalidates HWND. System must fail-closed with `NOT_FOUND` or `STALE_OBSERVATION`.

---

## 9. SECTION H — DYNAMIC UI RISKS

- Popups, modal dialogs, context menus, and tooltips alter on-screen topology asynchronously.
- Clicking an element that triggers a dynamic dialog must be verified through post-action state re-observation.

---

## 10. SECTION I — THEME AND VISUAL VARIATION RISKS

- `TemplateVisualMatcher` uses Normalized Cross-Correlation (NCC).
- NCC is invariant to linear brightness offsets ($I' = \alpha I + \beta$), but is sensitive to non-linear contrast inversions (Dark Mode white-on-black vs Light Mode black-on-white).
- For icon matching across unknown themes, multi-modal fusion combining OCR text anchors with visual icons provides fail-closed robustness.

---

## 11. SECTION J — DUPLICATE TARGET AMBIGUITY RISKS

- Real applications frequently display repeated UI elements (e.g. standard keypad buttons in Calculator, multiple "Close" buttons, duplicate toolbars).
- Ambiguity rules must enforce:
  1. If duplicate candidates exist without contextual anchors $\implies$ `TargetResolutionStatus.AMBIGUOUS`.
  2. If spatial text anchors (e.g. "Save" icon adjacent to "File" menu) exist and uniquely identify one candidate $\implies$ `TargetResolutionStatus.RESOLVED`.
  3. If two candidates are equidistant from the anchor ($|\Delta d| < 15\text{px}$) $\implies$ `TargetResolutionStatus.AMBIGUOUS`.

---

## 12. SECTION K — MULTI-MONITOR LIMITATIONS

- Virtual desktop coordinates with negative origins (`x < 0` or `y < 0`) on secondary monitors must map through `ProductionWorkspaceAdapter` virtual bounds.
- Target coordinates outside the primary monitor display frame must be mapped to the correct monitor index.

---

## 13. SECTION L — EXACT RECOMMENDED VALIDATION SUITE (SCENARIOS 1–12)

To satisfy the M1.7 Step 4 mission honestly and comprehensively, we recommend implementing a dedicated real-world validation suite in `tests/live/test_m1_7_live_real_world_perception.py` and `tests/integration/test_perception_robustness.py`:

1. **Scenario 1 (Real Window Discovery)**: Launch live Windows **Notepad** (`notepad.exe`) or **Calculator** (`calc.exe`), observe live HWND, PID, title, and bounds via `ProductionObservationAdapter`.
2. **Scenario 2 (Accessibility Target Resolution)**: Discover UI elements of the real application via accessibility metadata and resolve safe interior action points.
3. **Scenario 3 (Live OCR on Real Application)**: Capture real desktop containing running Notepad / Calculator; extract visible text ("File", "Edit", "Calculator") via `WindowsNativeOCRProvider`; locate target; fail-closed on missing text.
4. **Scenario 4 (Live Visual Icon Resolution)**: Crop a real live icon template directly from a live rendered window and match it back against live desktop pixels using NCC.
5. **Scenario 5 (Multi-Modal Fusion on Real App)**: Fuse real OCR text + visual template on live application controls.
6. **Scenario 6 (Window Movement Invalidation)**: Move the live window to new coordinates $(x_1, y_1) \to (x_2, y_2)$; verify old snapshot fails closed as stale; re-observe and resolve at new location.
7. **Scenario 7 (Window Resize Robustness)**: Resize the live window; verify bounding box and safe action point adaptation.
8. **Scenario 8 (DPI & Coordinate Verification)**: Query host DPI awareness and verify physical-to-virtual coordinate parity.
9. **Scenario 9 (Theme & Visual Variation)**: Test template matching against theme changes; verify fail-closed behavior on inverted themes.
10. **Scenario 10 (Dynamic UI Change)**: Open a dialog or menu in the live application; verify perception handles state transitions.
11. **Scenario 11 (Duplicate Target Disambiguation)**: Test real multi-button window (e.g. Calculator or controlled multi-button grid); prove duplicate ambiguity returns `AMBIGUOUS` unless disambiguated by text anchor.
12. **Scenario 12 (Human Takeover Preemption)**: Validate that human takeover immediately blocks perception-driven pointer dispatch.

---

## 14. FORENSIC AUDIT CONCLUSION

The forensic audit confirms:
1. Baseline test suite: **486 / 486 PASSING**.
2. Previous live tests validated WinRT OCR and NCC algorithms, but used in-memory drawn targets rather than live rendered Windows applications.
3. Real-world validation against independent Windows applications (Notepad, Calculator) and controlled multi-button GUIs is required to achieve genuine `LIVE_OS_VALIDATED` status.

**STOP GIVEN**: Audit is complete. Proceeding to implementation plan.
