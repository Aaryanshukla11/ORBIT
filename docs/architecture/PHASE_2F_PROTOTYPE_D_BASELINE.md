# PHASE 2F — PROTOTYPE D BASELINE AUDIT & CAPABILITY MAPPING

**Date**: 2026-09-16  
**Status**: ACTIVE MIGRATION BASELINE  
**Phase**: Phase 2F — Prototype D Removal & Clean Environment Proof  

---

## 1. Executive Summary

Phase 2F establishes complete native perception independence for ORBIT by eliminating all runtime, build, and test dependencies on `prototypes/prototype_d_observation/`.

This document records the forensic baseline of all Prototype D occurrences across the repository, maps every capability to its production native replacement in `src/orbit/runtime/perception/` and `src/orbit/adapters/observation/`, and specifies the migration actions required before physical prototype deletion.

---

## 2. Forensic Prototype D Repository Scan

A comprehensive search of the repository for `prototype_d_observation`, `Prototype D`, and prototype `sys.path` injections identified occurrences across the following classifications:

| Category | File Path | Line(s) | Description / Finding | Classification |
| :--- | :--- | :--- | :--- | :--- |
| **PRODUCTION** | `src/orbit/adapters/observation/adapter.py` | 72–82 | `sys.path.insert(0, proto_d_dir)` and lazy imports of `CoordinateMapper`, `CaptureEngine`, `WindowTracker`, `AccessibilityCoordinator`, `FreshnessTracker` | **PRODUCTION (BLOCKING)** |
| **TEST** | `tests/unit/test_observation_mapper.py` | 19–27 | Import of `app_types` (`ConfidenceLevel`, `Rect`, `WindowObservation`, etc.) | **TEST (TO MIGRATE)** |
| **TEST / DIAG**| `tests/diagnose_calculator_resolution.py` | 8–13 | `sys.path.insert(0, "prototypes/prototype_d_observation")` | **DIAGNOSTIC (TO MIGRATE)** |
| **TEST / DIAG**| `tests/inspect_uia_live.py` | 8 | `sys.path.insert(0, "prototypes/prototype_d_observation")` | **DIAGNOSTIC (TO MIGRATE)** |
| **TEST / DIAG**| `tests/test_live_semantic_acceptance.py` | 20 | `sys.path.insert(0, "prototypes/prototype_d_observation")` | **DIAGNOSTIC (TO MIGRATE)** |
| **TEST / DIAG**| `tests/test_uia_direct.py` | 8 | `sys.path.insert(0, "prototypes/prototype_d_observation")` | **DIAGNOSTIC (TO MIGRATE)** |
| **TEST / DIAG**| `tests/trace_task_step.py` | 10 | `sys.path.insert(0, "prototypes/prototype_d_observation")` | **DIAGNOSTIC (TO MIGRATE)** |
| **CONFIG** | `pyproject.toml` | 45 | Package path inclusion `prototypes/prototype_d_observation` | **BUILD CONFIG (TO REMOVE)** |
| **CONFIG** | `pyrightconfig.json` | 9 | Typecheck include path `prototypes/prototype_d_observation` | **BUILD CONFIG (TO REMOVE)** |
| **PROTOTYPE** | `prototypes/prototype_d_observation/*` | All | Prototype implementation, tests, and validation artifacts (20 modules) | **PROTOTYPE DIR (TO DELETE AFTER MIGRATION)** |

---

## 3. Capability Mapping Matrix

Every capability provided by Prototype D has an active, production-grade native replacement inside `src/orbit/runtime/perception/` and `src/orbit/adapters/observation/`:

