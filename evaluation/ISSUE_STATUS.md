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
