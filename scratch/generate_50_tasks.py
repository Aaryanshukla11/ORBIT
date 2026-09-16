"""Generates the authoritative 50 benchmark task specifications for Phase 2G."""

import json
from pathlib import Path

DEV_TASKS = [
    # 1. Application Launch
    {
        "task_id": "task_001",
        "title": "Launch Notepad Application",
        "split": "DEVELOPMENT",
        "category": "APPLICATION_LAUNCH",
        "natural_language_goal": "Open Notepad",
        "expectations": {
            "expected_window_title": "Notepad",
            "expected_process_name": "notepad.exe",
            "require_app_open": True
        },
        "timeout_sec": 30.0,
        "max_steps": 5
    },
    {
        "task_id": "task_002",
        "title": "Launch Paint Application",
        "split": "DEVELOPMENT",
        "category": "APPLICATION_LAUNCH",
        "natural_language_goal": "Open Paint",
        "expectations": {
            "expected_window_title": "Paint",
            "expected_process_name": "mspaint.exe",
            "require_app_open": True
        },
        "timeout_sec": 30.0,
        "max_steps": 5
    },
    # 2. Text Entry
    {
        "task_id": "task_003",
        "title": "Type Single Line Text in Notepad",
        "split": "DEVELOPMENT",
        "category": "TEXT_ENTRY",
        "natural_language_goal": "Open Notepad and type 'ORBIT Native Perception Active'",
        "expectations": {
            "expected_window_title": "Notepad",
            "expected_process_name": "notepad.exe",
            "expected_ui_text": "ORBIT Native Perception Active",
            "require_app_open": True
        },
        "timeout_sec": 45.0,
        "max_steps": 8
    },
    {
        "task_id": "task_004",
        "title": "Type Formatted Multi-Line Text",
        "split": "DEVELOPMENT",
        "category": "TEXT_ENTRY",
        "natural_language_goal": "Open Notepad and type:\nProject: ORBIT\nStatus: Verified\nPhase: 2G",
        "expectations": {
            "expected_window_title": "Notepad",
            "expected_process_name": "notepad.exe",
            "require_app_open": True
        },
        "timeout_sec": 45.0,
        "max_steps": 8
    },
    # 3. UI Interaction
    {
        "task_id": "task_005",
        "title": "Open Notepad About Dialog via Menu",
        "split": "DEVELOPMENT",
        "category": "UI_INTERACTION",
        "natural_language_goal": "Open Notepad and click on Help then About Notepad",
        "expectations": {
            "expected_window_title": "About Notepad",
            "require_app_open": True
        },
        "timeout_sec": 45.0,
        "max_steps": 8
    },
    {
        "task_id": "task_006",
        "title": "Toggle Word Wrap Setting in Notepad",
        "split": "DEVELOPMENT",
        "category": "UI_INTERACTION",
        "natural_language_goal": "Open Notepad and toggle Word Wrap from the Format or View menu",
        "expectations": {
            "expected_window_title": "Notepad",
            "require_app_open": True
        },
        "timeout_sec": 45.0,
        "max_steps": 8
    },
    # 4. Filesystem
    {
        "task_id": "task_007",
        "title": "Create Folder on Desktop",
        "split": "DEVELOPMENT",
        "category": "FILESYSTEM",
        "natural_language_goal": "Create a new folder named 'ORBIT_Test_Folder' in the workspace scratchpad",
        "expectations": {
            "expected_deliverable": {
                "file_path": "ORBIT_Test_Folder",
                "format": "dir",
                "min_size_bytes": 0
            }
        },
        "timeout_sec": 30.0,
        "max_steps": 6
    },
    {
        "task_id": "task_008",
        "title": "Create Test Text File on Filesystem",
        "split": "DEVELOPMENT",
        "category": "FILESYSTEM",
        "natural_language_goal": "Create a file named 'fs_test.txt' containing 'Filesystem verification test' in scratchpad",
        "expectations": {
            "expected_deliverable": {
                "file_path": "fs_test.txt",
                "format": "text",
                "min_size_bytes": 10,
                "expected_content_substr": "Filesystem verification test"
            }
        },
        "timeout_sec": 30.0,
        "max_steps": 6
    },
    # 5. Save / Export
    {
        "task_id": "task_009",
        "title": "Save Notepad Note to File",
        "split": "DEVELOPMENT",
        "category": "SAVE_EXPORT",
        "natural_language_goal": "Open Notepad, type 'Autonomous Save Verification', and save the file as 'saved_note.txt'",
        "expectations": {
            "expected_deliverable": {
                "file_path": "saved_note.txt",
                "format": "text",
                "min_size_bytes": 5,
                "expected_content_substr": "Autonomous Save Verification"
            }
        },
        "timeout_sec": 60.0,
        "max_steps": 10
    },
    {
        "task_id": "task_010",
        "title": "Save Paint Drawing to PNG",
        "split": "DEVELOPMENT",
        "category": "SAVE_EXPORT",
        "natural_language_goal": "Open Paint, draw a line on canvas, and save the drawing as 'saved_drawing.png'",
        "expectations": {
            "expected_deliverable": {
                "file_path": "saved_drawing.png",
                "format": "png",
                "min_size_bytes": 100,
                "magic_bytes_hex": "89504e47"
            }
        },
        "timeout_sec": 60.0,
        "max_steps": 10
    },
    # 6. Paint Canvas
    {
        "task_id": "task_011",
        "title": "Draw Rectangle on Paint Canvas",
        "split": "DEVELOPMENT",
        "category": "PAINT_CANVAS",
        "natural_language_goal": "Open Paint and draw a rectangle on the canvas",
        "expectations": {
            "expected_window_title": "Paint",
            "require_app_open": True
        },
        "timeout_sec": 45.0,
        "max_steps": 8
    },
    {
        "task_id": "task_012",
        "title": "Select Color Red and Draw Circle in Paint",
        "split": "DEVELOPMENT",
        "category": "PAINT_CANVAS",
        "natural_language_goal": "Open Paint, select the Red color from the palette, and draw a circle",
        "expectations": {
            "expected_window_title": "Paint",
            "require_app_open": True
        },
        "timeout_sec": 50.0,
        "max_steps": 10
    },
    # 7. Browser Inspection
    {
        "task_id": "task_013",
        "title": "Launch Edge Browser",
        "split": "DEVELOPMENT",
        "category": "BROWSER_INSPECTION",
        "natural_language_goal": "Open Microsoft Edge",
        "expectations": {
            "expected_process_name": "msedge.exe",
            "require_app_open": True
        },
        "timeout_sec": 45.0,
        "max_steps": 6
    },
    {
        "task_id": "task_014",
        "title": "Open Browser Search Bar",
        "split": "DEVELOPMENT",
        "category": "BROWSER_INSPECTION",
        "natural_language_goal": "Open Microsoft Edge and click the address bar",
        "expectations": {
            "expected_process_name": "msedge.exe",
            "require_app_open": True
        },
        "timeout_sec": 50.0,
        "max_steps": 8
    },
    # 8. Multi-App Workflow
    {
        "task_id": "task_015",
        "title": "Launch Calculator and Notepad Simultaneously",
        "split": "DEVELOPMENT",
        "category": "MULTI_APP_WORKFLOW",
        "natural_language_goal": "Open Calculator, then open Notepad",
        "expectations": {
            "expected_process_name": "notepad.exe",
            "require_app_open": True
        },
        "timeout_sec": 50.0,
        "max_steps": 8
    },
    # 9. Multi-Step Editing
    {
        "task_id": "task_016",
        "title": "Create, Append, and Save Document",
        "split": "DEVELOPMENT",
        "category": "MULTI_STEP_EDITING",
        "natural_language_goal": "Open Notepad, type 'Header line', add a second line 'Appended content', and save as 'multistep.txt'",
        "expectations": {
            "expected_deliverable": {
                "file_path": "multistep.txt",
                "format": "text",
                "min_size_bytes": 15,
                "expected_content_substr": "Appended content"
            }
        },
        "timeout_sec": 60.0,
        "max_steps": 12
    },
    # 10. Dialog Handling
    {
        "task_id": "task_017",
        "title": "Dismiss Unsaved Changes Modal on Exit",
        "split": "DEVELOPMENT",
        "category": "DIALOG_HANDLING",
        "natural_language_goal": "Open Notepad, type some unsaved text, close Notepad, and click 'Don't Save' on the confirmation dialog",
        "expectations": {
            "expected_process_name": "notepad.exe",
            "require_app_closed": True
        },
        "timeout_sec": 45.0,
        "max_steps": 8
    },
    {
        "task_id": "task_018",
        "title": "Cancel File Open Dialog",
        "split": "DEVELOPMENT",
        "category": "DIALOG_HANDLING",
        "natural_language_goal": "Open Notepad, click File -> Open, and click Cancel to dismiss the dialog",
        "expectations": {
            "expected_window_title": "Notepad",
            "require_app_open": True
        },
        "timeout_sec": 45.0,
        "max_steps": 8
    },
    # 11. Visual Grounding
    {
        "task_id": "task_019",
        "title": "Click Paint Brush Selector Tool",
        "split": "DEVELOPMENT",
        "category": "VISUAL_GROUNDING",
        "natural_language_goal": "Open Paint and click on the Brushes tool icon on the ribbon",
        "expectations": {
            "expected_window_title": "Paint",
            "require_app_open": True
        },
        "timeout_sec": 45.0,
        "max_steps": 8
    },
    # 12. State Recovery
    {
        "task_id": "task_020",
        "title": "Refocus Inactive Notepad Window",
        "split": "DEVELOPMENT",
        "category": "STATE_RECOVERY",
        "natural_language_goal": "Open Notepad, click Desktop to unfocus it, then click Notepad to refocus and type 'Focus Restored'",
        "expectations": {
            "expected_window_title": "Notepad",
            "require_app_open": True
        },
        "timeout_sec": 50.0,
        "max_steps": 10
    },
    # 13. Long-Horizon Task
    {
        "task_id": "task_021",
        "title": "12-Step Audit Log Report Creation",
        "split": "DEVELOPMENT",
        "category": "LONG_HORIZON",
        "natural_language_goal": "Open Notepad, write 5 bulleted status lines, save the file as 'audit_log.txt', and close Notepad",
        "expectations": {
            "expected_deliverable": {
                "file_path": "audit_log.txt",
                "format": "text",
                "min_size_bytes": 20
            },
            "expected_process_name": "notepad.exe",
            "require_app_closed": True
        },
        "timeout_sec": 90.0,
        "max_steps": 15
    },
    # 14. Artifact Validation
    {
        "task_id": "task_022",
        "title": "Generate Valid JSON Deliverable",
        "split": "DEVELOPMENT",
        "category": "ARTIFACT_VALIDATION",
        "natural_language_goal": "Create a file named 'config.json' with valid JSON: {\"orbit\": \"ready\", \"version\": 2}",
        "expectations": {
            "expected_deliverable": {
                "file_path": "config.json",
                "format": "json",
                "min_size_bytes": 10,
                "expected_content_substr": "\"orbit\": \"ready\""
            }
        },
        "timeout_sec": 30.0,
        "max_steps": 6
    },
    # 15. Mixed Workflow
    {
        "task_id": "task_023",
        "title": "Paint Diagram and Notepad Summary Sync",
        "split": "DEVELOPMENT",
        "category": "MIXED_WORKFLOW",
        "natural_language_goal": "Open Paint, draw a shape, save as 'diagram.png', then open Notepad and write 'Diagram created at diagram.png'",
        "expectations": {
            "expected_deliverable": {
                "file_path": "diagram.png",
                "format": "png",
                "min_size_bytes": 100,
                "magic_bytes_hex": "89504e47"
            },
            "expected_window_title": "Notepad",
            "require_app_open": True
        },
        "timeout_sec": 90.0,
        "max_steps": 15
    },
    {
        "task_id": "task_024",
        "title": "Create File and Rename via Filesystem",
        "split": "DEVELOPMENT",
        "category": "MIXED_WORKFLOW",
        "natural_language_goal": "Create 'temp_draft.txt' with text 'Draft Notes', then save the final version as 'final_report.txt'",
        "expectations": {
            "expected_deliverable": {
                "file_path": "final_report.txt",
                "format": "text",
                "min_size_bytes": 5
            }
        },
        "timeout_sec": 60.0,
        "max_steps": 10
    },
    {
        "task_id": "task_025",
        "title": "Launch Triple Utility Suite",
        "split": "DEVELOPMENT",
        "category": "MIXED_WORKFLOW",
        "natural_language_goal": "Open Notepad, Calculator, and Paint",
        "expectations": {
            "expected_process_name": "mspaint.exe",
            "require_app_open": True
        },
        "timeout_sec": 60.0,
        "max_steps": 12
    }
]

