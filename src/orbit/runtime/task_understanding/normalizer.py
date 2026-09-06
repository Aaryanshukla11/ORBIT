"""Literal-preserving normalization and clause segmentation for task understanding."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple


class TaskNormalizer:
    """Normalizes natural language task requests while strictly preserving exact literal payloads."""

    # Matches single quotes, double quotes, smart quotes, and guillemets
    QUOTE_PATTERN = re.compile(r'["\'“”«»‘](.*?)["\'“”«»’]', re.DOTALL)
    
    # Clause delimiter pattern (splits on conjunctions when not inside quotes)
    CONJUNCTION_PATTERN = re.compile(
        r'\b(?:and\s+then|after\s+that|then|and|but|while)\b',
        re.IGNORECASE,
    )

    def extract_literals(self, text: str) -> Tuple[str, Dict[str, str]]:
        """Extract quoted strings into placeholders to guarantee 100% case/Unicode preservation.

        Returns:
            Tuple of (sanitized_text_with_placeholders, literal_lookup_dict)
        """
        literals: Dict[str, str] = {}
        counter = 0

        def _replace_match(match: re.Match) -> str:
            nonlocal counter
            key = f"__ORBIT_LITERAL_{counter}__"
            literals[key] = match.group(1)
            counter += 1
            return key

        sanitized = self.QUOTE_PATTERN.sub(_replace_match, text)
        return sanitized, literals

    def restore_literal(self, text: Optional[str], literals: Dict[str, str]) -> Optional[str]:
        """Restore exact literal content if placeholder exists in string."""
        if not text:
            return text
        for key, val in literals.items():
            if key in text:
                text = text.replace(key, val)
        return text

    def split_into_clauses(self, text: str) -> List[str]:
        """Split sanitized text into ordered conceptual clauses based on conjunctions."""
        # Split on conjunctions
        parts = self.CONJUNCTION_PATTERN.split(text)
        clauses = []
        for part in parts:
            cleaned = part.strip().strip(",;.")
            if cleaned:
                clauses.append(cleaned)
        return clauses if clauses else [text.strip()]
