import asyncio
import io
import time
import subprocess
import ctypes
from ctypes import wintypes
from PIL import Image

from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.keyboard.adapter import ProductionKeyboardAdapter
from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.runtime.perception.engine import SemanticPerceptionEngine
from orbit.runtime.task_understanding.engine import TaskUnderstandingEngine
from orbit.runtime.plan_execution.models import PlanExecutionResult, PlanExecutionStatus
from orbit.runtime.planning.models import ExecutableTaskPlan

user32 = ctypes.windll.user32

async def test_live_goal_verifier():
    # 1. Launch notepad
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)
    
    hwnd = user32.FindWindowW(None, "Untitled - Notepad")
    if not hwnd:
        hwnd = user32.FindWindowW("Notepad", None)
    print(f"Notepad HWND: {hwnd}")
    
    # 2. Focus and click inside client area
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    center_x = (rect.left + rect.right) // 2
    center_y = (rect.top + rect.bottom) // 2
    user32.SetCursorPos(center_x, center_y)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.2)
    
    # 3. Type text via ProductionKeyboardAdapter
    kb = ProductionKeyboardAdapter()
    await kb.initialize()
    print("Keyboard initialized")
    res = await kb.type_text("HELLO ORBIT", target_hwnd=hwnd)
    print(f"Keyboard type_text returned: {res}")
    
    time.sleep(0.5)
    
    # 4. Capture Observation and Frame
    obs = ProductionObservationAdapter()
    await obs.initialize()
    snapshot = await obs.capture_snapshot()
    frame = await obs.capture_screen(0)
    post_image = Image.open(io.BytesIO(frame.raw_bytes))
    print(f"Captured snapshot {snapshot.snapshot_id}, windows: {len(snapshot.windows)}, image: {post_image.size}")
    
    # 5. Goal Verifier
    perception = SemanticPerceptionEngine()
    verifier = GoalVerifier(perception_engine=perception)
    
    engine = TaskUnderstandingEngine()
    understanding = engine.understand("Open Notepad and type HELLO ORBIT")
    print(f"Understanding intents: {understanding.intents}")
    for it in understanding.intents:
        print(f"  Goal: {it.goal}, Target: {it.target}, Constraints: {it.constraints}")
    from orbit.runtime.planning.planner import TaskPlanningEngine
    planner = TaskPlanningEngine()
    plan = planner.plan_task(understanding)
    plan_result = PlanExecutionResult(
        task_id="test_task",
        plan_id=plan.plan_id,
        final_status=PlanExecutionStatus.SUCCEEDED,
        is_success=True,
        step_results=[],
    )
    
    ver_res = await verifier.verify_goal(
        understanding=understanding,
        plan=plan,
        plan_result=plan_result,
        post_snapshot=snapshot,
        post_image=post_image,
    )
    
    print(f"Goal Verification Status: {ver_res.status}")
    print(f"Is Completed: {ver_res.is_completed}")
    print(f"Diagnostics: {ver_res.evidence.diagnostics if ver_res.evidence else None}")
    
    await kb.shutdown()
    await obs.shutdown()
    proc.terminate()

if __name__ == "__main__":
    asyncio.run(test_live_goal_verifier())
