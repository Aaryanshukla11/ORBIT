# ORBIT 50-TASK GENERAL RELIABILITY BENCHMARK REPORT
**Execution Date**: 2026-09-16 04:53:21 UTC  
**Total Tasks Evaluated**: 50 (25 Development + 25 Unseen)  
**Overall Success Rate**: **0.0%** (0/50)  

---

## 1. Primary Baseline Metrics

| Metric | Value | Target | Evaluation |
| :--- | :--- | :--- | :--- |
| **Overall Task Success Rate** | **0.0%** | $\ge 80\%$ | BASELINE ESTABLISHED |
| **Development Split Success Rate** | **0.0%** | $\ge 85\%$ | BASELINE ESTABLISHED |
| **Unseen Split Success Rate** | **0.0%** | $\ge 75\%$ | BASELINE ESTABLISHED |
| **Goal Verification Accuracy** | **32.0%** | $100\%$ | CALIBRATING |
| **Artifact Correctness Rate** | **60.0%** | $100\%$ | CALIBRATING |
| **Grounding Precision** | **100.0%** | $\ge 90\%$ | PASS |
| **Average Execution Time / Task** | **0.31s** | $< 45s$ | FAST |
| **Average Model Calls / Task** | **1.0** | $< 5.0$ | OPTIMAL |

---

## 2. 15-Class Failure Taxonomy Distribution

| Failure Category | Count | Percentage of Failures | Root Cause Remediation Phase |
| :--- | :--- | :--- | :--- |
| `INTENT_ERROR` | 30 | 60.0% | **Phase 2G.1 (Context)** |
| `SAVE_PERSISTENCE_ERROR` | 20 | 40.0% | **Phase 2G.4 (Artifacts)** |

---

## 3. Performance by Desktop Category

| Category | Success Rate | Status |
| :--- | :--- | :--- |
| `APPLICATION_LAUNCH` | **0.0%** | RED |
| `ARTIFACT_VALIDATION` | **0.0%** | RED |
| `BROWSER_INSPECTION` | **0.0%** | RED |
| `DIALOG_HANDLING` | **0.0%** | RED |
| `FILESYSTEM` | **0.0%** | RED |
| `LONG_HORIZON` | **0.0%** | RED |
| `MIXED_WORKFLOW` | **0.0%** | RED |
| `MULTI_APP_WORKFLOW` | **0.0%** | RED |
| `MULTI_STEP_EDITING` | **0.0%** | RED |
| `PAINT_CANVAS` | **0.0%** | RED |
| `SAVE_EXPORT` | **0.0%** | RED |
| `STATE_RECOVERY` | **0.0%** | RED |
| `TEXT_ENTRY` | **0.0%** | RED |
| `UI_INTERACTION` | **0.0%** | RED |
| `VISUAL_GROUNDING` | **0.0%** | RED |

---

## 4. Full Task-by-Task Manifest Results

