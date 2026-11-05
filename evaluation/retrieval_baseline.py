"""Export controlled retrieval API runs for Evaluation Lab; no answer generation."""
import argparse
import json
import math
import os
import statistics
from pathlib import Path

import httpx


def metrics(case, results, k):
    selected = results[:k]
    relevant = set(case["relevant_document_ids"])
    if not case["answerable"]:
        return {"answerable": False, "returned_any": bool(selected)}
    if not relevant:
        raise ValueError("Answerable case must have relevant documents")
    retrieved = {r["document_id"] for r in selected}
    first = next((i for i, r in enumerate(selected, 1) if r["document_id"] in relevant), None)
    spans = case.get("evidence_spans", [])
    covered = 0
    for span in spans:
        intervals = []
        for result in selected:
            metadata = result.get("chunk_metadata", {})
            if (result["document_id"] == span["document_id"] and
                    metadata.get("source_sha256") == span["source_sha256"] and
                    isinstance(metadata.get("start"), int) and isinstance(metadata.get("end"), int)):
                intervals.append((metadata["start"], metadata["end"]))
        cursor = span["start"]
        for start, end in sorted(intervals):
            if start <= cursor:
                cursor = max(cursor, end)
        covered += cursor >= span["end"]
    return {"answerable": True, "recall": len(retrieved & relevant) / len(relevant),
            "mrr": 1 / first if first else 0, "hit": int(first is not None),
            "evidence_recall": covered / len(spans) if spans else None}


def validate_dataset(dataset):
    if not dataset.get("dataset_version") or not dataset.get("corpus_version") or not dataset.get("index_version") or not dataset.get("embedding_model"):
        raise ValueError("Freeze corpus/index/model versions before evaluation")
    cases = dataset.get("cases", [])
    if len(cases) < 30 or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("At least 30 unique case IDs are required")
    for case in cases:
        if not case.get("query", "").strip() or not case.get("reviewed_by") or not case.get("reviewed_at"):
            raise ValueError("Every case must include human review provenance")
        if not isinstance(case.get("answerable"), bool) or not isinstance(case.get("relevant_document_ids"), list):
            raise ValueError("Invalid answerability or relevance labels")
        if bool(case["relevant_document_ids"]) != case["answerable"]:
            raise ValueError("Answerability and document labels disagree")


def medical_rules_for_run(path, corpus_version):
    from evaluation.medical_rules import evaluate_suite
    dataset = json.loads(Path(path).read_text())
    if dataset.get("corpus_version") != corpus_version:
        raise ValueError("Medical rules and retrieval must use the same frozen corpus version")
    return evaluate_suite(dataset)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--medical-rules", type=Path, help="Run deterministic rules for the same frozen corpus in this report")
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text())
    validate_dataset(dataset)
    medical_report = medical_rules_for_run(args.medical_rules, dataset["corpus_version"]) if args.medical_rules else None
    if args.output.exists() or args.output.with_suffix(".md").exists():
        raise FileExistsError("Use a fresh report path")
    headers = {"Authorization": "Bearer " + os.environ["EVALUATION_API_TOKEN"]} if os.getenv("EVALUATION_API_TOKEN") else {}
    retrieval_context = dataset.get("retrieval_context", {})
    if not isinstance(retrieval_context, dict) or (retrieval_context and set(retrieval_context) != {"branch_id", "department_id"}):
        raise ValueError("Only branch_id and department_id may be requested; organization and ACL come from authentication")
    experiments = []
    queries = {}
    with httpx.Client(base_url=args.base_url, headers=headers, timeout=180) as client:
        def verify_manifest():
            if retrieval_context:
                manifest_response = client.get("/api/knowledge/corpus-manifest", params=retrieval_context)
                manifest_response.raise_for_status()
                manifest = manifest_response.json()
                if manifest["manifest_sha256"] != dataset["corpus_version"]:
                    raise ValueError("Authorized corpus manifest changed or does not match the frozen dataset")
                return manifest
            return None
        corpus_manifest = verify_manifest()
        for expansion in (False, True):
            for mode in ("raw", "filtered"):
                # One request per case at max K: do not rewrite independently for K=3/5/10.
                runs = []
                for case in dataset["cases"]:
                    replay = queries.get((expansion, case["id"]))
                    payload = {"question": case["query"], "top_k": 10, "candidate_limit": 20,
                               "mode": mode, "query_expansion": expansion, **retrieval_context}
                    if replay:
                        payload.update(question=replay["standalone_query"], retrieval_terms=replay["terms"], query_expansion=False)
                    response = client.post("/api/retrieval/search", json=payload)
                    response.raise_for_status()
                    result = response.json()
                    queries[(expansion, case["id"])] = result
                    if result["settings"]["embedding_model"] != dataset["embedding_model"]:
                        raise ValueError("API embedding model differs from dataset freeze")
                    runs.append({"case_id": case["id"], "retrieval": result,
                                 "metrics": {str(k): metrics(case, result["results"], k) for k in (3, 5, 10)}})
                summary = {}
                for k in (3, 5, 10):
                    values = [r["metrics"][str(k)] for r in runs]
                    answerable = [v for v in values if v["answerable"]]
                    negatives = [v for v in values if not v["answerable"]]
                    summary[str(k)] = {name: statistics.mean(v[name] for v in answerable) if answerable else None for name in ("recall", "mrr", "hit")}
                    summary[str(k)]["unanswerable_return_rate"] = statistics.mean(v["returned_any"] for v in negatives) if negatives else None
                    evidence = [v["evidence_recall"] for v in answerable if v["evidence_recall"] is not None]
                    summary[str(k)]["evidence_recall"] = statistics.mean(evidence) if evidence else None
                latencies = sorted(r["retrieval"]["elapsed_ms"] for r in runs)
                experiments.append({"mode": mode, "query_expansion": expansion, "summary": summary,
                                    "p50_ms": statistics.median(latencies),
                                    "p95_ms": latencies[math.ceil(len(latencies) * .95) - 1], "runs": runs})
        verify_manifest()
    report = {"dataset": dataset, "corpus_manifest": corpus_manifest, "experiments": experiments, "generation_faithfulness": "Not measured by retrieval evaluation",
              "limitations": "Human labels are supplied, not verified by this script. Freeze DB externally; synthetic data is not clinical validation. K is the first K chunk results; documents are counted once for recall. The same standalone query and terms are replayed across raw/filtered; K runs reuse results. Freeze corpus and index externally during the run."}
    if medical_report is not None:
        report["medical_rules"] = medical_report
    with args.output.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    failures = [r for exp in experiments for r in exp["runs"] if r["metrics"]["10"].get("recall", 1) < 1]
    lines = ["# Retrieval baseline", "", report["limitations"], "", "| Mode | Expansion | K | Recall | MRR | Hit |", "|---|---|---:|---:|---:|---:|"]
    for exp in experiments:
        for k, score in exp["summary"].items():
            lines.append(f"| {exp['mode']} | {exp['query_expansion']} | {k} | {score['recall']} | {score['mrr']} | {score['hit']} |")
    lines += ["", "## Failure review queue", "", "Review the stored queries, terms, distances and evidence offsets for these cases. Causes require human analysis."]
    lines += [f"- {r['case_id']} (Recall@10={r['metrics']['10']['recall']})" for r in failures[:5]]
    if not failures:
        lines.append("No labelled retrieval failures in this run; do not invent five failures.")
    if medical_report is not None:
        from evaluation.medical_rules import markdown
        lines += ["", markdown(medical_report)]
    with args.output.with_suffix(".md").open("x") as stream:
        stream.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
