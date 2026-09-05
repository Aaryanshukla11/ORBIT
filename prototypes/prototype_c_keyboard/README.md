# ORBIT — Prototype C: Reliable Keyboard Interaction & Unicode Engine

## Overview

ORBIT Prototype C is an isolated experimental prototype that establishes the foundational native Windows keyboard interaction and Unicode streaming architecture for the ORBIT Autonomous Operating System project.

### Core Invariants & Safety Guarantees
1. **The Human Always Owns the Keyboard:** When human takeover, emergency stop (`F12`), focus shift, or an exception occurs, ORBIT immediately halts and releases only its own injected keys.
2. **Deterministic Phased Shortcuts:** All modifier shortcuts follow a 4-phase lifecycle (`Mod Down` $\rightarrow$ `Key Down` $\rightarrow$ `Key Up` $\rightarrow$ `Mod Up`) with reverse-order modifier release ensuring 0 stuck keys.
3. **Full Unicode Support:** Handles ASCII, multilingual scripts (e.g. Hindi Devanagari viramas), mathematical notation, currency symbols, and non-BMP emoji surrogate pairs.
4. **4-Step Focus Race Protection:** Validates target window `HWND`, process ID, executable name, and title before and after dispatch.
5. **Multi-Stage Latency Profiling:** High-resolution hardware monotonic timestamps ($T_1 \dots T_7$) measuring true end-to-end cancellation latency.

---

## Directory Layout

```
prototypes/prototype_c_keyboard/
├── app_types.py             # Enums, dataclasses, telemetry models
├── keyboard_controller.py   # Native Win32 SendInput controller & session manager
├── keyboard_state.py        # 3-tier key ownership tracker & selective sanitizer
├── unicode_engine.py        # UTF-16 surrogate pair encoder & grapheme normalizer
├── shortcut_engine.py       # 4-phase compound modifier engine
├── shortcut_policy.py       # Shortcut safety & risk classification policy
├── target_tracker.py        # 4-step window focus race verifier
├── cancellation_contract.py # Decoupled ICancellationSink & coordinator
├── clipboard_preserver.py   # Clipboard snapshot, readback, and restore
├── telemetry.py             # Multi-stage latency tracking (T1-T7) & JSON export
├── prototype_ui.py          # Interactive Tkinter dashboard & live telemetry UI
├── formal_test_suite.py     # Automated acceptance test suite (Tests C1 - C14)
├── live_validation.py       # Multi-tier live validation runner (Tiers 1, 2, 3)
├── requirements.txt         # Dependencies manifest (Standard Library + ctypes)
├── test_assets/
│   └── tier3_browser_test.html # Controlled local HTML test harness
└── results/
    ├── formal_audit_report_c.json     # Automated formal test JSON report
    ├── live_validation_results_c.json # Multi-tier live validation JSON results
    ├── prototype_c_validation_report.md # Formal 15-section validation report
    └── prototype_c_evidence_audit.md   # Independent reality & evidence audit
```

---

## Running Prototype C

### 1. Run the Formal Acceptance Test Suite (Tests C1 – C14)
```bash
python formal_test_suite.py
```

### 2. Run Multi-Tier Live Validation
```bash
python live_validation.py
```

### 3. Launch Interactive UI Dashboard & Live Telemetry
```bash
python prototype_ui.py
```
- Use the dashboard to type test corpora into the Tier 1 widget.
- Watch modifier status lamps (Ctrl, Shift, Alt, Win).
- Press **F12** or click **EMERGENCY STOP** to test immediate hardware-level sanitization.

---

## Validation Status

- **Formal Acceptance Suite (C1–C14):** **14/14 PASS**
- **Average True Cancellation Latency ($T_7 - T_4$):** **74.0 µs**
- **Average Sanitization Latency ($T_6 - T_5$):** **12.4 µs**
- **Prototype Status:** **FROZEN / PASS**
