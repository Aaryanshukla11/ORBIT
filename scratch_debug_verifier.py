import asyncio
import logging
import subprocess
import time
import ctypes
from ctypes import wintypes
from PIL import Image

from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.runtime.perception.engine import SemanticPerceptionEngine
from orbit.runtime.perception.ocr import WindowsNativeOCRProvider
from orbit.runtime.task_understanding.engine import TaskUnderstandingEngine
from orbit.adapters.observation.snapshot import ObservationSnapshot, ObservedWindow
from orbit.models.common import BoundingBox
from orbit.runtime.plan_execution.models import PlanExecutionResult, PlanExecutionStatus, PlanStepExecutionResult, PlanStepExecutionStatus, PlanActionType
from orbit.adapters.keyboard.text import TextTypingExecutor
from orbit.adapters.keyboard.focus import TargetFocusValidator
from orbit.adapters.keyboard.state import KeyboardStateManager

logging.basicConfig(level=logging.INFO)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

async def test():
    # 1. Launch Notepad
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)
    
    notepad_hwnd = 0
    def find_np(hwnd, lparam):
        nonlocal notepad_hwnd
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            if "Notepad" in buf.value or "Untitled" in buf.value:
                notepad_hwnd = hwnd
                return False
        return True
    
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    cb = WNDENUMPROC(find_np)
    user32.EnumWindows(cb, 0)
    print("Found Notepad HWND:", notepad_hwnd)
    
    # 2. Attach thread input and set focus
    cur_thread = kernel32.GetCurrentThreadId()
    target_thread = user32.GetWindowThreadProcessId(notepad_hwnd, None)
    user32.AttachThreadInput(cur_thread, target_thread, True)
    user32.SetForegroundWindow(notepad_hwnd)
    
    # Enumerate children
    children = []
    def enum_cb(h, l):
        buf_c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf_c, 256)
        children.append((h, buf_c.value))
        return True
    
    cb_c = WNDENUMPROC(enum_cb)
    user32.EnumChildWindows(notepad_hwnd, cb_c, 0)
    print("Children:", children)
    
    # Find RichEdit / Edit child
    edit_hwnds = [h for h, cls in children if "richedit" in cls.lower() or "edit" in cls.lower() or "textbox" in cls.lower()]
    print("Edit HWNDs:", edit_hwnds)
    for eh in edit_hwnds:
        user32.SetFocus(eh)
        
    # Send WM_CHAR to all edit HWNDs and top window
    WM_CHAR = 0x0102
    for c in "HELLO ORBIT":
        for eh in edit_hwnds:
            user32.SendMessageW(eh, WM_CHAR, ord(c), 0)
        time.sleep(0.01)
        
    user32.AttachThreadInput(cur_thread, target_thread, False)
    time.sleep(0.5)
    
    # Verify with GoalVerifier
    ocr_provider = WindowsNativeOCRProvider()
    perception = SemanticPerceptionEngine(ocr_provider=ocr_provider)
    verifier = GoalVerifier(perception_engine=perception)
    
    windows = [
        ObservedWindow(
            hwnd=notepad_hwnd,
            window_title="*Untitled - Notepad",
            process_name="Notepad.exe",
            process_id=proc.pid,
            extended_bounds=BoundingBox(left=0, top=0, width=800, height=600),
            is_foreground=True,
            is_visible=True,
        )
    ]
    
    post_snapshot = ObservationSnapshot(
        snapshot_id="snap_1",
        timestamp_ns=0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        windows=windows,
        foreground_window=windows[0],
        detected_elements=[],
    )
    
    tu = TaskUnderstandingEngine()
    u = tu.understand("Open Notepad and type HELLO ORBIT")
    
    step_res = PlanStepExecutionResult(
        step_id="s1",
        step_index=0,
        action_type=PlanActionType.ENTER_TEXT,
        status=PlanStepExecutionStatus.SUCCEEDED,
    )
    plan_res = PlanExecutionResult(
        plan_id="p1",
        task_id="t1",
        final_status=PlanExecutionStatus.SUCCEEDED,
        is_success=True,
        step_results=[step_res],
    )
    
    res = await verifier.verify_goal(
        understanding=u,
        plan=None,
        plan_result=plan_res,
        post_snapshot=post_snapshot,
        post_image=None,
    )
    print("Verification result status:", res.status)
    print("Verification completed:", res.is_completed)
    print("Evidence verified_text:", res.evidence.verified_text if res.evidence else None)
    
    try:
        proc.kill()
    except Exception:
        pass

asyncio.run(test())
