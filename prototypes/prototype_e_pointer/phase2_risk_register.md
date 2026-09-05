# ORBIT PROTOTYPE E — PHASE 2 FAILURE MATRIX & RISK REGISTER (F16–F34)
## Failure Modes, Detection Mechanisms, System Responses & Boundaries (Updated C1–C6)

**Document Version:** 2.1.0  
**Target Phase:** Phase 2 (Safe Pointer Action & Click Execution Engine)  

---

## 1. Phase 2 Critical Failure Matrix (F16–F34)

| Scenario ID | Failure Condition | Detection Mechanism | Immediate System Response | Pointer State Consequence | Future Actions Blocked? | Truthful Classification |
| :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| **F16** | `SendInput` returns 0 | Return value $M == 0$ | Abort dispatch; query `GetLastError()` | `_orbit_left_down` remains False | NO | `SENDINPUT_FAILED` |
| **F17** | Partial click dispatch ($0 < M < N$) | Return value $0 < M < N$ | Emit emergency `MOUSEEVENTF_LEFTUP` | `PARTIAL_DISPATCH` $\to$ `SANITIZED` | NO (if sanitized) | `PARTIAL_DISPATCH_RECOVERED` |
| **F18** | Sanitization UP fails ($M=0$) | Emergency UP returns 0 | Transition to `UNRESOLVED_LOCKED` | `ORBIT_INTERNAL_STATE_UNRESOLVED` | **YES (HARD LOCK)** | `UNRESOLVED_POINTER_STATE` |
| **F19** | Cancellation before dispatch | `token.is_cancelled` at CP5 | Drop dispatch immediately (0 packets) | State remains `IDLE` | NO | `CANCELLED_BEFORE_DISPATCH` |
| **F20** | Cancellation between stages | `token.is_cancelled` at CP6/CP7 | Abort subsequent stages | State remains `IDLE` | NO | `CANCELLED_BETWEEN_STAGES` |
| **F21** | Cancellation after DOWN | `token.is_cancelled` at CP8 | Immediate `sanitize_orbit_buttons()` | Emits synthetic UP; clears bitmask | NO | `CANCELLED_DURING_HOLD` |
| **F22** | Human takeover during motion | `WH_MOUSE_LL` hook velocity delta | Trajectory halted in $< 1\text{ms}$ | Motion ceases immediately | NO | `MOVE_INTERRUPTED_TAKEOVER` |
| **F23** | Human button interference | Hook detects physical click | Sets cancellation token; aborts ORBIT | Emits UP if ORBIT held button | NO | `CANCELLED_USER_INTERFERENCE` |
| **F24** | Cursor verification mismatch | `GetCursorPos()` delta $> 1\text{px}$ | Log position discrepancy | Motion completed to unverified coord | NO | `MOVE_DISPATCHED_POSITION_CHANGED` |
| **F25** | Target HWND destroyed | `IsWindow(hwnd) == False` at gate | Reject action; 0 SendInput | State remains `IDLE` | NO | `REJECTED_HWND_DESTROYED` |
| **F26** | PID identity mismatch | `GetWindowThreadProcessId` mismatch | Reject action; 0 SendInput | State remains `IDLE` | NO | `REJECTED_PID_MISMATCH` |
| **F27** | Foreground focus changed | `GetForegroundWindow` mismatch | Reject action; 0 SendInput | State remains `IDLE` | NO | `REJECTED_FOREGROUND_LOST` |
| **F28** | Snapshot TTL expired | Age $> \text{validity\_ttl\_ms}$ | Reject action; 0 SendInput | State remains `IDLE` | NO | `REJECTED_TTL_EXPIRED` |
| **F29** | Desktop generation changed | `live_gen != source_gen` | Reject action; 0 SendInput | State remains `IDLE` | NO | `REJECTED_STALE_GENERATION` |
| **F30** | Display topology changed | Topology fingerprint mismatch | Reject action; 0 SendInput | State remains `IDLE` | NO | `REJECTED_TOPOLOGY_MUTATED` |
| **F31** | DPI configuration changed | DPI awareness context mismatch | Re-initialize / re-normalize | Normalization refreshed | NO | `REJECTED_DPI_MUTATED` |
| **F32** | Target window minimized | `IsIconic(hwnd) == True` at gate | Reject action; 0 SendInput | State remains `IDLE` | NO | `REJECTED_WINDOW_MINIMIZED` |
| **F33** | Elevated target permission | Target PID is elevated; 0 mutation | Layer 4 OK, Layer 7 unchanged | State remains `IDLE` | NO | `PERMISSION_RESTRICTION_POSSIBLE` |
| **F34** | Post-dispatch effect absent | Target callback does not fire | Log Layer 4 OK, Layer 7 Failed | State returns to `IDLE` cleanly | NO | `TARGET_EFFECT_NOT_OBSERVED` |

---

## 2. Hard Safety Lockout Invariant (Correction C4)

If scenario **F18** (`UNRESOLVED_POINTER_STATE`) occurs:
- The `PointerStateManager` enters a locked state: `is_locked_unresolved = True`.
- Telemetry records the exact internal failure timestamp, button type, and error code.
- All subsequent pointer movements, clicks, and button-down requests are immediately rejected with `UNRESOLVED_POINTER_STATE`.
- Automatic unlocks on timer resets or new actions are strictly prohibited.
