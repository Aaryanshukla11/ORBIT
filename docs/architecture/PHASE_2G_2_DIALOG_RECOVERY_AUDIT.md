# Phase 2G.2 — Dialog Traps & Modal Recovery Engine Audit

## 1. Overview & Objectives

Phase 2G.2 introduces native modal dialog detection, classification, and targeted recovery mechanisms into ORBIT's cognitive execution loop (`AgentExecutionLoop` + `AgentRecoveryManager`).

When operating against native Windows applications (Notepad, Paint, Excel, Word, File Explorer, Web Browsers, Installers), modal dialogs frequently interrupt standard execution flows:
1. **File Overwrite / Collision Dialogs** (e.g. `Confirm Save As`, "file already exists. Do you want to replace it?")
2. **Discard Unsaved Changes Dialogs** (e.g. `Notepad`, "Do you want to save changes to Untitled?", "Don't Save")
3. **Error / Warning Alert Dialogs** (e.g. "Path not found", "Access Denied", "Invalid File Extension")
4. **Interactive Save-As Dialogs** requiring path confirmation.

Without dedicated dialog handling, general-purpose agents enter infinite loops or stall when unexpected modal windows capture desktop focus and block parent input.

---

## 2. Architecture & Implementation

### 2.1 Modal Dialog Detection (`ModalDialogDetector`)
- **File**: `src/orbit/runtime/cognitive/dialog_handler.py`
- Recognizes Win32 dialog window classes (`#32770`, `DirectUIHWND`, `OperationStatusWindow`, `Credential Dialog Xaml Host`, `TaskDialogDirectUIHWND`, `Shell_Dialog`).
- Inspects OCR text streams, window titles, and visible controls to classify dialog intent:
  - `FILE_COLLISION`: Identifies prompts asking to replace/overwrite an existing file.
  - `CONFIRM_DISCARD`: Identifies prompts asking whether to save or discard changes before closing.
  - `ERROR_ALERT`: Identifies alert/error boxes with Dismiss/OK buttons.
  - `SAVE_AS_PROMPT`: Identifies standard file save picker modals.

### 2.2 Deterministic Dialog Trap Handler (`DialogTrapHandler`)
- Synthesizes exact canonical actions to resolve modal blockers without requiring LLM re-prompting:
  - `OVERWRITE_FILE_COLLISION` $\to$ Synthesizes `CLICK('Yes')` or `CLICK('Replace')` with fallback to `SEND_HOTKEY('Alt+y')` / `SEND_HOTKEY('Enter')`.
  - `DISCARD_UNSAVED_CHANGES` $\to$ Synthesizes `CLICK("Don't Save")` with fallback to `SEND_HOTKEY('Alt+n')`.
  - `DISMISS_ALERT` $\to$ Synthesizes `CLICK('OK')` / `CLICK('Close')` with fallback to `SEND_HOTKEY('Escape')` / `SEND_HOTKEY('Enter')`.

### 2.3 Recovery Engine Integration (`AgentRecoveryManager`)
- **File**: `src/orbit/runtime/cognitive/recovery.py`
- Integrated into `diagnose_and_synthesize()`:
  - If a step failure occurs and a modal dialog is detected in the active window hierarchy, `AgentRecoveryManager` immediately selects the specialized dialog strategy (`RESOLVE_DIALOG_TRAP`, `OVERWRITE_FILE_COLLISION`, or `DISCARD_UNSAVED_CHANGES`).
  - Synthesizes the exact abstract action and passes it to the execution loop for immediate dispatch.

---

## 3. Verification & Gate Evidence

### 3.1 Unit Test Coverage
- `tests/unit/test_dialog_handler.py`:
  - `test_modal_dialog_detector_identifies_save_collision` (PASS)
  - `test_modal_dialog_detector_identifies_confirm_discard` (PASS)
  - `test_modal_dialog_detector_identifies_error_alert` (PASS)
  - `test_dialog_trap_handler_synthesizes_collision_action` (PASS)
  - `test_dialog_trap_handler_synthesizes_discard_action` (PASS)
  - `test_agent_recovery_manager_diagnoses_and_synthesizes_dialog_recovery` (PASS)

### 3.2 Closed-Loop Integration Test
- `tests/integration/test_dialog_recovery.py`:
  - `test_dialog_recovery_closed_loop_resolves_save_collision` (PASS)
  - Validates full closed-loop recovery: Step 0 encounters Save As collision modal $\to$ Transition verifier flags unverified effect $\to$ Recovery engine detects `#32770` dialog $\to$ Synthesizes `CLICK('Yes')` $\to$ Modal cleared $\to$ Step 1 succeeds and goal concludes.

---

## 4. Exit Gate Confirmation
- [x] Modal dialog detection operates over live Win32 classes & OCR.
- [x] Canonical dialog resolution strategies operational.
- [x] Full integration into `AgentExecutionLoop` and `AgentRecoveryManager`.
- [x] Zero regressions across existing test suite.
