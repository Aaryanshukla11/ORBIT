# ORBIT Milestone M1.5 Step 2: Native AppBar Driver & Window Positioning Pre-Implementation Audit

**Milestone**: M1.5 — Production Workspace / AppBar Integration  
**Step**: Step 2 — Native AppBar Driver & Window Positioning (Pre-Implementation Audit)  
**Status**: **AUDIT COMPLETE — READY FOR STEP 2 IMPLEMENTATION**  
**Date**: September 6, 2026  
**Host Environment**: Windows 11 CoreSingleLanguage AMD64 (Build 10.0.26200), Python 3.13.7  
**Baseline Frozen Commit**: `ca87ef8`

---

## 1. Executive Summary & Purpose

Milestone **M1.5 Step 2** implements the **Native AppBar Driver and Window Positioning** layer under `src/orbit/adapters/workspace/`. This layer provides the concrete Win32 window lifecycle management, `SHAppBarMessage` transactional registration (`ABM_NEW`, `ABM_QUERYPOS`, `ABM_SETPOS`, `ABM_REMOVE`), coordinate positioning via `SetWindowPos`, callback message routing, and fail-closed rollback.

This document serves as the formal pre-implementation audit establishing exact API signatures, handle ownership boundaries, failure/rollback semantics, thread-affinity rules, and multi-monitor / DPI coordinate preservation.

---

## 2. Win32 & Shell32 API Inventory

All native operations required for Step 2 are defined with explicit 64-bit AMD64 calling conventions in `src/orbit/adapters/workspace/abi.py`:

| API Name | DLL | C Signature | Purpose in Step 2 | Error Handling Strategy |
| :--- | :--- | :--- | :--- | :--- |
| `SHAppBarMessage` | `shell32.dll` | `UINT_PTR SHAppBarMessage(DWORD dwMessage, PAPPBARDATA pData);` | Dispatches `ABM_NEW`, `ABM_QUERYPOS`, `ABM_SETPOS`, `ABM_REMOVE` to Windows Shell (`Explorer.exe`). | Returns `0` / `FALSE` on failure. Checked explicitly on each call. |
| `RegisterClassExW` | `user32.dll` | `ATOM RegisterClassExW(const WNDCLASSEXW *unnamedParam1);` | Registers the window class for the AppBar window with custom `WNDPROC`. | Returns `0` on failure; checks `kernel32.GetLastError()`. |
| `UnregisterClassW` | `user32.dll` | `BOOL UnregisterClassW(LPCWSTR lpClassName, HINSTANCE hInstance);` | Cleans up registered window class on window destruction. | Returns non-zero `TRUE` on success. |
| `CreateWindowExW` | `user32.dll` | `HWND CreateWindowExW(DWORD dwExStyle, LPCWSTR lpClassName, LPCWSTR lpWindowName, DWORD dwStyle, int X, int Y, int nWidth, int nHeight, HWND hWndParent, HMENU hMenu, HINSTANCE hInstance, LPVOID lpParam);` | Creates top-level borderless window (`WS_EX_TOPMOST \| WS_POPUP \| WS_VISIBLE`). | Returns `NULL` (0) on failure. Fail-closed. |
| `DestroyWindow` | `user32.dll` | `BOOL DestroyWindow(HWND hWnd);` | Destroys native window handle. | Returns `TRUE` on success; verifies window is gone via `IsWindow()`. |
| `SetWindowPos` | `user32.dll` | `BOOL SetWindowPos(HWND hWnd, HWND hWndInsertAfter, int X, int Y, int cx, int cy, UINT uFlags);` | Positions window at negotiated coordinates with `HWND_TOPMOST` and `SWP_NOACTIVATE \| SWP_SHOWWINDOW`. | Returns `TRUE` on success. |
| `GetWindowRect` | `user32.dll` | `BOOL GetWindowRect(HWND hWnd, LPRECT lpRect);` | Reads current physical window bounds for verification. | Returns `TRUE` on success. |
| `DefWindowProcW` | `user32.dll` | `LRESULT DefWindowProcW(HWND hWnd, UINT Msg, WPARAM wParam, LPARAM lParam);` | Default message handler for non-AppBar messages. | Standard default return. |
| `IsWindow` | `user32.dll` | `BOOL IsWindow(HWND hWnd);` | Verifies whether HWND is a live valid window. | Returns `TRUE` if live, `FALSE` if dead/invalid. |

---

## 3. HWND & Window Ownership Model

1. **Window Identity**: Each `NativeWorkspaceWindow` instance owns exactly one Win32 `HWND`.
2. **Class Registration**: A unique class name (`OrbitWorkspaceWindow_<uuid>`) is registered per window instance to avoid class name collisions.
3. **Thread Ownership**: The window and its `WNDPROC` are created and managed on the native workspace thread or host UI thread.
4. **Lifecycle Guarantee**:
   - Window creation is strictly pair-matched with `DestroyWindow` and `UnregisterClassW`.
   - Repeated create/destroy cycles must leave zero dangling `ATOM` or `HWND` references.
   - If window creation fails, the class is unregistered immediately and an exception is raised.

---

## 4. `APPBARDATA` Lifecycle & Callback Strategy

