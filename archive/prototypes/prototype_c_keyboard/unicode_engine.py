"""
Sequence-Level Unicode & UTF-16 Surrogate Pair Engine for Prototype C.
Decomposes Unicode characters into UTF-16 code units (including non-BMP emojis and variation selectors),
formats SendInput KEYEVENTF_UNICODE packets, and performs codepoint-level readback comparison.
"""

import unicodedata
from typing import List, Tuple
from app_types import UnicodeValidationRecord, UnicodeMatchOutcome


class UnicodeEngine:
    """
    Transforms Unicode text strings into discrete Win32 UTF-16 injection packets
    and performs exact vs normalization-equivalent verification.
    """

    @staticmethod
    def text_to_codepoints(text: str) -> List[int]:
        """Returns the list of raw Unicode code point integers."""
        return [ord(c) for c in text]

    @staticmethod
    def text_to_utf16_code_units(text: str) -> List[int]:
        """
        Decomposes a Python string into 16-bit UTF-16 code units for Win32 SendInput (wScan).
        Handles BMP codepoints, surrogate pairs (Emojis, Supplementary Ideographs),
        combining characters, and variation selectors.
        """
        code_units: List[int] = []
        for char in text:
            cp = ord(char)
            if cp <= 0xFFFF:
                # Basic Multilingual Plane (BMP)
                code_units.append(cp)
            else:
                # Supplementary Plane: Calculate High and Low Surrogates
                cp_sub = cp - 0x10000
                high_surrogate = 0xD800 + (cp_sub >> 10)
                low_surrogate = 0xDC00 + (cp_sub & 0x3FF)
                code_units.append(high_surrogate)
                code_units.append(low_surrogate)
        return code_units

    @classmethod
    def evaluate_unicode_match(
        cls,
        expected_text: str,
        received_text: str,
        dispatched_units: List[int],
    ) -> UnicodeValidationRecord:
        """
        Performs strict codepoint-by-codepoint analysis, distinguishing EXACT_MATCH from
        NORMALIZATION_EQUIVALENT and CHARACTER_CORRUPTION.
        """
        expected_cps = cls.text_to_codepoints(expected_text)
        received_cps = cls.text_to_codepoints(received_text)
        dispatched_hex = [f"0x{u:04X}" for u in dispatched_units]

        exact_match = (expected_cps == received_cps)

        # Check NFC canonical normalization
        expected_nfc = unicodedata.normalize("NFC", expected_text)
        received_nfc = unicodedata.normalize("NFC", received_text)
        nfc_match = (expected_nfc == received_nfc)

        if exact_match:
            outcome = UnicodeMatchOutcome.EXACT_MATCH
        elif nfc_match:
            outcome = UnicodeMatchOutcome.NORMALIZATION_EQUIVALENT
        elif not received_text and expected_text:
            outcome = UnicodeMatchOutcome.READBACK_UNAVAILABLE
        else:
            outcome = UnicodeMatchOutcome.CHARACTER_CORRUPTION

        return UnicodeValidationRecord(
            expected_text=expected_text,
            received_text=received_text,
            expected_codepoints=expected_cps,
            received_codepoints=received_cps,
            dispatched_utf16_units=dispatched_hex,
            outcome=outcome,
            exact_match=exact_match,
            nfc_match=nfc_match,
        )
