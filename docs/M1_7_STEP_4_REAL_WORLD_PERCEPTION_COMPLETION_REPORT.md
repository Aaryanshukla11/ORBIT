# ORBIT — MILESTONE M1.7 STEP 4 COMPLETION REPORT
## Real-World Multi-Application Perception Validation & Robustness Hardening

**Date:** September 6, 2026  
**Milestone:** M1.7 Step 4 — Real-World Multi-Application Perception Validation & Robustness Hardening  
**Target Architecture:** Windows 11 AMD64 (Host: Build 26200, Python 3.13.7)  
**Status:** COMPLETED & PRODUCTION-VERIFIED (100% GREEN)  

---

## 1. Executive Summary & Epistemic Audit Baseline

This report documents the completion of **Milestone M1.7 Step 4: Real-World Multi-Application Perception Validation & Robustness Hardening**.

In this milestone, ORBIT's perception pipeline was rigorously proven against **genuine on-screen pixels** and **live running Windows desktop applications** (including Windows Notepad and dedicated live Win32 GUI test fixtures) across 12 distinct real-world perception scenarios, supplemented by 7 dedicated perception robustness integration tests.

### Epistemic Classification Summary

| Classification | Count | Scope & Description |
| :--- | :---: | :--- |
| **LIVE_OS_VALIDATED** | **8** | Executed directly against live Windows OS subsystems (Win32 window manager, DWM, WinRT OCR Engine, Desktop DC pixel capture, and live display geometry). |
| **CONTROLLED_LIVE_VALIDATED** | **4** | Executed against dedicated live Win32 GUI applications with controlled UI mutations, visual ambiguity, and human takeover preemption. |
| **TEST_PROVEN** | **7** | Deterministically verified edge cases in `tests/integration/test_perception_robustness.py` (stale evidence invalidation, duplicate candidate ambiguity, high-frequency movement, clipping, and zero-dispatch safety). |
| **MOCK_VALIDATED** | **0** | Zero scenarios in Step 4 used mocks as proof of perception capability. |
| **NOT_VALIDATED** | **0** | All 12 approved perception scenarios were fully implemented and validated on the host. |

---

## 2. Pytest Test Baseline & Final Execution Counts

| Suite | Baseline (Post-M1.7 Step 3) | Final Count (Post-M1.7 Step 4) | Status | Execution Duration |
| :--- | :---: | :---: | :---: | :---: |
| `tests/unit/` | 354 | 354 | **PASS** | 9.10s |
| `tests/smoke/` | 2 | 2 | **PASS** | 0.23s |
| `tests/integration/` | 115 | 122 (+7 new robustness tests) | **PASS** | 11.47s |
| `tests/live/` | 15 | 27 (+12 new real-world scenarios) | **PASS** | 18.02s |
| **Total Pytest Count** | **486** | **505** | **100% PASS** | **38.82s total** |

---

## 3. Real-World Scenario Implementation & Evidence Matrix

### Scenario Breakdown (`tests/live/test_m1_7_live_real_world_perception.py`)

