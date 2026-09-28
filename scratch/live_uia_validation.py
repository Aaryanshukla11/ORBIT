"""Live Windows UIA Smoke & Hardening Gate Validation Script.

Executes Gates 3 through 9 directly on the live Windows OS:
- Gate 3: Live Windows UIA Smoke Test (Notepad)
- Gate 4: Cache Reality Test
- Gate 5: Cache Fallback Test
- Gate 6: Stale Element Test
- Gate 7: Focused Element Test
- Gate 8: Multi-Window Test
- Gate 9: Raw Performance Baseline
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import List, Optional

from orbit.runtime.perception.windows import Win32WindowObserver
from orbit.adapters.uia.controls import Control, ControlFromHandle
from orbit.adapters.uia.core import CacheRequest
from orbit.adapters.uia.tree.cache_utils import CacheRequestFactory, CachedControlHelper
from orbit.adapters.uia.tree.service import TreeService
from orbit.adapters.uia.tree.traversal import traverse_tree
from orbit.runtime.perception.models import UIElementObservation


def find_notepad_window(exclude_hwnds: set = None) -> Optional[int]:
    """Find a newly created visible Notepad window HWND."""
    exclude = exclude_hwnds or set()
    observer = Win32WindowObserver()
    for _ in range(20):  # poll up to 4 seconds
        _, wins = observer.observe_windows()
        for w in wins:
            if w.hwnd in exclude:
                continue
            proc = (w.process_name or "").lower()
            title = (w.title or "").lower()
            if ("notepad" in proc or "notepad" in title) and w.title:
                return w.hwnd
        time.sleep(0.2)
    return None


def run_validation():
    print("=" * 60)
    print("STARTING LIVE WINDOWS UIA VALIDATION (GATES 3 - 9)")
    print("=" * 60)

    service = TreeService()
    win_observer = Win32WindowObserver()

    # Get baseline windows before launching
    _, initial_wins = win_observer.observe_windows()
    initial_hwnds = {w.hwnd for w in initial_wins}

    # ---------------------------------------------------------
    # GATE 3, 4, 7: Launch Notepad and Test
    # ---------------------------------------------------------
    print("\n--- LAUNCHING NOTEPAD FOR GATES 3, 4, 7 ---")
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.0)

    hwnd = find_notepad_window(exclude_hwnds=initial_hwnds)
    print(f"Notepad PID: {proc.pid}, Resolved HWND: {hwnd}")

    if not hwnd:
        print("FAIL: Could not locate Notepad HWND!")
        proc.kill()
        return

    # GATE 4: Cache Reality Test
    print("\n[GATE 4] Checking CacheRequest creation & usage...")
    cache_req = CacheRequestFactory.create_tree_traversal_cache()
    if cache_req is not None:
        print(f"PASS: CacheRequest created successfully. Type: {type(cache_req)}")
    else:
        print("FAIL: CacheRequestFactory returned None!")

    # GATE 3: Observe Window Elements
    print("\n[GATE 3] Interrogating UIA tree via TreeService...")
    t0 = time.perf_counter()
    focused_obs, elements = service.observe_window_elements(target_hwnd=hwnd, max_elements=50)
    t1 = time.perf_counter()
    print(f"Observation complete in {t1 - t0:.4f}s. Total elements extracted: {len(elements)}")

    if len(elements) > 0:
        print("PASS: Non-empty observations extracted.")
        print(f"Discovered elements (sample up to 10):")
        for i, el in enumerate(elements[:10]):
            bbox = el.bounding_box
            bbox_str = f"({bbox.left}, {bbox.top}, {bbox.width}x{bbox.height})" if bbox else "None"
            print(f"  [{i+1}] Name='{el.name}' | Type='{el.control_type}' | AutoId='{el.automation_id}' | Bounds={bbox_str}")
    else:
        print("FAIL: Zero elements extracted from active Notepad window!")

    # GATE 7: Focused Element
    print("\n[GATE 7] Testing focused element extraction...")
    focused = service.get_focused_element(parent_context="Notepad", target_hwnd=hwnd)
    if focused:
        print(f"PASS: Focused element found: Name='{focused.name}', Type='{focused.control_type}', AutoId='{focused.automation_id}'")
    else:
        print("INFO: No active keyboard focus reported in Notepad (could be unfocused during test).")

    # GATE 5: Cache Fallback
    print("\n[GATE 5] Testing Cache Fallback (cache_request=None)...")
    root_ctrl, title = service.resolve_root_control(target_hwnd=hwnd)
    if root_ctrl:
        t_fb0 = time.perf_counter()
        fb_elements = traverse_tree(
            root_control=root_ctrl,
            max_depth=6,
            max_elements=30,
            cache_request=None,  # Force uncached fallback
            parent_context=title,
            target_hwnd=hwnd,
        )
        t_fb1 = time.perf_counter()
        print(f"PASS: Uncached fallback traversal succeeded with {len(fb_elements)} elements in {t_fb1 - t_fb0:.4f}s.")
        if len(fb_elements) > 0:
            print(f"  First fallback element: Name='{fb_elements[0].name}', Type='{fb_elements[0].control_type}'")
    else:
        print("FAIL: Could not resolve root control for fallback test!")

    # ---------------------------------------------------------
    # GATE 6: Stale Element Test
    # ---------------------------------------------------------
    print("\n[GATE 6] Closing Notepad to test stale / dead HWND handling...")
    import ctypes
    ctypes.windll.user32.SendMessageW(hwnd, 0x0010, 0, 0)
    time.sleep(1.0)  # Ensure OS window handle destruction

    print(f"Querying dead HWND {hwnd}...")
    stale_focused, stale_elements = service.observe_window_elements(target_hwnd=hwnd, max_elements=50)
    print(f"Result on dead HWND: focused={stale_focused}, element_count={len(stale_elements)}")
    if stale_focused is None and len(stale_elements) == 0:
        print("PASS: Dead HWND safely returned empty result without crashing or producing stale state.")
    else:
        print(f"FAIL: Dead HWND produced unexpected state: {stale_elements}")

    # ---------------------------------------------------------
    # GATE 8: Multi-Window Test
    # ---------------------------------------------------------
    print("\n[GATE 8] Testing Multi-Window isolation with two independent Notepad instances...")
    _, pre_multi_wins = win_observer.observe_windows()
    pre_multi_hwnds = {w.hwnd for w in pre_multi_wins}

    proc1 = subprocess.Popen(["notepad.exe"])
    time.sleep(1.0)
    hwnd1 = find_notepad_window(exclude_hwnds=pre_multi_hwnds)

    proc2 = subprocess.Popen(["notepad.exe"])
    time.sleep(1.0)
    hwnd2 = find_notepad_window(exclude_hwnds=pre_multi_hwnds | ({hwnd1} if hwnd1 else set()))

    print(f"Window 1: HWND={hwnd1}")
    print(f"Window 2: HWND={hwnd2}")

    if hwnd1 and hwnd2 and hwnd1 != hwnd2:
        window_nodes = service.get_window_wise_nodes([hwnd1, hwnd2], max_elements_per_window=20)
        count1 = len(window_nodes.get(hwnd1, []))
        count2 = len(window_nodes.get(hwnd2, []))
        print(f"Window 1 elements: {count1}")
        print(f"Window 2 elements: {count2}")

        # Check HWND tagging integrity
        leaks = False
        for el in window_nodes.get(hwnd1, []):
            if el.hwnd != hwnd1:
                leaks = True
        for el in window_nodes.get(hwnd2, []):
            if el.hwnd != hwnd2:
                leaks = True

        if not leaks and count1 > 0 and count2 > 0:
            print("PASS: Multi-window isolation verified (zero cross-window element leakage).")
        else:
            print(f"FAIL: Cross-window leakage detected or empty observations: leaks={leaks}")

        # Poisoning check: close window 1 and observe window 2
        print("Terminating Window 1; checking if Window 2 remains observable...")
        ctypes.windll.user32.SendMessageW(hwnd1, 0x0010, 0, 0)
        time.sleep(1.0)

        post_poison_nodes = service.get_window_wise_nodes([hwnd1, hwnd2], max_elements_per_window=20)
        p_count1 = len(post_poison_nodes.get(hwnd1, []))
        p_count2 = len(post_poison_nodes.get(hwnd2, []))
        print(f"Post-closure Window 1 elements: {p_count1}, Window 2 elements: {p_count2}")

        if p_count1 == 0 and p_count2 > 0:
            print("PASS: Dead Window 1 did not poison observation of living Window 2.")
        else:
            print("FAIL: Window closure poisoned multi-window extraction!")

        ctypes.windll.user32.SendMessageW(hwnd2, 0x0010, 0, 0)
    else:
        print("WARN: Could not acquire two distinct window HWNDs for multi-window test.")
        if hwnd1: ctypes.windll.user32.SendMessageW(hwnd1, 0x0010, 0, 0)
        if hwnd2: ctypes.windll.user32.SendMessageW(hwnd2, 0x0010, 0, 0)

    # ---------------------------------------------------------
    # GATE 9: Performance Baseline
    # ---------------------------------------------------------
    print("\n[GATE 9] Gathering Performance Baseline on Live Window...")
    _, pre_bench_wins = win_observer.observe_windows()
    pre_bench_hwnds = {w.hwnd for w in pre_bench_wins}

    bench_proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.0)
    bench_hwnd = find_notepad_window(exclude_hwnds=pre_bench_hwnds)

    if bench_hwnd:
        root_ctrl, title = service.resolve_root_control(target_hwnd=bench_hwnd)
        cache_req = CacheRequestFactory.create_tree_traversal_cache()

        cached_durations = []
        uncached_durations = []
        cached_counts = []
        uncached_counts = []

        # 5 iterations cached
        for it in range(5):
            t_s = time.perf_counter()
            els = traverse_tree(root_ctrl, max_depth=6, max_elements=40, cache_request=cache_req, parent_context=title, target_hwnd=bench_hwnd)
            d = time.perf_counter() - t_s
            cached_durations.append(d)
            cached_counts.append(len(els))

        # 5 iterations uncached
        for it in range(5):
            t_s = time.perf_counter()
            els = traverse_tree(root_ctrl, max_depth=6, max_elements=40, cache_request=None, parent_context=title, target_hwnd=bench_hwnd)
            d = time.perf_counter() - t_s
            uncached_durations.append(d)
            uncached_counts.append(len(els))

        print(f"Raw Measurements (5 runs each, max_elements=40):")
        print(f"  CACHED runs:   durations={[round(x, 4) for x in cached_durations]}s (avg: {sum(cached_durations)/len(cached_durations):.4f}s), element counts={cached_counts}")
        print(f"  UNCACHED runs: durations={[round(x, 4) for x in uncached_durations]}s (avg: {sum(uncached_durations)/len(uncached_durations):.4f}s), element counts={uncached_counts}")

        bench_proc.terminate()
        bench_proc.wait(timeout=3)
    else:
        print("FAIL: Could not launch benchmark process.")

    print("\n" + "=" * 60)
    print("LIVE WINDOWS UIA VALIDATION FINISHED")
    print("=" * 60)


if __name__ == "__main__":
    run_validation()
