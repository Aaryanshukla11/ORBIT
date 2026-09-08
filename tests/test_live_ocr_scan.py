import os
import sys
import ctypes
from ctypes import wintypes
import time
from PIL import Image

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("prototypes/prototype_d_observation"))

from capture_engine import CaptureEngine
from orbit.runtime.perception.ocr import WindowsNativeOCRProvider

# Attach thread to interactive input desktop
hdesk = ctypes.windll.user32.OpenInputDesktop(0, False, 0x01FF)
print(f"OpenInputDesktop: {hdesk}")
if hdesk:
    res_std = ctypes.windll.user32.SetThreadDesktop(hdesk)
    print(f"SetThreadDesktop: {res_std}")

t0 = time.perf_counter()
cap = CaptureEngine()
img, dur, b = cap.capture_full_desktop()
print(f"Captured screenshot: {img.size if img else None} in {dur:.2f}ms")
print(f"Image extrema: {img.getextrema() if img else None}")
sample_px = [img.getpixel((x, y)) for x in [100, 500, 1000, 1500] for y in [100, 500, 1000]]
print(f"Sample pixels: {sample_px}")

ocr = WindowsNativeOCRProvider()
print(f"OCR available: {ocr.is_available()}")
t0 = time.perf_counter()
res_full = ocr.extract_text_sync(img)
print(f"Full desktop OCR status: {res_full.status.value}, Regions: {len(res_full.text_regions)}, Text Len: {len(res_full.full_text)}, Duration: {res_full.duration_ms}ms")
print(f"Sample full text:\n{res_full.full_text[:400]}")
for r in res_full.text_regions[:10]:
    print(f"  '{r.text}' at ({r.bounding_box.left}, {r.bounding_box.top}, {r.bounding_box.width}x{r.bounding_box.height})")

ibuffer = ctypes.c_void_p()
hr_buf = ocr._crypto_factory.contents.lpVtbl.contents.CreateFromByteArray(
    ocr._crypto_factory, len(raw_bytes), ctypes.cast(c_buf, ctypes.POINTER(ctypes.c_ubyte)), ctypes.byref(ibuffer)
)
print(f"CreateFromByteArray hr=0x{hr_buf & 0xFFFFFFFF:08X}, ibuffer={ibuffer.value}")

software_bitmap = ctypes.c_void_p()
hr_sb = ocr._sb_factory.contents.lpVtbl.contents.CreateCopyFromBuffer(
    ocr._sb_factory, ibuffer, 87, conv_img.width, conv_img.height, ctypes.byref(software_bitmap)
)
print(f"CreateCopyFromBuffer hr=0x{hr_sb & 0xFFFFFFFF:08X}, software_bitmap={software_bitmap.value}")

async_op = ctypes.c_void_p()
hr_rec = ocr._ocr_engine.contents.lpVtbl.contents.RecognizeAsync(
    ocr._ocr_engine, software_bitmap, ctypes.byref(async_op)
)
print(f"RecognizeAsync hr=0x{hr_rec & 0xFFFFFFFF:08X}, async_op={async_op.value}")

if async_op.value:
    from orbit.runtime.perception.ocr import _GUID, _IAsyncInfo, _IAsyncOperation, _IOcrResult
    qi_ptr = ctypes.cast(ctypes.cast(async_op, ctypes.POINTER(ctypes.c_void_p)).contents, ctypes.POINTER(ctypes.c_void_p))[0]
    QueryInterface = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))(qi_ptr)
    iid_async_info = _GUID.from_str("00000036-0000-0000-C000-000000000046")
    async_info = ctypes.POINTER(_IAsyncInfo)()
    hr_qi = QueryInterface(async_op, ctypes.byref(iid_async_info), ctypes.cast(ctypes.byref(async_info), ctypes.POINTER(ctypes.c_void_p)))
    print(f"QueryInterface IAsyncInfo hr=0x{hr_qi & 0xFFFFFFFF:08X}, async_info={async_info}")

    status = ctypes.c_int(0)
    for _ in range(50):
        async_info.contents.lpVtbl.contents.get_Status(async_info, ctypes.byref(status))
        if status.value == 1:
            break
        time.sleep(0.01)
    print(f"Async status after wait: {status.value}")

    async_op_typed = ctypes.cast(async_op, ctypes.POINTER(_IAsyncOperation))
    ocr_result_ptr = ctypes.POINTER(_IOcrResult)()
    hr_res = async_op_typed.contents.lpVtbl.contents.GetResults(async_op_typed, ctypes.byref(ocr_result_ptr))
    print(f"GetResults hr=0x{hr_res & 0xFFFFFFFF:08X}, ocr_result_ptr={ocr_result_ptr}")

    if ocr_result_ptr:
        hs_full = ctypes.c_void_p()
        hr_gt = ocr_result_ptr.contents.lpVtbl.contents.get_Text(ocr_result_ptr, ctypes.byref(hs_full))
        print(f"get_Text hr=0x{hr_gt & 0xFFFFFFFF:08X}, hs_full value={hs_full.value}")
        if hs_full.value:
            length = ctypes.c_uint(0)
            buf = ocr._WindowsGetStringRawBuffer(hs_full, ctypes.byref(length))
            print(f"WindowsGetStringRawBuffer -> length={length.value}, buf='{buf}'")

# Query MaxImageDimension
ocr_statics = ocr._get_factory("Windows.Media.Ocr.OcrEngine", "5bffa85a-3384-3540-9940-699120d428a8")
from orbit.runtime.perception.ocr import _IOcrEngineStatics
ocr_statics_typed = ctypes.cast(ocr_statics, ctypes.POINTER(_IOcrEngineStatics))
get_MaxImageDimension = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint))(
    ocr_statics_typed.contents.lpVtbl.contents.get_MaxImageDimension
)
max_dim = ctypes.c_uint(0)
get_MaxImageDimension(ocr_statics, ctypes.byref(max_dim))
print(f"OcrEngine MaxImageDimension: {max_dim.value} pixels (Current image was {img.width}x{img.height})")

# Test on scaled image or cropped image
cropped = img.resize((img.width // 2, img.height // 2))
res_scaled = ocr.extract_text_sync(cropped)
print(f"Resized image ({cropped.width}x{cropped.height}) OCR status: {res_scaled.status.value}, text len={len(res_scaled.full_text)}, regions={len(res_scaled.text_regions)}")
print(f"Sample full text:\n{res_scaled.full_text[:300]}")
for r in res_scaled.text_regions[:10]:
    print(f"  Region: '{r.text}' at {r.bounding_box}")

