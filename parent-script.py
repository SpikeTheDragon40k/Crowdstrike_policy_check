#!/usr/bin/env python3
"""Export prevention policies from Flight Control child CIDs with parent credentials."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from falconpy import FlightControl, PreventionPolicy


PAGE_SIZE = 5000
CHILD_PAGE_SIZE = 500
CHILD_DETAILS_BATCH = 100


def resources(response, operation):
    if response.get("status_code") != 200:
        body = response.get("body", {})
        errors = body.get("errors", body) if isinstance(body, dict) else body
        raise RuntimeError(f"{operation}: HTTP {response.get('status_code')}: {errors}")
    body = response.get("body")
    items = body.get("resources") if isinstance(body, dict) else None
    if not isinstance(items, list):
        raise RuntimeError(f"{operation}: missing resources list")
    return items, body


def paginated(fetch, label, limit):
    collected = []
    offset = 0
    while True:
        batch, body = resources(fetch(limit=limit, offset=offset), label)
        collected.extend(batch)
        meta = body.get("meta", {})
        pagination = meta.get("pagination", {}) if isinstance(meta, dict) else {}
        total = pagination.get("total") if isinstance(pagination, dict) else None
        if isinstance(total, int) and not isinstance(total, bool):
            if len(collected) >= total:
                break
            if not batch:
                raise RuntimeError(f"{label}: empty page before total {total}")
        elif len(batch) < limit:
            break
        if not batch:
            raise RuntimeError(f"{label}: empty page at offset {offset}")
        offset += len(batch)
    return collected


def child_cid(item):
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("child_cid") or item.get("cid")
    return None


def discover_children(flight):
    matches = paginated(flight.query_children, "query_children", CHILD_PAGE_SIZE)
    cids = sorted({cid for item in matches if (cid := child_cid(item))})
    if len(cids) != len(matches):
        raise RuntimeError("query_children returned records without a CID or duplicate CIDs")
    if not cids:
        return []
    children = []
    for start in range(0, len(cids), CHILD_DETAILS_BATCH):
        chunk = cids[start:start + CHILD_DETAILS_BATCH]
        details, _ = resources(flight.get_children(ids=chunk), "get_children")
        children.extend(details)
    by_cid = {child_cid(item): item for item in children}
    missing = set(cids) - set(by_cid)
    if missing:
        raise RuntimeError(f"get_children omitted CIDs: {', '.join(sorted(missing))}")
    return [(cid, by_cid[cid]) for cid in cids]


def fetch_policies(client):
    return paginated(client.query_combined_policies, "query_combined_policies", PAGE_SIZE)


def write_json_atomic(path, data):
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("exports"))
    parser.add_argument(
        "--include-parent", action="store_true",
        help="Also export policies visible in the parent CID context",
    )
    parser.add_argument(
        "--base-url", help="CrowdStrike cloud region, e.g. us1, us2, eu1, usgov1"
    )
    args = parser.parse_args()
    load_dotenv()
    client_id = os.getenv("FALCON_CLIENT_ID")
    client_secret = os.getenv("FALCON_CLIENT_SECRET")
    if not client_id or not client_secret:
        parser.error("Set FALCON_CLIENT_ID and FALCON_CLIENT_SECRET in .env")

    auth = {"client_id": client_id, "client_secret": client_secret}
    if args.base_url:
        auth["base_url"] = args.base_url
    flight = FlightControl(**auth)
    try:
        children = discover_children(flight)
    except RuntimeError as exc:
        parser.exit(2, f"Child discovery failed: {exc}\n")
    if not children:
        parser.exit(2, "No linked child CIDs found; no exports written.\n")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    targets = [(cid, info, "child") for cid, info in children]
    if args.include_parent:
        targets.append((None, None, "parent"))
    failures = 0
    for cid, info, scope in targets:
        label = cid if cid else "parent"
        try:
            options = dict(auth)
            if cid:
                options["member_cid"] = cid
            client = PreventionPolicy(**options)
            policies = fetch_policies(client)
            data = {
                "scope": scope,
                "target_cid": cid,
                "child_details": info,
                "exported_at_utc": datetime.now(timezone.utc).isoformat(),
                "policy_type": "prevention",
                "policy_count": len(policies),
                "policies": policies,
            }
            destination = args.output_dir / f"{label}_prevention_policies.json"
            write_json_atomic(destination, data)
            print(f"[{label}] saved {len(policies)} policies to {destination}")
        except (RuntimeError, OSError, TypeError, ValueError) as exc:
            failures += 1
            print(f"[{label}] FAILED: {exc}", file=sys.stderr)
    print(f"Completed: {len(targets) - failures}/{len(targets)} contexts exported.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
