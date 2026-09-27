"""Gate 2: Real Model Verification and Backoff Probe.

Tests live Google Gemini API connectivity and ORBIT production ModelManager runtime integration
without mocks, fake planners, or deterministic fallbacks.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
import time
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv(".env")

from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.models.models import ModelGenerateRequest


def sanitize(text: str) -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if key and len(key) > 5:
        text = text.replace(key, "[REDACTED_API_KEY]")
    return text


def run_direct_probe(model_name: str = "gemini-flash-latest", max_attempts: int = 5) -> dict:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return {"error": "GEMINI_API_KEY not found in environment"}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": "Reply with exactly: ORBIT_MODEL_READY"}]}]
    }).encode("utf-8")

    attempts = []
    backoff = 2.0

    for attempt in range(1, max_attempts + 1):
        t0 = time.perf_counter()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                lat = (time.perf_counter() - t0) * 1000.0
                status_code = resp.status
                body = json.loads(resp.read().decode())
                cand = body.get("candidates", [])
                content = ""
                if cand:
                    parts = cand[0].get("content", {}).get("parts", [])
                    content = "".join(p.get("text", "") for p in parts if "text" in p).strip()
                
                attempts.append({
                    "attempt": attempt,
                    "status_code": status_code,
                    "latency_ms": round(lat, 2),
                    "success": True,
                    "content": content,
                    "error": None
                })
                return {
                    "model": model_name,
                    "success": True,
                    "attempts": attempts,
                    "final_content": content
                }
        except urllib.error.HTTPError as e:
            lat = (time.perf_counter() - t0) * 1000.0
            err_body = sanitize(e.read().decode()[:300])
            attempts.append({
                "attempt": attempt,
                "status_code": e.code,
                "latency_ms": round(lat, 2),
                "success": False,
                "content": None,
                "error": err_body
            })
            if attempt < max_attempts:
                time.sleep(backoff)
                backoff *= 1.5
        except Exception as ex:
            lat = (time.perf_counter() - t0) * 1000.0
            attempts.append({
                "attempt": attempt,
                "status_code": "NETWORK_ERR",
                "latency_ms": round(lat, 2),
                "success": False,
                "content": None,
                "error": sanitize(str(ex))
            })
            if attempt < max_attempts:
                time.sleep(backoff)
                backoff *= 1.5

    return {
        "model": model_name,
        "success": False,
        "attempts": attempts,
        "final_content": None
    }


async def run_orbit_runtime_probe(model_name: str = "gemini-flash-latest") -> dict:
    bus = EventBus()
    orch = OrbitOrchestrator(event_bus=bus)
    
    t0 = time.perf_counter()
    act_res = await orch.model_manager.activate_model(model_name)
    act_lat = (time.perf_counter() - t0) * 1000.0
    
    if not act_res.is_successful:
        return {
            "activation_success": False,
            "diagnostic": act_res.diagnostic_message,
            "inference_success": False,
            "content": None
        }

    t1 = time.perf_counter()
    try:
        resp = await orch.model_manager.generate(prompt="Reply with exactly: ORBIT_RUNTIME_ONLINE")
        gen_lat = (time.perf_counter() - t1) * 1000.0
        return {
            "activation_success": True,
            "activation_latency_ms": round(act_lat, 2),
            "inference_success": True,
            "inference_latency_ms": round(gen_lat, 2),
            "content": resp.content.strip(),
            "model_id": resp.model_id,
            "total_duration_ms": resp.total_duration_ms
        }
    except Exception as e:
        gen_lat = (time.perf_counter() - t1) * 1000.0
        return {
            "activation_success": True,
            "activation_latency_ms": round(act_lat, 2),
            "inference_success": False,
            "inference_latency_ms": round(gen_lat, 2),
            "error": sanitize(str(e))
        }


async def main():
    print("=== GATE 2 STEP 1: DIRECT HTTP INFERENCE PROBE (WITH BACKOFF) ===")
    direct_res = run_direct_probe(model_name="gemini-flash-latest", max_attempts=5)
    print(json.dumps(direct_res, indent=2))
    
    if not direct_res["success"]:
        print("\nGATE 2 RESULT: DIRECT PROBE FAILED AFTER 5 ATTEMPTS")
        return

    print("\n=== GATE 2 STEP 2: ORBIT MODELMANAGER PRODUCTION RUNTIME PROBE ===")
    runtime_res = await run_orbit_runtime_probe(model_name="gemini-flash-latest")
    print(json.dumps(runtime_res, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
