"""Dynamic Stage Output Binding and Reference Resolution (M1.9).

Enables data pipelines between strategy stages, e.g.
  Stage 0 produces `image_path`
  Stage 2 consumes `{{stage_0.image_path}}` or `{{stages.IMAGE_GEN.image_path}}`

INVARIANT:
Reference resolution is strict and fail-closed. If a template variable references
an unexecuted or missing stage output, resolution fails immediately.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


REF_PATTERN = re.compile(r"\{\{([^}]+)\}\}")


class StageOutputBindingError(Exception):
    """Raised when an output reference in a strategy stage cannot be safely resolved."""

    def __init__(self, expression: str, reason: str) -> None:
        self.expression = expression
        self.reason = reason
        super().__init__(f"Stage output binding failed for '{expression}': {reason}")


class StageOutputResolver:
    """Resolves template variable references against accumulated stage execution outputs."""

    @classmethod
    def resolve_parameters(
        cls,
        raw_parameters: Dict[str, Any],
        stage_outputs: Dict[str, Any],
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """Recursively resolve all `{{...}}` references in raw_parameters.

        Args:
            raw_parameters: Parameters dictionary with potential template references.
            stage_outputs: Dictionary mapping stage keys (e.g. "stage_0", "stages.LAUNCH_APP")
                           to stage output dictionaries.

        Returns:
            Tuple of (success, resolved_parameters_dict, optional_error_message).
        """
        try:
            resolved = cls._resolve_value(raw_parameters, stage_outputs)
            if not isinstance(resolved, dict):
                return False, {}, "Resolved parameters must be a dictionary"
            return True, resolved, None
        except StageOutputBindingError as err:
            return False, {}, str(err)
        except Exception as ex:
            return False, {}, f"Unexpected resolution error: {ex}"

    @classmethod
    def _resolve_value(cls, val: Any, stage_outputs: Dict[str, Any]) -> Any:
        if isinstance(val, str):
            return cls._resolve_string(val, stage_outputs)
        elif isinstance(val, dict):
            return {k: cls._resolve_value(v, stage_outputs) for k, v in val.items()}
        elif isinstance(val, list):
            return [cls._resolve_value(item, stage_outputs) for item in val]
        return val

    @classmethod
    def _resolve_string(cls, text: str, stage_outputs: Dict[str, Any]) -> Any:
        matches = list(REF_PATTERN.finditer(text))
        if not matches:
            return text

        # If text is exactly a single reference e.g. "{{stage_0.path}}", preserve underlying data type
        if len(matches) == 1 and matches[0].group(0) == text.strip():
            expr = matches[0].group(1).strip()
            return cls._lookup_expression(expr, stage_outputs)

        # Otherwise perform string substitution
        result = text
        for match in matches:
            expr = match.group(1).strip()
            resolved_val = cls._lookup_expression(expr, stage_outputs)
            result = result.replace(match.group(0), str(resolved_val))
        return result

    @classmethod
    def _lookup_expression(cls, expr: str, stage_outputs: Dict[str, Any]) -> Any:
        parts = expr.split(".")
        if len(parts) < 2:
            raise StageOutputBindingError(expr, "Reference must contain at least 'stage.field' (e.g. 'stage_0.image_path')")

        # Try direct match for hierarchical key e.g. stage_outputs["stage_0"]["image_path"]
        stage_key = parts[0]
        field_path = parts[1:]

        # Also support "stages.CAPABILITY_ID.field"
        if stage_key == "stages" and len(parts) >= 3:
            stage_key = f"stages.{parts[1]}"
            field_path = parts[2:]

        if stage_key not in stage_outputs:
            available_stages = list(stage_outputs.keys())
            raise StageOutputBindingError(
                expr,
                f"Source stage '{stage_key}' not found in accumulated outputs. Available stages: {available_stages}",
            )

        current = stage_outputs[stage_key]
        for field in field_path:
            if not isinstance(current, dict) or field not in current:
                avail_fields = list(current.keys()) if isinstance(current, dict) else type(current).__name__
                raise StageOutputBindingError(
                    expr,
                    f"Field '{field}' not found in stage '{stage_key}'. Available fields: {avail_fields}",
                )
            current = current[field]

        return current
