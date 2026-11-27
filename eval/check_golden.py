"""Validate Assignment 03 golden-set count, provenance, review and page labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path, nargs="?", default=Path(__file__).with_name("golden.jsonl"))
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    failures: list[str] = []
    if len(rows) < 25:
        failures.append(f"need at least 25 questions; found {len(rows)}")
    answerable = [q for q in rows if q.get("relevant")]
    abstain = [q for q in rows if q.get("must_abstain")]
    hard = [q for q in rows if q.get("type") == "hard"]
    human = [q for q in rows if q.get("origin") == "human"]
    synthetic_reviewed = [q for q in rows if q.get("origin") == "synthetic" and q.get("human_reviewed") is True]
    if len(answerable) < 15:
        failures.append(f"need at least 15 answerable; found {len(answerable)}")
    if len(abstain) < 5:
        failures.append(f"need at least 5 must-abstain; found {len(abstain)}")
    if len(hard) < 5:
        failures.append(f"need at least 5 hard; found {len(hard)}")
    if len(human) < 8:
        failures.append(f"need at least 8 group-written questions; found {len(human)}")
    if len(synthetic_reviewed) < 8:
        failures.append(f"need at least 8 synthetic questions reviewed by a person; found {len(synthetic_reviewed)}")
    bad_ground_truth = []
    for question in answerable:
        for relevant in question.get("relevant", []):
            page = relevant.get("page")
            if not relevant.get("source") or not isinstance(page, int) or page < 1:
                bad_ground_truth.append(question.get("id", "?"))
                break
    if bad_ground_truth:
        failures.append("answerable questions need exact source and positive page: " + ", ".join(bad_ground_truth))
    summary = {"questions": len(rows), "answerable": len(answerable), "must_abstain": len(abstain),
               "hard": len(hard), "human_authored": len(human),
               "synthetic_reviewed": len(synthetic_reviewed), "missing_ground_truth_page": len(bad_ground_truth)}
    print(json.dumps({"summary": summary, "failures": failures}, indent=2))
    if failures:
        print("GOLDEN SET NOT READY")
        return 1
    print("GOLDEN SET READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