| Prototype D Component | Capability Provided | Current Production Caller | Native Replacement Module | Replacement Class / Function | Migration Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`CaptureEngine`** | Win32 GDI Desktop Screenshot capture (`BitBlt`, `GetDIBits`) | `ProductionObservationAdapter.capture_screen` / `capture_snapshot` | `src/orbit/runtime/perception/screenshot.py` | `DesktopScreenshotObserver` / `NativeScreenshotEngine` / `_capture_gdi` | **READY (MIGRATING CALLER)** |
| **`WindowTracker`** | Top-level window enumeration (`EnumWindows`, `GetForegroundWindow`, process metadata) | `ProductionObservationAdapter.capture_snapshot` | `src/orbit/runtime/perception/windows.py` | `Win32WindowObserver` (`observe_windows`, `_observe_single_hwnd`) | **READY (MIGRATING CALLER)** |
| **`AccessibilityCoordinator`** | UIA COM accessibility tree interrogation & descendant extraction | `ProductionObservationAdapter.capture_snapshot` | `src/orbit/runtime/perception/uia.py` | `UIAElementObserver` (`observe_elements`) | **READY (MIGRATING CALLER)** |
| **`CoordinateMapper`** | Monitor metrics & Virtual Desktop BoundingBox queries | `ProductionObservationAdapter._on_initialize`, `get_display_metrics` | `src/orbit/runtime/perception/coordinate_mapper.py` + Win32 GDI | `OCRCoordinateMapper` + `user32.GetSystemMetrics` | **READY (MIGRATING CALLER)** |
| **`FreshnessTracker`** | Monotonic generation tracking & TTL freshness evaluation | `ProductionObservationAdapter.capture_snapshot`, `sync_generation` | `src/orbit/adapters/observation/freshness.py` | `FreshnessEvaluator` + adapter `generation_id` | **READY (MIGRATING CALLER)** |
| **`app_types`** | Data transfer models (`Rect`, `ConfidenceLevel`, `WindowObservation`) | `ProductionObservationAdapter`, `mapper.py` | `src/orbit/models/common.py` & `src/orbit/adapters/observation/snapshot.py` | `BoundingBox`, `ObservationConfidence`, `ObservedWindow`, `ObservedElement` | **READY (MIGRATING CALLER)** |
| **`fusion_engine.py`** | Multi-channel perceptual fusion & contradiction detection | `MultiModalPerceptionFusionEngine` | `src/orbit/runtime/perception/fusion_engine.py` | `MultiModalPerceptionFusionEngine` | **ALREADY NATIVE** |
| **`DesktopObserver`** | Unified desktop snapshot capture coordinator | `ProductionObservationAdapter` | `src/orbit/runtime/perception/observer.py` | `DesktopObserver` | **ALREADY NATIVE** |

---

## 4. Migration Action Plan

1. **Migrate `src/orbit/adapters/observation/adapter.py`**:
   - Completely remove `proto_d_dir` and `sys.path.insert(0, proto_d_dir)`.
   - Remove imports of `CoordinateMapper`, `CaptureEngine`, `WindowTracker`, `AccessibilityCoordinator`, `FreshnessTracker`, `app_types`.
   - Directly initialize native `DesktopObserver`, `Win32WindowObserver`, `DesktopScreenshotObserver`, `UIAElementObserver`, and `FreshnessEvaluator`.
   - Replace prototype snapshot construction with native `DesktopObserver.observe_desktop()` and `ObservationSnapshot.from_desktop_observation()`.

2. **Clean `tests/unit/test_observation_mapper.py`**:
   - Remove imports from `prototypes.prototype_d_observation.app_types`.
   - Use native ORBIT types (`BoundingBox`, `ObservationConfidence`, etc.) and duck-typed objects to test mapping logic.

3. **Migrate Diagnostic Scripts in `tests/`**:
   - Remove `sys.path.insert(0, ...prototype_d_observation...)` from `tests/diagnose_calculator_resolution.py`, `tests/test_uia_direct.py`, `tests/test_live_semantic_acceptance.py`, `tests/inspect_uia_live.py`, `tests/trace_task_step.py`.

4. **Implement Clean-Environment & Negative Import Tests**:
   - `tests/integration/test_clean_environment.py`: Intercepts `sys.modules` to forbid any prototype import and executes real desktop capture through `ProductionObservationAdapter`.
   - Architecture test checking all files under `src/orbit/` for zero prototype references.

5. **Verify Real Windows E2E**:
   - Test live desktop observation, multi-application state transition, and WorldState construction.

6. **Delete Prototype D**:
   - Delete `prototypes/prototype_d_observation/`.
   - Clean `pyproject.toml` and `pyrightconfig.json`.
