import os
from PIL import Image
import numpy as np

user_profile = os.environ.get("USERPROFILE", "")
target_path = os.path.join(user_profile, "OneDrive", "Desktop", "test.png")
if not os.path.exists(target_path):
    target_path = os.path.join(user_profile, "Desktop", "test.png")

if os.path.exists(target_path):
    img = Image.open(target_path)
    arr = np.array(img.convert("RGB"))
    non_white = np.sum(arr < 240)
    print("Image size:", img.size)
    print("Non-white pixel values count:", non_white)
    print("Unique colors:", len(set(tuple(p) for row in arr for p in row)))
else:
    print("File does not exist")