UNSEEN_TASKS = [
    # 1. Application Launch
    {
        "task_id": "task_026",
        "title": "Launch Windows Calculator",
        "split": "UNSEEN",
        "category": "APPLICATION_LAUNCH",
        "natural_language_goal": "Start Calculator",
        "expectations": {
            "expected_window_title": "Calculator",
            "require_app_open": True
        },
        "timeout_sec": 30.0,
        "max_steps": 5
    },
    {
        "task_id": "task_027",
        "title": "Bring Up Microsoft Edge Browser",
        "split": "UNSEEN",
        "category": "APPLICATION_LAUNCH",
        "natural_language_goal": "Launch Microsoft Edge",
        "expectations": {
            "expected_process_name": "msedge.exe",
            "require_app_open": True
        },
        "timeout_sec": 30.0,
        "max_steps": 5
    },
    # 2. Text Entry
    {
        "task_id": "task_028",
        "title": "Type Numerical Matrix in Notepad",
        "split": "UNSEEN",
        "category": "TEXT_ENTRY",
        "natural_language_goal": "Open Notepad and type: 100, 200, 300, 400",
        "expectations": {
            "expected_window_title": "Notepad",
            "expected_process_name": "notepad.exe",
            "expected_ui_text": "100, 200, 300, 400",
            "require_app_open": True
        },
        "timeout_sec": 45.0,
        "max_steps": 8
    },
    {
        "task_id": "task_029",
        "title": "Type Indented Python Snippet",
        "split": "UNSEEN",
        "category": "TEXT_ENTRY",
        "natural_language_goal": "Open Notepad and enter: def test(): return True",
        "expectations": {
            "expected_window_title": "Notepad",
            "expected_process_name": "notepad.exe",
            "require_app_open": True
        },
        "timeout_sec": 45.0,
        "max_steps": 8
    },
    # 3. UI Interaction
    {
        "task_id": "task_030",
        "title": "Toggle Status Bar in Notepad",
        "split": "UNSEEN",
        "category": "UI_INTERACTION",
        "natural_language_goal": "Open Notepad, open View menu, and toggle Status Bar",
        "expectations": {
            "expected_window_title": "Notepad",
            "require_app_open": True
        },
        "timeout_sec": 45.0,
        "max_steps": 8
    },
    {
        "task_id": "task_031",
        "title": "Open Font Settings in Notepad",
        "split": "UNSEEN",
        "category": "UI_INTERACTION",
        "natural_language_goal": "Open Notepad and navigate to Font settings dialog",
        "expectations": {
            "expected_window_title": "Notepad",
            "require_app_open": True
        },
        "timeout_sec": 45.0,
        "max_steps": 8
    },
    # 4. Filesystem
    {
        "task_id": "task_032",
        "title": "Create Nested Directory Structure",
        "split": "UNSEEN",
        "category": "FILESYSTEM",
        "natural_language_goal": "Create folder 'data' and inside it create 'raw_logs' directory in scratchpad",
        "expectations": {
            "expected_deliverable": {
                "file_path": "data/raw_logs",
                "format": "dir",
                "min_size_bytes": 0
            }
        },
        "timeout_sec": 35.0,
        "max_steps": 6
    },
    {
        "task_id": "task_033",
        "title": "Write Markdown Summary Deliverable",
        "split": "UNSEEN",
        "category": "FILESYSTEM",
        "natural_language_goal": "Create a markdown file 'summary.md' containing '# Executive Summary\\nAll tests passed.'",
        "expectations": {
            "expected_deliverable": {
                "file_path": "summary.md",
                "format": "text",
                "min_size_bytes": 15,
                "expected_content_substr": "Executive Summary"
            }
        },
        "timeout_sec": 30.0,
        "max_steps": 6
    },
    # 5. Save / Export
    {
        "task_id": "task_034",
        "title": "Export Notepad Content as Log File",
        "split": "UNSEEN",
        "category": "SAVE_EXPORT",
        "natural_language_goal": "Open Notepad, write 'SYSTEM_BOOT_SUCCESS', and save as 'system.log'",
        "expectations": {
            "expected_deliverable": {
                "file_path": "system.log",
                "format": "text",
                "min_size_bytes": 10,
                "expected_content_substr": "SYSTEM_BOOT_SUCCESS"
            }
        },
        "timeout_sec": 60.0,
        "max_steps": 10
    },
    {
        "task_id": "task_035",
        "title": "Save Paint Bitmap Image",
        "split": "UNSEEN",
        "category": "SAVE_EXPORT",
        "natural_language_goal": "Open Paint, draw a line, and save the image as 'render.bmp'",
        "expectations": {
            "expected_deliverable": {
                "file_path": "render.bmp",
                "format": "bmp",
                "min_size_bytes": 100,
                "magic_bytes_hex": "424d"
            }
        },
        "timeout_sec": 60.0,
        "max_steps": 10
    },
    # 6. Paint Canvas
    {
        "task_id": "task_036",
        "title": "Draw Triangle Shape in Paint",
        "split": "UNSEEN",
        "category": "PAINT_CANVAS",
        "natural_language_goal": "Open Paint, select the Triangle shape from the shapes ribbon, and draw on canvas",
        "expectations": {
            "expected_window_title": "Paint",
            "require_app_open": True
        },
        "timeout_sec": 50.0,
        "max_steps": 10
    },
    {
        "task_id": "task_037",
        "title": "Fill Background with Color in Paint",
        "split": "UNSEEN",
        "category": "PAINT_CANVAS",
        "natural_language_goal": "Open Paint, select the Fill with color bucket tool, choose Blue, and click canvas",
        "expectations": {
            "expected_window_title": "Paint",
            "require_app_open": True
        },
        "timeout_sec": 50.0,
        "max_steps": 10
    },
    # 7. Browser Inspection
    {
        "task_id": "task_038",
        "title": "Focus Address Bar in Browser",
        "split": "UNSEEN",
        "category": "BROWSER_INSPECTION",
        "natural_language_goal": "Open Edge, click the URL input bar, and type 'localhost:8000'",
        "expectations": {
            "expected_process_name": "msedge.exe",
            "require_app_open": True
        },
        "timeout_sec": 50.0,
        "max_steps": 8
    },
    {
        "task_id": "task_039",
        "title": "Navigate Browser Tabs",
        "split": "UNSEEN",
        "category": "BROWSER_INSPECTION",
        "natural_language_goal": "Open Edge and click the New Tab button (+)",
        "expectations": {
            "expected_process_name": "msedge.exe",
            "require_app_open": True
        },
        "timeout_sec": 50.0,
        "max_steps": 8
    },
    # 8. Multi-App Workflow
    {
        "task_id": "task_040",
        "title": "Calculate and Log to Notepad",
        "split": "UNSEEN",
        "category": "MULTI_APP_WORKFLOW",
        "natural_language_goal": "Open Calculator, then open Notepad and type 'Calculation ready'",
        "expectations": {
            "expected_process_name": "notepad.exe",
            "require_app_open": True
        },
        "timeout_sec": 55.0,
        "max_steps": 10
    },
    # 9. Multi-Step Editing
    {
        "task_id": "task_041",
        "title": "Append Revision to Existing File",
        "split": "UNSEEN",
        "category": "MULTI_STEP_EDITING",
        "natural_language_goal": "Open Notepad, type 'Version 1.0', save as 'release.txt', then add 'Revision A' and re-save",
        "expectations": {
            "expected_deliverable": {
                "file_path": "release.txt",
                "format": "text",
                "min_size_bytes": 10,
                "expected_content_substr": "Revision A"
            }
        },
        "timeout_sec": 70.0,
        "max_steps": 12
    },
    # 10. Dialog Handling
    {
        "task_id": "task_042",
        "title": "Handle Save Overwrite Dialog",
        "split": "UNSEEN",
        "category": "DIALOG_HANDLING",
        "natural_language_goal": "Open Notepad, save as 'existing.txt', type more text, save as 'existing.txt' again and confirm Yes on overwrite",
        "expectations": {
            "expected_deliverable": {
                "file_path": "existing.txt",
                "format": "text",
                "min_size_bytes": 5
            }
        },
        "timeout_sec": 75.0,
        "max_steps": 14
    },
    {
        "task_id": "task_043",
        "title": "Dismiss Open File Dialog without Opening",
        "split": "UNSEEN",
        "category": "DIALOG_HANDLING",
        "natural_language_goal": "Open Paint, click File -> Open, press Escape to cancel dialog, and keep Paint open",
        "expectations": {
            "expected_window_title": "Paint",
            "require_app_open": True
        },
        "timeout_sec": 45.0,
        "max_steps": 8
    },
    # 11. Visual Grounding
    {
        "task_id": "task_044",
        "title": "Select Green Color Swatch in Paint",
        "split": "UNSEEN",
        "category": "VISUAL_GROUNDING",
        "natural_language_goal": "Open Paint and click the Green color box in the color palette ribbon",
        "expectations": {
            "expected_window_title": "Paint",
            "require_app_open": True
        },
        "timeout_sec": 45.0,
        "max_steps": 8
    },
    # 12. State Recovery
    {
        "task_id": "task_045",
        "title": "Recover from Minimized Window",
        "split": "UNSEEN",
        "category": "STATE_RECOVERY",
        "natural_language_goal": "Open Paint, minimize Paint, restore Paint window to foreground",
        "expectations": {
            "expected_window_title": "Paint",
            "require_app_open": True
        },
        "timeout_sec": 50.0,
        "max_steps": 10
    },
    # 13. Long-Horizon Task
    {
        "task_id": "task_046",
        "title": "15-Step Multi-Window Data Consolidation",
        "split": "UNSEEN",
        "category": "LONG_HORIZON",
        "natural_language_goal": "Open Calculator, open Notepad, type 'Metrics collected', save as 'consolidated_metrics.txt', and close both windows",
        "expectations": {
            "expected_deliverable": {
                "file_path": "consolidated_metrics.txt",
                "format": "text",
                "min_size_bytes": 10
            },
            "expected_process_name": "notepad.exe",
            "require_app_closed": True
        },
        "timeout_sec": 100.0,
        "max_steps": 16
    },
    # 14. Artifact Validation
    {
        "task_id": "task_047",
        "title": "Create Valid CSV Deliverable",
        "split": "UNSEEN",
        "category": "ARTIFACT_VALIDATION",
        "natural_language_goal": "Create a file 'table.csv' with columns: id,status,score and one data row: 1,PASS,98",
        "expectations": {
            "expected_deliverable": {
                "file_path": "table.csv",
                "format": "text",
                "min_size_bytes": 15,
                "expected_content_substr": "id,status,score"
            }
        },
        "timeout_sec": 30.0,
        "max_steps": 6
    },
    # 15. Mixed Workflow
    {
        "task_id": "task_048",
        "title": "Notepad and Filesystem Synchronized Deliverable",
        "split": "UNSEEN",
        "category": "MIXED_WORKFLOW",
        "natural_language_goal": "Open Notepad, type 'Batch Process Complete', save as 'batch.log', and confirm file exists",
        "expectations": {
            "expected_deliverable": {
                "file_path": "batch.log",
                "format": "text",
                "min_size_bytes": 15,
                "expected_content_substr": "Batch Process Complete"
            }
        },
        "timeout_sec": 60.0,
        "max_steps": 10
    },
    {
        "task_id": "task_049",
        "title": "Multi-Format Export Workflow",
        "split": "UNSEEN",
        "category": "MIXED_WORKFLOW",
        "natural_language_goal": "Create 'manifest.json' with {\"status\": \"ok\"} and create 'manifest.txt' with 'Status: OK'",
        "expectations": {
            "expected_deliverable": {
                "file_path": "manifest.json",
                "format": "json",
                "min_size_bytes": 10
            }
        },
        "timeout_sec": 50.0,
        "max_steps": 8
    },
    {
        "task_id": "task_050",
        "title": "End-to-End Autonomous System Check",
        "split": "UNSEEN",
        "category": "MIXED_WORKFLOW",
        "natural_language_goal": "Open Paint, draw a shape, save as 'final_check.png', open Notepad, write 'Phase 2G Unseen Benchmark Verified', save as 'final_check.txt', and close all open applications",
        "expectations": {
            "expected_deliverable": {
                "file_path": "final_check.png",
                "format": "png",
                "min_size_bytes": 100,
                "magic_bytes_hex": "89504e47"
            },
            "expected_process_name": "notepad.exe",
            "require_app_closed": True
        },
        "timeout_sec": 120.0,
        "max_steps": 20
    }
]

def main():
    root = Path(__file__).resolve().parents[1]
    dev_dir = root / "benchmark" / "development"
    unseen_dir = root / "benchmark" / "unseen"
    
    dev_dir.mkdir(parents=True, exist_ok=True)
    unseen_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Writing 25 Development tasks to {dev_dir}...")
    for t in DEV_TASKS:
        path = dev_dir / f"{t['task_id']}.json"
        path.write_text(json.dumps(t, indent=2), encoding="utf-8")
        
    print(f"Writing 25 Unseen tasks to {unseen_dir}...")
    for t in UNSEEN_TASKS:
        path = unseen_dir / f"{t['task_id']}.json"
        path.write_text(json.dumps(t, indent=2), encoding="utf-8")
        
    print("Done! 50 benchmark tasks generated successfully.")

if __name__ == "__main__":
    main()
