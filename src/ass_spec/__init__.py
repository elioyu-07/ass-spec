"""Standalone ass-spec audit plugin (independent distribution).

This package is the externalized Spec domain. It depends on the Assayer
platform (``assayer``) and exposes one ``assayer.plugins`` entry point,
``registration``, that the platform loads after static package validation.

The module bodies in ``runtime.py``, ``review.py``, and ``evaluation.py`` are
relocated from the platform source and use absolute ``assayer_platform``
imports; this package is the single source of truth for the Spec domain.
"""

from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from pathlib import Path

from assayer_platform import AgentContractBundle, PluginRegistration

from .runtime import AssSpecPlugin
from .review import AssSpecDecisionCommitter
from .evaluation import (
    evaluate_semantic_review_case,
    evaluate_semantic_review_corpus,
    inspect_evaluation_case,
    load_semantic_review_from_ledger,
    load_evaluation_corpus,
    validate_evaluation_corpus,
)


ASS_SPEC_SCOPE_SCHEMA = json.loads(
    Path(__file__).with_name("scope.schema.json").read_text(encoding="utf-8")
)

_AGENT_BOUNDARIES = json.loads(
    Path(__file__).with_name("agent-boundaries.schema.json").read_text(encoding="utf-8")
)


def _referenced_definitions(value) -> set[str]:
    if isinstance(value, dict):
        names = {
            ref.removeprefix("#/$defs/")
            for ref in (value.get("$ref"),)
            if isinstance(ref, str) and ref.startswith("#/$defs/")
        }
        for item in value.values():
            names.update(_referenced_definitions(item))
        return names
    if isinstance(value, list):
        names = set()
        for item in value:
            names.update(_referenced_definitions(item))
        return names
    return set()


def _agent_boundary(name: str) -> dict:
    """Resolve one boundary with only its transitive local definitions."""
    definitions = _AGENT_BOUNDARIES["$defs"]
    schema = deepcopy(definitions[name])
    schema["$schema"] = _AGENT_BOUNDARIES["$schema"]
    selected = {}
    pending = _referenced_definitions(schema)
    while pending:
        dependency = pending.pop()
        if dependency in selected:
            continue
        selected[dependency] = deepcopy(definitions[dependency])
        pending.update(_referenced_definitions(selected[dependency]) - selected.keys())
    if selected:
        schema["$defs"] = selected
    return schema


_SEMANTIC_REVIEW_PATH = Path(__file__).with_name("semantic-review.md")
ASS_SPEC_AGENT_CONTRACT = AgentContractBundle(
    contract_id="dev.assayer.ass-spec.review",
    contract_version="1.0.0",
    check_id="SPEC-001",
    check_version="1.0.0",
    checkpoint_payload_schemas={
        "candidate-findings": _agent_boundary("candidateCheckpoint"),
        "document-navigation": _agent_boundary("candidateCheckpoint"),
        "cross-document-relationships": _agent_boundary("crossDocumentCheckpoint"),
        "checklist-dimensions": _agent_boundary("checklistCheckpoint"),
    },
    finalization_schema=_agent_boundary("finalization"),
    semantic_instructions_path="ass_spec/semantic-review.md",
    semantic_instructions_sha256=hashlib.sha256(
        _SEMANTIC_REVIEW_PATH.read_bytes()
    ).hexdigest(),
)


registration = PluginRegistration(
    AssSpecPlugin.manifest,
    plugin_factory=lambda _runtime=None: AssSpecPlugin(),
    committer_factory=lambda _runtime=None: AssSpecDecisionCommitter(),
    capabilities=frozenset({"structured_read"}),
    result_features=frozenset({"evidence_graph"}),
    execution_modes=frozenset({"interactive"}),
    scope_schema=ASS_SPEC_SCOPE_SCHEMA,
    agent_contracts=(ASS_SPEC_AGENT_CONTRACT,),
)


__all__ = [
    "AssSpecDecisionCommitter",
    "AssSpecPlugin",
    "evaluate_semantic_review_case",
    "evaluate_semantic_review_corpus",
    "inspect_evaluation_case",
    "load_semantic_review_from_ledger",
    "load_evaluation_corpus",
    "validate_evaluation_corpus",
    "ASS_SPEC_SCOPE_SCHEMA",
    "ASS_SPEC_AGENT_CONTRACT",
    "registration",
]
