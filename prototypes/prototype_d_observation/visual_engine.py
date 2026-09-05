"""
3-Layer Visual Engine for ORBIT Prototype D v1.2.1.
Enforces the fundamental architectural invariant:
VISUAL CHANGE DETECTION != SEMANTIC UI UNDERSTANDING

Layer V1: Visual Change Detection (Perceptual dHash, Pixel Variance, Contrast)
Layer V2: Visual Text Extraction (OCR adapter integration)
Layer V3: Semantic UI Interpretation (Experimental / Capability Dependent)
"""

import math
import time
from typing import List, Tuple, Optional
from PIL import Image, ImageStat, ImageOps, ImageChops

from app_types import (
    Rect,
    VisualFeatureObservation,
    EvidenceSource,
)
from ocr_engine import DefaultOCRDispatcher


class VisualEngine:
    """
    3-Layer Visual Engine separating raw pixel heuristics from semantic UI understanding.
    """

    def __init__(self):
        self.ocr_dispatcher = DefaultOCRDispatcher()

    # -------------------------------------------------------------------------
    # Layer V1: Visual Change Detection & Pixel Statistics
    # -------------------------------------------------------------------------

    @staticmethod
    def compute_dhash(image: Image.Image, hash_size: int = 8) -> str:
        """
        Computes 64-bit Difference Hash (dHash) for fast perceptual visual change detection.
        """
        # Resize to (hash_size + 1, hash_size), grayscale
        resized = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
        pixels = list(resized.getdata())

        difference = []
        for row in range(hash_size):
            for col in range(hash_size):
                pixel_left = pixels[row * (hash_size + 1) + col]
                pixel_right = pixels[row * (hash_size + 1) + col + 1]
                difference.append(pixel_left > pixel_right)

        # Convert boolean list to hex string
        decimal_val = 0
        hex_str = []
        for idx, val in enumerate(difference):
            if val:
                decimal_val += 2 ** (idx % 4)
            if (idx % 4) == 3:
                hex_str.append(hex(decimal_val)[2:])
                decimal_val = 0
        return "".join(hex_str)

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        """Calculates hamming distance between two hex dHash strings."""
        if len(hash1) != len(hash2):
            return 999
        dist = 0
        for c1, c2 in zip(hash1, hash2):
            val1 = int(c1, 16)
            val2 = int(c2, 16)
            xor_val = val1 ^ val2
            dist += bin(xor_val).count("1")
        return dist

    @staticmethod
    def compute_color_variance(image: Image.Image) -> float:
        """Calculates average RGB color channel variance."""
        stat = ImageStat.Stat(image.convert("RGB"))
        variances = stat.var
        return sum(variances) / len(variances) if variances else 0.0

    @staticmethod
    def compute_contrast_ratio(image: Image.Image) -> float:
        """Calculates grayscale Michelson contrast ratio (0.0 .. 1.0)."""
        gray = image.convert("L")
        extrema = gray.getextrema()
        if not extrema:
            return 0.0
        min_val, max_val = extrema
        if (max_val + min_val) == 0:
            return 0.0
        return (max_val - min_val) / (max_val + min_val)

    def detect_visual_change(self, image1: Image.Image, image2: Image.Image, threshold_distance: int = 1) -> bool:
        """
        Layer V1 Change Detection: Returns True if visual frame or ROI differs beyond threshold.
        """
        if image1.size != image2.size:
            return True
        h1 = self.compute_dhash(image1)
        h2 = self.compute_dhash(image2)
        dist = self.hamming_distance(h1, h2)
        var_diff = abs(self.compute_color_variance(image1) - self.compute_color_variance(image2))
        return dist >= threshold_distance or var_diff > 1.0

    def detect_changes(
        self, image1: Image.Image, image2: Image.Image
    ) -> Tuple[bool, Optional[Rect], int, float]:
        """
        Layer V1 Detailed Change Detection: Returns (has_changed, change_bbox, dhash_diff, variance_diff).
        """
        if not image1 or not image2 or image1.size != image2.size:
            return True, None, 999, 999.0

        h1 = self.compute_dhash(image1)
        h2 = self.compute_dhash(image2)
        dist = self.hamming_distance(h1, h2)
        v1 = self.compute_color_variance(image1)
        v2 = self.compute_color_variance(image2)
        var_diff = abs(v1 - v2)

        # Compute difference bounding box
        diff_img = ImageChops.difference(image1.convert("RGB"), image2.convert("RGB"))
        bbox = diff_img.getbbox()
        change_rect = Rect(left=bbox[0], top=bbox[1], right=bbox[2], bottom=bbox[3]) if bbox else None
        has_changed = (bbox is not None) or (dist >= 1) or (var_diff > 0.5)

        return has_changed, change_rect, dist, var_diff

    # -------------------------------------------------------------------------
    # Layer V2: Visual Text Extraction (OCR)
    # -------------------------------------------------------------------------

    def extract_visual_text(self, image: Image.Image) -> Tuple[List[Tuple[Rect, str, float]], str, bool]:
        """
        Layer V2 Text Extraction: Extracts text bounding boxes using local OCR dispatcher.
        Returns (list of (Rect, text, confidence), provider_name, is_available).
        """
        return self.ocr_dispatcher.extract_text(image)

    # -------------------------------------------------------------------------
    # Layer V3: Feature Extraction Pipeline
    # -------------------------------------------------------------------------

    def extract_features_from_region(
        self,
        full_screenshot: Image.Image,
        region_rect: Rect,
        generation_id: int = 0,
        feature_id_prefix: str = "vis_feat",
    ) -> Optional[VisualFeatureObservation]:
        """
        Extracts multi-layer visual observation from specific screen bounding rect.
        """
        w, h = full_screenshot.size
        # Clip rect to image bounds
        crop_left = max(0, min(w, region_rect.left))
        crop_top = max(0, min(h, region_rect.top))
        crop_right = max(crop_left, min(w, region_rect.right))
        crop_bottom = max(crop_top, min(h, region_rect.bottom))

        if (crop_right - crop_left) <= 0 or (crop_bottom - crop_top) <= 0:
            return None

        crop_img = full_screenshot.crop((crop_left, crop_top, crop_right, crop_bottom))

        dhash_val = self.compute_dhash(crop_img)
        variance_val = round(self.compute_color_variance(crop_img), 2)
        contrast_val = round(self.compute_contrast_ratio(crop_img), 3)

        # Layer V2: Attempt local OCR on cropped box
        detected_text = None
        ocr_conf = 0.0
        ocr_boxes, prov, avail = self.extract_visual_text(crop_img)
        if avail and ocr_boxes:
            detected_text = " ".join([b[1] for b in ocr_boxes]).strip()
            ocr_conf = sum([b[2] for b in ocr_boxes]) / len(ocr_boxes)

        return VisualFeatureObservation(
            feature_id=f"{feature_id_prefix}_{region_rect.left}_{region_rect.top}",
            bounds=region_rect,
            detected_text=detected_text,
            ocr_confidence=round(ocr_conf, 2),
            perceptual_hash=dhash_val,
            color_variance=variance_val,
            contrast_ratio=contrast_val,
            timestamp_ns=time.perf_counter_ns(),
            generation_id=generation_id,
        )
