import asyncio
from PIL import Image, ImageDraw, ImageFont
from orbit.runtime.perception.ocr import WindowsNativeOCRProvider

async def test_ocr():
    ocr = WindowsNativeOCRProvider()
    print("OCR available:", ocr.is_available())
    
    # Create test image with text "ORBIT TEST"
    img = Image.new('RGB', (400, 100), color='white')
    d = ImageDraw.Draw(img)
    d.text((20, 30), "ORBIT TEST", fill='black')
    
    res = await ocr.extract_text(img)
    print("OCR Status:", res.status)
    print("OCR Full Text:", res.full_text)
    print("OCR Text Regions:", len(res.text_regions))

if __name__ == "__main__":
    asyncio.run(test_ocr())
