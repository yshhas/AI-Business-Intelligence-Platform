"""P0-1: Golden eval runner (core deterministic + optional llm suite).

Usage (from backend/):
  python scripts/smoke_eval_golden.py --suite core
  python scripts/smoke_eval_golden.py --suite core --report ../evals/baselines/core_latest.json
  python scripts/smoke_eval_golden.py --suite core --fail-on-regression ../evals/baselines/core_latest.json

Exit: 0 pass · 1 case/regression fail · 2 config/env error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.core.repo_path import ensure_repo_root_on_path  # noqa: E402

ensure_repo_root_on_path()

from evals.runner import (  # noqa: E402
    compare_baseline,
    evals_root,
    run_suite,
    write_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P0-1 Evaluation Framework runner")
    parser.add_argument(
        "--suite",
        default="core",
        choices=("core", "llm", "quality", "profile", "e2e", "safety", "repair", "all"),
        help="Suite to run (default: core)",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Write JSON report to this path",
    )
    parser.add_argument(
        "--fail-on-regression",
        default="",
        help="Baseline report JSON; fail if previously passing cases regress",
    )
    parser.add_argument(
        "--print-summary",
        action="store_true",
        default=True,
        help="Print summary to stdout (default on)",
    )
    args = parser.parse_args(argv)

    suites = ["core", "quality", "llm", "e2e", "safety", "repair"] if args.suite == "all" else [args.suite]
    exit_code = 0
    combined_reports: list[dict] = []

    for name in suites:
        try:
            report = run_suite(name)
        except FileNotFoundError as exc:
            print(f"EVAL_CONFIG_ERROR: {exc}", file=sys.stderr)
            return 2
        except Exception as exc:  # noqa: BLE001
            print(f"EVAL_ENV_ERROR: {exc}", file=sys.stderr)
            return 2

        combined_reports.append(report)
        summary = report["summary"]
        print(f"\n=== EVAL suite={name} ===")
        print(
            f"passed={summary['passed']}/{summary['total']} "
            f"failed={summary['failed']} skipped={summary['skipped']}"
        )
        print(
            "rates: "
            f"gate={summary.get('gate_pass_rate')} "
            f"execute={summary.get('execute_success_rate')} "
            f"result={summary.get('result_match_rate')} "
            f"outcome={summary.get('outcome_success_rate')}"
        )
        print(f"failure_class_distribution={summary.get('failure_class_distribution')}")
        print(f"heuristic_use_count={summary.get('heuristic_use_count')}")
        if summary.get("pipeline_cases"):
            print(
                f"e2e: pipeline_cases={summary.get('pipeline_cases')} "
                f"e2e_success_rate={summary.get('e2e_success_rate')} "
                f"sql_gen_pass_rate={summary.get('sql_gen_pass_rate')}"
            )
        if summary.get("gate_safety_pass_rate") is not None:
            print(f"gate_safety_pass_rate={summary.get('gate_safety_pass_rate')}")
        if summary.get("result_checks_cases"):
            print(
                f"result_checks_cases={summary.get('result_checks_cases')} "
                f"result_accuracy_rate={summary.get('result_accuracy_rate')}"
            )
        if summary.get("total_attack_cases"):
            print(
                f"safety: attack_cases={summary.get('total_attack_cases')} "
                f"blocked={summary.get('blocked_attack_count')} "
                f"safety_pass_rate={summary.get('safety_pass_rate')} "
                f"regression_cases={summary.get('regression_cases')} "
                f"regression_pass={summary.get('regression_pass_count')}"
            )
        if summary.get("schema_link_cases"):
            print(
                "link: "
                f"dist={summary.get('link_status_distribution')} "
                f"ok_rate={summary.get('link_ok_rate')} "
                f"fallback_rate={summary.get('link_fallback_rate')} "
                f"failed_rate={summary.get('link_failed_rate')} "
                f"passed={summary.get('schema_link_passed')}/{summary.get('schema_link_cases')}"
            )
        if summary.get("repair_cases"):
            print(
                f"repair: cases={summary.get('repair_cases')} "
                f"triggered={summary.get('repair_triggered_count')} "
                f"triggered_rate={summary.get('repair_triggered_rate')}"
            )
            print(
                f"repair: success_rate={summary.get('repair_success_rate')} "
                f"success_count={summary.get('repair_success_count')} "
                f"denied_rate={summary.get('repair_denied_rate')}"
            )
            print(f"repair_by_class={summary.get('repair_by_class')}")
            print(f"repair_attempt_success_rate={summary.get('repair_attempt_success_rate')}")
            print(f"max_retry_exceeded_rate={summary.get('max_retry_exceeded_rate')}")

        for case in report["cases"]:
            if case.get("skipped"):
                print(f"  SKIP {case['id']}: {case.get('skip_reason')}")
            elif case.get("passed"):
                print(f"  PASS {case['id']}")
            else:
                print(f"  FAIL {case['id']}: {case.get('errors')}")
                exit_code = 1

        if int(summary.get("heuristic_use_count") or 0) > 0:
            print("EVAL_FAIL: heuristic_use_count > 0")
            exit_code = 1

        if summary["failed"] > 0:
            exit_code = 1

        report_path = Path(args.report) if args.report else None
        if report_path and name == suites[-1] and len(suites) == 1:
            write_report(report, report_path)
            print(f"report written: {report_path.resolve()}")
        elif report_path and len(suites) > 1:
            # write per-suite beside basename
            p = report_path
            stem = p.stem
            out = p.with_name(f"{stem}_{name}{p.suffix or '.json'}")
            write_report(report, out)
            print(f"report written: {out.resolve()}")
        elif not args.report and name in {"core", "quality"}:
            # default artifact under evals/reports (gitignored optional) — still write for operators
            out = evals_root() / "reports" / f"{name}_last.json"
            write_report(report, out)
            print(f"report written: {out.resolve()}")

        baseline_path = Path(args.fail_on_regression) if args.fail_on_regression else None
        if baseline_path:
            if not baseline_path.is_file():
                print(f"EVAL_CONFIG_ERROR: baseline not found: {baseline_path}", file=sys.stderr)
                return 2
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            regs = compare_baseline(report, baseline)
            if regs:
                print("REGRESSION:")
                for msg in regs:
                    print(f"  - {msg}")
                exit_code = 1
            else:
                print("regression check: OK")

    if exit_code == 0:
        print("\nEVAL_OK")
    else:
        print("\nEVAL_FAIL")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
