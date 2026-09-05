# ORBIT — PROTOTYPE B
# HUMAN TAKEOVER & INPUT OWNERSHIP EXPERIMENT

## Status
- **Status**: FROZEN
- **Verdict**: **PROTOTYPE B — PASS**
- **Test Environment**: Windows 11 (Build 26200), AMD64, 192 DPI (200% scaling)

---

## Objective
To empirically evaluate Windows input boundary mechanisms (`WH_MOUSE_LL`, `WH_KEYBOARD_LL`, `SendInput`, `dwExtraInfo`), implement real-time adaptive trajectory envelopes for action categories, and enforce the core non-negotiable architectural invariant:
$$\text{AMBIGUOUS INPUT} \longrightarrow \text{PAUSE ORBIT}$$
$$\text{THE USER ALWAYS OWNS THE COMPUTER}$$

---

## Directory Structure
```
prototype_b_human_takeover/
├── README.md
├── requirements.txt
├── app_types.py            # Enums, dataclasses, and shared definitions
├── input_monitor.py        # Low-level Win32 LL hooks (WH_MOUSE_LL / WH_KEYBOARD_LL)
├── input_controller.py     # Win32 SendInput synthetic generator tagged with ORBIT session signature
├── trajectory_engine.py    # Cubic Bezier curve planner & dynamic DPI-scaled adaptive thresholds
├── state_machine.py        # 5-state lifecycle (IDLE, EXECUTING, SUSPECTED_TAKEOVER, PAUSED_BY_USER, RELEASE_PENDING)
├── takeover_detector.py    # Sub-millisecond arbitration engine & safety latch
├── telemetry.py            # Structured metrics logger (microsecond detection & halt latency)
├── prototype_ui.py         # Visual experimental dashboard & emergency stop
├── formal_test_suite.py    # Automated test runner for formal acceptance scenarios B1–B10
└── results/
    ├── formal_audit_report_b.json
    └── prototype_b_validation_report.md
```

---

## Running the Acceptance Suite
```powershell
python formal_test_suite.py
```

## Running the Visual Dashboard
```powershell
python prototype_ui.py
```
*(Press **ESC** or **F12** at any time to trigger the Emergency Stop).*

---

## Key Validated Capabilities & Limits
1. **Low-Level Hook Arbitration**: Uses `WH_MOUSE_LL` and `WH_KEYBOARD_LL` to distinguish physical input from ORBIT synthetic input tagged via `dwExtraInfo = 0x08B17001`.
2. **Adaptive Envelopes**:
   - `PRECISE_CLICK`: $8\text{px} \times \text{DPI} = 16\text{px}$ base corridor
   - `NORMAL_MOVE`: $18\text{px} \times \text{DPI} = 36\text{px}$ base corridor + velocity factor
   - `DRAG_OPERATION`: $24\text{px} \times \text{DPI} = 48\text{px}$ base corridor
   - `TEXT_INPUT`: $4\text{px} \times \text{DPI} = 8\text{px}$ (zero-tolerance touch detection)
3. **Safety-First Ambiguity Rule**: Any unclassified synthetic event or physical interruption halts autonomous input generation within $<0.1\text{ms}$.
4. **No Blind Automatic Resumption**: Inactivity transitions to `RELEASE_PENDING`, holding control until the future AI re-observation layer evaluates desktop state.
