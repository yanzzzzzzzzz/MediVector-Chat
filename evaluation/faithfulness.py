"""Deterministic citation checks plus explicit human support annotations.

This does not infer semantic entailment from distances or lexical overlap.
"""
import json
import re
from pathlib import Path


def evaluate(case):
    references = {int(ref["index"]) for ref in case["references"]}
    cited = {int(number) for number in re.findall(r"\[(\d+)\]", case["answer"])}
    claims = case.get("claims", [])
    missing = [c["text"] for c in claims if c.get("requires_evidence", True) and not c.get("citations")]
    unsupported, unreviewed = [], []
    for claim in claims:
        for citation in claim.get("citations", []):
            verdict = claim.get("support", {}).get(str(citation))
            if verdict is False:
                unsupported.append({"claim": claim["text"], "citation": citation})
            elif verdict is not True:
                unreviewed.append({"claim": claim["text"], "citation": citation})
    return {"id": case["id"], "invalid_citations": sorted(cited - references),
            "missing_citations": missing, "unsupported_citations": unsupported,
            "unreviewed_citations": unreviewed,
            "generation_faithfulness": "unreviewed" if unreviewed or not claims else (
                "fail" if cited - references or missing or unsupported else "pass"),
            "retrieval_quality": case.get("retrieval_metrics"),
            "method": "Citation existence is automatic; claim coverage and support require human annotations."}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    cases = json.loads(args.dataset.read_text())
    with args.output.open("x") as stream:
        json.dump([evaluate(case) for case in cases], stream, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
