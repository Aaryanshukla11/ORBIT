import asyncio
import json
import websockets
import time
import sys

async def run_acceptance_tests():
    uri = "ws://127.0.0.1:8765/ws"
    print(f"Connecting to live ORBIT Gateway at {uri}...")
    
    async with websockets.connect(uri) as ws:
        print("[TEST A PASS] WebSocket connection established successfully!")
        
        # Test B: Model Discovery
        print("\n--- TEST B: MODEL DISCOVERY ---")
        discover_cmd = {
            "command_type": "MODEL_DISCOVER",
            "session_id": "test_session_001",
            "payload": {}
        }
        await ws.send(json.dumps(discover_cmd))
        
        discovered_models = []
        active_model = None
        
        # Wait for responses
        start_time = time.time()
        while time.time() - start_time < 5:
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(msg)
            event_type = data.get("event_type")
            payload = data.get("payload", {})
            print(f"Received Event: {event_type} -> {json.dumps(payload)[:200]}...")
            
            if event_type == "MODEL_DISCOVER_RESPONSE":
                discovered_models = payload.get("models", [])
                print(f"[TEST B PASS] Discovered {len(discovered_models)} real models from Ollama:")
                for m in discovered_models:
                    print(f"  - {m.get('model_id')} ({m.get('display_name')}) [Status: {m.get('status')}]")
                break
                
        # Test C: Model Switch / Activation
        print("\n--- TEST C: MODEL ACTIVATION ---")
        if discovered_models:
            target_model_id = discovered_models[0].get("model_id")
            print(f"Activating model: {target_model_id}")
            switch_cmd = {
                "command_type": "MODEL_SWITCH",
                "session_id": "test_session_001",
                "payload": {"target_model_id": target_model_id}
            }
            await ws.send(json.dumps(switch_cmd))
            
            start_time = time.time()
            while time.time() - start_time < 5:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(msg)
                event_type = data.get("event_type")
                payload = data.get("payload", {})
                if event_type == "MODEL_SWITCHED":
                    active_model = payload.get("active_model_id")
                    print(f"[TEST C PASS] Model successfully activated: {active_model} (previous: {payload.get('previous_model_id')})")
                    break
        
        # Test E: Real Task Execution
        print("\n--- TEST E: REAL TASK EXECUTION ---")
        task_prompt = "Open Notepad and type: ORBIT runtime test"
        submit_cmd = {
            "command_type": "SUBMIT_TASK",
            "session_id": "test_session_001",
            "payload": {
                "prompt": task_prompt,
                "input_mode": "task"
            }
        }
        print(f"Submitting task: '{task_prompt}'")
        await ws.send(json.dumps(submit_cmd))
        
        task_done = False
        start_time = time.time()
        while time.time() - start_time < 20:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                data = json.loads(msg)
                event_type = data.get("event_type")
                payload = data.get("payload", {})
                
                print(f"Task Event [{event_type}]: {json.dumps(payload)[:300]}")
                
                if event_type == "PLAN_UPDATED":
                    plan = payload.get("plan", {})
                    print(f"  -> Formulated Plan: {plan.get('description')} with {len(plan.get('steps', []))} steps")
                    for s in plan.get("steps", []):
                        print(f"     Step {s.get('step_index')}: {s.get('action_type')} - {s.get('description')}")
                        
                if event_type == "EXECUTION_RECORD_UPDATED":
                    rec = payload.get("record", {})
                    print(f"  -> Execution Record Updated: status={rec.get('status')}")
                    if rec.get("status") in ["COMPLETED", "FAILED", "CANCELLED"]:
                        print(f"[TEST E RESULT] Execution finished with status: {rec.get('status')}")
                        task_done = True
                        break
                        
                if event_type == "TASK_STATE_CHANGED":
                    status = payload.get("status")
                    if status in ["COMPLETED", "FAILED", "CANCELLED"]:
                        print(f"[TEST E RESULT] Task state changed to: {status}")
                        task_done = True
                        break
            except asyncio.TimeoutError:
                print("Wait timed out waiting for further task events.")
                break

        print("\nLive Acceptance Testing Completed.")

if __name__ == "__main__":
    asyncio.run(run_acceptance_tests())