### 4.1 `APPBARDATA` Construction
On 64-bit AMD64, `APPBARDATA` is 48 bytes:
```python
abd = APPBARDATA()
abd.cbSize = 48  # ctypes.sizeof(APPBARDATA)
abd.hWnd = self.hwnd
abd.uCallbackMessage = WM_APPBAR_CALLBACK  # WM_USER + 101 (0x0465)
abd.uEdge = edge_constant  # ABE_RIGHT (2), ABE_LEFT (0), etc.
abd.rc = requested_rect
abd.lParam = 0
```

### 4.2 Callback Message Strategy
- `uCallbackMessage = WM_APPBAR_CALLBACK` (`WM_USER + 101`).
- The window procedure (`WNDPROC`) intercepts `msg == WM_APPBAR_CALLBACK`.
- `wParam` contains the notification code:
  - `ABN_STATECHANGE (0)`: Taskbar autohide / state changed.
  - `ABN_POSCHANGED (1)`: Another AppBar resized or screen resolution changed.
  - `ABN_FULLSCREENAPP (2)`: A fullscreen application opened/closed.
  - `ABN_WINDOWARRANGE (3)`: User arranged windows (e.g. Cascade/Side-by-side).
- Notifications are recorded in a thread-safe telemetry buffer without blocking the message pump.

---

## 5. Transactional Registration & Removal Lifecycle

### 5.1 Registration Flow (`register_and_dock`)

```
[Start Registration]
        │
        ▼
1. Validate / Create Window ────(Fail)───> [Rollback: Destroy Window, State -> FAILED]
        │
        ▼
2. Transition State: REGISTERING
        │
        ▼
3. SHAppBarMessage(ABM_NEW) ────(Fail)───> [Rollback: Destroy Window, State -> FAILED]
        │
        ▼
4. SHAppBarMessage(ABM_QUERYPOS) ─(Fail)─> [Rollback: ABM_REMOVE + Destroy Window, State -> FAILED]
        │
        ▼
5. Geometry Re-clamping (honor shell proposals)
        │
        ▼
6. SHAppBarMessage(ABM_SETPOS) ───(Fail)───> [Rollback: ABM_REMOVE + Destroy Window, State -> FAILED]
        │
        ▼
7. SetWindowPos(HWND_TOPMOST, negotiated rc) ─(Fail)─> [Rollback: ABM_REMOVE + Destroy Window, State -> FAILED]
        │
        ▼
8. Transition State: DOCKED (desktop_generation_id incremented)
        │
        ▼
[Return Success Operation Result]
```

### 5.2 Removal Flow (`unregister_and_release`)

```
[Start Unregistration]
        │
        ▼
1. Check if registered ──(Not registered)──> [Return Idempotent Success]
        │
        ▼
2. Transition State: RELEASING
        │
        ▼
3. SHAppBarMessage(ABM_REMOVE) ───(Fail)───> [State -> DEGRADED, Record Error]
        │
        ▼
4. Transition State: READY_FLOATING (desktop_generation_id incremented)
        │
        ▼
5. Destroy / Float Window (Optional based on retain flag)
        │
        ▼
[Return Success Operation Result]
```

---

## 6. Multi-Monitor & DPI Coordinate Rules

1. **Virtual Desktop Coordinates**: Window positioning uses exact physical desktop coordinates derived from `EnumDisplayMonitors` / `GetMonitorInfoW`.
2. **Negative Coordinates**: If a secondary monitor is positioned to the left or above the primary display, its coordinates will have negative `left` or `top` values (e.g. `left = -1920`). The driver must strictly preserve signed integer arithmetic.
3. **Negotiated Rect vs Synthetic Calculations**: `SetWindowPos` uses the `abd.rc` returned by `ABM_SETPOS` rather than independently guessing bounds.

---

## 7. Desktop Generation Accounting

- The state manager's `desktop_generation_id` remains the single authoritative generation counter.
- Generation increments occur atomically when transitioning:
  - `REGISTERING` $\to$ `DOCKED` (Dock committed)
  - `DOCKED` $\to$ `RELEASING` / `READY_FLOATING` (Undock committed)
  - `DOCKED` $\to$ `REGISTERING` (In-place reconfiguration)
- Zero competing or uncoordinated generation counters.

---

## 8. Thread Ownership & Platform Abstraction

- **Native Dispatch Gateway**: Native Win32 operations are encapsulated behind a `NativeWin32Gateway` class.
- **Dependency Injection**: `NativeAppBarDriver` accepts an optional `win32_gateway` instance, enabling 100% deterministic unit testing with mock gateways on non-Windows platforms or in CI without OS window dependencies.
- **Fail-Fast on Unsupported Platforms**: If run on a non-Windows OS with default gateway, the driver reports `UNSUPPORTED_PLATFORM` and fails closed safely.

---

## 9. Conclusion

The audit is complete. The boundary for Step 2 is strictly defined:
- Implement `NativeWorkspaceWindow` in `src/orbit/adapters/workspace/window.py`.
- Implement `NativeAppBarDriver` in `src/orbit/adapters/workspace/appbar.py`.
- Implement comprehensive unit tests in `tests/unit/test_workspace_appbar.py` and `tests/unit/test_workspace_window.py`.
- Verify full regression suite and 0-diff frozen boundary.
