"""Deterministic text normalization and comparison utilities for semantic perception."""

from __future__ import annotations

import re
import unicodedata
from typing import List, Optional

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(
    text: Optional[str],
    *,
    case_fold: bool = True,
    strip_whitespace: bool = True,
    collapse_whitespace: bool = True,
    unicode_form: str = "NFKC",
) -> str:
    """Deterministically normalize text for truthful, predictable matching.

    Invariants:
    1. None inputs produce empty strings.
    2. Applies standard Unicode normalization (default NFKC) to canonicalize compatibility characters.
    3. Collapses multiple consecutive whitespace characters into a single standard space (' ').
    4. Strips leading and trailing whitespace if requested.
    5. Applies Unicode case folding if requested (never simple ASCII lower).
    """
    if not text:
        return ""

    # 1. Unicode Normalization
    result = unicodedata.normalize(unicode_form, text)

    # 2. Whitespace collapsing
    if collapse_whitespace:
        result = _WHITESPACE_RE.sub(" ", result)

    # 3. Stripping
    if strip_whitespace:
        result = result.strip()

    # 4. Case folding
    if case_fold:
        result = result.casefold()

    return result


def matches_text(
    candidate: str,
    query: str,
    *,
    exact_match: bool = True,
    case_sensitive: bool = False,
) -> bool:
    """Evaluate whether candidate text matches the search query according to declared constraints."""
    norm_candidate = normalize_text(candidate, case_fold=not case_sensitive)
    norm_query = normalize_text(query, case_fold=not case_sensitive)

    if not norm_query:
        return False

    if exact_match:
        return norm_candidate == norm_query
    else:
        return norm_query in norm_candidate


def tokenize_text(text: str, *, case_sensitive: bool = False) -> List[str]:
    """Tokenize text into normalized word tokens."""
    norm = normalize_text(text, case_fold=not case_sensitive)
    if not norm:
        return []
    return norm.split()
