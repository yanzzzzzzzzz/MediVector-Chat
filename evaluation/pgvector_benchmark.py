"""Synthetic Exact/HNSW comparison in an isolated temporary table; no production writes."""
import argparse
import json
import math
import platform
import random
import statistics
import time
from pathlib import Path

import psycopg


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def run(dsn, *, rows=3000, queries=30, dimensions=64, k=10, ef_search=40, seed=42):
    if not (rows >= k >= 1 and queries >= 1 and 1 <= dimensions <= 2000 and ef_search >= k):
        raise ValueError("Invalid benchmark parameters")
    rng = random.Random(seed)
    def vector():
        return "[" + ",".join(str(rng.gauss(0, 1)) for _ in range(dimensions)) + "]"
    corpus = [vector() for _ in range(rows)]
    query_vectors = [vector() for _ in range(queries)]
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        extension = cur.fetchone()
        if not extension:
            raise ValueError("Install the vector extension in the test database first")
        cur.execute(f"CREATE TEMP TABLE benchmark_chunks (id int PRIMARY KEY, embedding vector({dimensions})) ON COMMIT DROP")
        cur.executemany("INSERT INTO benchmark_chunks VALUES (%s, %s::vector)", enumerate(corpus, 1))
        cur.execute("CREATE INDEX benchmark_hnsw ON benchmark_chunks USING hnsw (embedding vector_cosine_ops)")
        cur.execute("ANALYZE benchmark_chunks")
        cur.execute("SELECT version()")
        database_version = cur.fetchone()[0]
        cur.execute("SELECT pg_relation_size('benchmark_chunks'), pg_relation_size('benchmark_hnsw')")
        heap_bytes, index_bytes = cur.fetchone()
        cur.execute("SELECT name, setting FROM pg_settings WHERE name IN ('shared_buffers', 'work_mem', 'maintenance_work_mem', 'max_parallel_workers_per_gather')")
        settings = dict(cur.fetchall())
        outputs = {}
        sql = "SELECT id FROM benchmark_chunks ORDER BY embedding <=> %s::vector LIMIT %s"
        for mode in ("exact", "hnsw"):
            cur.execute("SET LOCAL enable_indexscan = " + ("off" if mode == "exact" else "on"))
            cur.execute("SET LOCAL enable_bitmapscan = off")
            cur.execute("SET LOCAL enable_seqscan = " + ("on" if mode == "exact" else "off"))
            cur.execute("SELECT set_config('hnsw.ef_search', %s, true)", (str(ef_search),))
            cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, (query_vectors[0], k))
            plan = cur.fetchone()[0]
            # Warm up once, then time the same fixed query batch in both modes.
            cur.execute(sql, (query_vectors[0], k))
            cur.fetchall()
            latencies, ids = [], []
            for query in query_vectors:
                start = time.perf_counter()
                cur.execute(sql, (query, k))
                ids.append([row[0] for row in cur.fetchall()])
                latencies.append((time.perf_counter() - start) * 1000)
            outputs[mode] = {"p50_ms": statistics.median(latencies),
                             "p95_ms": percentile(latencies, .95),
                             "serial_qps": queries / (sum(latencies) / 1000),
                             "latencies_ms": latencies, "ids": ids, "explain": plan}
        recall = statistics.mean(len(set(a) & set(b)) / len(a) for a, b in zip(outputs["exact"]["ids"], outputs["hnsw"]["ids"]))
    return {"environment": {"client_platform": platform.platform(), "postgres": database_version,
                            "pgvector": extension[0], "settings": settings},
            "config": {"rows": rows, "queries": queries, "dimensions": dimensions, "k": k,
                       "ef_search": ef_search, "seed": seed, "distribution": "seeded gaussian",
                       "heap_bytes": heap_bytes, "index_bytes": index_bytes},
            "recall_at_k": recall, "methods": outputs,
            "limitations": "Synthetic small corpus; warm-cache serial client latency; forced planner settings; not a medical retrieval-quality or production capacity result. Index bytes are disk footprint, not peak RAM."}


def main():
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("BENCHMARK_DATABASE_URL"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=3000)
    parser.add_argument("--queries", type=int, default=30)
    parser.add_argument("--dimensions", type=int, default=64)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--ef-search", type=int, default=40)
    args = parser.parse_args()
    if not args.dsn:
        parser.error("--dsn or BENCHMARK_DATABASE_URL is required (test database only)")
    report = run(args.dsn, rows=args.rows, queries=args.queries, dimensions=args.dimensions, k=args.k, ef_search=args.ef_search)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2)
    lines = ["# pgvector synthetic benchmark", "", f"Recall@{args.k}: {report['recall_at_k']:.4f}", "",
             "| Method | P50 ms | P95 ms | Serial QPS |", "|---|---:|---:|---:|"]
    for method, result in report["methods"].items():
        lines.append(f"| {method} | {result['p50_ms']:.3f} | {result['p95_ms']:.3f} | {result['serial_qps']:.1f} |")
    lines += ["", report["limitations"], "", "Environment, full query IDs, per-query timings, EXPLAIN plans and configuration are in the companion JSON."]
    with args.output.with_suffix(".md").open("x") as stream:
        stream.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
