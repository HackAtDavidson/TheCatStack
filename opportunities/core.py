from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def clean(value) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value or "")).strip()


def web_url(value: str) -> str:
    value = clean(value)
    parts = urlsplit(value)
    if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username:
        raise ValueError(f"Expected an HTTP(S) URL: {value[:100]}")
    return value


def canonical_url(value: str) -> str:
    parts = urlsplit(web_url(value))
    query = [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}]
    # Preserve application IDs, referral parameters, paths, and URL fragments.
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path,
                       urlencode(sorted(query)), parts.fragment))


def iso_date(value) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).date().isoformat()
    return date.fromisoformat(str(value)[:10]).isoformat()


def normalize(raw: dict) -> dict:
    title = clean(raw.get("title"))
    if not title:
        raise ValueError("A listing is missing its title")
    url = web_url(raw.get("url", ""))
    return {
        "id": hashlib.sha256(canonical_url(url).encode()).hexdigest()[:24],
        "title": title,
        "organization": clean(raw.get("organization")),
        "category": clean(raw.get("category")) or "Other",
        "location": clean(raw.get("location")) or "Not specified",
        "deadline": iso_date(raw.get("deadline")),
        "url": url,
        "source_url": web_url(raw.get("source_url") or url),
        "eligibility": clean(raw.get("eligibility")) or "Check the application page",
        "published_date": iso_date(raw.get("published_date")),
    }


def eligible(record: dict, config: dict, today: date) -> bool:
    if record["deadline"] and date.fromisoformat(record["deadline"]) < today:
        return False
    published = record["published_date"]
    max_age = config.get("max_age_days", 90)
    if published and max_age is not None and (today - date.fromisoformat(published)).days > max_age:
        return False
    text = f'{record["title"]} {record["organization"]} {record["category"]}'.casefold()
    includes = config.get("include_keywords", [])
    excludes = config.get("exclude_keywords", [])
    return (not includes or any(word.casefold() in text for word in includes)) and not any(
        word.casefold() in text for word in excludes)


def merge(previous: list[dict], batches: dict[str, list[dict]], configured: set[str], today: date) -> list[dict]:
    """Only successful snapshots can remove their own source memberships."""
    records = {row["id"]: dict(row) for row in previous}
    for row in records.values():
        row["active_sources"] = sorted(set(row.get("active_sources", [])) & configured - batches.keys())
    updated = set()
    for source, batch in batches.items():
        for item in batch:
            ident = item["id"]
            if ident not in records:
                records[ident] = {**item, "first_seen": today.isoformat(), "active_sources": []}
            row = records[ident]
            if ident not in updated:
                row.update(item)
                updated.add(ident)
            row["last_seen"] = today.isoformat()
            row["active_sources"] = sorted(set(row["active_sources"]) | {source})
    return sorted(records.values(), key=lambda row: (row["first_seen"], row["id"]), reverse=True)


def availability(row: dict, today: date, stale_days: int) -> str:
    if row.get("deadline") and date.fromisoformat(row["deadline"]) < today:
        return "Expired"
    if not row.get("active_sources"):
        return "Not in latest feed"
    if (today - date.fromisoformat(row["last_seen"])).days > stale_days:
        return "Needs recheck"
    return "Current"


def read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)
