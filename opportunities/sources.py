from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.request import Request, urlopen

from .core import clean, normalize, web_url


def fetch_json(url: str):
    request = Request(web_url(url), headers={"User-Agent": "Hack-Davidson-Opportunities/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=45) as response:
        data = response.read(20_000_001)
    if len(data) > 20_000_000:
        raise ValueError("Source exceeds the 20 MB limit")
    return json.loads(data)


def simplify_rows(payload, source: dict, config: dict) -> list[dict]:
    if not isinstance(payload, list):
        raise ValueError("Expected a JSON list from Simplify")
    rows = []
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("active"), bool):
            raise ValueError("Unexpected Simplify listing schema")
        if not item["active"] or not item.get("is_visible", True):
            continue
        advanced = item.get("is_advanced_degree", False)
        if advanced and config.get("exclude_advanced_degrees", True):
            continue
        eligibility = []
        if advanced:
            eligibility.append("Advanced degree indicated")
        if item.get("sponsorship"):
            eligibility.append(f'Sponsorship: {clean(item["sponsorship"])}')
        if item.get("terms"):
            eligibility.append("Terms: " + ", ".join(item["terms"]))
        eligibility.append("Verify degree, work authorization, and location on application page")
        rows.append(normalize({
            "title": item.get("title"), "organization": item.get("company_name"),
            "category": source["category"], "location": "; ".join(item.get("locations", [])),
            "url": item.get("url"), "source_url": source["homepage"],
            "published_date": item.get("date_posted"), "eligibility": "; ".join(eligibility),
        }))
    return rows


def collect_source(source: dict, config: dict, root: Path) -> list[dict]:
    if source["kind"] == "simplify":
        return simplify_rows(fetch_json(source["url"]), source, config)
    if source["kind"] == "csv":
        with (root / source["path"]).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not {"title", "url"}.issubset(reader.fieldnames or []):
                raise ValueError("CSV requires title and url columns")
            return [normalize(row) for row in reader if any(row.values())]
    raise ValueError(f'Unsupported source kind: {source["kind"]}')
