# ORBIT PROTOTYPE E — PHASE 2B FAILURE MATRIX & RISK REGISTER
## Absolute Cursor Movement Hazards, Boundaries & Mitigations (Architectural Revision v2.3.0)

**Document Version:** 2.3.0  
**Target Phase:** Phase 2B (Absolute Cursor Movement Only)  

---

## 1. Phase 2B Failure Matrix & Risk Register

| Risk ID | Triggering Condition | What Can Be Observed | What Cannot Be Known | Architectural Mitigation | Residual Limitation | Prohibited Overclaim |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **R-2B-1** | Display topology mutates before dispatch | `get_topology_identity()` mismatch against initial observation | Kernel screen re-layout occurring during `SendInput` call | Pre-dispatch structural identity comparison rejects with `REJECTED_TOPOLOGY_MUTATED` | Sub-microsecond topology shift during kernel execution | "Topology validation guarantees zero movement race" |
| **R-2B-2** | DPI scaling mismatch across monitors | Process DPI context differs from PMv2 | Per-window DPI virtualization without window handle | Explicit `DpiManager` Per-Monitor V2 initialization on startup | Host process locking DPI context prior to ORBIT initialization | "ORBIT works on arbitrary DPI without PMv2" |
| **R-2B-3** | Cursor readback delta exceeds tolerance $\pm 1\text{px}$ | `GetCursorPos()` differs from requested destination | True cause (human hand, OS acceleration, external app, display clamping) | Status `CURSOR_READBACK_MISMATCH` with diagnostic `EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE` | Readback reflects only final position at $T_5$, not intermediate cause | "Readback mismatch proves human takeover" |
| **R-2B-4** | Cancellation signal during dispatch | `token.is_cancelled` state | Kernel execution pipeline state at moment of signal | Checkpoints CP1–CP4 drop dispatch; CP5–CP7 record `CANCELLED_AFTER_DISPATCH` | In-flight User32 packets cannot be recalled | "Cancellation after SendInput prevented cursor movement" |
| **R-2B-5** | `SendInput` returns 0 for $N=1$ packet | Return value $M == 0$, `GetLastError()` | Specific internal User32 rejection reason if 0 | Log `DISPATCH_ZERO` / `SENDINPUT_FAILED`; zero automatic retries | Non-elevated ORBIT controlling elevated desktop window | "SendInput always succeeds on valid coords" |
| **R-2B-6** | Sub-pixel quantization variance | `GetCursorPos()` delta == $1\text{px}$ | Sub-pixel cursor position inside physical pixel | Formal $\le 1\text{px}$ tolerance acceptance criteria | Discrete integer screen grid quantization | "Movement achieves exact 0.0px float equality" |
| **R-2B-7** | Target coordinate out of virtual screen | Coordinate validator bounds check | Virtual desktop bounding box | Explicit rejection with `REJECTED_OUT_OF_BOUNDS`; 0 `SendInput` calls | Single-monitor host requires synthetic geometry simulation | "Out-of-bounds coordinates can be safely clamped without error" |
| **R-2B-8** | ABI structure size/offset mismatch | `AbiGate` verification check | C compiler struct padding on non-AMD64 platforms | Fail-closed `AbiGate` throws `RuntimeError` on mismatch | 32-bit Python / ARM64 not supported | "x64 ABI definitions work on any architecture" |
| **R-2B-9** | Magic number dependency in input flags | Flag bitmask construction | Bitwise arithmetic equivalence | Named bitwise OR `MOUSEEVENTF_MOVE \| MOUSEEVENTF_ABSOLUTE \| MOUSEEVENTF_VIRTUALDESK` | None (enforced by constant definitions) | "0xC001 is an independent magic constant contract" |
| **R-2B-10**| Movement failure automatic retry | Stale coordinate re-injected | Human user's intended focus at moment of retry | Hard ban on automatic movement retries; report failure cleanly | Higher-level planner must request fresh observation | "Automatic retries make movement reliable" |
| **R-2B-11**| False topology rejection from timestamp delta | Observation timestamp changed but geometry identical | Timing jitter in observation polling | Compare `VirtualDesktopTopologyIdentity` only, excluding timestamps | None (structural identity comparison) | "Topology comparison requires identical observation timestamps" |
| **R-2B-12**| Non-atomic trajectory assumption ($T_1 \to T_5$) | `GetCursorPos()` observed at $T_5$ | Path traveled by cursor or external events between $T_4$ and $T_5$ | Disclose non-atomic timeline; define `MOVEMENT_VERIFIED` strictly as arrival observation | Hardware pointer acceleration or micro-delays | "MOVEMENT_VERIFIED proves exclusive continuous trajectory control" |

---

## 2. Invariant Summary for Phase 2B

1. **Layer 4 vs Layer 5 Separation**: `SendInput` return value $1$ (`DISPATCH_ACCEPTED`) is **never** treated as proof of cursor arrival (`MOVEMENT_VERIFIED`). Cursor arrival must be independently observed via `GetCursorPos()`.
2. **Epistemic Modesty**: Cursor readback mismatch is classified as `CURSOR_READBACK_MISMATCH` with `EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE`, never asserting human takeover without hook confirmation.
3. **Single-Packet Dispatch Semantics**: For $N=1$, return is strictly $M=0$ (`DISPATCH_ZERO`) or $M=1$ (`DISPATCH_ACCEPTED`).
4. **Structural Topology Identity**: Pre-dispatch topology validation compares display geometry (`VirtualDesktopTopologyIdentity`) only, ignoring timestamp differences.
5. **Zero Magic Numbers**: All flags composed via named Win32 constants.
