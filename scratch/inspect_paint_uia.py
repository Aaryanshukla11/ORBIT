import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("src"))

from orbit.adapters.observation.uia import WindowsUiaTreeEngine

engine = WindowsUiaTreeEngine()
elements = engine.extract_uia_elements()
paint_elems = [e for e in elements if "paint" in (e.name or "").lower() or "save" in (e.name or "").lower() or "file" in (e.name or "").lower()]
print(f"Total UIA elements: {len(elements)}")
print(f"Paint/Save UIA elements: {len(paint_elems)}")
for e in paint_elems[:20]:
    print(f"  Name: '{e.name}', Type: '{e.control_type}', Class: '{e.class_name}', BBox: {e.bounding_box}")
