from __future__ import annotations

import csv
import json
import ssl
from pathlib import Path
from urllib.request import Request, urlopen

import certifi

from .core import clean, normalize, undergraduate_internship, web_url


def fetch_json(url: str):
    request = Request(web_url(url), headers={"User-Agent": "Hack-Davidson-Opportunities/1.0", "Accept": "application/json"})
    context = ssl.create_default_context()
    # Some Python installations have no default CA bundle. Keep configured roots
    # and add the project's public roots without disabling TLS verification.
    context.load_verify_locations(cafile=certifi.where())
    with urlopen(request, timeout=45, context=context) as response:
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
        if advanced:
            continue
        degrees = item.get("degrees", [])
        if not isinstance(degrees, list) or not all(isinstance(degree, str) for degree in degrees):
            raise ValueError("Expected a list of degree names from Simplify")
        if degrees:
            eligibility = ["Degrees: " + ", ".join(degrees)]
        elif source.get("undergraduate_feed"):
            eligibility = ["Undergraduate internship feed; verify eligibility on the application page"]
        else:
            eligibility = []
        if item.get("sponsorship"):
            sponsorship = clean(item["sponsorship"])
            eligibility.append(f'Sponsorship: {"Not confirmed" if sponsorship == "Other" else sponsorship}')
        if item.get("terms"):
            eligibility.append("Terms: " + ", ".join(item["terms"]))
        eligibility.append("Verify degree, work authorization, and location on application page")
        row = normalize({
            "title": item.get("title"), "organization": item.get("company_name"),
            "category": source["category"], "location": "; ".join(item.get("locations", [])),
            "url": item.get("url"), "source_url": source["homepage"],
            "published_date": item.get("date_posted"), "eligibility": "; ".join(eligibility),
        })
        if undergraduate_internship(row):
            rows.append(row)
    return rows


def collect_source(source: dict, config: dict, root: Path) -> list[dict]:
    if source["kind"] == "simplify":
        return simplify_rows(fetch_json(source["url"]), source, config)
    if source["kind"] == "csv":
        with (root / source["path"]).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not {"title", "url"}.issubset(reader.fieldnames or []):
                raise ValueError("CSV requires title and url columns")
            return [{**normalize(row), "community_record": bool(source.get("community"))}
                    for row in reader if any(row.values())]
    raise ValueError(f'Unsupported source kind: {source["kind"]}')
