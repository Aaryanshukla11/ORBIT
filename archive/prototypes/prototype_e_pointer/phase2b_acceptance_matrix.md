# ORBIT PROTOTYPE E — PHASE 2B FORMAL ACCEPTANCE MATRIX (P2B-1–P2B-22)
## Absolute Cursor Movement & Readback Verification (Architectural Revision v2.3.0)

**Document Version:** 2.3.0  
**Target Phase:** Phase 2B (Absolute Cursor Movement Only)  
**Host Platform:** Windows 11 Build 26200 AMD64 | Python 3.13.7  
**Frozen Baselines:** Prototypes A, B, C, D (Permanently Frozen)  

---

## 1. Acceptance Matrix Overview

The Phase 2B acceptance matrix defines **22 formal empirical verification tests (P2B-1 through P2B-22)** covering named flag composition (C1), structural topology identity separation (C2), external interference epistemic boundary (C3), single-packet dispatch honesty (C4), non-atomic readback tolerance (C5), ABI gating, and regression baselines.

---

## 2. Formal Acceptance Tests (P2B-1 to P2B-22)

| Test ID | Capability Tested | Preconditions & Target | Exact Action Executed | Observable Ground Truth | Expected Verdict | Reality Classification |
| :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| **P2B-1** | Named Flag Composition (C1) | Flag definitions | Evaluate bitwise OR composition | `MOUSEEVENTF_MOVE \| MOUSEEVENTF_ABSOLUTE \| MOUSEEVENTF_VIRTUALDESK` yields `0xC001` without magic numbers | **PASS** | `INTERNAL_LOGIC_VALIDATED` |
| **P2B-2** | Runtime ABI Gate Requirement | Uninitialized movement call | Invoke movement executor | `AbiGate.require_abi_valid()` verified before `SendInput` | **PASS** | `LIVE_OS_VALIDATED` |
| **P2B-3** | Zero-Action Rejection on Bad ABI | Simulated ABI mismatch | Attempt cursor movement | Rejects with `ABI_INVALID`; exactly 0 `SendInput` calls | **PASS** | `INTERNAL_LOGIC_VALIDATED` |
| **P2B-4** | Same Topology, Different Timestamps (C2 Case 1) | Same geometry, timestamps $T_1 \ne T_2$ | Evaluate pre-dispatch topology match | Identity matches; validation passes (`VALID`) | **PASS** | `INTERNAL_LOGIC_VALIDATED` |
| **P2B-5** | Virtual Desktop Width Mutation (C2 Case 2) | Topology with mutated width | Evaluate pre-dispatch topology match | Rejected with `REJECTED_TOPOLOGY_MUTATED`; 0 packets sent | **PASS** | `INTERNAL_LOGIC_VALIDATED` |
| **P2B-6** | Virtual Desktop Height Mutation (C2 Case 3) | Topology with mutated height | Evaluate pre-dispatch topology match | Rejected with `REJECTED_TOPOLOGY_MUTATED`; 0 packets sent | **PASS** | `INTERNAL_LOGIC_VALIDATED` |
| **P2B-7** | Virtual Desktop Origin Mutation (C2 Case 4) | Topology with mutated origin $(X, Y)$ | Evaluate pre-dispatch topology match | Rejected with `REJECTED_TOPOLOGY_MUTATED`; 0 packets sent | **PASS** | `INTERNAL_LOGIC_VALIDATED` |
| **P2B-8** | Monitor Count Mutation (C2 Case 5) | Topology with mutated monitor count | Evaluate pre-dispatch topology match | Rejected with `REJECTED_TOPOLOGY_MUTATED`; 0 packets sent | **PASS** | `INTERNAL_LOGIC_VALIDATED` |
| **P2B-9** | Single-Packet Dispatch M=1 (C4) | Single movement packet ($N=1$) | Win32 `SendInput` succeeds | Returns $M=1$; status `DISPATCH_ACCEPTED` | **PASS** | `LIVE_OS_VALIDATED` |
| **P2B-10**| Single-Packet Dispatch M=0 (C4) | Single movement packet ($N=1$) | Simulated Win32 `SendInput` returns 0 | Returns $M=0$; status `DISPATCH_ZERO`; zero retries | **PASS** | `INTERNAL_LOGIC_VALIDATED` |
| **P2B-11**| Partial Dispatch Inapplicability (C4) | Movement packet structure $N=1$ | Check partial dispatch model | Designated `DISPATCH_PARTIAL_NOT_APPLICABLE` for $N=1$ | **PASS** | `INTERNAL_LOGIC_VALIDATED` |
| **P2B-12**| Absolute Movement to Desktop Center | Desktop center $(x_c, y_c)$ | Dispatch absolute movement | `GetCursorPos()` reads $(x_c, y_c) \pm 1\text{px}$; status `MOVEMENT_VERIFIED` | **PASS** | `LIVE_OS_VALIDATED` |
| **P2B-13**| Top-Left Virtual Desktop Mapping | Top-left corner $(x_{\text{orig}}, y_{\text{orig}})$ | Dispatch absolute movement | `GetCursorPos()` reads $(x_{\text{orig}}, y_{\text{orig}}) \pm 1\text{px}$ | **PASS** | `LIVE_OS_VALIDATED` |
| **P2B-14**| Bottom-Right Virtual Desktop Mapping | Bottom-right corner $(W_v-1, H_v-1)$ | Dispatch absolute movement | `GetCursorPos()` reads $(W_v-1, H_v-1) \pm 1\text{px}$ | **PASS** | `LIVE_OS_VALIDATED` |
| **P2B-15**| Negative-Origin Synthetic Topology Math | Synthetic dual-monitor metrics | Normalize negative coordinates | Coords map to $0..65535$; zero underflow | **PASS** | `SYNTHETICALLY_SIMULATED` |
| **P2B-16**| Out-of-Bounds Movement Rejection | Coords $(99999, 99999)$ | Attempt cursor movement | Rejected with `REJECTED_OUT_OF_BOUNDS`; 0 `SendInput` calls | **PASS** | `LIVE_OS_VALIDATED` |
| **P2B-17**| Cursor Readback Mismatch Classification (C3) | Simulated readback delta $> 1\text{px}$ | Evaluate post-dispatch outcome | Status `CURSOR_READBACK_MISMATCH` with diagnostic `EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE` (no takeover overclaim) | **PASS** | `INTERNAL_LOGIC_VALIDATED` |
| **P2B-18**| Tolerance Multi-Point Verification (C5) | 5 distinct grid coordinates | Move to each coordinate | All 5 readbacks satisfy $|x_{\text{obs}}-x_{\text{req}}| \le 1\text{px}, |y_{\text{obs}}-y_{\text{req}}| \le 1\text{px}$ | **PASS** | `LIVE_OS_VALIDATED` |
| **P2B-19**| Pre-Dispatch Cancellation (CP1–CP4) | Token cancelled before gate | Attempt movement | Status `CANCELLED_BEFORE_DISPATCH`; 0 `SendInput` calls | **PASS** | `LIVE_OS_VALIDATED` |
| **P2B-20**| Post-Dispatch Cancellation (CP5–CP7) (C3) | Token cancelled after SendInput | Complete movement cycle | Status recorded as `CANCELLED_AFTER_DISPATCH` without claiming movement prevention | **PASS** | `INTERNAL_LOGIC_VALIDATED` |
| **P2B-21**| Phase 1 Regression Suite | Phase 1 test suite runner | Execute P1–P14 suite | 14 / 14 Passed (0 Regressions) | **PASS** | `LIVE_OS_VALIDATED` |
| **P2B-22**| Phase 2A Regression Suite | Phase 2A test suite runner | Execute P2A-1–P2A-10 suite | 10 / 10 Passed (0 Regressions) | **PASS** | `LIVE_OS_VALIDATED` |

---

## 3. Mandatory Acceptance Coverage Audit Summary

1. **Same topology identity with different observation timestamps**: Tested in **P2B-4** (PASS).
2. **Virtual origin mutation detection**: Tested in **P2B-7** (PASS).
3. **Width mutation detection**: Tested in **P2B-5** (PASS).
4. **Height mutation detection**: Tested in **P2B-6** (PASS).
5. **Monitor-count mutation detection**: Tested in **P2B-8** (PASS).
6. **Single-packet SendInput M=0 classification**: Tested in **P2B-10** (PASS).
7. **Single-packet SendInput M=1 classification**: Tested in **P2B-9** (PASS).
8. **Explicit documentation that partial dispatch is not applicable when N=1**: Tested in **P2B-11** (PASS).
9. **Cursor readback mismatch without assigning a human cause**: Tested in **P2B-17** (PASS).
10. **Post-dispatch readback matching requested destination within tolerance**: Tested in **P2B-12**, **P2B-13**, **P2B-14**, **P2B-18** (PASS).
11. **Post-dispatch cancellation classification without claiming prevention**: Tested in **P2B-20** (PASS).
12. **Named flag composition verification without magic-number dependency**: Tested in **P2B-1** (PASS).
