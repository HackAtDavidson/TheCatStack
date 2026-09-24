from __future__ import annotations

from datetime import date
from pathlib import Path
import re


SECTIONS = (
    ("Undergraduate Internships", "internship"),
    ("Research Opportunities", "research"),
    ("Programs & Fellowships", "program"),
    ("Scholarships & Grants", "scholarship"),
    ("Ambassador & Leadership Programs", "ambassador"),
    ("Resources & Events", "resource"),
    ("Other Opportunities", "other"),
)
README_START = "<!-- BEGIN CURRENT OPPORTUNITIES -->"
README_END = "<!-- END CURRENT OPPORTUNITIES -->"


def _text(value) -> str:
    return str(value or "").strip()


def _cell(value) -> str:
    return _text(value).replace("|", "\\|").replace("\n", " ")


def _status(row: dict, today: date) -> tuple[str, str]:
    deadline = _text(row.get("deadline"))
    if deadline:
        try:
            days = (date.fromisoformat(deadline) - today).days
        except ValueError:
            days = None
        if days is not None and days < 0:
            return "⛔ [CLOSED]", "closed"
        if days is not None and days <= 7:
            return "🔥 [CLOSING SOON]", "closing"
    return "✅ [OPEN]", "open"


def _section_for(row: dict) -> str:
    category = _text(row.get("category")).casefold()
    title = _text(row.get("title")).casefold()
    if "intern" in category or "intern" in title or "co-op" in title:
        return "internship"
    if any(word in category or word in title for word in ("research", "lab")):
        return "research"
    if any(word in category or word in title for word in ("program", "fellowship", "externship")):
        return "program"
    if any(word in category or word in title for word in ("scholarship", "grant", "financial aid")):
        return "scholarship"
    if any(word in category or word in title for word in ("ambassador", "leadership", "campus")):
        return "ambassador"
    if any(word in category or word in title for word in ("resource", "event", "conference", "career fair")):
        return "resource"
    return "other"


def _sort_key(row: dict, today: date) -> tuple[int, int, str, str]:
    _, status = _status(row, today)
    priority = {"closing": 0, "open": 1, "closed": 2}[status]
    published = _text(row.get("published_date"))
    return priority, -int(published.replace("-", "") or "0"), _text(row.get("organization")).casefold(), _text(row.get("title")).casefold()


def davidson_priority_score(row: dict, priority_config: dict) -> int:
    """Prefer practical Davidson connections for the small README snapshot."""
    organization = _text(row.get("organization")).casefold()
    location = _text(row.get("location")).casefold()
    score = 0
    for employer in priority_config.get("davidson_employers", []):
        if _text(employer).casefold() in organization:
            score += int(priority_config.get("davidson_employer_bonus", 0))
            break
    states = priority_config.get("nearby_states", {})
    for state, bonus in states.items():
        if re.search(rf"(?:,|\s)\s*{re.escape(state.casefold())}(?:\b|;)", location):
            score += int(bonus)
            break
    if "north carolina" in location or re.search(r"(?:,|\s)\s*nc(?:\b|;)", location):
        score += int(priority_config.get("north_carolina_bonus", 0))
    return score


def readme_sort_key(row: dict, today: date, priority_config: dict) -> tuple[int, int, int, str, str]:
    status, _ = _status(row, today)
    status_priority = {"🔥 [CLOSING SOON]": 0, "✅ [OPEN]": 1, "⛔ [CLOSED]": 2}[status]
    published = _text(row.get("published_date"))
    return (-davidson_priority_score(row, priority_config), status_priority,
            -int(published.replace("-", "") or "0"),
            _text(row.get("organization")).casefold(), _text(row.get("title")).casefold())


def _anchor(title: str) -> str:
    return re.sub(r"[^a-z0-9 -]", "", title.casefold()).replace(" ", "-")


def render_catalog(records: list[dict], today: date) -> str:
    grouped = {key: [] for _, key in SECTIONS}
    for row in records:
        grouped[_section_for(row)].append(row)
    lines = [
        "# Davidson Student Opportunities",
        "",
        "> A living catalog of opportunities for Hack@Davidson members. Automatic internship listings are limited to undergraduate roles posted within the configured freshness window; community-submitted records remain visible for human review and future cycles.",
        "",
        f"_Last refreshed: {today.isoformat()} by the opportunity collector._",
        "",
        "## Contents",
        "",
    ]
    for title, key in SECTIONS:
        if grouped[key]:
            lines.append(f"- [{title}](#{_anchor(title)})")
    lines.extend(["", "## How to use this catalog", "", "Status is based on the recorded deadline. Verify eligibility, work authorization, location, and the current deadline on the application page before applying. Use the source link in the workbook when a listing needs additional context.", ""])
    for title, key in SECTIONS:
        rows = sorted(grouped[key], key=lambda row: _sort_key(row, today))
        if not rows:
            continue
        lines.extend([f"## {title}", "", "Status | Organization | Opportunity | Location | Application | Deadline | Date posted", "--- | --- | --- | --- | --- | --- | ---"])
        for row in rows:
            status, _ = _status(row, today)
            organization = _cell(row.get("organization")) or "Not specified"
            opportunity = _cell(row.get("title"))
            location = _cell(row.get("location")) or "Check site"
            url = _text(row.get("url"))
            application = f"[Apply]({url})" if url else "Check site"
            deadline = _cell(row.get("deadline")) or "Rolling / check site"
            posted = _cell(row.get("published_date")) or "Community record"
            lines.append(f"{status} | {organization} | {opportunity} | {location} | {application} | {deadline} | {posted}")
        lines.extend(["", "---", ""])
    if not any(grouped.values()):
        lines.extend(["## No current opportunities", "", "The next scheduled collection will populate this catalog.", ""])
    return "\n".join(lines).rstrip() + "\n"


def render_readme_section(records: list[dict], today: date, limit: int = 20, priority_config: dict | None = None) -> str:
    priority_config = priority_config or {}
    rows = sorted(records, key=lambda row: readme_sort_key(row, today, priority_config))[:limit]
    if not rows:
        return "The next scheduled collection will populate this table."
    lines = [
        f"_Showing up to {len(rows)} current opportunities. See the [full catalog](OPPORTUNITIES.md) for every record._",
        "",
        "Status | Organization | Opportunity | Location | Apply | Deadline",
        "--- | --- | --- | --- | --- | ---",
    ]
    for row in rows:
        status, _ = _status(row, today)
        url = _text(row.get("url"))
        apply_link = f"[Apply]({url})" if url else "Check site"
        lines.append(" | ".join([
            status,
            _cell(row.get("organization")) or "Not specified",
            _cell(row.get("title")),
            _cell(row.get("location")) or "Check site",
            apply_link,
            _cell(row.get("deadline")) or "Rolling / check site",
        ]))
    return "\n".join(lines)


def update_readme(path: Path, records: list[dict], today: date, priority_config: dict | None = None) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    if README_START not in text or README_END not in text:
        raise ValueError("README is missing the current-opportunities markers")
    before, remainder = text.split(README_START, 1)
    _, after = remainder.split(README_END, 1)
    updated = before + README_START + "\n" + render_readme_section(records, today, priority_config=priority_config) + "\n" + README_END + after
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(updated, encoding="utf-8")
    temporary.replace(path)


def write_catalog(records: list[dict], path: Path, today: date) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(render_catalog(records, today), encoding="utf-8")
    temporary.replace(path)