| Task ID | Split | Category | Goal | Success | Goal Verif | Artifact Verif | Time | Failure Code |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `task_001` | DEV | `APPLICATION_LA` | Open Notepad... | *FAIL* | FAIL | PASS | 0.45s | `INTENT_ERROR` |
| `task_002` | DEV | `APPLICATION_LA` | Open Paint... | *FAIL* | FAIL | PASS | 0.21s | `INTENT_ERROR` |
| `task_003` | DEV | `TEXT_ENTRY` | Open Notepad and type 'ORBIT Native... | *FAIL* | FAIL | PASS | 0.21s | `INTENT_ERROR` |
| `task_004` | DEV | `TEXT_ENTRY` | Open Notepad and type: Project: ORB... | *FAIL* | FAIL | PASS | 0.21s | `INTENT_ERROR` |
| `task_005` | DEV | `UI_INTERACTION` | Open Notepad and click on Help then... | *FAIL* | FAIL | PASS | 0.2s | `INTENT_ERROR` |
| `task_006` | DEV | `UI_INTERACTION` | Open Notepad and toggle Word Wrap f... | *FAIL* | FAIL | PASS | 0.2s | `INTENT_ERROR` |
| `task_007` | DEV | `FILESYSTEM` | Create a new folder named 'ORBIT_Te... | *FAIL* | PASS | FAIL | 0.2s | `SAVE_PERSISTENCE_ERROR` |
| `task_008` | DEV | `FILESYSTEM` | Create a file named 'fs_test.txt' c... | *FAIL* | PASS | FAIL | 0.19s | `SAVE_PERSISTENCE_ERROR` |
| `task_009` | DEV | `SAVE_EXPORT` | Open Notepad, type 'Autonomous Save... | *FAIL* | PASS | FAIL | 0.2s | `SAVE_PERSISTENCE_ERROR` |
| `task_010` | DEV | `SAVE_EXPORT` | Open Paint, draw a line on canvas, ... | *FAIL* | PASS | FAIL | 0.18s | `SAVE_PERSISTENCE_ERROR` |
| `task_011` | DEV | `PAINT_CANVAS` | Open Paint and draw a rectangle on ... | *FAIL* | FAIL | PASS | 0.3s | `INTENT_ERROR` |
| `task_012` | DEV | `PAINT_CANVAS` | Open Paint, select the Red color fr... | *FAIL* | FAIL | PASS | 0.2s | `INTENT_ERROR` |
| `task_013` | DEV | `BROWSER_INSPEC` | Open Microsoft Edge... | *FAIL* | FAIL | PASS | 0.19s | `INTENT_ERROR` |
| `task_014` | DEV | `BROWSER_INSPEC` | Open Microsoft Edge and click the a... | *FAIL* | FAIL | PASS | 0.33s | `INTENT_ERROR` |
| `task_015` | DEV | `MULTI_APP_WORK` | Open Calculator, then open Notepad... | *FAIL* | FAIL | PASS | 0.18s | `INTENT_ERROR` |
| `task_016` | DEV | `MULTI_STEP_EDI` | Open Notepad, type 'Header line', a... | *FAIL* | PASS | FAIL | 0.19s | `SAVE_PERSISTENCE_ERROR` |
| `task_017` | DEV | `DIALOG_HANDLIN` | Open Notepad, type some unsaved tex... | *FAIL* | FAIL | PASS | 0.19s | `INTENT_ERROR` |
| `task_018` | DEV | `DIALOG_HANDLIN` | Open Notepad, click File -> Open, a... | *FAIL* | FAIL | PASS | 0.19s | `INTENT_ERROR` |
| `task_019` | DEV | `VISUAL_GROUNDI` | Open Paint and click on the Brushes... | *FAIL* | FAIL | PASS | 0.18s | `INTENT_ERROR` |
| `task_020` | DEV | `STATE_RECOVERY` | Open Notepad, click Desktop to unfo... | *FAIL* | FAIL | PASS | 0.19s | `INTENT_ERROR` |
| `task_021` | DEV | `LONG_HORIZON` | Open Notepad, write 5 bulleted stat... | *FAIL* | FAIL | FAIL | 0.19s | `SAVE_PERSISTENCE_ERROR` |
| `task_022` | DEV | `ARTIFACT_VALID` | Create a file named 'config.json' w... | *FAIL* | PASS | FAIL | 0.21s | `SAVE_PERSISTENCE_ERROR` |
| `task_023` | DEV | `MIXED_WORKFLOW` | Open Paint, draw a shape, save as '... | *FAIL* | FAIL | FAIL | 0.31s | `SAVE_PERSISTENCE_ERROR` |
| `task_024` | DEV | `MIXED_WORKFLOW` | Create 'temp_draft.txt' with text '... | *FAIL* | PASS | FAIL | 0.39s | `SAVE_PERSISTENCE_ERROR` |
| `task_025` | DEV | `MIXED_WORKFLOW` | Open Notepad, Calculator, and Paint... | *FAIL* | FAIL | PASS | 0.24s | `INTENT_ERROR` |
| `task_026` | UNS | `APPLICATION_LA` | Start Calculator... | *FAIL* | FAIL | PASS | 0.34s | `INTENT_ERROR` |
| `task_027` | UNS | `APPLICATION_LA` | Launch Microsoft Edge... | *FAIL* | FAIL | PASS | 0.26s | `INTENT_ERROR` |
| `task_028` | UNS | `TEXT_ENTRY` | Open Notepad and type: 100, 200, 30... | *FAIL* | FAIL | PASS | 0.28s | `INTENT_ERROR` |
| `task_029` | UNS | `TEXT_ENTRY` | Open Notepad and enter: def test():... | *FAIL* | FAIL | PASS | 0.87s | `INTENT_ERROR` |
| `task_030` | UNS | `UI_INTERACTION` | Open Notepad, open View menu, and t... | *FAIL* | FAIL | PASS | 1.18s | `INTENT_ERROR` |
| `task_031` | UNS | `UI_INTERACTION` | Open Notepad and navigate to Font s... | *FAIL* | FAIL | PASS | 0.18s | `INTENT_ERROR` |
| `task_032` | UNS | `FILESYSTEM` | Create folder 'data' and inside it ... | *FAIL* | PASS | FAIL | 0.2s | `SAVE_PERSISTENCE_ERROR` |
| `task_033` | UNS | `FILESYSTEM` | Create a markdown file 'summary.md'... | *FAIL* | PASS | FAIL | 0.37s | `SAVE_PERSISTENCE_ERROR` |
| `task_034` | UNS | `SAVE_EXPORT` | Open Notepad, write 'SYSTEM_BOOT_SU... | *FAIL* | PASS | FAIL | 0.32s | `SAVE_PERSISTENCE_ERROR` |
| `task_035` | UNS | `SAVE_EXPORT` | Open Paint, draw a line, and save t... | *FAIL* | PASS | FAIL | 0.52s | `SAVE_PERSISTENCE_ERROR` |
| `task_036` | UNS | `PAINT_CANVAS` | Open Paint, select the Triangle sha... | *FAIL* | FAIL | PASS | 0.71s | `INTENT_ERROR` |
| `task_037` | UNS | `PAINT_CANVAS` | Open Paint, select the Fill with co... | *FAIL* | FAIL | PASS | 0.44s | `INTENT_ERROR` |
| `task_038` | UNS | `BROWSER_INSPEC` | Open Edge, click the URL input bar,... | *FAIL* | FAIL | PASS | 0.32s | `INTENT_ERROR` |
| `task_039` | UNS | `BROWSER_INSPEC` | Open Edge and click the New Tab but... | *FAIL* | FAIL | PASS | 0.36s | `INTENT_ERROR` |
| `task_040` | UNS | `MULTI_APP_WORK` | Open Calculator, then open Notepad ... | *FAIL* | FAIL | PASS | 0.96s | `INTENT_ERROR` |
| `task_041` | UNS | `MULTI_STEP_EDI` | Open Notepad, type 'Version 1.0', s... | *FAIL* | PASS | FAIL | 0.27s | `SAVE_PERSISTENCE_ERROR` |
| `task_042` | UNS | `DIALOG_HANDLIN` | Open Notepad, save as 'existing.txt... | *FAIL* | PASS | FAIL | 0.21s | `SAVE_PERSISTENCE_ERROR` |
| `task_043` | UNS | `DIALOG_HANDLIN` | Open Paint, click File -> Open, pre... | *FAIL* | FAIL | PASS | 0.19s | `INTENT_ERROR` |
| `task_044` | UNS | `VISUAL_GROUNDI` | Open Paint and click the Green colo... | *FAIL* | FAIL | PASS | 0.19s | `INTENT_ERROR` |
| `task_045` | UNS | `STATE_RECOVERY` | Open Paint, minimize Paint, restore... | *FAIL* | FAIL | PASS | 0.19s | `INTENT_ERROR` |
| `task_046` | UNS | `LONG_HORIZON` | Open Calculator, open Notepad, type... | *FAIL* | FAIL | FAIL | 0.18s | `SAVE_PERSISTENCE_ERROR` |
| `task_047` | UNS | `ARTIFACT_VALID` | Create a file 'table.csv' with colu... | *FAIL* | PASS | FAIL | 0.46s | `SAVE_PERSISTENCE_ERROR` |
| `task_048` | UNS | `MIXED_WORKFLOW` | Open Notepad, type 'Batch Process C... | *FAIL* | PASS | FAIL | 0.19s | `SAVE_PERSISTENCE_ERROR` |
| `task_049` | UNS | `MIXED_WORKFLOW` | Create 'manifest.json' with {"statu... | *FAIL* | PASS | FAIL | 0.2s | `SAVE_PERSISTENCE_ERROR` |
| `task_050` | UNS | `MIXED_WORKFLOW` | Open Paint, draw a shape, save as '... | *FAIL* | FAIL | FAIL | 0.19s | `SAVE_PERSISTENCE_ERROR` |