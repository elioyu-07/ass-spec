#!/usr/bin/env python3
"""Prove the M4 exit gate for the ass-spec plugin end to end.

Journey against this standalone distribution, using a durable
``PluginInstallationStore`` and the domain-neutral interactive MCP transport:

    install -> discover -> run (Agent semantic review, Spec business input)
    -> valid platform result -> upgrade -> rollback -> uninstall

The platform never imports ``ass_spec``; it only loads the package
through the lifecycle loader after static validation.  No Assayer platform
source change is required to install or update the plugin.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]

from assayer_host import InteractivePlatformMcpToolTransport  # noqa: E402
from assayer_platform.plugin_installation import PluginInstallationStore  # noqa: E402
from assayer_platform.plugin_lifecycle import (  # noqa: E402
    PluginLifecycleManager,
    discover_plugin_registry,
)

PACKAGE = ROOT
PLUGIN_ID = "ass-spec"

SPEC_BUSINESS_INPUT = """# Product Spec: External Journey

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
The delivery provider must be available; otherwise the operation fails
explicitly.

## 11. Stage Differences
The first stage includes FR-001.

## 12. Revision History
Version 1.0 was created for the initial review.
"""


def _current_version(package: Path) -> str:
    descriptor = json.loads((package / "assayer-plugin-release.json").read_text(encoding="utf-8"))
    return descriptor["pluginVersion"]


def _next_version(version: str) -> str:
    major, minor, _patch = (int(part) for part in version.split("."))
    return f"{major}.{minor + 1}.0"


def _bumped_copy(package: Path, destination: Path, version: str) -> Path:
    shutil.copytree(package, destination)
    descriptor = json.loads((destination / "assayer-plugin-release.json").read_text(encoding="utf-8"))
    descriptor["pluginVersion"] = version
    (destination / "assayer-plugin-release.json").write_text(json.dumps(descriptor), encoding="utf-8")
    manifest_path = destination / "src" / "ass_spec" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = version
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    metadata = destination / "pyproject.toml"
    metadata.write_text(metadata.read_text(encoding="utf-8").replace(
        f'version = "{_current_version(package)}"', f'version = "{version}"',
    ))
    return destination


def _run_spec(registry, output_root: Path, spec_path: Path, *, scope=None) -> dict:
    """Drive one interactive Spec run with Agent semantic review and return
    the terminal result plus the run identity."""
    transport = InteractivePlatformMcpToolTransport(output_root, plugin_registry=registry)
    try:
        started = transport.call_tool("start_plugin_run", {
            "pluginId": PLUGIN_ID, "checkId": "SPEC-001",
            "scope": scope or {"files": [{"path": str(spec_path)}]},
        })["structuredContent"]["result"]
        run_id = started["runId"]
        boundary = transport.call_tool("advance_plugin_run", {})[
            "structuredContent"
        ]["result"]
        checklist = []
        checkpoint_pages = 0
        reviewed_collections = set()
        evidence_ref = None
        frozen_digest = started["result"]["agentContract"]["contractDigest"]
        while boundary["result"]["semanticTask"]["kind"] == "review_evidence_items":
            task = boundary["result"]["semanticTask"]
            contract = task["agentContract"]
            if contract["contractDigest"] != frozen_digest:
                raise RuntimeError("semantic boundary changed its frozen contract digest")
            collection_id = task["collectionId"]
            reviewed_collections.add(collection_id)
            if collection_id in {"candidate-findings", "document-navigation"}:
                payload = {"decisions": [{
                    "finding_id": f"reviewed-{item_id}",
                    "status": "SUPPRESSED",
                    "candidate_ids": [item_id],
                    "review_note": "The reviewed pointer is not a material Spec finding.",
                } for item_id in task["itemIds"]]}
            elif collection_id == "cross-document-relationships":
                payload = {"cross_document_review": [{
                    "relationship_id": item_id,
                    "outcome": "COMPATIBLE",
                    "note": "The frozen relationship evidence is compatible.",
                    "decisions": [],
                } for item_id in task["itemIds"]]}
            elif collection_id == "checklist-dimensions":
                if evidence_ref is None:
                    page = transport.call_tool("expand_evidence_collection", {
                        "workItemId": task["workItemId"],
                        "collectionId": "source-sections",
                        "pageSize": 1,
                    })["structuredContent"]["result"]["result"]
                    source = page["items"][0]
                    evidence_ref = {
                        key: source[key] for key in (
                            "source_chunk_id", "document_path", "source_digest",
                            "start_line", "end_line",
                        )
                    }
                batch = [{
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
                checklist.extend(batch)
                payload = {"checklist_review": batch}
            else:
                raise RuntimeError(f"unexpected review collection: {collection_id}")
            Draft202012Validator(contract["schema"]).validate(payload)
            boundary = transport.call_tool("advance_plugin_run", {
                "reviewCheckpoint": {
                    "workItemId": task["workItemId"],
                    "collectionId": collection_id,
                    "itemIds": task["itemIds"],
                    "payload": payload,
                    "contractDigest": frozen_digest,
                },
            })["structuredContent"]["result"]
            checkpoint_pages += 1

        task = boundary["result"]["semanticTask"]
        if task["kind"] != "finalize_decision":
            raise RuntimeError(f"unexpected terminal semantic task: {task}")
        finalization = {"readiness_context": {
            "mandatory_dimensions_checked": True,
            "unresolved_blockers": False,
            "escalations": [],
        }}
        Draft202012Validator(task["agentContract"]["schema"]).validate(finalization)
        finished = transport.call_tool("advance_plugin_run", {"decision": {
            "workItemId": task["workItemId"],
            "result": "scanned_no_issue",
            "reason": "Every required evidence page and checklist dimension was reviewed.",
            "findings": [{
                "dimension": item["check_id"],
                "status": "satisfied",
                "reason": item["note"],
            } for item in checklist],
            "finalization": finalization,
            "contractDigest": frozen_digest,
        }})["structuredContent"]["result"]
        return {
            "runId": run_id,
            "result": finished,
            "checkpointPages": checkpoint_pages,
            "reviewedCollections": sorted(reviewed_collections),
            "contractDigest": frozen_digest,
        }
    finally:
        transport.close()


def run() -> dict:
    with tempfile.TemporaryDirectory(prefix="assayer-spec-external-journey-") as directory:
        root = Path(directory)
        store_root = root / "installed"
        output_root = root / "output"
        spec_path = root / "spec.md"
        spec_path.write_text(SPEC_BUSINESS_INPUT, encoding="utf-8")

        store = PluginInstallationStore(store_root)
        manager = PluginLifecycleManager(store)
        current_version = _current_version(PACKAGE)
        upgrade_version = _next_version(current_version)

        installed = manager.install(PACKAGE)
        if installed["status"] != "completed" or installed["pluginId"] != PLUGIN_ID:
            raise RuntimeError(f"install did not complete: {installed}")

        registry = discover_plugin_registry(store)
        discovered = [item.manifest.plugin_id for item in registry.list()]
        if discovered != [PLUGIN_ID]:
            raise RuntimeError(f"discovery did not surface the plugin: {discovered}")

        run = _run_spec(registry, output_root / "candidate", spec_path)
        result = run["result"]
        if result["status"] != "completed":
            raise RuntimeError(f"run did not complete: {result}")
        summary = result["result"]["summary"]
        ledger_path = output_root / "candidate" / run["runId"] / f"{run['runId']}.platform-ledger.json"
        if not ledger_path.is_file():
            raise RuntimeError("run did not publish a platform ledger")
        html_artifacts = list((output_root / "candidate" / run["runId"]).rglob("*.html"))
        if html_artifacts:
            raise RuntimeError(f"run published HTML output: {html_artifacts}")

        navigation_run = _run_spec(
            registry, output_root / "navigation", spec_path,
            scope={"files": [{
                "path": str(spec_path), "reviewStrategy": "navigation",
            }]},
        )
        related_path = root / "related.md"
        related_path.write_text(
            "# Related Contract\n\nFR-001 creates one account result.\n",
            encoding="utf-8",
        )
        cross_document_run = _run_spec(
            registry, output_root / "cross-document", spec_path,
            scope={
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
        )
        strict_runs = (run, navigation_run, cross_document_run)
        reviewed_collections = sorted({
            collection_id
            for strict_run in strict_runs
            for collection_id in strict_run["reviewedCollections"]
        })

        with tempfile.TemporaryDirectory() as bumped:
            upgraded_source = _bumped_copy(
                PACKAGE, Path(bumped) / f"v{upgrade_version.replace('.', '')}", upgrade_version,
            )
            upgraded = manager.upgrade(upgraded_source)
        if upgraded["version"] != upgrade_version:
            raise RuntimeError(f"upgrade did not land: {upgraded}")

        rolled_back = manager.rollback(PLUGIN_ID)
        if rolled_back["version"] != current_version:
            raise RuntimeError(f"rollback did not restore: {rolled_back}")

        uninstalled = manager.uninstall(PLUGIN_ID)
        if uninstalled["status"] != "completed":
            raise RuntimeError(f"uninstall did not complete: {uninstalled}")
        if manager.list():
            raise RuntimeError("uninstall left installed plugins behind")

        return {
            "schemaVersion": "1.0.0",
            "mode": "external_spec_package",
            "publishable": False,
            "status": "passed",
            "pluginId": PLUGIN_ID,
            "steps": [
                {"operation": "install", "version": installed["version"], "status": "completed"},
                {"operation": "discover", "plugins": discovered},
                {
                    "operation": "run",
                    "runId": run["runId"],
                    "terminalStatus": result["status"],
                    "summaryPhase": summary["phase"],
                    "readiness": summary["readiness"]["status"],
                    "candidateCount": summary["review"]["candidateCount"],
                },
                {"operation": "upgrade", "version": upgraded["version"],
                 "previousVersion": upgraded["previousVersion"]},
                {"operation": "rollback", "version": rolled_back["version"],
                 "previousVersion": rolled_back["previousVersion"]},
                {"operation": "uninstall", "status": uninstalled["status"]},
            ],
            "assertions": {
                "structuredSummary": True,
                "htmlOutput": False,
                "ledgerPublished": True,
                "strictContract": bool(run["contractDigest"]),
                "checkpointPages": sum(item["checkpointPages"] for item in strict_runs),
                "completedStrictRuns": len(strict_runs),
                "reviewedCollections": reviewed_collections,
                "agentRetries": 0,
                "installedCount": len(manager.list()),
            },
        }


def main() -> int:
    try:
        result = run()
    except Exception:
        result = {
            "schemaVersion": "1.0.0",
            "mode": "external_spec_package",
            "publishable": False,
            "status": "failed",
            "result": {
                "code": "SPEC_EXTERNAL_JOURNEY_FAILED",
                "message": "The external ass-spec exit-gate journey did not complete.",
            },
        }
    schema = json.loads(
        (ROOT / "schemas" / "spec-external-journey.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
