# Phase 3C — Native Multi-Application Window Orchestrator Audit

## 1. Executive Summary & Objective

Phase 3C implements the Multi-Application Window Orchestrator (`MultiAppWindowOrchestrator`) for ORBIT's runtime.

Real-world computer use tasks (matching OpenAI Astra 6) span multiple applications simultaneously (e.g. Browser $\to$ Spreadsheet $\to$ Text Editor $\to$ Terminal). This requires:
1. **Multi-Window Tracking**: Synchronizing window state (`hwnd`, `bounds`, `process_name`, `title`, `is_focused`) against live perception snapshots.
2. **Deterministic Tiling Layouts**: Computing precise screen coordinate bounding boxes for Fullscreen, Split-Left, Split-Right, Side-by-Side, and Quad-Grid arrangements.
3. **Cross-Application Focus Switching**: Synthesizing verified `FOCUS_WINDOW` actions.
4. **Inter-Application Clipboard Pipeline**: Seamlessly transferring text and structured data across isolated application contexts.

---

## 2. Architecture & Components

### 2.1 Multi-App Window Orchestrator (`MultiAppWindowOrchestrator`)
- **File**: `src/orbit/runtime/cognitive/window_orchestrator.py`
- Implements `update_from_observation()` to track all visible and foreground application windows.
- Implements `calculate_tile_geometry()` for deterministic pixel partitioning.
- Implements `synthesize_focus_action()` targeting specific applications by name or HWND.
- Implements `set_clipboard()`, `get_clipboard()`, and `synthesize_paste_action()`.

---

## 3. Verification & Gate Evidence

### 3.1 Unit Test Coverage
- `tests/unit/test_window_orchestrator.py`:
  - `test_window_orchestrator_updates_tracked_windows` (PASS)
  - `test_window_orchestrator_tile_geometry_calculation` (PASS)
  - `test_window_orchestrator_synthesizes_focus_action` (PASS)
  - `test_window_orchestrator_clipboard_pipeline` (PASS)

### 3.2 Closed-Loop Integration Test
- `tests/integration/test_multi_app_orchestration.py`:
  - `test_cross_app_window_orchestration_closed_loop` (PASS)
  - Validates full end-to-end data transfer: Chrome $\to$ Clipboard $\to$ Notepad focus switch $\to$ Paste $\to$ Multi-modal verification.

---

## 4. Exit Gate Certification
- [x] Multi-window tracking operational.
- [x] Tiling geometry calculations verified.
- [x] Focus action synthesis operational.
- [x] Inter-application clipboard pipeline verified.
- [x] Closed-loop multi-application workflow passing.
