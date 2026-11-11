#!/usr/bin/env python3
"""Score a running RAHBAR against a golden set, and gate CI on the result (section 5).

    python eval/run_eval.py --api http://<ingress>                 # your corpus
    python eval/run_eval.py --api ... --golden eval/fixtures/golden.fixture.yaml
    python eval/run_eval.py --api ... --update-baseline            # after a deliberate improvement

Exit code 0 when every gate passes, 1 when any fails. CI relies on that exit code.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent

# The gate from section 5.4. Change these only with a reason written in docs/PIPELINE.md.
MAX_RECALL5_DROP = 0.05        # recall@5 may fall at most 5 points below the baseline
MIN_CITATION_VALIDITY = 0.95   # at least 95% of citations must match retrieved passages
REQUIRED_ABSTENTION = 1.0      # every must-abstain question must be declined


def load_golden(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    questions = data.get("questions") or []
    if not questions:
        sys.exit(f"no questions in {path}")
    return questions


def ask(client: httpx.Client, api: str, question: str) -> dict:
    """POST one question and return the AskResponse as a dict (see api/app/schemas.py)."""
    response = client.post(f"{api.rstrip('/')}/api/ask", json={"question": question})
    response.raise_for_status()
    return response.json()


def _is_match(rel: dict, ret: dict) -> bool:
    rel_src = str(rel.get("source", "")).lower().strip()
    ret_src = str(ret.get("source", "")).lower().strip()
    rel_sec = str(rel.get("section", "")).lower().strip()
    ret_sec = str(ret.get("section", "")).lower().strip()

    src_match = (not rel_src) or (rel_src in ret_src) or (ret_src in rel_src)
    sec_match = (not rel_sec) or (rel_sec in ret_sec) or (ret_sec in rel_sec)
    return src_match and sec_match


def recall_at_k(relevant: list[dict], retrieved: list[dict], k: int) -> float | None:
    """Fraction of the relevant (source, section) pairs found in the top k retrieved.

    Return None when the question has no relevant passages (must-abstain questions).
    """
    if not relevant:
        return None
    top_k = retrieved[:k]
    matched = 0
    for rel in relevant:
        if any(_is_match(rel, ret) for ret in top_k):
            matched += 1
    return matched / len(relevant)


def citation_validity(response: dict) -> float | None:
    """Fraction of the response's citations that match a passage in response['retrieved'].

    Return None when there are no citations.
    """
    citations = response.get("citations") or []
    if not citations:
        return None
    retrieved = response.get("retrieved") or []
    if not retrieved:
        return 0.0

    valid_count = 0
    for c in citations:
        if any(_is_match(c, r) for r in retrieved):
            valid_count += 1
    return valid_count / len(citations)


def summarise(rows: list[dict]) -> dict:
    """Overall recall@3, recall@5, citation validity and abstention correctness, plus

    recall@5 broken down by question type. This dict becomes results.json.
    """
    r3_scores: list[float] = []
    r5_scores: list[float] = []
    r5_by_type: dict[str, list[float]] = {}
    cit_scores: list[float] = []

    abstain_total = 0
    abstain_correct = 0

    for r in rows:
        q_type = r.get("type", "ordinary")
        rel = r.get("relevant") or []
        resp = r.get("response") or {}
        retrieved = resp.get("retrieved") or []

        if r.get("must_abstain"):
            abstain_total += 1
            if not resp.get("answered_from_context", True):
                abstain_correct += 1

        rec3 = recall_at_k(rel, retrieved, 3)
        if rec3 is not None:
            r3_scores.append(rec3)

        rec5 = recall_at_k(rel, retrieved, 5)
        if rec5 is not None:
            r5_scores.append(rec5)
            r5_by_type.setdefault(q_type, []).append(rec5)

        cit_val = citation_validity(resp)
        if cit_val is not None:
            cit_scores.append(cit_val)

    mean_r3 = round(sum(r3_scores) / len(r3_scores), 4) if r3_scores else 0.0
    mean_r5 = round(sum(r5_scores) / len(r5_scores), 4) if r5_scores else 0.0
    mean_cit = round(sum(cit_scores) / len(cit_scores), 4) if cit_scores else 1.0
    abstention_rate = (
        round(abstain_correct / abstain_total, 4) if abstain_total > 0 else 1.0
    )

    type_breakdown = {
        t: round(sum(vals) / len(vals), 4) for t, vals in r5_by_type.items() if vals
    }

    return {
        "recall_at_3": mean_r3,
        "recall_at_5": mean_r5,
        "citation_validity": mean_cit,
        "abstention_correctness": abstention_rate,
        "recall_by_type": type_breakdown,
    }


def gate(results: dict, baseline: dict | None) -> list[str]:
    """Return one message per failed gate (section 5.4); an empty list means pass."""
    failures: list[str] = []

    r5 = results.get("recall_at_5", 0.0)
    if baseline:
        base_r5 = baseline.get("recall_at_5", 0.0)
        if (base_r5 - r5) > MAX_RECALL5_DROP:
            failures.append(
                f"recall@5 dropped more than 5 points: current {r5:.4f} vs baseline {base_r5:.4f}"
            )

    abstain_rate = results.get("abstention_correctness", 1.0)
    if abstain_rate < REQUIRED_ABSTENTION:
        failures.append(
            f"abstention correctness is {abstain_rate * 100:.1f}%; must be 100%"
        )

    cit_val = results.get("citation_validity", 1.0)
    if cit_val < MIN_CITATION_VALIDITY:
        failures.append(
            f"citation validity {cit_val * 100:.1f}% is below required 95%"
        )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate RAHBAR against a golden set.")
    parser.add_argument("--api", required=True, help="base URL, e.g. http://192.168.49.2")
    parser.add_argument("--host", help="Host header, when your Ingress rule names a host")
    parser.add_argument("--golden", type=Path, default=HERE / "golden.yaml")
    parser.add_argument("--baseline", type=Path, default=HERE / "baseline.json")
    parser.add_argument("--out", type=Path, default=HERE / "results.json")
    parser.add_argument("--update-baseline", action="store_true",
                        help="write these results as the new baseline")
    args = parser.parse_args()

    questions = load_golden(args.golden)
    rows = []
    headers = {"Host": args.host} if args.host else {}
    with httpx.Client(timeout=120.0, headers=headers) as client:
        for q in questions:
            started = time.perf_counter()
            response = ask(client, args.api, q["question"])
            rows.append({
                "id": q["id"], "type": q.get("type", "ordinary"),
                "must_abstain": bool(q.get("must_abstain", False)),
                "relevant": q.get("relevant") or [],
                "expect": q.get("expect"),
                "response": response,
                "seconds": round(time.perf_counter() - started, 2),
            })
            print(f"  {q['id']:<5} {rows[-1]['seconds']:>6.2f}s  {q['question'][:60]}")

    try:
        results = summarise(rows)
        baseline = json.loads(args.baseline.read_text()) if args.baseline.exists() else None
        failures = gate(results, baseline)
    except Exception as exc:
        print(f"\nevaluation error: {exc}")
        return 2

    results["golden"] = str(args.golden)
    results["questions"] = len(rows)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nresults written to {args.out}")
    if args.update_baseline:
        args.baseline.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"baseline updated: {args.baseline}")

    if failures:
        print("\nGATE FAILED")
        for message in failures:
            print(f"  - {message}")
        return 1
    print("\ngate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
