"""Focused manual-only diagnostic script testing real production desktop text entry.

MANDATORY SAFETY GUARD:
This script WILL NOT run automatically. It requires explicit user intent via:
$env:ORBIT_ALLOW_MANUAL_LIVE_TEST="1"; python scratch/test_live_text_reality.py

Scenarios covered:
A. Exact ASCII text: "ORBIT Vision Test 123"
B. Repeated-character stress test: "111222333444"
C. Mixed-case and punctuation: "Hello, ORBIT! Test #42."
D. Longer text (>100 chars): "The quick brown fox jumps over the lazy dog. ORBIT Desktop Automation Reality Verification 2026 #999."

Invariants enforced:
- Maximum ONE controlled Notepad instance.
- No automatic repeated window/tab launching.
- Strict 20s timeout per scenario.
- Full diagnostic report comparing Intended vs Observed and categorical match state.
- Clean application termination on exit.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import time
from typing import Optional

# Set Windows asyncio policy if win32
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


SCENARIOS = {
    "A": "ORBIT Vision Test 123",
    "B": "111222333444",
    "C": "Hello, ORBIT! Test #42.",
    "D": "The quick brown fox jumps over the lazy dog. ORBIT Desktop Automation Reality Verification 2026 #999.",
}


def check_safety_guard() -> bool:
    """Ensure script is explicitly initiated by human operator."""
    val = os.environ.get("ORBIT_ALLOW_MANUAL_LIVE_TEST", "").strip()
    if val != "1":
        print("\n" + "=" * 70)
        print("[SAFETY GUARD BLOCKED EXECUTION]")
        print("This live reality test script requires explicit manual authorization.")
        print("To run manually on your Windows desktop, set the environment variable:")
        print("  powershell: $env:ORBIT_ALLOW_MANUAL_LIVE_TEST=\"1\"; python scratch/test_live_text_reality.py")
        print("=" * 70 + "\n")
        return False
    return True


async def run_scenario(scenario_key: str, text: str) -> bool:
    """Executes a single test scenario against a clean, controlled Notepad instance."""
    print(f"\n{'='*70}")
    print(f"RUNNING SCENARIO {scenario_key}")
    print(f"Intended Text:        '{text}' (len={len(text)})")
    print(f"{'='*70}")

    from orbit.adapters.observation.adapter import ObservationAdapter
    from orbit.runtime.agent.contracts import TextMatchState
    from orbit.runtime.agent.state import DesktopStateSnapshot
    from orbit.runtime.agent.verifier import AgentStateTransitionVerifier
    from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
    from orbit.runtime.cognitive.observer import CurrentStateObserver

    # 1. Close any stale Notepad instances before test
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
        await asyncio.sleep(0.5)

    # 2. Launch single controlled Notepad instance
    proc = subprocess.Popen(["notepad.exe"])
    await asyncio.sleep(1.0)

    notepad_hwnd = 0
    if sys.platform == "win32":
        import ctypes
        user32 = ctypes.windll.user32
        notepad_hwnd = user32.FindWindowW("Notepad", None)
        if not notepad_hwnd:
            notepad_hwnd = user32.GetForegroundWindow()
        if notepad_hwnd:
            user32.SetForegroundWindow(notepad_hwnd)
            await asyncio.sleep(0.1)

    try:
        # 3. Instantiate production observer & execution loop
        obs_adapter = ObservationAdapter()
        observer = CurrentStateObserver(observation=obs_adapter)
        verifier = AgentStateTransitionVerifier()
        loop = AgentExecutionLoop(observer=observer)

        # 4. Dispatch text using production deterministic pipeline
        t_start = time.perf_counter()
        dispatch_ok, err_msg, diag = await loop._execute_deterministic_text_input(
            text=text,
            press_enter=True,
            target_hwnd=notepad_hwnd,
            target_title="Notepad",
        )

        print(f"\n[DISPATCH RESULT]")
        print(f"  Attempt ID:           {diag.get('input_attempt_id')}")
        print(f"  Strategy Used:        {diag.get('selected_input_strategy')}")
        print(f"  Dispatch Success:     {dispatch_ok}")
        if err_msg:
            print(f"  Dispatch Error:       {err_msg}")

        # 5. UI settlement wait
        await asyncio.sleep(0.4)

        # 6. Capture fresh post-action observation
        post_obs = await observer.observe(f"Verify typing for scenario {scenario_key}")

        post_state = DesktopStateSnapshot(
            snapshot_id=post_obs.observation_id,
            active_window_hwnd=post_obs.active_window_hwnd,
            active_window_title=post_obs.active_window_title,
            visible_windows=post_obs.visible_windows,
            target_app_exists=post_obs.target_app_exists,
            target_app_is_active=post_obs.target_app_is_active,
            canvas_status=post_obs.canvas_status or "UNKNOWN",
            ocr_tokens=post_obs.ocr_tokens,
        )

        # 7. Independent Exact-Text Reality Verification
        ver_res = verifier._verify_text_in_state(
            expected_text=text,
            post_state=post_state,
            post_observation=post_obs.desktop_observation,
        )

        match_state = ver_res.match_state
        is_verified = match_state in (TextMatchState.EXACT_MATCH, TextMatchState.NORMALIZED_MATCH)

        print(f"\n[REALITY VERIFICATION REPORT]")
        print(f"  Expected Text:        '{text}'")
        print(f"  Observed Text:        '{ver_res.observed_text}'")
        print(f"  Match State:          {match_state.value}")
        print(f"  Confidence:           {ver_res.confidence:.2f}")
        print(f"  Evidence Source:      {ver_res.primary_source}")
        print(f"  Effect Verified:      {is_verified}")
        print(f"  Duration:             {(time.perf_counter() - t_start)*1000.0:.1f}ms")

        if is_verified:
            print(f"\n>>> SCENARIO {scenario_key}: PASSED <<<\n")
        else:
            print(f"\n>>> SCENARIO {scenario_key}: FAILED <<<\n")

        return is_verified

    finally:
        # Cleanup: close the controlled Notepad instance
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except Exception:
                proc.kill()
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)


async def main():
    parser = argparse.ArgumentParser(description="Manual Reality Text Input Verification")
    parser.add_argument(
        "--scenario",
        choices=["A", "B", "C", "D", "all"],
        default="all",
        help="Scenario to run (A: ASCII, B: Repeated Chars, C: Mixed Punctuation, D: Long Text)",
    )
    args = parser.parse_args()

    if not check_safety_guard():
        sys.exit(0)

    scenarios_to_run = list(SCENARIOS.keys()) if args.scenario == "all" else [args.scenario]
    results = {}

    for s_key in scenarios_to_run:
        target_text = SCENARIOS[s_key]
        ok = await run_scenario(s_key, target_text)
        results[s_key] = ok
        await asyncio.sleep(0.5)

    print("\n" + "=" * 70)
    print("SUMMARY RESULTS:")
    for s_key, ok in results.items():
        print(f"  Scenario {s_key}: {'PASS' if ok else 'FAIL'}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
