# Spec-Quality Semantic Review Contract

The ass-spec plugin discovers and inspects Markdown specification documents,
then produces immutable Evidence collections for Agent review. The Agent is the
semantic decision boundary: the deterministic scanner only marks candidates
and never declares a formal pass or failure on its own.

The plugin runs as check `SPEC-001`. Its scope accepts a `files` list whose
entries carry a `path` and a `reviewStrategy` of `navigation` (independent
review) or an explicit `anchor`, `relatedDocuments`, and `relationships` scope
(cross-document review). Start exactly one Run with `pluginId=ass-spec` and
`checkId=SPEC-001`.

## Executable boundary

Treat the `agentContract.schema` in the current `semanticTask` as the only
authoritative input shape. Submit exactly the current page's `itemIds`, echo
the current `contractDigest`, and do not reuse a schema or digest from another
collection or Run.

- `candidate-findings` and `document-navigation` accept `decisions`. Every
  decision must cover one or more current item IDs through `candidate_ids`.
- `cross-document-relationships` accepts `cross_document_review`. Every
  relationship result must cover one current relationship ID and carry
  bilateral decisions when its outcome is not `COMPATIBLE`.
- `checklist-dimensions` accepts `checklist_review`. Each page may contain only
  the CHK IDs requested by that task; it is not an all-18 payload.
- Finalization accepts only `readiness_context` and optional source-bound
  `reviewer_origin_decisions`. Do not resend persisted checkpoint content.

The Host validates these structures before calling plugin code. A rejected
submission has one explicit correction opportunity; it is not an instruction
to retry automatically.

## Authority and profiles

The bundled `authority.md` is the sole normative entrypoint. The default
`product-spec` profile is content-first and does not require one chapter layout.
Use `strict-12-chapter` only when the user or an explicit project policy
requires the bundled structure. Use `speckit` only when an explicit higher-level
project policy selects it. `adversarial` is optional.

Keep unavailable target versions, external references, existing-system claims,
business correctness, and human approvals explicitly unverified. Do not confirm
a finding from a filename, a missing keyword, or a score.

## Decision boundary

For each candidate finding, the Agent must:

1. Confirm, suppress, or merge the candidate against immutable evidence (the
   source chunk, its line range, and the document digest) — never from memory.
2. For checklist dimensions, mark each `CHK-01` through `CHK-18` as `PASS`,
   `REWORK`, `ESCALATE`, or `UNVERIFIED`. Every row must provide
   `applicability`, `observation`, `gap`, `impact`, `recommendation`, `owner`,
   `next_action`, and `confidence`, plus a bounded `note`. Every row must cite
   at least one immutable source chunk with `source_chunk_id`, `document_path`,
   `source_digest`, `start_line`, and `end_line`. A `REWORK` row must name its
   accepted finding IDs in `finding_refs`.
3. For cross-document relationships, resolve each declared relationship as
   `COMPATIBLE`, `FINDING`, or `UNVERIFIED`, naming both documents and, for a
   `FINDING` or `UNVERIFIED` outcome, the admitted bilateral semantic decisions.

A confirmed candidate or reviewer-origin finding must provide the actionable,
source-bound fields required by the current schema, including `observed_fact`,
`affected_elements`, `owner`, `next_action`, `confidence`, and
`evidence_refs`. Suppressed, merged, and unverified candidates must explain the
disposition in `review_note`; merged candidates must also name `merged_into`.

## Semantic calibration

- A scanner hit is only a reading pointer. Confirm ambiguity only when two
  reasonable interpretations remain, they change implementation, testing, or
  acceptance, and no authorized evidence resolves the choice.
- Confirm contradiction only when statements govern the same object under an
  overlapping role, state, phase, region, and effective time and cannot both be
  true. Cite both statements. Contextual differences are not contradictions;
  competing authorities that require an owner choice are `ESCALATE`, not an
  invented reconciliation.
- Consolidate repeated wording or multiple symptoms of one missing decision
  into one root-cause finding. Do not multiply remediation work merely because
  the scanner emitted multiple candidates.
- Suppress quoted examples, rejected alternatives, historical text, and
  explicitly non-normative wording unless the surrounding contract makes them
  operative. Review source sections beyond scanner hits: the Agent may add a
  directly traceable reviewer-origin finding when the scanner misses a semantic
  defect.
- A cross-document reviewer-origin finding uses `semantic_type` equal to
  `ambiguity`, `conflict`, `contradiction`, `drift`, or
  `unverified_dependency`. It names one relationship and both documents, maps
  to one CHK, lists affected elements, owner, and next action, and cites at
  least one exact frozen evidence reference from each side. Submit it inside
  the matching `cross-document-relationships` checkpoint; never defer it to
  finalization or send it as an unbound direct Finding.
- If the required evidence or authority is unavailable, use `UNVERIFIED`; if a
  business/governance owner must decide, use `ESCALATE`.

## Readiness

Map the reviewed readiness to the platform result exactly: `READY` maps to
`scanned_no_issue`, `REWORK` to `issue_found`, and `ESCALATE` or `UNVERIFIED`
to `needs_review`. Never use a numerical score to override this mapping.

## Required evidence

- Candidate findings carry a `candidate_id`, `rule_id`, and source reference.
- Every decision must trace back to a source chunk and document identity.
- A `REWORK` finding requires a concrete next action.

## Non-goals

- HTML is not a canonical or required output. The plugin emits a structured
  review summary (candidate findings + checklist + cross-document review) and
  a portable platform result derived from the durable ledger.
