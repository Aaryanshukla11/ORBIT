import asyncio
import ctypes
import ctypes.wintypes
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.adapters.pointer.safety import attached_to_input_desktop
from orbit.runtime.cognitive.loop import CognitiveExecutionLoop

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.wintypes.LPARAM]
user32.EnumWindows.restype = ctypes.wintypes.BOOL

def find_paint_hwnd():
    with attached_to_input_desktop():
        wins = []
        def proc(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    cls_buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, cls_buf, 256)
                    title = buf.value
                    cls_name = cls_buf.value
                    if "antigravity" in title.lower():
                        return True
                    if 'paint' in title.lower() or 'paint' in cls_name.lower():
                        wins.append((hwnd, title, cls_name))
            return True
        cb = WNDENUMPROC(proc)
        user32.EnumWindows(cb, 0)
        return wins[0][0] if wins else None

async def main():
    hwnd = find_paint_hwnd()
    print("Paint HWND:", hwnd)
    if not hwnd:
        print("Paint not found!")
        return

    # Bring Paint to foreground
    user32.ShowWindow(hwnd, 9) # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    await asyncio.sleep(0.5)

    # Get window rect
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    print(f"Paint Window Rect: left={rect.left}, top={rect.top}, right={rect.right}, bottom={rect.bottom}")
    
    # Compute canvas center within paint window
    # In Windows 11 Paint, the ribbon is at the top (~150px), canvas occupies the center/right
    win_w = rect.right - rect.left
    win_h = rect.bottom - rect.top
    center_x = rect.left + win_w // 2
    center_y = rect.top + 150 + (win_h - 150) // 2
    print(f"Calculated Canvas Drawing Center: ({center_x}, {center_y})")

    pointer = ProductionPointerAdapter()
    await pointer.initialize()
    print("Pointer adapter initialized.")

    cog_loop = CognitiveExecutionLoop(pointer=pointer)
    # Generate car paths around canvas center
    paths = cog_loop._generate_shape_paths("car", center_x=center_x, center_y=center_y, size=140)
    print(f"Generated {len(paths)} strokes for car:")
    for idx, s in enumerate(paths):
        print(f"  Stroke {idx+1}: {len(s)} points, start={s[0]}, end={s[-1]}")

    print("\nExecuting physical drawing strokes via PointerAdapter...")
    for idx, stroke in enumerate(paths):
        print(f"Executing stroke {idx+1}/{len(paths)} ({len(stroke)} pts)...")
        start_pt = stroke[0]
        await pointer.move_to(int(start_pt[0]), int(start_pt[1]))
        await asyncio.sleep(0.04)
        await pointer.press_down(button="left")
        await asyncio.sleep(0.03)

        for pt in stroke[1:]:
            await pointer.move_to(int(pt[0]), int(pt[1]))
            await asyncio.sleep(0.02)

        await pointer.release_up(button="left")
        await asyncio.sleep(0.04)

    print("Successfully drawn all strokes!")
    await pointer.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
