import os
import sys
import ctypes
from ctypes import wintypes
import time

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("prototypes/prototype_d_observation"))

ctypes.windll.ole32.CoInitializeEx(None, 0)

from accessibility_coordinator import AccessibilityCoordinator
from capture_engine import CaptureEngine
from orbit.runtime.perception.ocr import WindowsNativeOCRProvider
from orbit.runtime.targeting import EvidenceBasedTargetLocator, TargetIntent
from orbit.adapters.observation.snapshot import ObservationSnapshot, ObservedWindow, ObservedElement
from orbit.models.common import BoundingBox

# Find Calculator HWND via EnumDesktopWindows
calc_hwnd = 0
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

def _cb(h, _):
    global calc_hwnd
    if ctypes.windll.user32.IsWindowVisible(h):
        length = ctypes.windll.user32.GetWindowTextLengthW(h)
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(h, buff, length + 1)
        title = buff.value
        pid = wintypes.DWORD(0)
        ctypes.windll.user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        pname = ""
        if pid.value:
            hp = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)
            if hp:
                pbuf = ctypes.create_unicode_buffer(1024)
                sz = wintypes.DWORD(1024)
                if ctypes.windll.kernel32.QueryFullProcessImageNameW(hp, 0, pbuf, ctypes.byref(sz)):
                    pname = os.path.basename(pbuf.value)
                ctypes.windll.kernel32.CloseHandle(hp)
        if ("calc" in title.lower() or "calc" in pname.lower()) and ctypes.windll.user32.IsWindow(h):
            r = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(h, ctypes.byref(r))
            w = r.right - r.left
            h_dim = r.bottom - r.top
            if w > 100 and h_dim > 100:
                print(f"Found Calc Candidate HWND: {h}, title='{title}', proc='{pname}', size=({w}x{h_dim})")
                calc_hwnd = h
    return True

hdesk = ctypes.windll.user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    ctypes.windll.user32.EnumDesktopWindows(hdesk, WNDENUMPROC(_cb), 0)
    ctypes.windll.user32.CloseDesktop(hdesk)

if not calc_hwnd:
    hdesk_t = ctypes.windll.user32.GetThreadDesktop(ctypes.windll.kernel32.GetCurrentThreadId())
    if hdesk_t:
        ctypes.windll.user32.EnumDesktopWindows(hdesk_t, WNDENUMPROC(_cb), 0)

print(f"Target Calc HWND: {calc_hwnd}")

if calc_hwnd:
    ctypes.windll.user32.ShowWindow(calc_hwnd, 9)
    ctypes.windll.user32.SetForegroundWindow(calc_hwnd)
    time.sleep(0.5)

    # 1. Test AccessibilityCoordinator with 2000ms timeout
    coord = AccessibilityCoordinator(timeout_ms=2000.0)
    elements, prov_results = coord.collect_accessibility_observations(calc_hwnd)
    print(f"\n--- ACCESSIBILITY OBSERVATION FOR HWND {calc_hwnd} ---")
    print(f"Elements count: {len(elements)}")
    for pres in prov_results:
        print(f"Provider: {pres.provider_name}, status={pres.status.value}, duration={pres.duration_ms}ms, error={pres.error_message}, elements={len(pres.elements)}")
    
    for el in elements:
        print(f"  ELEMENT: name='{el.name}', aid='{el.automation_id}', role='{el.role}', bounds=({el.bounds.left},{el.bounds.top},{el.bounds.right},{el.bounds.bottom})")

    # 2. Test OCR Provider on screenshot
    cap = CaptureEngine()
    img, dur, b = cap.capture_full_desktop()
    print(f"\n--- OCR OBSERVATION ---")
    ocr = WindowsNativeOCRProvider()
    ocr_res = ocr.extract_text_sync(img)
    print(f"OCR Status: {ocr_res.status.value}, Regions: {len(ocr_res.text_regions)}")
    for r in ocr_res.text_regions:
        if any(c in r.text for c in ["7", "1", "2", "8", "9", "File", "Edit", "Calculator"]):
            print(f"  OCR Region: text='{r.text}', bounds=({r.bounding_box.left},{r.bounding_box.top},{r.bounding_box.width},{r.bounding_box.height})")

    # 3. Test Locator resolution for "7"
    locator = EvidenceBasedTargetLocator()
    from orbit.adapters.observation.mapper import map_prototype_snapshot
    from app_types import DesktopGeometry, Rect, WindowObservation
    
    rect_win = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(calc_hwnd, ctypes.byref(rect_win))
    win_obs = WindowObservation(
        hwnd=calc_hwnd,
        process_id=0,
        process_name="CalculatorApp.exe",
        window_title="Calculator",
        extended_bounds=Rect(left=rect_win.left, top=rect_win.top, right=rect_win.right, bottom=rect_win.bottom),
        client_bounds=Rect(left=rect_win.left, top=rect_win.top, right=rect_win.right, bottom=rect_win.bottom),
        is_visible=True,
        is_minimized=False,
        is_maximized=False,
        is_foreground=True,
        z_order_rank=0,
        dpi_scaling=1.0,
    )
    
    from freshness_tracker import FreshnessTracker
    ft = FreshnessTracker()
    from app_types import ConfidenceLevel
    psnap = ft.build_snapshot(
        snapshot_id="snap_test_diag",
        capture_duration_ms=10.0,
        desktop_geometry=DesktopGeometry(virtual_left=0, virtual_top=0, virtual_right=2880, virtual_bottom=1800, virtual_width=2880, virtual_height=1800, primary_display_index=0, dpi_scale=1.0),
        foreground_window=win_obs,
        windows=(win_obs,),
        visual_evidence=(),
        accessibility_evidence=elements,
        detected_targets=(),
        confidence=ConfidenceLevel.CONFIRMED,
        conflicts=(),
    )
    prod_snap = map_prototype_snapshot(psnap, snapshot_id="snap_test_diag")
    prod_snap.telemetry["screenshot"] = img
    
    intent7 = TargetIntent(
        target_type="element",
        name="7",
        role="button",
        window_title="Calculator",
        target_hwnd=calc_hwnd,
    )
    res7 = locator.resolve_target(prod_snap, intent7)
    print(f"\n--- LOCATOR RESOLUTION FOR '7' ---")
    print(f"Status: {res7.status.value}")
    if res7.target:
        print(f"Resolved Target: ID={res7.target.target_id}, Source={res7.target.evidence.source}, Name='{res7.target.evidence.name}', SafePoint=({res7.target.safe_point.x},{res7.target.safe_point.y}), Bounds={res7.target.bounding_box}")
    else:
        print(f"Diagnostic: {res7.diagnostic_message}")
