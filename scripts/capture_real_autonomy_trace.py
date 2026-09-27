import os
from dotenv import load_dotenv
load_dotenv('.env')

import asyncio
import json
import subprocess
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator

async def capture_trace():
    bus = EventBus()
    events = []
    
    orch = OrbitOrchestrator(event_bus=bus)
    await orch.model_manager.activate_model('gemini-flash-latest')
    
    prompt = 'Open Notepad and type: ORBIT ASTRA-6 AUTONOMY TEST'
    print(f'=== EXECUTING TASK: "{prompt}" ===')
    res = await orch.execute_task(prompt=prompt)
    
    # Cleanup notepad
    subprocess.run(['taskkill', '/F', '/IM', 'notepad.exe'], capture_output=True)
    
    print('\n=== EXECUTION RESULT ===')
    print('Task ID:', res.task_id)
    print('Completion Status:', res.completion_status.value)
    print('Is Success:', res.is_success)
    print('Duration ms:', res.elapsed_duration_ms)
    print('Goal Verification Status:', res.goal_verification_result.status.value)
    print('Goal Verification Is Completed:', res.goal_verification_result.is_completed)
    print('Goal Verification Reason:', res.goal_verification_result.failure_reason)

if __name__ == '__main__':
    asyncio.run(capture_trace())
