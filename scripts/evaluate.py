"""Explicit CLI; default mode never calls a paid model."""

import argparse
from pathlib import Path

from opsmind.core.config import Settings
from opsmind.evaluation.report import save_report
from opsmind.evaluation.runner import evaluate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/cases.v1.jsonl"))
    parser.add_argument("--mode", choices=["scripted", "live"], default="scripted")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--allow-test-writes", action="store_true")
    parser.add_argument("--output", type=Path, default=Path(".data/evaluation-reports"))
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("limit must be 1..100")
    report = evaluate(
        args.dataset, Settings(llm_max_retries=0), args.mode, args.limit, args.allow_test_writes
    )
    path = args.output / report["run_id"]
    save_report(report, path)
    passed = sum(r["passed"] for r in report["results"])
    print(
        f"mode={args.mode}; passed={passed}/{len(report['results'])}; report={path / 'report.md'}"
    )
    raise SystemExit(0 if passed == len(report["results"]) else 1)


if __name__ == "__main__":
    main()
