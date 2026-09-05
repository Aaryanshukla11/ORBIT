# ORBIT Milestone M1.1 — Observation Capability Integration Audit

**Document Identifier:** `docs/M1_1_OBSERVATION_INTEGRATION_AUDIT.md`  
**Date:** September 6, 2026  
**Status:** APPROVED ARCHITECTURAL PRE-IMPLEMENTATION AUDIT  
**Target:** Milestone M1.1 (Production Observation Capability Integration)  

---

## 1. Executive Summary

Milestone M1.1 replaces the synthetic `MockObservationAdapter` in production mode with a real `ProductionObservationAdapter` backed by validated **Prototype D (Screen & UI Observation)** capabilities.

This audit establishes:
1. The classification of all Prototype D modules to determine their reuse safety.
2. The exact adapter boundary structure under `src/orbit/adapters/observation/`.
3. The translation contracts preventing Prototype D internal dataclasses from leaking into ORBIT core runtime, gateway, state machines, or contracts.
4. The coordinate-space and freshness preservation rules ensuring epistemic honesty.
5. The runtime backend selection (`OBSERVATION_BACKEND=mock` vs `OBSERVATION_BACKEND=prototype_d`) with strict fail-closed, no-silent-fallback guarantees.

---

## 2. Prototype D Dependency Classification Matrix

Every component of `prototypes/prototype_d_observation/` has been audited and classified according to the 4-tier rubric:
- **A. Safe Direct Reuse** — Standalone utility/engine safe to invoke inside the adapter boundary.
- **B. Requires Production Adapter Wrapper** — Core capability needing boundary translation, lifecycle management, or thread isolation.
- **C. Prototype-Only / Testing Code** — Test harnesses, scripts, or prototype UI not to be imported into production.
- **D. Unsafe / Deferred** — Components with heavy unverified external dependencies or non-essential for M1.1.

| Component | Classification | Integration Role | Rationale & Architectural Handling |
| :--- | :---: | :--- | :--- |
| `coordinate_mapper.py` | **A** | Virtual desktop & DPI metrics | Pure Win32 DPI math; Per-Monitor v2 coordinate translation. Safe inside adapter boundary. |
| `capture_engine.py` | **A** | Win32 GDI screen capture | High-performance sub-60ms GDI capture, zero memory leaks, returns standard PIL Images. |
| `window_tracker.py` | **A** | Window hierarchy & DWM bounds | Window enumeration, Z-order, PID tracking, and extended frame bounds via `DwmGetWindowAttribute`. |
| `accessibility_coordinator.py` | **B** | Multi-provider coordinator | Coordinates Win32, MSAA, and UIA providers with watchdog timeouts and health management. |
| `freshness_tracker.py` | **B** | Monotonic generation & TTL | Monotonic desktop generation tracking and multi-signal invalidation. Output mapped to ORBIT models. |
| `fusion_engine.py` | **B** | Multi-source evidence fusion | Fuses visual and accessibility evidence into target candidates. Encapsulated in adapter boundary. |
| `provider_health.py` | **B** | Circuit breaker & health | Tracks worker threads, timeout statistics, and health states (`HEALTHY`, `DEGRADED`, `QUARANTINED`). |
| `uia_provider.py` | **B** | UI Automation provider | COM-based UIA walker. Requires COM MTA initialization in dedicated worker threads. |
| `msaa_provider.py` | **B** | MSAA provider | `AccessibleObjectFromWindow` tree walker for legacy/native controls. |
| `win32_control_provider.py` | **B** | Win32 control provider | Fast `EnumChildWindows` control hierarchy enumeration. |
| `visual_engine.py` | **B** | Visual feature extractor | Screenshot perceptual hashing, color variance, and contrast analysis. |
| `app_types.py` | **B** | Internal prototype types | Enums and dataclasses (`Rect`, `ObservationSnapshot`, etc.). Mapped explicitly in `mapper.py`. |
| `ocr_engine.py` | **D** | OCR engine | Optional OCR provider. Requires external Tesseract / Windows.Media.Ocr. Deferred / optional in M1.1. |
| `formal_test_suite.py` | **C** | Prototype test suite | Prototype D research validation suite only. |
| `live_validation.py` | **C** | Prototype live script | Standalone live validation runner for Prototype D. |
| `prototype_ui.py` | **C** | Prototype GUI | Standalone Tkinter prototype visualization UI. |

---

## 3. Production Adapter Boundary Design

The production observation adapter lives under `src/orbit/adapters/observation/` with strict single-responsibility files:

```
src/orbit/adapters/observation/
├── __init__.py           # Package exports (ProductionObservationAdapter, ObservationSnapshot, etc.)
├── adapter.py            # ProductionObservationAdapter implementing ObservationCapability & BaseCapabilityAdapter
├── mapper.py             # Translates Prototype D dataclasses into typed ORBIT models (zero prototype leak)
├── snapshot.py           # Production observation snapshot, UI element, and target models
├── freshness.py          # Freshness tracking enum (FRESH, AGING, STALE, UNKNOWN) and validation logic
└── health.py             # Provider health tracker and diagnostic reporting
```

### Dependency Inversion Invariant:
```
┌──────────────────────────────────────────────────────────────┐
│                    ORBIT Core Runtime                        │
│            (contracts, orchestrator, gateway)                │
└──────────────────────────────┬───────────────────────────────┘
                               │ Depends ONLY on:
                               ▼
┌──────────────────────────────────────────────────────────────┐
│        ObservationCapability Protocol & Snapshot Models      │
│                (src/orbit/contracts/capabilities.py)         │
└──────────────────────────────┬───────────────────────────────┘
                               │ Implemented by:
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                 ProductionObservationAdapter                 │
│              (src/orbit/adapters/observation/)               │
└──────────────────────────────┬───────────────────────────────┘
                               │ Translates internally via mapper.py
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                 Prototype D Implementation                   │
│          (prototypes/prototype_d_observation/)               │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Epistemic Honesty & Coordinate Contracts

1. **Coordinate Frames:** Every bounding box emitted by the production adapter explicitly declares its coordinate frame:
   - `PHYSICAL_PIXELS` — Hardware screen pixel coordinates (used for pointer targeting).
   - `VIRTUAL_DESKTOP` — Unified desktop space across all monitors (supports negative origins).
   - `WINDOW_RELATIVE` — Relative to top-left of target window extended frame.
   - `LOGICAL_DIP` — Device-independent pixels (DPI scaled).
2. **No Data Fabrication:**
   - If an accessibility name, automation ID, or bounding box is missing from a provider, it remains `None` or explicitly `UNAVAILABLE`.
   - Missing fields are NEVER populated with placeholder defaults like `"Button"` or `(0, 0, 0, 0)`.
3. **Freshness Invariant:**
   - Snapshots older than `default_ttl_ms` (500ms) or whose desktop generation has advanced are marked `STALE`.
   - The orchestrator verifies snapshot freshness before dispatching actions.

---

## 5. Mock / Real Adapter Selection Policy

- Explicit selection via `RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION)` or environment variable `ORBIT_OBSERVATION_BACKEND=prototype_d` (or `ORBIT_ADAPTER_MODE=PRODUCTION`).
- **Fail-Closed Guarantee:** If `prototype_d` backend is requested but COM or GDI initialization fails, the adapter transitions to `FAILED` and raises `CapabilityInitializationError`. It **NEVER silently falls back to MockObservationAdapter**.

---

## 6. Audit Conclusion & Implementation Authorization

The pre-implementation audit confirms that Prototype D capabilities can be safely integrated through the proposed adapter boundary without modifying any frozen prototype code. Implementation of Milestone M1.1 is approved.
