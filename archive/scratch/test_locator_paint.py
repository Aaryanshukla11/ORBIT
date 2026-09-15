import sys
from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
from orbit.runtime.targeting.models import TargetIntent, TargetStrategy
import asyncio

async def test():
    adapter = ProductionObservationAdapter()
    await adapter.initialize()
    snap = await adapter.capture_snapshot()
    
    locator = EvidenceBasedTargetLocator()
    intent = TargetIntent(
        strategy=TargetStrategy.WINDOW_TITLE,
        window_title="Paint",
        name="Paint",
    )
    res = locator.locate_target(snap, intent)
    print("Locate target status:", res.status)
    print("Resolved target:", res.target)
    print("Diagnostic:", res.diagnostic_message)
    
    await adapter.shutdown()

if __name__ == "__main__":
    asyncio.run(test())
