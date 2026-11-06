# RAG evaluation utilities

Install runtime dependencies plus `pip install -r evaluation/requirements.txt` using Python 3.11+.
These are small interchange/diagnostic tools for a separate Evaluation Lab, not a hosted benchmark platform.

## Chunking and isolated versioned imports (#3)

```sh
python -m evaluation.chunking source.txt baseline-v1.json --document-id stable-doc-1 --version baseline-v1
python -m evaluation.chunking source.txt token-v1.json --document-id stable-doc-1 --version token-v1 --strategy token --max-tokens 512 --overlap 64
python -m evaluation.index_manifest token-v1.json --experiment token-v1
```

Use a fresh output filename and experiment ID for every rebuild. Output files use exclusive creation;
index import refuses an existing experiment schema. No baseline rows are deleted or updated.
The importer calls embeddings (requires OPENAI_API_KEY and an initialized PostgreSQL database),
then imports into the separate principal `experiment:token-v1`. Add that exact principal to API_USERS
and restart to query its results using its own Token. A failed import can reserve an empty namespace;
use a new version rather than automatically deleting an existing one.

Manifests retain original text, SHA256, version, strategy, Unicode character start/end offsets
(end exclusive), chunk index, and PDF page numbers. PDF offsets refer to extracted text joined with
blank lines, not PDF byte positions. Empty PDF pages retain numbering but add no text. The production
upload baseline stays unchanged. Baseline whitespace normalization is recorded; the offset span can
include original whitespace absent from chunk content. Token strategy counts cl100k_base tokens and
keeps Unicode character boundaries; overlap is up to the requested token count. The budget applies
to chunk content, not metadata subsequently prepended by a consumer. Tokenizer data downloads on
first use; set TIKTOKEN_CACHE_DIR to a writable directory and prewarm it for offline operation.
Original document IDs are retained in metadata; database document IDs use UUIDv5(NAMESPACE_URL, ID).
Use those UUIDs in ground-truth relevant_document_ids. Retrieval returns chunk_metadata with offsets,
page references and source SHA; old rows have empty metadata rather than invented offsets.

## Exact vs HNSW (#4)

Run only against a test database with the vector extension installed:

```sh
BENCHMARK_DATABASE_URL='postgresql://...' python -m evaluation.pgvector_benchmark --output run.json
```

Seeded Gaussian corpus and queries live in a temporary table that is dropped on commit. The JSON
records all query results, EXPLAIN (ANALYZE, BUFFERS), pgvector/PostgreSQL versions, settings,
row/query/dimension counts, ef_search, table/index disk bytes and serial client latencies/QPS.
The Markdown companion summarizes results. Sample measured results: [report](reports/hnsw-synthetic.md),
[full plans and environment](reports/hnsw-synthetic.json). Check that HNSW plan uses benchmark_hnsw;
the script intentionally disables Seq Scan for that comparison, unlike normal production planning.
Small warm-cache synthetic measurements cannot establish clinical quality or production throughput.
Disk bytes are not peak RAM; use host/container monitoring for RAM and concurrent load experiments.

## Faithfulness (#5)

```sh
python -m evaluation.faithfulness evaluation/faithfulness_cases.json citations-run.json
```

Fixtures are deliberately nonclinical. They cover supported claims, absent citations, nonexistent
indices, valid indices with unsupported claims, no evidence and unreviewed support. Citation
existence is automatic; claim segmentation, which claims need sources, and citation support are
explicit annotations. A human must inspect all claims against reference text. The script does not
infer truth from distance/count or claim to automate semantic entailment. Omitting claims means
unreviewed, not pass. The fixtures demonstrate the scoring contract and are not a medical validation
set or independent human review. Retrieval quality is a separate report field.

## Ground truth / Evaluation Lab handoff (#8)

