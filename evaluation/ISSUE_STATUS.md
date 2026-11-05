# GitHub issue implementation status — 2026-11-04

Changes are organized into feature commits; see the repository history. No deployment or GitHub
issue closure is part of this change. Issue #8 remains preparation only.

User confirmed that the ground-truth dataset and separate Evaluation Lab have not yet been
established. Issue #8 remains pending dataset creation and human review; the existing template
and exporter are preparation only, not a verified baseline.

| Issue | Implementation and verification | Remaining limits |
|---|---|---|
| [#1](https://github.com/yanzzzzzzzzz/MediVector-Chat/issues/1) | Stateless POST /api/retrieval/search, request/response schemas, effective query/config, ranking/timing, local/token authorization; success/empty/error/access tests | No real OpenAI calls were made; embeddings are mocked in integration tests |
| [#2](https://github.com/yanzzzzzzzzz/MediVector-Chat/issues/2) | retrieve_candidates/filter_references split, configurable K/candidate/distance/dedup, raw ranks, compatible chat wrapper; boundary/sort/dedup/K tests | Controlled clinical quality comparisons require reviewed corpus labels |
| [#3](https://github.com/yanzzzzzzzzz/MediVector-Chat/issues/3) | Legacy and token strategies, overlap, source SHA/version/offsets/PDF page mappings, fresh experiment schema importer, retrieval metadata; DB import/reject-overwrite tests | Opt-in experiment tooling; existing production uploads keep the baseline strategy. No claim of improved Recall without reviewed data |
| [#4](https://github.com/yanzzzzzzzzz/MediVector-Chat/issues/4) | Seeded synthetic corpus/query script, Exact/HNSW plans, Recall@K/P50/P95/serial QPS, environment and table/index footprint; executed against isolated pgvector container | Small warm-cache synthetic test, not production capacity or clinical quality; peak RAM and concurrent load not measured |
| [#5](https://github.com/yanzzzzzzzzz/MediVector-Chat/issues/5) | UI labels retrieval heuristic explicitly; citation failure fixtures and annotation-based scorer separate generation/retrieval results; tests cover all fixture cases | Semantic support requires human annotation; fixtures are illustrative and not independently reviewed medical examples |
| [#6](https://github.com/yanzzzzzzzzz/MediVector-Chat/issues/6) | Bounded transient retries, exponential backoff/jitter, Retry-After, absolute cancellable deadline, sanitized structured diagnostics; mock status/network/deadline tests | Deadline is per external call, not the entire multi-call question workflow |
| [#7](https://github.com/yanzzzzzzzzz/MediVector-Chat/issues/7) | All APIs protected, per-principal schemas, admin document mutations, front-end Token input, bounded body size/rate, local Docker bindings; real DB read/delete/chat/retrieval isolation tests | No automatic migration of legacy public data; process-local limiter and static tokens are a demo deployment boundary, not a complete enterprise identity platform |
| [#8](https://github.com/yanzzzzzzzzz/MediVector-Chat/issues/8) | Dataset contract, review-provenance validation, raw/filtered expansion on/off K=3/5/10 exporter, JSON/Markdown metrics and failure review queue; metric tests | **Pending:** actual 30+ human-reviewed cases, frozen corpus/index, Evaluation Lab repository/integration, measured baseline and human analysis of five failures. Template is intentionally rejected as unreviewed |

Validation: 41 backend tests passed on Python 3.12, including three real PostgreSQL integration
tests, chat regression cases and OpenAI mock/deadline tests. Five frontend HTTP client tests passed,
as did frontend production build, TypeScript checks and full ESLint. Test databases and tokenizer
cache are isolated; no production data or real OpenAI API calls are used.

GitHub Actions now runs the backend suite with PostgreSQL on Python 3.11 and 3.12, plus frontend
HTTP client tests, ESLint and production build on Node 24. CI status is reported by each workflow
run rather than inferred from local checks. See [test instructions](../tests/README.md).

See [experiment instructions](README.md) and [measured synthetic benchmark](reports/hnsw-synthetic.md).


## Institutional source-governance increment (#13–#15)

- #13: additive normalized organization/branch/department/document/version/chunk schema, stable
  version identities, source/license/checksum/validity/ACL metadata, ERD and migration tests.
  Legacy data becomes unapproved/unscoped Draft; an authorized corpus manifest supports evaluation.
- #14: Draft → In Review → Approved / returned Draft → Superseded / Archived, role/scope checks,
  reason/actor/timestamps, atomic superseding with history retention and append-only event guards.
  Future-dated publication scheduling is not implemented; approval waits until effective_from.
- #15: server-owned identity/grants and required institutional scope; approved/effective ACL filtering
  occurs before exact vector ranking, raw mode cannot bypass it, and no evidence means no answer-model
  fallback. Shared organization schemas retain private conversation ownership.
- #16 partial: citation version IDs, offsets and access revalidation/redaction are implemented,
  with a source-inspection UI. Full PDF attachment flow and ten-query source-viewer coverage remain.
- #17 partial foundation: the source-version workspace exists; generated education drafts and their
  own review/publication/feedback flow remain pending. #18/#19 full rules/snapshots/release gate and
  #20 real interviews/Pilot remain pending. #8 still requires independent human labels.

Validation for this increment: 53 backend tests, including real PostgreSQL migration/state/ACL/ownership,
source provenance/event integrity and scoped export protocol cases. Frontend HTTP tests, full lint,
TypeScript and production build are checked by CI. See [governance design](../docs/knowledge-governance.md).

## Citation completion (#16)

Added immutable version-bound PDF ingestion/original bytes, page extraction diagnostics, authenticated
attachment reads and source links with cited page/offset/scope. Ten deterministic multi-page QA traces
and permission/withdrawal/invalid-PDF regression cases exercise provenance. OCR is explicitly unsupported;
all-image PDFs are rejected. See `docs/knowledge-governance.md` for endpoint and storage details.

## Generated education workspace (#17)

The separate `/education` workbench generates pending copy from selected approved sources, retains
immutable evidence snapshots and human revision diffs, and requires explicit Reviewer/Admin publication.
Nurse editing/submission, return, publish and withdrawal are covered end-to-end. Reader access is restricted
to published copy whose sources remain valid/authorized. Source/query feedback is linked to exact version
and owned conversation IDs. See `docs/education-workspace.md`; semantic and clinical review remain human
responsibilities, not an automatic consequence of syntactically valid citations.

## Medical evaluation rules (#18)

Added a network-free deterministic source/version/scope/ACL/citation evaluator, JSON/Markdown reports,
19 synthetic controls (five per required negative category), explicit Pass/Fail/Review Required and
same-corpus integration with the retrieval baseline CLI. Unknown semantics do not become Pass.
Rule fixtures remain separate from #8's still-pending independently human-reviewed baseline.

## Experiment audit and release gate (#19)

Added allowlisted model/prompt/corpus/index/dataset/Git/source-code snapshots, private immutable query
trace IDs without copied raw questions/answers, and authenticated publication-review records. Online
publication blocks deterministic Fail and requires explicit Reviewer/Admin review for uncertain semantics.
Offline/CI gates replay frozen traces, bind manual approvals to the exact report hash, cannot override
Fail, emit non-overwriting JSON/Markdown and retain CI reports in run summaries. See `docs/quality-audit.md`.
Human-reviewed clinical baseline and real professional Pilot remain #8/#20 requirements.

## #8 human-review preparation (still open)

Prepared 30 stable-ID candidate cases with a frozen synthetic preview source/manifest packet and human
review worksheet. Python and the independent .NET Lab reject pending-human data; review provenance remains
blank. The separate .NET 10 checkout passes its Release build and synthetic metric/contract self-tests,
but remote repository creation/push is pending. No human-reviewed baseline, clinical claim or five-failure
analysis is fabricated. These external/human completion requirements keep #8 open.

## #20 interview/Pilot preparation (still open)

Prepared a 3–5-participant interview guide, synthetic task protocol, timing/source/citation/revision/error
measurement definitions and an empty anonymized report template in `docs/pilot/`. No participants, consent,
interviews, measurements, adoption findings or validated product hypotheses are invented. Real professional
participation and completed reports are required before #20 can be closed.
