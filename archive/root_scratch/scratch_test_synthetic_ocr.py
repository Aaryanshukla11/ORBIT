import asyncio
from PIL import Image, ImageDraw, ImageFont
from orbit.runtime.perception.ocr import WindowsNativeOCRProvider

async def test_synthetic_ocr():
    # Create white image with black text "HELLO ORBIT"
    img = Image.new("RGB", (600, 200), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "HELLO ORBIT", fill="black")
    img.save("test_text.png")
    
    ocr = WindowsNativeOCRProvider()
    print(f"OCR is_available: {ocr.is_available()}")
    res = await ocr.extract_text(img)
    print(f"OCR Status: {res.status}")
    print(f"OCR Error: {res.error_message}")
    print(f"OCR Full Text: '{res.full_text}'")
    print(f"OCR Regions: {len(res.text_regions)}")

if __name__ == "__main__":
    asyncio.run(test_synthetic_ocr())