The independent [.NET Evaluation Lab](https://github.com/yanzzzzzzzzz/rag-evaluation-lab) is now available
in its own private repository. Human-reviewed ground truth is not established yet; start with corpus
selection and annotation. There is no existing reviewed baseline to import.

`dataset.template.json` is deliberately incomplete. Fill at least 30 stable cases using the frozen
corpus; include reviewer name/date, answerable, relevant_document_ids and optional evidence_spans
(document_id, source_sha256, start, end). Offsets use the same extracted text as the chunk manifest.
Unanswerable cases have no relevant IDs. Freeze corpus_version, index_version, embedding_model and
dataset_version; retain a database snapshot externally. Do not call generated draft labels reviewed.

```sh
EVALUATION_API_TOKEN='...' python -m evaluation.retrieval_baseline reviewed-dataset.json baseline-run.json
```

One command exports full raw/filtered responses and JSON/Markdown metrics for expansion on/off and
K=3/5/10. Each K uses the same retrieved run. Raw/filtered replay the same standalone query and terms,
so query rewrite randomness does not confound the mode comparison. Other changes to the DB during
export invalidate the comparison. Top K means the first K chunks; duplicate chunks from the same
document count once toward Recall. MRR uses the first relevant chunk rank. Multiple relevant documents
are supported. Evidence Recall requires the union of same-version retrieved offsets to cover the full
labelled span. Unanswerable return rate is separate from answerable Recall/MRR/Hit. P50/P95 measure
server retrieval duration including embedding/optional rewrite, not full HTTP end-to-end latency.
The failure review queue lists up to five failed cases; humans must analyze causes, not merely relabel
them. No baseline is claimed until a real dataset is supplied and independently reviewed.

## Checks

```sh
python -m unittest discover -s tests -v
RUN_DB_TESTS=1 PG_HOST=127.0.0.1 PG_PORT=55439 PG_USER=postgres PG_PASSWORD=... PG_DATABASE=postgres python -m unittest discover -s tests -v
```

DB tests create randomized test schemas and drop only those schemas. Use a disposable test database.

## Medical source rules (#18)

Run without a key, database or LLM:

```sh
python -m evaluation.medical_rules evaluation/medical_rules_cases.json /tmp/medical-rules.json
```

The 19 synthetic cases include five stale/unapproved/expired/future versions, five wrong
organization/branch/department/role/named-user scopes, five deliberately unsupported no-answer responses,
and four Pass/Review controls. Expected fixture outcomes are test assertions, not a clinical benchmark.
The report intentionally records 15 Fail outcomes for polluted examples, plus two Pass and two Review
Required controls. It includes rule IDs, document/version/chunk IDs, query context and trace in JSON;
Markdown lists each rule, outcome, reason and affected version. Files are exclusively created, not overwritten.

The source catalog is supplied as a frozen artifact, independently from answer references. Rules check
identity binding, approved/effective status at the recorded query time, scope/ACL, labelled expected
versions, citation marker existence and expected evidence. Canonical no-evidence refusals without references
can pass the refusal rule. Noncanonical refusals and unknown semantic support require review; no distance,
reference count or lexical overlap is used as proof of entailment. Optional support reviews require reviewer
and timezone-aware review time, but their authenticity/clinical competence is not established by this tool.

For a reviewed retrieval dataset, add `--medical-rules path/to/rules.json` to the existing
`evaluation.retrieval_baseline` command. The corpus version must exactly match; mismatched corpora are
rejected. Rules then appear in the same JSON/Markdown run report while generation faithfulness remains
separate. Use only synthetic or appropriately authorized nonpersonal cases; do not put personal health
information in stored evaluation traces. Release gating is handled separately in #19.

## Human-review handoff for #8

`candidates/local-preview-v1.json` contains 30 proposed cases against the frozen synthetic preview corpus.
`candidates/local-preview-corpus-v1.json` preserves the authorized nonpersonal source text/version/page
snapshot; `candidates/REVIEW.md` is the review worksheet. All review identities/times are intentionally
empty and `review_status` is `pending_human`. The exporter refuses this state. Real reviewers must correct
answerability, document/version and evidence spans, enter actual reviewer IDs/timezones, set a new dataset
version and mark it reviewed. Do not bulk-fill fake provenance. Corpus changes require refreezing/review.

An independent .NET 10 `rag-evaluation-lab` checkout has been prepared separately (not embedded in this
repository). Its dependency-free Release build/self-tests independently cover Recall/MRR/Hit/evidence
coverage/no-answer/P50/P95 and controlled export contracts. The private remote is
https://github.com/yanzzzzzzzzz/rag-evaluation-lab and its CI builds/tests the independent evaluator.
The Lab consumes this export contract without any OpenAI credential. After creating a reviewed export, run
`dotnet run --project /path/to/rag-evaluation-lab -- baseline-run.json new-lab-report.json`.
Do not treat the self-tests or a passing CI as a reviewed baseline. At least five real failure analyses remain dependent
on a valid reviewed run; do not fabricate failures to fill the queue.

## Authorized branch comparison (#10)

Use a nonpersonal question and a token explicitly granted both requested scopes. Example request JSON:

```json
{"question":"合成檢查前準備","scopes":[{"branch_id":"a","department_id":"general"},{"branch_id":"b","department_id":"general"}],"target":{"branch_id":"a","department_id":"general"},"top_k":5}
```

```sh
EVALUATION_API_TOKEN='...' python -m evaluation.scope_comparison request.json new-scope-report.json
```

The diagnostic compares target-scope candidates with a deduplicated union of separately authorized scope
queries. All organization/approval/effective-period/role/user ACL predicates remain active; it never adds
a dangerous "disable scope ACL" API flag. Permissions for every manifest are checked before paying for
query embeddings. Raw/filtered comparison is a different experiment; this diagnostic fixes raw mode,
query expansion off, identical question/model and K. Manifests are checked before/after; changes abort.
A shared version is counted once, with its authorized scope list and union rank retained. JSON/Markdown
outputs are non-overwriting. Real PostgreSQL tests verify A versus A+B, shared-version dedup and refusal
of a reader not granted B before embedding calls. This is a scope diagnostic, not a reviewed quality score.

## Unreviewed synthetic engineering diagnostic

Before human review is available, use the separately labelled diagnostic command:

```sh
EVALUATION_API_TOKEN='...' python -m evaluation.synthetic_diagnostic \
  evaluation/candidates/local-preview-v1.json new-diagnostic.json \
  --acknowledge-synthetic-data
```

This accepts only pending-human candidate packets, never fills review provenance, checks the authorized
corpus before/after and shares the exact raw/filtered query-replay protocol with the reviewed exporter.
It compares expansion off/on and K=3/5/10 against **proposed** labels, measures API latency and creates
JSON/Markdown observations for human review. It does not generate answers or score their faithfulness.

The diagnostic has a different report schema (`groups`, `candidate_packet`, `verified_baseline: false`),
so it cannot be passed to the independent Lab's reviewed-baseline command or the release gate. The
reviewed `retrieval_baseline` command still rejects pending-human inputs. Never relabel a diagnostic as
a verified baseline. A two-chunk corpus cannot meaningfully distinguish K=3/5/10, and sequential latency
with reused rewrites is not a fair causal comparison of raw versus filtered speed. Do not change live
thresholds based solely on these small, unreviewed examples.
