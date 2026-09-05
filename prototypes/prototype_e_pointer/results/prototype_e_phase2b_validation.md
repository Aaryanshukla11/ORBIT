# ORBIT PROTOTYPE E — PHASE 2B FORMAL ACCEPTANCE VALIDATION REPORT
## Absolute Cursor Movement Only (Win32 SendInput & GetCursorPos Verification)

**Validation Date:** 2026-09-05T20:21:28Z  
**Host Platform:** Windows 11 Build 26200 AMD64 | Python 3.13.7  
**Virtual Desktop Layout:** 2880x1800 (Origin: `0, 0`)  
**Monitor Count:** 1  
**Original Cursor Position:** `(2671, 1459)`  
**Final Verdict:** **🟢 PASSED (22/22)**  

---

## 1. Executive Summary & Non-Action Invariant

$$\boxed{\mathbf{PHASE\ 2B\ IMPLEMENTS\ ABSOLUTE\ CURSOR\ MOVEMENT\ ONLY}}$$

- **Zero Mouse Clicks**: 0 `MOUSEEVENTF_LEFTDOWN`, 0 `MOUSEEVENTF_LEFTUP`
- **Zero Button Actions**: 0 Right/Middle/X button events, 0 drag trajectories, 0 wheel actions
- **Zero Magic Numbers (C1)**: Flags composed via `MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK`
- **Structural Topology Identity (C2)**: Pre-dispatch guard compares display geometry only (timestamp-independent)
- **Epistemic Honesty (C3)**: Readback mismatches classified without assigning human takeover causality
- **Single-Packet Semantics (C4)**: N=1 packets; return value strictly M=0 or M=1
- **Non-Atomic Readback Timing (C5)**: T1 -> T5 timeline disclosed; arrival observed within +/- 1px tolerance
- **Single Native Gateway**: All SendInput calls routed exclusively through NativeDispatchGateway

---

## 2. Test Execution Matrix (P2B-1 to P2B-22)

| Test ID | Capability Tested | Expected Verdict | Reality Classification | Status |
| :--- | :--- | :---: | :--- | :---: |
| **P2B-1** | Named Flag Composition (C1) | **PASS** | `INTERNAL_LOGIC_VALIDATED` | 🟢 PASS |
| **P2B-2** | Runtime ABI Gate Requirement | **PASS** | `LIVE_OS_VALIDATED` | 🟢 PASS |
| **P2B-3** | Zero-Action Rejection on Bad ABI | **PASS** | `INTERNAL_LOGIC_VALIDATED` | 🟢 PASS |
| **P2B-4** | Same Topology Identity, Different Timestamps (C2 Case 1) | **PASS** | `INTERNAL_LOGIC_VALIDATED` | 🟢 PASS |
| **P2B-5** | Virtual Desktop Width Mutation (C2 Case 2) | **PASS** | `INTERNAL_LOGIC_VALIDATED` | 🟢 PASS |
| **P2B-6** | Virtual Desktop Height Mutation (C2 Case 3) | **PASS** | `INTERNAL_LOGIC_VALIDATED` | 🟢 PASS |
| **P2B-7** | Virtual Desktop Origin Mutation (C2 Case 4) | **PASS** | `INTERNAL_LOGIC_VALIDATED` | 🟢 PASS |
| **P2B-8** | Monitor Count Mutation (C2 Case 5) | **PASS** | `INTERNAL_LOGIC_VALIDATED` | 🟢 PASS |
| **P2B-9** | Single-Packet SendInput M=1 Classification (C4) | **PASS** | `LIVE_OS_VALIDATED` | 🟢 PASS |
| **P2B-10** | Single-Packet SendInput M=0 Classification (C4) | **PASS** | `INTERNAL_LOGIC_VALIDATED` | 🟢 PASS |
| **P2B-11** | Partial Dispatch Inapplicability for N=1 (C4) | **PASS** | `INTERNAL_LOGIC_VALIDATED` | 🟢 PASS |
| **P2B-12** | Absolute Movement to Desktop Center | **PASS** | `LIVE_OS_VALIDATED` | 🟢 PASS |
| **P2B-13** | Top-Left Virtual Desktop Mapping | **PASS** | `LIVE_OS_VALIDATED` | 🟢 PASS |
| **P2B-14** | Bottom-Right Virtual Desktop Mapping | **PASS** | `LIVE_OS_VALIDATED` | 🟢 PASS |
| **P2B-15** | Negative-Origin Synthetic Topology Math | **PASS** | `SYNTHETICALLY_SIMULATED` | 🟢 PASS |
| **P2B-16** | Out-of-Bounds Movement Rejection | **PASS** | `LIVE_OS_VALIDATED` | 🟢 PASS |
| **P2B-17** | Cursor Readback Mismatch Classification (C3) | **PASS** | `INTERNAL_LOGIC_VALIDATED` | 🟢 PASS |
| **P2B-18** | Tolerance Multi-Point Verification (5 Points) (C5) | **PASS** | `LIVE_OS_VALIDATED` | 🟢 PASS |
| **P2B-19** | Pre-Dispatch Cancellation (CP1-CP4) | **PASS** | `LIVE_OS_VALIDATED` | 🟢 PASS |
| **P2B-20** | Post-Dispatch Cancellation (CP5-CP7) (C3) | **PASS** | `INTERNAL_LOGIC_VALIDATED` | 🟢 PASS |
| **P2B-21** | Phase 1 Regression Suite (14/14 Tests) | **PASS** | `LIVE_OS_VALIDATED` | 🟢 PASS |
| **P2B-22** | Phase 2A Regression Suite (10/10 Tests) | **PASS** | `LIVE_OS_VALIDATED` | 🟢 PASS |
| **P2B-23** | ActionCounter SendInput Instrumentation Verification | **PASS** | `LIVE_OS_VALIDATED` | 🟢 PASS |
| **P2B-24** | Zero-Click Non-Invasive Invariant Verification | **PASS** | `INTERNAL_LOGIC_VALIDATED` | 🟢 PASS |

---

## 3. Cursor Movement Latency & Accuracy Statistics

- **Total Live Movements Measured:** 6
- **Mean Latency:** 1573.63 us
- **Median Latency:** 1480.15 us
- **Min / Max Latency:** 979.3 us / 2288.0 us
- **Max Measured Delta X / Y:** 0px / 0px (All within configured +/- 1px tolerance)

---

## 4. Frozen Baseline Verification

```text
git diff ca87ef8 -- prototypes/prototype_a_workspace/ prototypes/prototype_b_human_takeover/ prototypes/prototype_c_keyboard/ prototypes/prototype_d_observation/
Result: 0 lines modified (Prototypes A, B, C, D 100% frozen)
```

---

## 5. Known Hardware & OS Subsystem Limitations

1. **Observable Evidence Boundary**: A successful SendInput return value records the number of input structures accepted by the API. It does not independently prove the time at which the requested cursor position becomes observable, uninterrupted cursor ownership, or any target-level task success. GetCursorPos provides a later point-in-time observation of the cursor position.
2. **Sensor Noise**: High-polling physical mice may introduce sub-pixel movement during test execution.
3. **Display Hardware Shifts**: Resolution changes during the sub-microsecond pre-dispatch window cannot be prevented in user-mode.
