import os
import unittest

from evaluation.pgvector_benchmark import run


@unittest.skipUnless(os.getenv("RUN_DB_TESTS") == "1", "requires isolated test PostgreSQL")
class BenchmarkIntegrationTests(unittest.TestCase):
    def test_exact_and_hnsw_execute_distinct_plans_on_same_query_batch(self):
        from medivector.db import get_pg_conninfo, init_db
        from unittest.mock import patch
        with patch.dict(os.environ, {"API_USERS": "{}"}):
            init_db()
        report = run(get_pg_conninfo(), rows=100, queries=3, dimensions=16, k=3, ef_search=20)
        self.assertGreaterEqual(report["recall_at_k"], 0)
        self.assertLessEqual(report["recall_at_k"], 1)
        plans = {}
        def nodes(plan):
            yield plan
            for child in plan.get("Plans", []):
                yield from nodes(child)
        for mode, results in report["methods"].items():
            self.assertEqual(len(results["ids"]), 3)
            self.assertTrue(all(len(ids) == 3 for ids in results["ids"]))
            self.assertGreater(results["serial_qps"], 0)
            self.assertGreaterEqual(results["p95_ms"], results["p50_ms"])
            plans[mode] = list(nodes(results["explain"][0]["Plan"]))
        self.assertTrue(any(p["Node Type"] == "Seq Scan" for p in plans["exact"]))
        self.assertFalse(any("Index Name" in p for p in plans["exact"]))
        self.assertTrue(any(p.get("Index Name") == "benchmark_hnsw" for p in plans["hnsw"]))
