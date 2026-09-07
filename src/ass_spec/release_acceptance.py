"""Installed-wheel acceptance journey for the strict interactive contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator

from assayer_platform import PluginRegistration


SPEC_BUSINESS_INPUT = """# Product Spec: Installed Wheel Journey

## 1. Module Definition
The journey service creates and manages an isolated demonstration account.

## 2. State Model
An account is draft until verification, then becomes active.

## 3. Functional Requirements
FR-001: The service must create an account for a unique identifier.
AC-FR001-01: Given a valid identifier, when the account is created, then a
verification message is sent and the account enters the draft state.
CASE-01: Given a duplicate identifier, when registration runs, then the request
is rejected with a duplicate error.

## 4. Key Entities
The Account entity owns the identifier, verification status, and state.

## 5. Data Fields
The identifier is a required string with a maximum length of 128 characters.

## 6. Non-functional Requirements
NFR-GEN-001: Every create operation must complete within 2000 milliseconds.

## 7. Success Criteria
SC-01: Every accepted identifier produces exactly one account.

## 8. References and Compliance
The platform governance document is the selected authority.

## 9. Key Decisions
D-01: The identifier is the unique account identity.

## 10. Dependencies and Assumptions
The delivery provider must be available; otherwise the operation fails explicitly.

## 11. Stage Differences
The first stage includes FR-001.