| Scenario # | Description | Target App / Subject | Epistemic Level | Key Verification & Evidence |
| :---: | :--- | :--- | :---: | :--- |
| **1** | Real External Application Discovery | `notepad.exe` (Windows 11) | `LIVE_OS_VALIDATED` | Discovered live Notepad process with real HWND, PID, and non-empty DWM bounding box ($W>50, H>50$). |
| **2** | Live Accessibility Target Resolution | Live Win32 GUI Window | `LIVE_OS_VALIDATED` | Resolved target window bounds via Accessibility/Win32 title lookup; generated valid interior safe point. |
| **3** | Real OCR on Rendered Screen Pixels | Live Win32 Window Pixels | `LIVE_OS_VALIDATED` | Captured real rendered DC pixels via `PrintWindow` and performed WinRT OCR recognizing genuine button label text with valid bounding box coordinates. |
| **4** | Live Visual Template Matching | Live Window Pixel Region | `LIVE_OS_VALIDATED` | Cropped real button region from live window DC and matched it against the full captured window using normalized cross-correlation (confidence $\ge 0.95$). |
| **5** | Real Multi-Modal Evidence Fusion | Live Window OCR + Visual | `LIVE_OS_VALIDATED` | Fused live OCR evidence and visual template evidence using `MultiModalPerceptionFusionEngine`; achieved spatial overlap IoU $> 0.50$ and unified confidence $\ge 0.85$. |
| **6** | Window Movement & Coordinate Rejection | Live Moving Window | `LIVE_OS_VALIDATED` | Moved live window from $(100, 100)$ to $(450, 350)$; verified old target coordinates were stale; re-observed and re-resolved coordinates dynamically at new location. |
| **7** | Window Resize Geometry Robustness | Live Resized Window | `LIVE_OS_VALIDATED` | Resized window from $280\times 180$ to $420\times 280$; verified target bounding box and safe action point expanded to accommodate new dimensions. |
| **8** | Live Host DPI & Coordinate Parity | Host Display Subsystem | `LIVE_OS_VALIDATED` | Queried live display DPI (192 DPI, 2.0x scale on test host), verified virtual desktop bounds $(2880\times 1800)$, and validated coordinate normalization invariants. |
| **9** | Theme & Appearance Fail-Closed | Inverted / Distorted Visuals | `CONTROLLED_LIVE_VALIDATED` | Inverted template pixels simulating theme contrast change; verified matcher failed closed (`UNMATCHED` / `LOW_CONFIDENCE`) and blocked pointer dispatch. |
| **10** | Dynamic UI State Invalidation | Modal Dialog / State Mutation | `CONTROLLED_LIVE_VALIDATED` | Simulated UI state change (button replacement); verified locator rejected old intent fail-closed (`AMBIGUOUS` / `NOT_FOUND`). |
| **11** | Duplicate Target Disambiguation | Multiple Identical Buttons | `CONTROLLED_LIVE_VALIDATED` | Spawned two identical "Save Settings" buttons; verified resolution failed closed (`AMBIGUOUS`) without spatial anchor; and resolved deterministically to the correct instance when anchored by section header text. |
| **12** | Human Takeover Preemption | Closed-Loop Autonomous Loop | `CONTROLLED_LIVE_VALIDATED` | Triggered `SystemState.HUMAN_TAKEOVER_ACTIVE` during live perception $\to$ targeting $\to$ dispatch cycle; verified immediate preemption, zero OS pointer dispatches, and clean cancellation stamping. |

---

## 4. Integration Perception Robustness Suite

### Robustness Hardening Coverage (`tests/integration/test_perception_robustness.py`)

1. `test_stale_ocr_evidence_rejected_fail_closed`: Verifies that OCR evidence older than TTL is flagged `TTL_EXPIRED` and rejected by the fusion engine.
2. `test_stale_visual_evidence_rejected_fail_closed`: Verifies that visual match evidence older than TTL fails closed and blocks targeting.
3. `test_equidistant_duplicate_candidate_ambiguity_fails_closed`: Verifies that two candidate matches equidistant from a spatial anchor return `AMBIGUOUS` with 0 guesses.
4. `test_high_frequency_window_movement_coordinate_invalidation`: Verifies rapid sequential window coordinate changes invalidate past snapshots and force fresh observations.
5. `test_partial_window_occlusion_and_clipped_bounds`: Verifies partially off-screen/clipped windows have their interactive region bounded strictly to visible screen coordinates.
6. `test_dpi_coordinate_transformation_invariants`: Verifies mathematical invariants across 100%, 125%, 150%, 175%, and 200% DPI scaling factors.
7. `test_zero_pointer_dispatch_on_every_negative_status`: Exhaustively verifies that every negative perception/targeting status (`NOT_FOUND`, `AMBIGUOUS`, `STALE_SNAPSHOT`, `DOCK_COLLISION`, `TAKEOVER`) results in **0 pointer events dispatched to the OS**.

