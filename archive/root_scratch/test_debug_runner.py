import asyncio
import subprocess
import sys
import time
import traceback
from uuid import uuid4

def log(msg):
    with open("debug_out.txt", "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%X')}] {msg}\n")
    print(f"[{time.strftime('%X')}] {msg}", flush=True)

async def main():
    log("Main started")
    p = None
    try:
        unique_title = f"ORBIT_WIN_{uuid4().hex[:6]}"
        code = f'''import tkinter as tk
root = tk.Tk()
root.title("{unique_title}")
root.geometry("300x200+200+200")
root.mainloop()
'''
        p = subprocess.Popen([sys.executable, "-c", code])
        log(f"Subprocess spawned with pid {p.pid}")
        time.sleep(1.0)

        from orbit.adapters.observation.adapter import ProductionObservationAdapter
        from orbit.adapters.workspace.adapter import ProductionWorkspaceAdapter
        from orbit.adapters.pointer.adapter import ProductionPointerAdapter
        from orbit.runtime.targeting import EvidenceBasedTargetLocator, TargetIntent, TargetStrategy
        from orbit.runtime.verification import ActionVerifier, ExpectedOutcome, ExpectedOutcomeType, VerificationStrategy
        from orbit.runtime.execution import ClosedLoopExecutionEngine, ExecutionPolicy

        log("Imports succeeded")
        obs = ProductionObservationAdapter()
        wsp = ProductionWorkspaceAdapter()
        ptr = ProductionPointerAdapter()
        log("Initializing adapters...")
        await obs.initialize()
        await wsp.initialize()
        await ptr.initialize()
        log("Adapters initialized")

        engine = ClosedLoopExecutionEngine(
            observation=obs,
            pointer=ptr,
            workspace=wsp,
            target_locator=EvidenceBasedTargetLocator(),
            action_verifier=ActionVerifier(),
        )

        intent = TargetIntent(
            strategy=TargetStrategy.WINDOW_TITLE,
            window_title=unique_title,
            expected_outcome=ExpectedOutcome(
                strategy=VerificationStrategy.WINDOW_STATE_CHANGE,
                outcome_type=ExpectedOutcomeType.ANY_OBSERVABLE_CHANGE,
            ),
        )

        log("Executing task action...")
        result = await engine.execute_task_action(
            session_id="test_sess",
            task_id="test_task_1",
            prompt="Click test window",
            target_intent=intent,
            action_type="pointer_move",
            expected_outcome=intent.expected_outcome,
            policy=ExecutionPolicy(max_total_attempts=2, allow_inconclusive_as_success=True),
        )
        log(f"RESULT SUCCESS: {result.is_success} STATE: {result.final_state} RESOLVED: {result.resolved_target is not None}")
        log(f"STAGE: {result.dispatch_stage}")
        log(f"VERIFICATION: {result.verification_result}")
        log(f"TRANSITIONS: {[t[0] + '->' + t[1] for t in result.transition_history]}")

        log("Shutting down adapters...")
        await ptr.shutdown()
        await wsp.shutdown()
        await obs.shutdown()
        log("Shutdown complete")
    except Exception as ex:
        log(f"EXCEPTION: {ex}\n{traceback.format_exc()}")
    finally:
        if p:
            p.terminate()
            log("Subprocess terminated")

if __name__ == "__main__":
    with open("debug_out.txt", "w", encoding="utf-8") as f:
        f.write("DEBUG START\n")
    asyncio.run(main()) 