## 12. Revision History
Version 1.0 was created for the initial review.
"""


def _result(response: dict[str, Any]) -> dict[str, Any]:
    return response["structuredContent"]["result"]


def _checkpoint_payload(
    transport: Any,
    task: dict[str, Any],
    checklist: list[dict[str, Any]],
) -> dict[str, Any]:
    collection_id = task["collectionId"]
    if collection_id in {"candidate-findings", "document-navigation"}:
        return {"decisions": [{
            "finding_id": f"reviewed-{item_id}",
            "status": "SUPPRESSED",
            "candidate_ids": [item_id],
            "review_note": "The reviewed pointer is not a material Spec finding.",
        } for item_id in task["itemIds"]]}
    if collection_id == "cross-document-relationships":
        return {"cross_document_review": [{
            "relationship_id": item_id,
            "outcome": "COMPATIBLE",
            "note": "The frozen relationship evidence is compatible.",
            "decisions": [],
        } for item_id in task["itemIds"]]}
    if collection_id != "checklist-dimensions":
        raise RuntimeError(f"unexpected review collection: {collection_id}")
    source_page = _result(transport.call_tool("expand_evidence_collection", {
        "workItemId": task["workItemId"],
        "collectionId": "source-sections",
        "pageSize": 1,
    }))["result"]
    source = source_page["items"][0]
    evidence_ref = {
        key: source[key] for key in (
            "source_chunk_id", "document_path", "source_digest",
            "start_line", "end_line",
        )
    }
    page = [{
        "check_id": check_id,
        "status": "PASS",
        "note": "Reviewed and satisfied.",
        "evidence_refs": [evidence_ref],
        "applicability": "APPLICABLE",
        "observation": "The dimension was checked against frozen source evidence.",
        "gap": "No material gap was observed for this dimension.",
        "impact": "No adverse impact is established by the reviewed evidence.",
        "recommendation": "Keep the current evidence-backed definition.",
        "owner": "Spec owner",
        "next_action": "Retain the evidence reference on the next revision.",
        "confidence": "high",
    } for check_id in task["itemIds"]]
    checklist.extend(page)
    return {"checklist_review": page}


def _drive_run(
    registration: PluginRegistration,
    output_root: Path,
    scope: dict[str, Any],
    transport_factory: Callable[[Path], Any],
    *, verify_resume: bool,
) -> dict[str, Any]:
    transport = transport_factory(output_root)
    resumed = False
    try:
        started = _result(transport.call_tool("start_plugin_run", {
            "pluginId": registration.manifest.plugin_id,
            "checkId": "SPEC-001",
            "scope": scope,
        }))
        run_id = started["runId"]
        contract_digest = started["result"]["agentContract"]["contractDigest"]
        boundary = _result(transport.call_tool("advance_plugin_run", {}))
        collections: set[str] = set()
        checklist: list[dict[str, Any]] = []
        checkpoint_pages = 0
        while boundary["result"]["semanticTask"]["kind"] == "review_evidence_items":
            task = boundary["result"]["semanticTask"]
            contract = task["agentContract"]
            if contract["contractDigest"] != contract_digest:
                raise RuntimeError("the Run-frozen Agent contract digest changed")
            payload = _checkpoint_payload(transport, task, checklist)
            Draft202012Validator(contract["schema"]).validate(payload)
            boundary = _result(transport.call_tool("advance_plugin_run", {
                "reviewCheckpoint": {
                    "workItemId": task["workItemId"],
                    "collectionId": task["collectionId"],
                    "itemIds": task["itemIds"],
                    "payload": payload,
                    "contractDigest": contract_digest,
                },
            }))
            collections.add(task["collectionId"])
            checkpoint_pages += 1
            if verify_resume and not resumed:
                transport.close()
                transport = transport_factory(output_root)
                boundary = _result(transport.call_tool(
                    "resume_plugin_run", {"runId": run_id},
                ))
                if boundary.get("resumed") is not True:
                    raise RuntimeError("the running acceptance Run was not resumed")
                resumed = True

        task = boundary["result"]["semanticTask"]
        if task["kind"] != "finalize_decision":
            raise RuntimeError("the strict journey did not reach finalization")
        finalization = {"readiness_context": {
            "mandatory_dimensions_checked": True,
            "unresolved_blockers": False,
            "escalations": [],
        }}
        Draft202012Validator(task["agentContract"]["schema"]).validate(finalization)
        terminal = _result(transport.call_tool("advance_plugin_run", {"decision": {
            "workItemId": task["workItemId"],
            "result": "scanned_no_issue",
            "reason": "Every required evidence page and checklist dimension was reviewed.",
            "findings": [{
                "dimension": item["check_id"],
                "status": "satisfied",
                "reason": item["note"],
            } for item in checklist],
            "finalization": finalization,
            "contractDigest": contract_digest,
        }}))
        if terminal["status"] != "completed":
            raise RuntimeError("the strict acceptance Run did not complete")
        replay = _result(transport.call_tool("advance_plugin_run", {}))
        if replay.get("replayed") is not True or replay["result"] != terminal["result"]:
            raise RuntimeError("the terminal response was not replayed identically")
        decisions = replay["result"]["decisions"]
        page = _result(transport.call_tool("get_plugin_result", {
            "sectionId": decisions["sectionId"],
        }))
        if page["result"]["page"]["total"] < 1:
            raise RuntimeError("the terminal result decision page is empty")
        run_root = output_root / run_id
        ledger_path = run_root / f"{run_id}.platform-ledger.json"
        if not ledger_path.is_file() or not (run_root / "result-summary.json").is_file():
            raise RuntimeError("the Run did not publish its ledger and terminal result")
        return {
            "runId": run_id,
            "checkpointPages": checkpoint_pages,
            "reviewedCollections": collections,
            "resumeVerified": resumed if verify_resume else True,
            "replayVerified": True,
            "terminalPublicationVerified": True,
            "ledgerPath": ledger_path.relative_to(output_root).as_posix(),
        }
    finally:
        transport.close()


def run(
    *, registration: PluginRegistration, output_root: Path,
    transport_factory: Callable[[Path], Any],
) -> dict[str, Any]:
    """Execute all collection shapes through the installed registration."""
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    inputs = output_root / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    spec_path = inputs / "spec.md"
    spec_path.write_text(SPEC_BUSINESS_INPUT, encoding="utf-8")
    related_path = inputs / "related.md"
    related_path.write_text(
        "# Related Contract\n\nFR-001 creates one account result.\n",
        encoding="utf-8",
    )
    runs = [
        _drive_run(
            registration, output_root / "candidate",
            {"files": [{"path": str(spec_path)}]}, transport_factory,
            verify_resume=True,
        ),
        _drive_run(
            registration, output_root / "navigation",
            {"files": [{"path": str(spec_path), "reviewStrategy": "navigation"}]},
            transport_factory,
            verify_resume=False,
        ),
        _drive_run(
            registration, output_root / "cross-document",
            {
                "anchor": {"documentId": "anchor", "path": str(spec_path)},
                "relatedDocuments": [{
                    "documentId": "related", "path": str(related_path),
                }],
                "relationships": [{
                    "relationshipId": "anchor-related",
                    "fromDocumentId": "anchor",
                    "toDocumentId": "related",
                    "kind": "implements",
                    "evidence": "The related contract implements FR-001.",
                    "resolutionOwner": "Product owner",
                }],
            },
            transport_factory,
            verify_resume=False,
        ),
    ]
    return {
        "schemaVersion": "1.0.0",
        "status": "passed",
        "checks": [{
            "checkId": "SPEC-001",
            "checkVersion": "1.0.0",
            "completedRuns": len(runs),
            "checkpointPages": sum(item["checkpointPages"] for item in runs),
            "reviewedCollections": sorted({
                collection
                for item in runs
                for collection in item["reviewedCollections"]
            }),
            "agentRetries": 0,
            "ledgerPaths": [
                (Path(mode) / item["ledgerPath"]).as_posix()
                for mode, item in zip(
                    ("candidate", "navigation", "cross-document"), runs,
                )
            ],
            "resumeVerified": all(item["resumeVerified"] for item in runs),
            "replayVerified": all(item["replayVerified"] for item in runs),
            "terminalPublicationVerified": all(
                item["terminalPublicationVerified"] for item in runs
            ),
        }],
    }


__all__ = ["run"]
