import asyncio
from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
from orbit.runtime.targeting.models import TargetIntent, TargetStrategy

async def test_acc():
    adapter = ProductionObservationAdapter()
    await adapter.initialize()
    
    # 1. Capture snapshot to find Notepad HWND
    snap = await adapter.capture_snapshot()
    locator = EvidenceBasedTargetLocator()
    res = locator.locate_target(snap, TargetIntent(strategy=TargetStrategy.WINDOW_TITLE, window_title="Notepad"))
    print("Resolved target:", res.status, res.target.target_hwnd if res.target else None)
    
    if res.target and res.target.target_hwnd:
        hwnd = res.target.target_hwnd
        snap_with_acc = await adapter.capture_snapshot(target_hwnd=hwnd)
        print("Snapshot with target_hwnd elements count:", len(snap_with_acc.detected_elements))
        for el in snap_with_acc.detected_elements:
            print(f"Element: {el.control_type} | Name: '{el.name}' | Role: {el.role}")
            
    await adapter.shutdown()

if __name__ == "__main__":
    asyncio.run(test_acc())
