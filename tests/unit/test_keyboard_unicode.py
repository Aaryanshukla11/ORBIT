"""Unit tests for UnicodeEngine and UTF-16 surrogate handling in ORBIT M1.3."""

from orbit.adapters.keyboard.unicode import (
    UnicodeEngine,
    UnicodeMatchOutcome,
)


def test_unicode_ascii_decomposition():
    text = "Hello 123"
    units = UnicodeEngine.text_to_utf16_code_units(text)
    assert len(units) == len(text)
    assert units == [ord(c) for c in text]


def test_unicode_multilingual_decomposition():
    text = "你好世界 (Arabic: مرحبا)"
    units = UnicodeEngine.text_to_utf16_code_units(text)
    assert len(units) == len(text)
    assert all(0 <= u <= 0xFFFF for u in units)


def test_unicode_surrogate_pair_emojis():
    # '🚀' is U+1F680 -> surrogate pair: 0xD83D, 0xDE80
    emoji = "🚀"
    units = UnicodeEngine.text_to_utf16_code_units(emoji)
    assert len(units) == 2
    assert units[0] == 0xD83D
    assert units[1] == 0xDE80


def test_unicode_match_evaluation():
    # Exact match
    res_exact = UnicodeEngine.evaluate_unicode_match("Hello 🚀", "Hello 🚀", [0x0048, 0xD83D, 0xDE80])
    assert res_exact.outcome == UnicodeMatchOutcome.EXACT_MATCH
    assert res_exact.exact_match is True

    # Character corruption
    res_corrupt = UnicodeEngine.evaluate_unicode_match("Hello 🚀", "Hello ?", [0x0048, 0xD83D, 0xDE80])
    assert res_corrupt.outcome == UnicodeMatchOutcome.CHARACTER_CORRUPTION
    assert res_corrupt.exact_match is False

    # Readback unavailable
    res_unavail = UnicodeEngine.evaluate_unicode_match("Hello", "", [0x0048])
    assert res_unavail.outcome == UnicodeMatchOutcome.READBACK_UNAVAILABLE
