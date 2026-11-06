"""Deterministic citation checks plus explicit human support annotations.

This does not infer semantic entailment from distances or lexical overlap.
"""
import json
import re
from datetime import datetime
from pathlib import Path


def review_provenance_valid(case):
    """Validate supplied fields, without authenticating the reviewer's identity."""
    if case.get("review_status") != "reviewed":
        return False
    reviewer = case.get("reviewed_by")
    try:
        timestamp = datetime.fromisoformat(case["reviewed_at"].replace("Z", "+00:00"))
        return isinstance(reviewer, str) and bool(reviewer.strip()) and timestamp.utcoffset() is not None
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def annotation_integrity(case, references, cited):
    """Require ordered verbatim claims to cover all non-citation answer text."""
    def normalize(text):
        return re.sub(r"\s+", "", re.sub(r"\[(?:索引\s*)?(\d+)\]", "", text))
    claims = case.get("claims", [])
    coverage = bool(claims) and normalize("".join(c["text"] for c in claims)) == normalize(case["answer"])
    errors = []
    for index, claim in enumerate(claims):
        citations = claim.get("citations", [])
        if any(type(c) is not int or c <= 0 for c in citations):
            errors.append(f"claim[{index}]: citation IDs must be positive integers")
            continue
        if set(citations) - references:
            errors.append(f"claim[{index}]: annotated citation does not exist")
        if set(citations) - cited:
            errors.append(f"claim[{index}]: annotated citation is absent from the answer")
        if not claim.get("text", "").strip():
            errors.append(f"claim[{index}]: empty claim")
        if "requires_evidence" in claim and type(claim["requires_evidence"]) is not bool:
            errors.append(f"claim[{index}]: requires_evidence must be boolean")
    return coverage, errors


def evaluate(case):
    references = {int(ref["index"]) for ref in case["references"]}
    cited = {int(number) for number in re.findall(r"\[(?:索引\s*)?(\d+)\]", case["answer"])}
    claims = case.get("claims", [])
    coverage, annotation_errors = annotation_integrity(case, references, cited)
    missing = [c["text"] for c in claims if c.get("requires_evidence", True) and not c.get("citations")]
    unsupported, unreviewed = [], []
    for claim in claims:
        for citation in claim.get("citations", []):
            verdict = claim.get("support", {}).get(str(citation))
            if verdict is False:
                unsupported.append({"claim": claim["text"], "citation": citation})
            elif verdict is not True:
                unreviewed.append({"claim": claim["text"], "citation": citation})
    pending = case.get("review_status") == "pending_human"
    provenance_valid = review_provenance_valid(case)
    status = ("fail" if cited - references or annotation_errors or (not pending and (missing or unsupported)) else
              "unreviewed" if pending or unreviewed or not coverage or
              (case.get("review_status") == "reviewed" and not provenance_valid) else "pass")
    return {"id": case["id"], "invalid_citations": sorted(cited - references),
            "missing_citations": missing, "unsupported_citations": unsupported,
            "unreviewed_citations": unreviewed,
            "annotation_coverage_complete": coverage,
            "annotation_errors": annotation_errors,
            "human_review_provenance_valid": provenance_valid,
            "generation_faithfulness": status,
            "review_status": case.get("review_status", "annotation_provenance_not_supplied"),
            "retrieval_quality": case.get("retrieval_metrics"),
            "method": "Citation existence and ordered verbatim annotation coverage are automatic; semantic support uses supplied annotations, whose authenticity is not established. Pending human review cannot pass; no clinical validation is claimed."}


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
