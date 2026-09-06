import asyncio
from orbit.adapters.observation.adapter import ProductionObservationAdapter

async def probe():
    adapter = ProductionObservationAdapter()
    await adapter.initialize()
    
    snap = await adapter.capture_snapshot()
    print(f"Captured snapshot {snap.snapshot_id} with {len(snap.windows)} windows:")
    for w in snap.windows:
        print(f"  - HWND: {w.hwnd:#x}, Title: '{w.window_title}', Process: '{w.process_name}', Bounds: {w.extended_bounds}")

if __name__ == "__main__":
    asyncio.run(probe())
