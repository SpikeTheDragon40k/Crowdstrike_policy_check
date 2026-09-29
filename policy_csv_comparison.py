#!/usr/bin/env python3
"""Convert a Phase 3 diff JSON report into readable customer-grouped CSV."""

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path


FIELDS = [
    "customer_name", "policy_name", "platform_name", "status",
    "setting_id", "field", "expected", "actual", "reason", "policy_id", "file",
]


def as_text(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def safe_cell(value):
    text = as_text(value)
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def slug(name):
    stem = re.sub(r"[^\w.-]+", "_", name, flags=re.UNICODE).strip("._")
    return stem[:80] or "unnamed_customer"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="phase3_diff.json from compare_phase3_with_tenants.py")
    parser.add_argument("--output-dir", type=Path, default=Path("customer_reports"))
    args = parser.parse_args()

    try:
        with args.report.open("r", encoding="utf-8") as handle:
            report = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"Cannot read diff report: {exc}")
    policies = report.get("policies") if isinstance(report, dict) else None
    if not isinstance(policies, list):
        parser.error("Report must contain a policies array")
    if report.get("errors"):
        print(f"Warning: source report contains {len(report['errors'])} parse errors", file=sys.stderr)

    by_customer = {}
    for policy in policies:
        if not isinstance(policy, dict):
            continue
        name = policy.get("customer_name") or "UNKNOWN CUSTOMER"
        differences = policy.get("differences", [])
        if not isinstance(differences, list):
            parser.error(f"Invalid differences for policy {policy.get('policy_name')}")
        if not differences:
            continue
        rows = by_customer.setdefault(name, [])
        for diff in differences:
            if not isinstance(diff, dict):
                continue
            rows.append({
                "customer_name": name,
                "policy_name": policy.get("policy_name"),
                "platform_name": policy.get("platform_name"),
                "status": policy.get("status"),
                "setting_id": diff.get("setting_id"),
                "field": diff.get("field"),
                "expected": diff.get("expected"),
                "actual": diff.get("actual"),
                "reason": diff.get("reason"),
                "policy_id": policy.get("policy_id"),
                "file": policy.get("file"),
            })

    args.output_dir.mkdir(parents=True, exist_ok=True)
    used = Counter()
    for name, rows in sorted(by_customer.items(), key=lambda item: item[0].casefold()):
        base = slug(name)
        used[base] += 1
        suffix = f"_{used[base]}" if used[base] > 1 else ""
        target = args.output_dir / f"{base}{suffix}_diff.csv"
        rows.sort(key=lambda row: (
            as_text(row["policy_name"]).casefold(),
            as_text(row["setting_id"]).casefold(),
            as_text(row["field"]).casefold(),
        ))
        try:
            with target.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows({key: safe_cell(row[key]) for key in FIELDS} for row in rows)
        except OSError as exc:
            parser.exit(2, f"Cannot write {target}: {exc}\n")
        print(f"{name}: {len(rows)} differences -> {target}")

    if not by_customer:
        print("No differences found; no CSV files created.")
    unknown = by_customer.get("UNKNOWN CUSTOMER")
    if unknown:
        print("Warning: some exports had no readable customer name in child_details.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
