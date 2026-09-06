"""Deterministic, rule-based natural language parser for structured intent extraction."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from orbit.runtime.task_understanding.models import (
    RawTaskRequest,
    StructuredTaskIntent,
    TargetReference,
    TaskConstraints,
    TaskGoal,
)
from orbit.runtime.task_understanding.normalizer import TaskNormalizer


class DeterministicTaskParser:
    """Deterministic parser extracting ordered structured intents from natural language clauses."""

    KNOWN_APPLICATIONS = {
        "notepad": "Notepad",
        "calculator": "Calculator",
        "calc": "Calculator",
        "paint": "Paint",
        "mspaint": "Paint",
        "chrome": "Google Chrome",
        "google chrome": "Google Chrome",
        "edge": "Microsoft Edge",
        "msedge": "Microsoft Edge",
        "firefox": "Firefox",
        "word": "Microsoft Word",
        "excel": "Microsoft Excel",
        "powerpoint": "Microsoft PowerPoint",
        "terminal": "Windows Terminal",
        "cmd": "Command Prompt",
        "powershell": "PowerShell",
        "vscode": "Visual Studio Code",
        "code": "Visual Studio Code",
        "explorer": "File Explorer",
        "file explorer": "File Explorer",
        "settings": "Settings",
        "spotify": "Spotify",
        "photoshop": "Adobe Photoshop",
    }

    NEGATION_TERMS = ["do not", "don't", "dont", "never", "cannot", "without", "should not", "must not"]

    def __init__(self, normalizer: Optional[TaskNormalizer] = None):
        self._normalizer = normalizer or TaskNormalizer()

    def parse_request(self, raw_request: RawTaskRequest) -> List[StructuredTaskIntent]:
        """Parse a RawTaskRequest into an ordered sequence of StructuredTaskIntent instances."""
        text = raw_request.raw_text.strip()
        if not text:
            return []

        # 1. Extract quoted literals to avoid corrupting user casing or punctuation
        sanitized_text, literals = self._normalizer.extract_literals(text)

        # 2. Split into ordered clauses by conjunctions
        clauses = self._normalizer.split_into_clauses(sanitized_text)

        intents: List[StructuredTaskIntent] = []
        context_app: Optional[str] = None

        for idx, clause in enumerate(clauses):
            intent, detected_app = self._parse_single_clause(
                clause=clause,
                seq_index=idx,
                literals=literals,
                inherited_app=context_app,
                raw_full_text=text,
            )
            if detected_app:
                context_app = detected_app
            elif context_app and not intent.constraints.application_name:
                intent.constraints.application_name = context_app
                intent.evidence.append(f"inherited application context '{context_app}' from preceding clause")

            intents.append(intent)

        return intents

    def _parse_single_clause(
        self,
        clause: str,
        seq_index: int,
        literals: Dict[str, str],
        inherited_app: Optional[str],
        raw_full_text: str,
    ) -> Tuple[StructuredTaskIntent, Optional[str]]:
        """Parse one clause string into a StructuredTaskIntent and return any discovered application name."""
        clause_lower = clause.lower().strip()
        evidence: List[str] = []
        is_negated = False
        negation_details = None

        # Check for negation
        for neg in self.NEGATION_TERMS:
            if re.search(rf"\b{re.escape(neg)}\b", clause_lower):
                is_negated = True
                negation_details = self._normalizer.restore_literal(clause, literals)
                evidence.append(f"detected negation marker '{neg}'")
                break

        # 1. OPEN_APPLICATION
        if self._matches_open(clause_lower):
            return self._parse_open_clause(clause, clause_lower, seq_index, literals, is_negated, negation_details, evidence)

        # 2. WRITE_TEXT / TYPE_TEXT
        if self._matches_write(clause_lower):
            return self._parse_write_clause(clause, clause_lower, seq_index, literals, inherited_app, is_negated, negation_details, evidence)

        # 3. CLICK_TARGET
        if self._matches_click(clause_lower):
            return self._parse_click_clause(clause, clause_lower, seq_index, literals, inherited_app, is_negated, negation_details, evidence)

        # 4. SEARCH
        if self._matches_search(clause_lower):
            return self._parse_search_clause(clause, clause_lower, seq_index, literals, inherited_app, is_negated, negation_details, evidence)

        # 5. SAVE_DOCUMENT
        if self._matches_save(clause_lower):
            return self._parse_save_clause(clause, clause_lower, seq_index, literals, inherited_app, is_negated, negation_details, evidence)

        # 6. CLOSE_APPLICATION
        if self._matches_close(clause_lower):
            return self._parse_close_clause(clause, clause_lower, seq_index, literals, inherited_app, is_negated, negation_details, evidence)

        # 7. COPY_CONTENT
        if self._matches_copy(clause_lower):
            return self._parse_copy_clause(clause, clause_lower, seq_index, literals, inherited_app, is_negated, negation_details, evidence)

        # 8. PASTE_CONTENT
        if self._matches_paste(clause_lower):
            return self._parse_paste_clause(clause, clause_lower, seq_index, literals, inherited_app, is_negated, negation_details, evidence)

        # 9. CREATE_DOCUMENT
        if self._matches_create(clause_lower):
            return self._parse_create_clause(clause, clause_lower, seq_index, literals, inherited_app, is_negated, negation_details, evidence)

        # 10. SELECT_OPTION
        if self._matches_select(clause_lower):
            return self._parse_select_clause(clause, clause_lower, seq_index, literals, inherited_app, is_negated, negation_details, evidence)

        # 11. NAVIGATE
        if self._matches_navigate(clause_lower):
            return self._parse_navigate_clause(clause, clause_lower, seq_index, literals, inherited_app, is_negated, negation_details, evidence)

        # UNKNOWN / UNSUPPORTED
        evidence.append(f"unrecognized task clause: '{clause}'")
        unsupported_intent = StructuredTaskIntent(
            sequence_index=seq_index,
            goal=TaskGoal.UNKNOWN,
            target=TargetReference(
                semantic_type="unknown",
                is_ambiguous=True,
                unresolved_reason=f"No matching deterministic rule for clause '{clause}'",
            ),
            constraints=TaskConstraints(
                is_negated=is_negated,
                negation_details=negation_details,
            ),
            evidence=evidence,
            is_negated=is_negated,
            is_ambiguous=True,
            unresolved_reason=f"Unrecognized intent in clause '{clause}'",
        )
        return unsupported_intent, None

    # --- Matcher Helpers ---

    def _matches_open(self, text: str) -> bool:
        return bool(re.search(r"\b(open|launch|start|run)\b", text))

    def _matches_write(self, text: str) -> bool:
        return bool(re.search(r"\b(type|write|enter|input)\b", text))

    def _matches_click(self, text: str) -> bool:
        return bool(re.search(r"\b(click|press|tap|activate|push)\b", text))

    def _matches_search(self, text: str) -> bool:
        return bool(re.search(r"\b(search|look up|find|query)\b", text))

    def _matches_save(self, text: str) -> bool:
        return bool(re.search(r"\b(save)\b", text))

    def _matches_close(self, text: str) -> bool:
        return bool(re.search(r"\b(close|exit|quit|terminate)\b", text))

    def _matches_copy(self, text: str) -> bool:
        return bool(re.search(r"\b(copy)\b", text))

    def _matches_paste(self, text: str) -> bool:
        return bool(re.search(r"\b(paste)\b", text))

    def _matches_create(self, text: str) -> bool:
        return bool(re.search(r"\b(create|new)\b", text))

    def _matches_select(self, text: str) -> bool:
        return bool(re.search(r"\b(select|choose)\b", text))

    def _matches_navigate(self, text: str) -> bool:
        return bool(re.search(r"\b(go to|navigate to|browse to)\b", text))

    # --- Clause Handlers ---

    def _parse_open_clause(
        self, clause: str, clause_lower: str, seq_index: int, literals: Dict[str, str],
        is_negated: bool, negation_details: Optional[str], evidence: List[str]
    ) -> Tuple[StructuredTaskIntent, Optional[str]]:
        evidence.append("matched verb 'open/launch/start'")
        
        # Check pronoun / ambiguous target
        if re.search(r"\b(open|launch|start|run)\s+(it|this|that|them|the app|the application)\b", clause_lower):
            evidence.append("detected ambiguous pronoun target without bound application")
            target = TargetReference(
                semantic_type="application",
                identifier=None,
                role="window",
                is_ambiguous=True,
                unresolved_reason="Application reference 'it' has no known binding",
            )
            intent = StructuredTaskIntent(
                sequence_index=seq_index,
                goal=TaskGoal.OPEN_APPLICATION,
                target=target,
                constraints=TaskConstraints(is_negated=is_negated, negation_details=negation_details),
                evidence=evidence,
                is_negated=is_negated,
                is_ambiguous=True,
                unresolved_reason="Application reference 'it' has no known binding",
            )
            return intent, None

        # Check known apps
        matched_app = None
        for key, canonical_name in self.KNOWN_APPLICATIONS.items():
            if re.search(rf"\b{re.escape(key)}\b", clause_lower):
                matched_app = canonical_name
                evidence.append(f"recognized explicit application entity: '{canonical_name}'")
                break

        if matched_app:
            target = TargetReference(
                semantic_type="application",
                identifier=matched_app,
                role="window",
                is_ambiguous=False,
            )
            intent = StructuredTaskIntent(
                sequence_index=seq_index,
                goal=TaskGoal.OPEN_APPLICATION,
                target=target,
                constraints=TaskConstraints(
                    application_name=matched_app,
                    is_negated=is_negated,
                    negation_details=negation_details,
                ),
                evidence=evidence,
                is_negated=is_negated,
                is_ambiguous=False,
            )
            return intent, matched_app

        # Extract generic candidate entity after verb
        m = re.search(r"\b(?:open|launch|start|run)\s+(?:the\s+)?([a-zA-Z0-9_\-\.\s]+)", clause, re.IGNORECASE)
        candidate = m.group(1).strip() if m else None
        candidate = self._normalizer.restore_literal(candidate, literals)

        if candidate:
            target = TargetReference(
                semantic_type="application",
                identifier=candidate,
                role="window",
                is_ambiguous=False,
            )
            evidence.append(f"extracted application candidate name: '{candidate}'")
            intent = StructuredTaskIntent(
                sequence_index=seq_index,
                goal=TaskGoal.OPEN_APPLICATION,
                target=target,
                constraints=TaskConstraints(
                    application_name=candidate,
                    is_negated=is_negated,
                    negation_details=negation_details,
                ),
                evidence=evidence,
                is_negated=is_negated,
                is_ambiguous=False,
            )
            return intent, candidate

        # Fallback ambiguous
        target = TargetReference(
            semantic_type="application",
            is_ambiguous=True,
            unresolved_reason="Unspecified application target",
        )
        intent = StructuredTaskIntent(
            sequence_index=seq_index,
            goal=TaskGoal.OPEN_APPLICATION,
            target=target,
            constraints=TaskConstraints(is_negated=is_negated, negation_details=negation_details),
            evidence=evidence,
            is_negated=is_negated,
            is_ambiguous=True,
            unresolved_reason="Unspecified application target",
        )
        return intent, None

    def _parse_write_clause(
        self, clause: str, clause_lower: str, seq_index: int, literals: Dict[str, str],
        inherited_app: Optional[str], is_negated: bool, negation_details: Optional[str], evidence: List[str]
    ) -> Tuple[StructuredTaskIntent, Optional[str]]:
        evidence.append("matched verb 'write/type/enter'")

        # Look for literal placeholder first
        extracted_content = None
        for key, val in literals.items():
            if key in clause:
                extracted_content = val
                evidence.append(f"preserved exact quoted user content: '{val}'")
                break

        # If no literal quotes found, extract trailing text after keyword
        if extracted_content is None and not is_negated:
            m = re.search(r"\b(?:type|write|enter|input):?(?:\s+the\s+following\s+text:?|\s+text:?|\s+into\s+[a-zA-Z0-9_\-]+:?|:)?\s*(.*)$", clause, re.IGNORECASE)
            if m and m.group(1).strip():
                raw_payload = m.group(1).strip()
                if raw_payload.startswith(":"):
                    raw_payload = raw_payload.lstrip(":").strip()
                extracted_content = self._normalizer.restore_literal(raw_payload, literals)
                evidence.append(f"extracted unquoted literal text payload: '{extracted_content}'")

        is_ambiguous = False
        unresolved_reason = None
        if not is_negated and (extracted_content is None or not extracted_content.strip()):
            is_ambiguous = True
            unresolved_reason = "Missing text content to type"
            evidence.append("flagged missing content payload")

        target = TargetReference(
            semantic_type="ui_control",
            identifier="document_body",
            role="edit",
            is_ambiguous=False,
        )

        intent = StructuredTaskIntent(
            sequence_index=seq_index,
            goal=TaskGoal.WRITE_TEXT,
            target=target,
            constraints=TaskConstraints(
                application_name=inherited_app,
                content=extracted_content,
                is_negated=is_negated,
                negation_details=negation_details,
            ),
            evidence=evidence,
            is_negated=is_negated,
            is_ambiguous=is_ambiguous,
            unresolved_reason=unresolved_reason,
        )
        return intent, None

    def _parse_click_clause(
        self, clause: str, clause_lower: str, seq_index: int, literals: Dict[str, str],
        inherited_app: Optional[str], is_negated: bool, negation_details: Optional[str], evidence: List[str]
    ) -> Tuple[StructuredTaskIntent, Optional[str]]:
        evidence.append("matched verb 'click/press/tap'")

        # Check ambiguous pronoun / generic button
        if re.search(r"\b(click|press|tap)\s+(the\s+button|button|it|this|that|something)\b", clause_lower):
            evidence.append("detected ambiguous generic button target")
            target = TargetReference(
                semantic_type="ui_control",
                identifier=None,
                role="button",
                is_ambiguous=True,
                unresolved_reason="Generic control reference without specific label or identifier",
            )
            intent = StructuredTaskIntent(
                sequence_index=seq_index,
                goal=TaskGoal.CLICK_TARGET,
                target=target,
                constraints=TaskConstraints(
                    application_name=inherited_app,
                    is_negated=is_negated,
                    negation_details=negation_details,
                ),
                evidence=evidence,
                is_negated=is_negated,
                is_ambiguous=True,
                unresolved_reason="Generic control reference without specific label or identifier",
            )
            return intent, None

        # Extract target label
        m = re.search(r"\b(?:click|press|tap|activate)\s+(?:the\s+)?([a-zA-Z0-9_\-\.\s]+?)(?:\s+button|\s+icon|\s+menu)?$", clause, re.IGNORECASE)
        label = m.group(1).strip() if m else None
        label = self._normalizer.restore_literal(label, literals)

        if label:
            target = TargetReference(
                semantic_type="ui_control",
                identifier=label,
                role="button",
                is_ambiguous=False,
            )
            evidence.append(f"extracted target control label: '{label}'")
            intent = StructuredTaskIntent(
                sequence_index=seq_index,
                goal=TaskGoal.CLICK_TARGET,
                target=target,
                constraints=TaskConstraints(
                    application_name=inherited_app,
                    is_negated=is_negated,
                    negation_details=negation_details,
                ),
                evidence=evidence,
                is_negated=is_negated,
                is_ambiguous=False,
            )
            return intent, None

        # Fallback ambiguous
        target = TargetReference(
            semantic_type="ui_control",
            is_ambiguous=True,
            unresolved_reason="Unspecified click target",
        )
        intent = StructuredTaskIntent(
            sequence_index=seq_index,
            goal=TaskGoal.CLICK_TARGET,
            target=target,
            constraints=TaskConstraints(
                application_name=inherited_app,
                is_negated=is_negated,
                negation_details=negation_details,
            ),
            evidence=evidence,
            is_negated=is_negated,
            is_ambiguous=True,
            unresolved_reason="Unspecified click target",
        )
        return intent, None

    def _parse_search_clause(
        self, clause: str, clause_lower: str, seq_index: int, literals: Dict[str, str],
        inherited_app: Optional[str], is_negated: bool, negation_details: Optional[str], evidence: List[str]
    ) -> Tuple[StructuredTaskIntent, Optional[str]]:
        evidence.append("matched verb 'search/find/look up'")

        # Extract search query
        query = None
        for key, val in literals.items():
            if key in clause:
                query = val
                evidence.append(f"preserved exact quoted query: '{val}'")
                break

        if query is None:
            m = re.search(r"\b(?:search\s+for|search|look\s+up|find)\s+(.*)$", clause, re.IGNORECASE)
            if m and m.group(1).strip():
                query = self._normalizer.restore_literal(m.group(1).strip(), literals)
                evidence.append(f"extracted unquoted search query: '{query}'")

        is_ambiguous = False
        unresolved_reason = None
        if not is_negated and (query is None or not query.strip()):
            is_ambiguous = True
            unresolved_reason = "Missing search query parameter"
            evidence.append("flagged missing query parameter")

        target = TargetReference(
            semantic_type="search_box",
            identifier="search_input",
            role="edit",
            is_ambiguous=False,
        )

        intent = StructuredTaskIntent(
            sequence_index=seq_index,
            goal=TaskGoal.SEARCH,
            target=target,
            constraints=TaskConstraints(
                application_name=inherited_app,
                content=query,
                custom_parameters={"query": query} if query else {},
                is_negated=is_negated,
                negation_details=negation_details,
            ),
            evidence=evidence,
            is_negated=is_negated,
            is_ambiguous=is_ambiguous,
            unresolved_reason=unresolved_reason,
        )
        return intent, None

    def _parse_save_clause(
        self, clause: str, clause_lower: str, seq_index: int, literals: Dict[str, str],
        inherited_app: Optional[str], is_negated: bool, negation_details: Optional[str], evidence: List[str]
    ) -> Tuple[StructuredTaskIntent, Optional[str]]:
        evidence.append("matched verb 'save'")

        # Check pronoun / ambiguous target destination
        is_ambiguous = False
        unresolved_reason = None
        if re.search(r"\b(save\s+it|save\s+the\s+file\s+somewhere|save\s+somewhere)\b", clause_lower):
            is_ambiguous = True
            unresolved_reason = "Ambiguous save destination or target reference 'it'"
            evidence.append("detected ambiguous save target or destination")

        target = TargetReference(
            semantic_type="document",
            identifier="current_document",
            role="file",
            is_ambiguous=is_ambiguous,
            unresolved_reason=unresolved_reason,
        )

        intent = StructuredTaskIntent(
            sequence_index=seq_index,
            goal=TaskGoal.SAVE_DOCUMENT,
            target=target,
            constraints=TaskConstraints(
                application_name=inherited_app,
                is_negated=is_negated,
                negation_details=negation_details,
            ),
            evidence=evidence,
            is_negated=is_negated,
            is_ambiguous=is_ambiguous,
            unresolved_reason=unresolved_reason,
        )
        return intent, None

    def _parse_close_clause(
        self, clause: str, clause_lower: str, seq_index: int, literals: Dict[str, str],
        inherited_app: Optional[str], is_negated: bool, negation_details: Optional[str], evidence: List[str]
    ) -> Tuple[StructuredTaskIntent, Optional[str]]:
        evidence.append("matched verb 'close/exit/quit'")

        matched_app = None
        for key, canonical_name in self.KNOWN_APPLICATIONS.items():
            if re.search(rf"\b{re.escape(key)}\b", clause_lower):
                matched_app = canonical_name
                evidence.append(f"recognized application entity to close: '{canonical_name}'")
                break

        app_name = matched_app or inherited_app
        is_ambiguous = False
        unresolved_reason = None

        if not app_name and re.search(r"\b(close|exit|quit)\s+(it|this|that|the window|the app)\b", clause_lower):
            is_ambiguous = True
            unresolved_reason = "Application reference 'it' has no known binding to close"
            evidence.append("detected ambiguous close target pronoun 'it'")

        target = TargetReference(
            semantic_type="application",
            identifier=app_name,
            role="window",
            is_ambiguous=is_ambiguous,
            unresolved_reason=unresolved_reason,
        )

        intent = StructuredTaskIntent(
            sequence_index=seq_index,
            goal=TaskGoal.CLOSE_APPLICATION,
            target=target,
            constraints=TaskConstraints(
                application_name=app_name,
                is_negated=is_negated,
                negation_details=negation_details,
            ),
            evidence=evidence,
            is_negated=is_negated,
            is_ambiguous=is_ambiguous,
            unresolved_reason=unresolved_reason,
        )
        return intent, None

    def _parse_copy_clause(
        self, clause: str, clause_lower: str, seq_index: int, literals: Dict[str, str],
        inherited_app: Optional[str], is_negated: bool, negation_details: Optional[str], evidence: List[str]
    ) -> Tuple[StructuredTaskIntent, Optional[str]]:
        evidence.append("matched verb 'copy'")
        target = TargetReference(
            semantic_type="text",
            identifier="selected_content",
            role="selection",
            is_ambiguous=False,
        )
        intent = StructuredTaskIntent(
            sequence_index=seq_index,
            goal=TaskGoal.COPY_CONTENT,
            target=target,
            constraints=TaskConstraints(
                application_name=inherited_app,
                is_negated=is_negated,
                negation_details=negation_details,
            ),
            evidence=evidence,
            is_negated=is_negated,
            is_ambiguous=False,
        )
        return intent, None

    def _parse_paste_clause(
        self, clause: str, clause_lower: str, seq_index: int, literals: Dict[str, str],
        inherited_app: Optional[str], is_negated: bool, negation_details: Optional[str], evidence: List[str]
    ) -> Tuple[StructuredTaskIntent, Optional[str]]:
        evidence.append("matched verb 'paste'")
        target = TargetReference(
            semantic_type="ui_control",
            identifier="document_body",
            role="edit",
            is_ambiguous=False,
        )
        intent = StructuredTaskIntent(
            sequence_index=seq_index,
            goal=TaskGoal.PASTE_CONTENT,
            target=target,
            constraints=TaskConstraints(
                application_name=inherited_app,
                is_negated=is_negated,
                negation_details=negation_details,
            ),
            evidence=evidence,
            is_negated=is_negated,
            is_ambiguous=False,
        )
        return intent, None

    def _parse_create_clause(
        self, clause: str, clause_lower: str, seq_index: int, literals: Dict[str, str],
        inherited_app: Optional[str], is_negated: bool, negation_details: Optional[str], evidence: List[str]
    ) -> Tuple[StructuredTaskIntent, Optional[str]]:
        evidence.append("matched verb 'create/new'")
        target = TargetReference(
            semantic_type="document",
            identifier="new_document",
            role="file",
            is_ambiguous=False,
        )
        intent = StructuredTaskIntent(
            sequence_index=seq_index,
            goal=TaskGoal.CREATE_DOCUMENT,
            target=target,
            constraints=TaskConstraints(
                application_name=inherited_app,
                is_negated=is_negated,
                negation_details=negation_details,
            ),
            evidence=evidence,
            is_negated=is_negated,
            is_ambiguous=False,
        )
        return intent, None

    def _parse_select_clause(
        self, clause: str, clause_lower: str, seq_index: int, literals: Dict[str, str],
        inherited_app: Optional[str], is_negated: bool, negation_details: Optional[str], evidence: List[str]
    ) -> Tuple[StructuredTaskIntent, Optional[str]]:
        evidence.append("matched verb 'select/choose'")
        target = TargetReference(
            semantic_type="ui_control",
            identifier=self._normalizer.restore_literal(clause, literals),
            role="option",
            is_ambiguous=False,
        )
        intent = StructuredTaskIntent(
            sequence_index=seq_index,
            goal=TaskGoal.SELECT_OPTION,
            target=target,
            constraints=TaskConstraints(
                application_name=inherited_app,
                is_negated=is_negated,
                negation_details=negation_details,
            ),
            evidence=evidence,
            is_negated=is_negated,
            is_ambiguous=False,
        )
        return intent, None

    def _parse_navigate_clause(
        self, clause: str, clause_lower: str, seq_index: int, literals: Dict[str, str],
        inherited_app: Optional[str], is_negated: bool, negation_details: Optional[str], evidence: List[str]
    ) -> Tuple[StructuredTaskIntent, Optional[str]]:
        evidence.append("matched navigation phrase")
        m = re.search(r"\b(?:go\s+to|navigate\s+to|browse\s+to)\s+(.*)$", clause, re.IGNORECASE)
        dest = m.group(1).strip() if m else None
        dest = self._normalizer.restore_literal(dest, literals)

        target = TargetReference(
            semantic_type="view",
            identifier=dest,
            role="location",
            is_ambiguous=not bool(dest),
            unresolved_reason="Missing destination location" if not dest else None,
        )
        intent = StructuredTaskIntent(
            sequence_index=seq_index,
            goal=TaskGoal.NAVIGATE,
            target=target,
            constraints=TaskConstraints(
                application_name=inherited_app,
                destination=dest,
                is_negated=is_negated,
                negation_details=negation_details,
            ),
            evidence=evidence,
            is_negated=is_negated,
            is_ambiguous=not bool(dest),
            unresolved_reason="Missing destination location" if not dest else None,
        )
        return intent, None
