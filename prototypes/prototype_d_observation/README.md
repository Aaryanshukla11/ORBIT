# ORBIT Prototype D v1.3.1 — Screen Observation & Evidence Fusion Engine

**Document Version:** 1.3.1  
**Target Environment:** Windows 11 Build 26200+ (64-bit AMD64), Python 3.13.7  
**Isolated Path:** `prototypes/prototype_d_observation/`

---

## 1. Overview & Core Mission

ORBIT Prototype D investigates how ORBIT can ingest, normalize, reconcile, and score multi-source desktop evidence (Visual screen capture, Window metadata, Win32 controls, MSAA accessibility, UI Automation trees, and optional local OCR text) to produce an immutable, evidence-backed representation of the current desktop state with explicit confidence bounds and failure exposure.

### Fundamental Invariants
- $\mathbf{TOOL\ SUCCESS\ \neq\ OBSERVATION\ SUCCESS}$
- $\mathbf{OBSERVATION\ SUCCESS\ \neq\ SEMANTIC\ UNDERSTANDING\ SUCCESS}$
- $\mathbf{OBSERVATION\ \neq\ ACTIONABLE\ CERTAINTY}$
- $\mathbf{SOFT\ TIMEOUT\ \neq\ WORKER\ TERMINATED}$
- $\mathbf{VISUAL\ CHANGE\ DETECTION\ \neq\ SEMANTIC\ UI\ UNDERSTANDING}$
- $\mathbf{REQUESTED\ SWITCH\ RATE\ \neq\ OBSERVED\ FOREGROUND\ SWITCH\ RATE}$

---

## 2. Directory Structure

```text
prototypes/prototype_d_observation/
├── app_types.py                        # Immutable data models, enums, ObservationSnapshot, ProviderResult
├── capture_engine.py                   # Win32 GDI BitBlt + PrintWindow DWM extended frame capture driver
├── window_tracker.py                   # Win32 HWND hierarchy, foreground state, process token tracker
├── accessibility_coordinator.py        # Coordinator managing independent Win32, MSAA, and UIA providers
├── provider_health.py                  # ProviderWorkerHealthManager & circuit breaker quarantine engine
├── win32_control_provider.py           # Independent native Win32 EnumChildWindows control provider
├── msaa_provider.py                    # Independent native Win32 oleacc / IAccessible traversal provider
├── uia_provider.py                     # Independent genuine COM UIAutomationCore.dll traversal provider
├── ocr_engine.py                       # OCRProvider abstraction (NativeWinRTOCRProvider, OptionalTesseractOCRProvider)
├── visual_engine.py                    # 3-Layer Visual Engine (V1 Change Detection, V2 OCR, V3 Semantic stub)
├── coordinate_mapper.py                # Mathematical coordinate normalizer with signed 64-bit precision bounds
├── fusion_engine.py                    # Multi-source spatial alignment, occlusion separation & confidence scoring
├── freshness_tracker.py                # Monotonic generation counter & multi-signal invalidation engine
├── takeover_observer.py                # Prototype B human takeover observation invalidation contract
├── telemetry.py                        # Performance profiling & worker lifecycle telemetry logging
├── formal_test_suite.py                # D1–D15 formal acceptance test runner
├── live_validation.py                  # Multi-application live validation harness (Tiers 1–5B)
├── smoke_tests/                        # Isolated Phase 1 capability smoke tests (S1–S7)
│   ├── s1_win32_metadata.py
│   ├── s2_gdi_screen_capture.py
│   ├── s3_dpi_awareness.py
│   ├── s4_genuine_ui_automation.py
│   ├── s5_msaa_accessibility.py
│   ├── s6_ocr_capability.py
│   ├── s7_foreground_observation.py
│   └── run_all_smoke_tests.py
├── validation/                         # Dedicated empirical reality validation harnesses
│   ├── uia_multi_tier_validation.py    # Native UIA COM multi-tier validation (U1–U5)
│   ├── real_occlusion_validation.py    # Phase P1: Live HWND Z-order and visual occlusion test
│   ├── real_focus_validation.py        # Phase P2: Live focus switching & rate divergence test
│   ├── monitor_reality_validation.py   # Phase P3: Multi-monitor topology discovery & coordinate math
│   ├── ocr_capability_validation.py    # Phase P4: Actual OCR runtime probe & decoupled fallback
│   └── v1_3_closure_suite.py           # Formal D16–D30 reality closure matrix runner
├── test_assets/
│   ├── observation_test_target.html    # Controlled browser test target with rich accessibility & DOM elements
│   └── ground_truth_manifest.json      # Ground truth bounding boxes for controlled test widgets
└── results/
    ├── native_capability_smoke_report.md  # Phase 1 S1–S7 smoke test results
    ├── formal_validation_results.json     # Complete 30-test matrix telemetry (D1–D30)
    ├── formal_audit_report_d.json         # D1–D15 telemetry
    ├── prototype_d_v1_3_validation_results.json # D16–D30 telemetry
    ├── live_validation_results_d.json     # Tiers 1–5B telemetry
    ├── uia_validation_results.json        # U1–U5 telemetry
    ├── occlusion_validation_results.json   # Phase P1 telemetry
    ├── focus_validation_results.json       # Phase P2 telemetry
    ├── monitor_validation_results.json     # Phase P3 telemetry
    ├── ocr_validation_results.json         # Phase P4 telemetry
    ├── environment_metadata.json          # Live OS & hardware metadata
    ├── prototype_d_validation_report.md   # Comprehensive validation report
    └── prototype_d_evidence_audit.md      # Claim-by-claim reality audit
```

---

## 3. Running Formal Tests and Validation

```powershell
# 1. Run Pre-Implementation Capability Smoke Tests (S1–S7)
python smoke_tests/run_all_smoke_tests.py

# 2. Run Formal Acceptance Matrix (D1–D15)
python formal_test_suite.py

# 3. Run Formal Reality Closure Matrix (D16–D30)
python validation/v1_3_closure_suite.py

# 4. Run Multi-Application Live Validation Matrix (Tiers 1–5B)
python live_validation.py

# 5. Run Native UIA COM Multi-Tier Validation (U1–U5)
python validation/uia_multi_tier_validation.py

# 6. Run Dedicated Reality Closures (P1–P4)
python validation/real_occlusion_validation.py
python validation/real_focus_validation.py
python validation/monitor_reality_validation.py
python validation/ocr_capability_validation.py
```
