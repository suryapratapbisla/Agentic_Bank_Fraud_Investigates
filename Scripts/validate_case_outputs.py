"""Validate case submission JSON files against InvestigationResult schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
AGENT_DIR = PROJECT_ROOT / "agent"
sys.path.insert(0, str(AGENT_DIR))

from output_models import InvestigationResult  # noqa: E402


def expected_case_ids() -> list[str]:
    return [f"HHG-{i:03d}" for i in range(1, 21)]


def validate_cases(cases_dir: Path) -> dict:
    missing: list[str] = []
    errors: list[str] = []
    ok: list[str] = []

    for cid in expected_case_ids():
        path = cases_dir / f"{cid}.json"
        if not path.exists():
            missing.append(cid)
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{cid}: invalid JSON ({exc})")
            continue
        if "error" in data and "case" not in data:
            errors.append(f"{cid}: {data['error']}")
            continue
        try:
            InvestigationResult.model_validate(data)
        except Exception as exc:
            errors.append(f"{cid}: {exc}")
            continue

        case = data.get("case", {})
        verdict = case.get("verdict")
        if verdict == "legitimate":
            if case.get("affected_txn_ids"):
                errors.append(f"{cid}: legitimate verdict but affected_txn_ids not empty")
            if case.get("exposure_usd", 0) != 0:
                errors.append(f"{cid}: legitimate verdict but exposure_usd != 0")
            if data.get("sar", {}).get("file"):
                errors.append(f"{cid}: legitimate verdict but sar.file is true")

        final_actions = {a.get("action") for a in data.get("next_best_actions", {}).get("final", [])}
        sar_file = data.get("sar", {}).get("file", False)
        if sar_file and "FILE_REPORT" not in final_actions:
            errors.append(f"{cid}: sar.file true but FILE_REPORT not in final actions")
        if "FILE_REPORT" in final_actions and not sar_file:
            errors.append(f"{cid}: FILE_REPORT in final actions but sar.file false")

        ok.append(cid)

    return {
        "cases_dir": str(cases_dir),
        "expected": len(expected_case_ids()),
        "ok_count": len(ok),
        "missing": missing,
        "errors": errors,
        "ok": ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate cases/*.json submission files.")
    parser.add_argument(
        "--cases-dir",
        default=str(PROJECT_ROOT / "cases"),
        help="Directory containing HHG-*.json files",
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "artifacts" / "case_run_summary.json"),
        help="Write validation summary JSON here",
    )
    args = parser.parse_args()

    cases_dir = Path(args.cases_dir).expanduser().resolve()
    summary = validate_cases(cases_dir)

    out_path = Path(args.output).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"OK: {summary['ok_count']}/{summary['expected']}")
    if summary["missing"]:
        print("Missing:", ", ".join(summary["missing"]))
    if summary["errors"]:
        print("Errors:")
        for err in summary["errors"]:
            print(f"  - {err}")
    else:
        print("Errors: none")

    print(f"Summary written to {out_path}")
    return 0 if summary["ok_count"] == summary["expected"] and not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
