# ORBIT Prototype D v1.2.1 — Claim vs Evidence Matrix

**Engine**: Screen Observation & Evidence Fusion Engine  
**Auditor Role**: Independent Software Engineering Reality Auditor  
**Audit Date**: September 5, 2026  
**Target Directory**: [`prototypes/prototype_d_observation/`](file:///c:/Users/Aaryan%20shukla/OneDrive/Desktop/ORBIT/prototypes/prototype_d_observation)  

---

## 1. Executive Claim Audit Summary

This document contrasts every major architectural and validation claim made in [ORBIT Prototype D v1.2.1](file:///c:/Users/Aaryan%20shukla/OneDrive/Desktop/ORBIT/prototypes/prototype_d_observation/README.md) and its [validation report](file:///c:/Users/Aaryan%20shukla/OneDrive/Desktop/ORBIT/prototypes/prototype_d_observation/results/prototype_d_validation_report.md) against verified runtime evidence, source code execution paths, and OS interaction levels.

```
═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
                               CLAIM AUDIT VERDICT SUMMARY
═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
  Total Formal Acceptance Claims Audited (D1–D15) : 15
    ├── Verified on Live Windows OS               : 9 Claims (60.0%)
    ├── Verified via Controlled Live Environment  : 1 Claim  (6.7%)
    ├── Verified as Contract / Architectural Only : 1 Claim  (6.7%)
    ├── Verified as Internal Logic / Algorithms   : 1 Claim  (6.7%)
    └── Overclaimed / Misclassified as Live OS    : 3 Claims (20.0%) [D9, D14, D15]

  Total Multi-Application Matrix Tiers Audited    : 6 Tiers (T1–T5B)
    ├── Live OS / Controlled Live App Validated   : 4 Tiers (T1, T2, T3, T5A)
    ├── Live Probed with Fallback Documented      : 1 Tier  (T4 - Browser DOM)
    └── Internal Logic Verification               : 1 Tier  (T5B - Synthetic Guard)

  Overall Empirical Audit Status                  : PASS WITH LIMITATIONS (High Core Reality, 3 Overclaims)
═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
```

---

## 2. High-Level Architectural Claim Inventory

| Claim ID | Claim Description | Original Source | Evidence Currently Available | Evidence Strength | Initial Audit Status | Auditor Reality Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **CLM-01** | Full desktop GDI BitBlt screen capture operates under 75ms with Per-Monitor DPI Aware v2. | `prototype_d_validation_report.md:52`, `capture_engine.py:46-86` | Real Win32 GDI `BitBlt` capture of 2880x1800 bitmap measured at 54.39ms. | Strong (Live OS telemetry) | `VERIFIED` | **VERIFIED** (`LIVE OS VALIDATED`) |
| **CLM-02** | Coordinate normalization eliminates scaling offsets with $\le 1.0\text{px}$ error bound. | `coordinate_mapper.py:138-149`, `formal_test_suite.py:141-163` | Live Win32 `ClientToScreen` comparison yielding 0.00px error. | Strong (Live OS API) | `VERIFIED` | **VERIFIED** (`LIVE OS VALIDATED`) |
| **CLM-03** | Foreground window detection captures active HWND and excludes DWM drop-shadow margins. | `window_tracker.py:65-88`, `formal_test_suite.py:167-189` | Live `GetForegroundWindow` + `DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)` calls. | Strong (Live OS API) | `VERIFIED` | **VERIFIED** (`LIVE OS VALIDATED`) |
| **CLM-04** | Window hierarchy enumeration discovers visible top-level windows in true visual Z-order. | `window_tracker.py:90-130`, `formal_test_suite.py:193-213` | Live `EnumWindows` traversal returning active desktop window hierarchy. | Strong (Live OS API) | `VERIFIED` | **VERIFIED** (`LIVE OS VALIDATED`) |
| **CLM-05** | UI Automation Provider traverses live Windows UI Automation element trees. | `uia_provider.py:1-158`, `formal_test_suite.py:217-241` | Provider uses `EnumChildWindows`, `GetClassNameW`, `GetWindowTextW`. No `UIAutomationCore.dll` or `IUIAutomation` COM interfaces. | Moderate (Native Win32 child enum) | `PARTIALLY VERIFIED` | **OVERCLAIMED AS UIA** (Actually Win32 Child Control Enum) |
| **CLM-06** | MSAA Provider traverses live accessible UI hierarchies via `oleacc.dll`. | `msaa_provider.py:1-303`, `formal_test_suite.py:217-241` | Live `AccessibleObjectFromWindow`, `AccessibleChildren`, and COM vtable traversal (`get_accName`, `get_accRole`, `accLocation`). | Strong (Live COM vtable) | `VERIFIED` | **VERIFIED** (`LIVE OS VALIDATED`) |
| **CLM-07** | Watchdog soft timeout abandons blocked workers at 150ms without hanging the host process. | `accessibility_coordinator.py:110-136`, `provider_health.py` | Host thread joins worker with timeout; records `ABANDONED_STILL_ACTIVE` without host freeze. | Strong (Runtime thread telemetry) | `VERIFIED` | **VERIFIED** (`LIVE OS VALIDATED`) |
| **CLM-08** | Multi-monitor architecture validated for negative virtual desktop coordinates `(-1920, -200)`. | `formal_test_suite.py:491-515`, `prototype_d_validation_report.md:65` | Negative tuple `(-1920, -200)` was manually constructed in Python. No physical secondary monitor was attached (`SM_XVIRTUALSCREEN = 0`). | Weak (Pure Python arithmetic) | `OVERCLAIMED` | **OVERCLAIMED AS LIVE OS** (`INTERNAL LOGIC VALIDATED`) |
| **CLM-09** | Layer V1 visual change detection detects pixel changes via 64-bit dHash and color variance. | `visual_engine.py:120-145`, `formal_test_suite.py:330-359`, `live_validation.py:406-483` | In `formal_test_suite.py`, image was mutated via in-memory PIL draw. In `live_validation.py` (Tier 5A), live Tkinter canvas was drawn to and detected (dHash diff 11). | Moderate-Strong | `PARTIALLY OVERCLAIMED in D9` / `VERIFIED in T5A` | **VERIFIED in Live App (Tier 5A)** / **Synthetic in D9** |
| **CLM-10** | Snapshot freshness invalidation enforces TTL boundaries and monotonic generation parity. | `freshness_tracker.py:52-105`, `formal_test_suite.py:363-429` | High-resolution timestamp checks and generation comparison in Python. | Strong (Deterministic logic) | `VERIFIED` | **VERIFIED** (`INTERNAL LOGIC VALIDATED`) |
| **CLM-11** | Human takeover from Prototype B immediately invalidates observations. | `takeover_observer.py:1-57`, `formal_test_suite.py:460-487` | Callback `on_human_takeover()` tested via direct invocation. No physical mouse hook active during test. | Moderate (Architectural contract) | `VERIFIED` | **VERIFIED** (`CONTRACT VALIDATED`) |
| **CLM-12** | Local OCR text extraction is decoupled and enriches visual features without pipeline blocking. | `ocr_engine.py:1-110`, `fusion_engine.py:113-126` | Neither `winsdk` nor `pytesseract` is installed. Fallback returned `([], 'NONE_AVAILABLE', False)`. | Weak (Fallback verified, engine unexecuted) | `PARTIALLY VERIFIED` | **UNAVAILABLE / NOT VALIDATED** (Decoupling verified; OCR unexecuted) |
| **CLM-13** | Contradiction & occlusion resolution flags hidden elements as `is_occluded = True` and `CONFLICTING`. | `fusion_engine.py:76-88`, `formal_test_suite.py:519-565` | In `formal_test_suite.py`, mock `WindowObservation` instances were passed. In live tiers, spatial intersection checked against open windows. | Moderate | `OVERCLAIMED in D15` | **INTERNAL LOGIC VALIDATED** (Algorithm correct; D15 was synthetic) |

---

## 3. Formal Acceptance Test Matrix Audit (D1–D15)

The table below contrasts original claimed classifications against independent auditor findings:

| Test ID | Test Name | Original Classification | Auditor Classification | Evidence Basis | Reality Level | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TEST D1** | Primary Screen Capture Accuracy | `LIVE OS VALIDATED` | **`LIVE OS VALIDATED`** | GDI `BitBlt` with `CAPTUREBLT` from screen DC (`GetDC(0)`). Captured 2880x1800 PIL Image in 54.39ms. | Live Desktop Screen Context | **VERIFIED** |
| **TEST D2** | DPI Coordinate Normalization Contract | `LIVE OS VALIDATED` | **`LIVE OS VALIDATED`** | `user32.ClientToScreen` queried under `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)`. 0.00px error. | Live Win32 API | **VERIFIED** |
| **TEST D3** | Foreground Window Detection | `LIVE OS VALIDATED` | **`LIVE OS VALIDATED`** | `GetForegroundWindow` + `DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)` queried on live foreground HWND. | Live Win32 & DWM API | **VERIFIED** |
| **TEST D4** | Window Lifecycle & State Detection | `LIVE OS VALIDATED` | **`LIVE OS VALIDATED`** | `EnumWindows` top-level traversal returning live desktop windows in true visual Z-order. | Live Win32 Window Manager | **VERIFIED** |
| **TEST D5** | Independent Accessibility Traversal | `LIVE OS VALIDATED` | **`CONTROLLED LIVE ENVIRONMENT`** | Executed against live Tkinter test fixture. MSAA used `oleacc.dll`; UIA used `EnumChildWindows`. | Live COM & Win32 Controls | **VERIFIED** (with provider scope note) |
| **TEST D6** | Traversal Watchdog & Soft Timeout | `LIVE OS VALIDATED` | **`LIVE OS VALIDATED`** | Executed with 0.01ms timeout; host thread unblocked, worker flagged `ABANDONED_STILL_ACTIVE`, no hang. | Live Threading & COM Dispatch | **VERIFIED** |
| **TEST D7** | Screen / Accessibility Coordinate Alignment | `LIVE OS VALIDATED` | **`LIVE OS VALIDATED`** | GDI bitmap sub-rectangle cropped at client bounds; dimensions match physical client rect exactly in 0.49ms. | Live GDI & Pixel Memory | **VERIFIED** |
| **TEST D8** | Multi-Dimensional Ground Truth Matching | `LIVE OS VALIDATED` | **`INTERNAL LOGIC VALIDATED`** | Fusion algorithm executed over real captured screenshot and accessibility elements. Reconciliation is deterministic Python. | Deterministic Python Reconciliation | **DOWNGRADED** (Internal Logic on Live Inputs) |
| **TEST D9** | Visual Change Detection (Layer V1) | `LIVE OS VALIDATED` | **`SYNTHETICALLY SIMULATED`** | Tested by drawing a red box via PIL `ImageDraw` into an in-memory bitmap copy, NOT by live OS window redraw. | In-Memory Bitmap Mutation | **OVERCLAIMED** in D9 (Live OS in Tier 5A) |
| **TEST D10** | Observation Freshness & Staleness (TTL) | `INTERNAL LOGIC VALIDATED` | **`INTERNAL LOGIC VALIDATED`** | High-resolution timestamp comparison against TTL threshold in Python. Initial check valid; expired check STALE. | Deterministic Timestamp Math | **VERIFIED** |
| **TEST D11** | Rapid Focus Switching Invalidation | `LIVE OS VALIDATED` | **`INTERNAL LOGIC VALIDATED`** | Focus change was simulated by manually calling `increment_generation()`. No real OS focus switch occurred during D11. | Python Generation State Machine | **OVERCLAIMED** as Live OS (`INTERNAL LOGIC`) |
| **TEST D12** | Window Destruction Invalidation | `LIVE OS VALIDATED` | **`LIVE OS VALIDATED`** | Real Win32 API `user32.IsWindow(0xDEADBEEF)` invoked and returned FALSE; snapshot validation caught destruction. | Live Win32 API Query | **VERIFIED** |
| **TEST D13** | Human Takeover Invalidation Contract | `CONTRACT VALIDATED` | **`CONTRACT VALIDATED`** | Callback `takeover_obs.on_human_takeover()` invoked directly. Verified generation increment and snapshot invalidation. | Interface Contract Execution | **VERIFIED** |
| **TEST D14** | Multi-Monitor Architecture Support | `LIVE OS VALIDATED` | **`SYNTHETICALLY SIMULATED`** | Negative rect `(-1920, -200, 400, 300)` was manually constructed in Python. No secondary monitor attached (`SM_XVIRTUALSCREEN = 0`). | Synthetic Python Coordinates | **OVERCLAIMED** as Live OS (`SYNTHETIC`) |
| **TEST D15** | Contradiction & Occlusion Resolution | `LIVE OS VALIDATED` | **`SYNTHETICALLY SIMULATED`** | Mock `WindowObservation` and `UIElementObservation` dataclass instances created in Python to test occlusion math. | Synthetic Python Dataclasses | **OVERCLAIMED** as Live OS (`SYNTHETIC`) |

---

## 4. Multi-Application Matrix Reality Breakdown (Tiers 1–5B)

| Tier ID | Application Name | Launch Mechanism | Target HWND / Process | Observation Method | Auditor Reality Level | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | Controlled Tkinter Reference | `subprocess.Popen([sys.executable, controlled_testbed.py])` | Live HWND (`ORBIT_TIER1_TARGET_TESTBED`) | GDI BitBlt + DWM Extended Frame + MSAA/ChildEnum | `CONTROLLED LIVE ENVIRONMENT` | **PASS (Live)** |
| **Tier 2** | Standard Windows App (`Notepad.exe`) | `subprocess.Popen(["notepad.exe"])` | Live HWND (`Notepad.exe`, PID verified) | GDI BitBlt + DWM Extended Frame + Child Enum | `LIVE OS VALIDATED` | **PASS (Live)** |
| **Tier 3** | Complex Native / Shell GUI | `subprocess.Popen([sys.executable, complex_native_testbed.py])` | Live HWND (`ORBIT_TIER3_COMPLEX_SHELL_TESTBED`) | Multi-tab Treeview traversal under 150ms timeout | `CONTROLLED LIVE ENVIRONMENT` | **PASS (Live)** |
| **Tier 4** | Modern Web Browser DOM | Scanned live desktop for browser processes (`msedge.exe`, etc.) | Live browser HWND if present (or static fallback) | Probed DOM accessibility boundary; documented lazy accessibility | `LIVE OS VALIDATED` / `CONTRACT VALIDATED` | **PASS WITH LIMITATIONS** |
| **Tier 5A** | Custom Canvas (Pixel Graphics Only) | Live `tk.Tk()` with `tk.Canvas` raw graphics | Live Canvas HWND (Zero child HWNDs) | Frame 0 vs Frame 1 GDI capture; dHash diff 11; BBox isolated | `CONTROLLED LIVE ENVIRONMENT` | **PASS (Live)** |
| **Tier 5B** | Synthetic Canvas Semantic Guard | Pure Python in-memory simulation | Mock HWND 9999 | Verified confidence capped at `LOW_CONFIDENCE` / `PARTIALLY_CONFIRMED` | `INTERNAL LOGIC VALIDATED` | **PASS (Logic)** |

---

## 5. Auditor Synthesis & Reclassification Summary

1. **Reality Strengths**:
   - GDI Screen capture, DPI normalization, DWM extended frame bounds, window hierarchy traversal, MSAA COM vtable interaction, watchdog timeout handling, and snapshot identity invalidation are **genuinely executing against the live Windows 11 operating system**.
   - Live application tiers (Tkinter testbed, Notepad.exe, Complex tree GUI, Custom canvas) were genuinely spawned as live OS processes and observed.

2. **Auditor Downgrades & Corrections**:
   - **Test D14 (Negative Virtual Coordinates)**: Reclassified from `LIVE OS VALIDATED` to `SYNTHETICALLY SIMULATED / INTERNAL LOGIC VALIDATED`. No secondary monitor hardware existed.
   - **Test D9 (Visual Change Detection)**: In `formal_test_suite.py`, reclassified from `LIVE OS VALIDATED` to `SYNTHETICALLY SIMULATED` (tested via PIL `ImageDraw` mutation). Live visual change was proven separately in Tier 5A.
   - **Test D15 (Occlusion Resolution)**: In `formal_test_suite.py`, reclassified from `LIVE OS VALIDATED` to `SYNTHETICALLY SIMULATED / INTERNAL LOGIC VALIDATED` (tested via mock dataclasses).
   - **Test D11 (Focus Switch Invalidation)**: Reclassified from `LIVE OS VALIDATED` to `INTERNAL LOGIC VALIDATED` (generation incremented manually in Python).
   - **Test D8 (Multi-Source Fusion)**: Reclassified from `LIVE OS VALIDATED` to `INTERNAL LOGIC VALIDATED` (reconciliation logic is internal Python).
   - **UIAutomationProvider**: Clarified as a **Native Win32 Child Control Enumerator** (`EnumChildWindows`), not an `IUIAutomation` COM client from `UIAutomationCore.dll`.
   - **OCR Engine**: Clarified as **UNAVAILABLE / NOT VALIDATED** on live pixels due to uninstalled native OCR drivers (`winsdk`/`pytesseract`), though the decoupling fallback operates as designed.
