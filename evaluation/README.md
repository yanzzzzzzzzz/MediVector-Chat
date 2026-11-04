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

The user confirmed that the dataset and separate Evaluation Lab have not been established yet.
Start with corpus selection and annotation; there is no existing reviewed baseline to import.

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
