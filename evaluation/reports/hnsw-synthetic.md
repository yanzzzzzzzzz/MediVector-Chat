# pgvector synthetic benchmark

Recall@10: 0.9300

| Method | P50 ms | P95 ms | Serial QPS |
|---|---:|---:|---:|
| exact | 0.455 | 0.623 | 2123.1 |
| hnsw | 0.351 | 0.401 | 2789.2 |

Synthetic small corpus; warm-cache serial client latency; forced planner settings; not a medical retrieval-quality or production capacity result. Index bytes are disk footprint, not peak RAM.

Environment, full query IDs, per-query timings, EXPLAIN plans and configuration are in the companion JSON.
