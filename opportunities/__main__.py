from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .core import eligible, merge, read_json, write_json
from .digest import prepare_digest
from .sources import collect_source
from .workbook import export_csv, export_workbook, read_review


def collect(config: dict, config_root: Path, state_path: Path, output: Path, today) -> int:
    sources = [source for source in config["sources"] if source.get("enabled", True)]
    names = [source["name"] for source in sources]
    if not names or len(names) != len(set(names)):
        raise ValueError("Configure at least one source, with unique source names")
    previous = read_json(state_path, [])
    review_path = output / "reviews.json"
    reviews = read_json(review_path, {})
    workbook_path = output / "opportunities.xlsx"
    if workbook_path.exists():
        reviews.update({row["id"]: {"decision": row["decision"], "notes": row["notes"]}
                        for row in read_review(workbook_path)})
    batches, statuses = {}, []
    for source in sources:
        try:
            rows = collect_source(source, config, config_root)
            batches[source["name"]] = [row for row in rows if eligible(row, config, today)]
            statuses.append({"name": source["name"], "status": "OK", "count": len(batches[source["name"]])})
        except Exception as error:
            # Keep previous observations if a source fails; expose the failure in outputs and exit status.
            statuses.append({"name": source["name"], "status": "Failed", "error": str(error)})
            print(f'Source failed: {source["name"]}: {error}', file=sys.stderr)
    report = {"collected_on": today.isoformat(), "sources": statuses}
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "collection-report.json", report)
    if not batches:
        raise ValueError("Every source failed. Existing state and workbook were preserved.")
    records = merge(previous, batches, set(names), today)
    export_workbook(records, reviews, report, workbook_path, config, today)
    export_csv(records, output / "opportunities.csv")
    write_json(review_path, reviews)
    write_json(state_path, records)
    print(f"Tracked {len(records)} unique listings. Excel review: {workbook_path}")
    return 1 if any(row["status"] == "Failed" for row in statuses) else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Collect opportunities, review in Excel, and prepare a club email.")
    sub = parser.add_subparsers(dest="command", required=True)
    gather = sub.add_parser("collect", help="Refresh listings and generate the Excel review workbook")
    gather.add_argument("--config", type=Path, default=Path("config.json"))
    gather.add_argument("--state", type=Path, default=Path("data/opportunities.json"))
    gather.add_argument("--output", type=Path, default=Path("output"))
    digest = sub.add_parser("digest", help="Build email drafts from Include rows in a saved workbook")
    digest.add_argument("--workbook", type=Path, default=Path("output/opportunities.xlsx"))
    digest.add_argument("--config", type=Path, default=Path("config.json"))
    digest.add_argument("--output", type=Path, default=Path("output/digest"))
    args = parser.parse_args(argv)
    today = datetime.now(timezone.utc).date()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        if args.command == "collect":
            return collect(config, args.config.resolve().parent, args.state, args.output, today)
        count = prepare_digest(read_review(args.workbook), args.output,
                               config.get("club_name", "Hack@Davidson"), today,
                               config.get("stale_after_days", 7))
        print(f"Prepared {count} opportunities in {args.output / 'email-preview.html'}. No email was sent.")
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
