#!/usr/bin/env python3
"""Run the existing parent export, policy diff, and customer CSV scripts."""

import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
EXPORTS = BASE / "exports"
MATRIX = BASE / "phase3_matrix.json"
REPORT = BASE / "phase3_diff.json"
CUSTOMER_REPORT = BASE / "customer_report"


def run(label, args, allowed=(0,)):
    print(f"\n=== {label} ===", flush=True)
    print("$ " + " ".join(str(arg) for arg in args), flush=True)
    try:
        result = subprocess.run(args, cwd=BASE, check=False)
    except OSError as exc:
        raise RuntimeError(f"Could not start {label}: {exc}") from exc
    if result.returncode not in allowed:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}")
    return result.returncode


def main():
    for filename in ("parent-script.py", "comparatore.py", "policy_csv_comparison.py", "phase3_matrix.json"):
        if not (BASE / filename).is_file():
            print(f"ERROR: Missing {filename} in {BASE}", file=sys.stderr)
            return 2

    # Clear old outputs so a partial run cannot silently reuse earlier results.
    if EXPORTS.exists():
        if not EXPORTS.is_dir():
            print(f"ERROR: {EXPORTS} is not a directory", file=sys.stderr)
            return 2
        shutil.rmtree(EXPORTS)
    if CUSTOMER_REPORT.exists():
        if not CUSTOMER_REPORT.is_dir():
            print(f"ERROR: {CUSTOMER_REPORT} is not a directory", file=sys.stderr)
            return 2
        shutil.rmtree(CUSTOMER_REPORT)
    REPORT.unlink(missing_ok=True)

    try:
        run("Export policies", [sys.executable, "parent-script.py"])
        if not EXPORTS.is_dir() or not any(EXPORTS.glob("*.json")):
            raise RuntimeError("Exporter did not create JSON files in exports/")

        run(
            "Compare policies",
            [sys.executable, "comparatore.py", "./exports/", "--matrix", MATRIX.name, "--output", REPORT.name],
            allowed=(0, 1),
        )
        if not REPORT.is_file():
            raise RuntimeError("Comparator did not create phase3_diff.json")

        run(
            "Generate customer CSVs",
            [sys.executable, "policy_csv_comparison.py", REPORT.name, "--output-dir", "customer_report/"],
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print("\nDone. CSV files are in customer_report/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