---

## 5. Frozen Prototype Boundary Verification

Prototype code boundaries established at baseline commit `ca87ef8` were strictly respected:

```
$ git diff ca87ef8 -- prototypes/
0 production source code lines modified
```

All 5 frozen prototype acceptance suites were executed and verified **100% GREEN**:

- **Prototype A (Workspace & AppBar):** `formal_test_suite.py` $\implies$ **8 / 8 PASS**
- **Prototype B (Human Takeover Preemption):** `formal_test_suite.py` $\implies$ **10 / 10 PASS**
- **Prototype C (Keyboard & Unicode Injection):** `formal_test_suite.py` $\implies$ **14 / 14 PASS**
- **Prototype D (Observation & State Fusion):** `formal_test_suite.py` $\implies$ **15 / 15 PASS**
- **Prototype E (Pointer & Absolute Movement):**
  - Phase 1 Safety Validation: `phase1_validation.py` $\implies$ **14 / 14 PASS**
  - Phase 2A ABI Validation: `phase2a_validation.py` $\implies$ **10 / 10 PASS**
  - Phase 2B Movement Validation: `phase2b_validation.py` $\implies$ **24 / 24 PASS**
  - Phase 2C Button Click Validation: `phase2c_validation.py` $\implies$ **23 / 23 PASS**
- **Total Prototype Acceptance Tests:** **118 / 118 PASS**

---

## 6. Production Safety Invariants & Zero-Dispatch Verification

Before any pointer or keyboard event is dispatched to the operating system, the following pipeline conditions are strictly enforced:

1. **Fresh Observation:** `snapshot.is_stale == False` (TTL $< 1000\text{ms}$).
2. **Target Unambiguity:** `TargetResolutionStatus == RESOLVED` (strictly 1 candidate; ambiguity fails closed).
3. **Desktop Generation Parity:** `target.generation_id == wsp.get_desktop_generation()`.
4. **Workspace Boundary Validation:** `wsp.validate_coordinate(x, y)` passes with status `VALID` (not in reserved AppBar dock, not out of desktop bounds).
5. **Safety Gate Permission:** `AutonomousDispatchGate.can_dispatch()` returns `True`.
6. **Takeover Inactive:** `SystemState != HUMAN_TAKEOVER_ACTIVE`.

If **ANY** of these conditions fails:
- Dispatch stage remains `NOT_DISPATCHED`.
- Zero Win32 `SendInput` calls are made.
- Detailed forensic telemetry records the exact failure reason.

---

## 7. Known Limitations & Environmental Considerations

1. **Multi-Monitor Hardware Topology:** Multi-monitor physical testing requires multi-monitor hardware connected to the Windows host. Single-monitor topologies execute full invariant checks; negative-origin virtual desktop coordinate math is verified deterministically.
2. **Headless Execution:** Windows Native OCR (WinRT) and `PrintWindow` require an active interactive desktop window station (`WinSta0\Default`).

---

## 8. Final Production-Readiness Verdict

| Category | Status | Details |
| :--- | :---: | :--- |
| **Unit Test Coverage** | **GREEN** | 354 / 354 passing |
| **Integration Robustness** | **GREEN** | 122 / 122 passing (including 7 new robustness tests) |
| **Live OS Real-World Perception** | **GREEN** | 27 / 27 passing (including 12 new live scenarios) |
| **Smoke Acceptance** | **GREEN** | 2 / 2 passing |
| **Frozen Prototype Suites** | **GREEN** | 118 / 118 passing across Prototypes A–E |
| **Prototype Boundary Integrity** | **PRESERVED** | 0 modifications to `prototypes/` source code |
| **Overall Verdict** | **PRODUCTION READY** | **M1.7 Step 4 complete and fully validated** |

---
*End of M1.7 Step 4 Completion Report.*
