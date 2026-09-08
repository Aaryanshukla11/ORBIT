import asyncio
import sys
from uuid import uuid4
import time

sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\src")
sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\prototypes\prototype_d_observation")
sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\tests\integration")

from test_m1_6_live_autonomous_validation import spawn_live_test_window
from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
from orbit.runtime.targeting.models import TargetIntent, TargetStrategy

async def test_debug():
    obs = ProductionObservationAdapter()
    await obs.initialize()
    unique_title = f"ORBIT_Scenario_A_{uuid4().hex[:6]}"
    with spawn_live_test_window(unique_title, width=350, height=250, x=200, y=200):
        time.sleep(1.0)
        snap = await obs.capture_snapshot()
        print(f"Snapshot has {len(snap.windows)} windows:")
        for w in snap.windows:
            print(f"  HWND: {w.hwnd} | Title: {repr(w.window_title)} | Proc: {w.process_name} | Vis: {w.is_visible} | Bounds: {w.extended_bounds}")
        
        locator = EvidenceBasedTargetLocator()
        res = locator.resolve_target(snap, TargetIntent(strategy=TargetStrategy.WINDOW_TITLE, window_title=unique_title))
        print(f"\nLocator resolve result status: {res.status.value}")
        if res.target:
            print(f"Resolved target: {res.target.target_id}, safe_point: {res.target.safe_point}")
    await obs.shutdown()

if __name__ == "__main__":
    asyncio.run(test_debug())
