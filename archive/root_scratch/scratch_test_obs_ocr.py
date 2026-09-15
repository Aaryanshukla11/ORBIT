import asyncio
import io
import time
import subprocess
from PIL import Image

from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.runtime.perception.ocr import WindowsNativeOCRProvider

async def test_obs_ocr():
    adapter = ProductionObservationAdapter()
    await adapter.initialize()
    print("Observation adapter initialized successfully")
    
    # Capture screen
    frame_data = await adapter.capture_screen()
    # Load image from frame_data
    image = Image.open(io.BytesIO(frame_data.raw_bytes))
    print(f"PIL Image size: {image.size}, bytes: {len(frame_data.raw_bytes)}")
    print(f"PIL Image: {image.size}")
    
    # OCR
    ocr = WindowsNativeOCRProvider()
    ocr_res = await ocr.extract_text(image)
    print(f"OCR Success: {ocr_res.is_success}")
    print(f"OCR Error: {ocr_res.error_message}")
    print(f"OCR Full Text: '{ocr_res.full_text}'")
    
    await adapter.shutdown()

if __name__ == "__main__":
    asyncio.run(test_obs_ocr())
