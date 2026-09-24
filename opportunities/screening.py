"""Evidence-based shortlisting for a broad undergraduate tech audience."""
from __future__ import annotations

import html
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from .core import availability, eligible, iso_date, read_json, write_json
from .catalog import davidson_priority_score
from .job_pages import JobReader, supported_ats

DEFAULT_INTERESTS = ["software", "computer science", "data", "machine learning", "cybersecurity",
                     "product", "engineering", "quantitative", "research", "analytics"]
SKILLS = ["python", "java", "javascript", "typescript", "sql", "c++", "react", "excel", "statistics", "git"]
DEFAULT_NEARBY_LOCATIONS = ["Davidson, NC", "Charlotte, NC", "Cornelius, NC", "Huntersville, NC",
                            "Mooresville, NC", "Concord, NC", "Kannapolis, NC"]
DEFAULT_DAVIDSON_FIT_TERMS = ["mentor", "mentorship", "training", "collaborat", "cross-functional",
                               "communication", "team", "research", "analytics", "product"]


def evidence(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.I)
    if not match:
        return ""
    start = max(text.rfind("\n", 0, match.start()) + 1, match.start() - 160)
    end = text.find("\n", match.end())
    return text[start:min(end if end >= 0 else len(text), match.end() + 200)].strip()


def contains(term: str, text: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.I))


def source_priority(row: dict, settings: dict) -> int:
    """Prioritize locations that are practical for Davidson students."""
    location = row.get("location", "")
    nearby_locations = settings.get("nearby_locations", DEFAULT_NEARBY_LOCATIONS)
    if any(place.casefold() in location.casefold() for place in nearby_locations):
        distance = 3
    elif re.search(r"(?:\bNorth Carolina\b|,\s*NC\b)", location, re.I):
        distance = 2
    elif re.search(r"\bremote\b", location, re.I):
        distance = 1
    else:
        distance = 0
    return distance


def assess(row: dict, page: dict, config: dict, today: date) -> dict:
    result = {"id": row["id"], "title": row["title"], "organization": row["organization"],
              "url": row["url"], "status": "Needs review", "score": 0, "reasons": [],
              "davidson_priority": 0,
              "unknowns": [], "evidence": {}, "authorization": "Not specified — verify before applying",
              "class_years": "Not specified", "skills": [], "pay": "Not specified",
              "priority_labels": [], "checked_on": page.get("checked_on", ""), "selected": False}
    if availability(row, today, config.get("stale_after_days", 7)) != "Current" or not eligible(row, config, today):
        return {**result, "status": "Excluded", "reasons": ["Outside current undergraduate internship filters"]}
    if page.get("error"):
        return {**result, "reasons": [page["error"]]}
    if not page.get("text"):
        return {**result, "status": "Not checked", "reasons": ["Awaiting a page check; run again to check more listings"]}
    text = page["text"]
    result["page_format"] = page.get("format", "")
    if evidence(r"(?:position|job|role) (?:has been|is) (?:filled|closed)|no longer accepting applications|job is no longer available", text):
        return {**result, "status": "Excluded", "reasons": ["Employer page says this role is closed"]}
    for field in ("posted", "deadline"):
        try:
            value = iso_date(page.get(field))
        except (ValueError, TypeError, OverflowError):
            return {**result, "reasons": [f"Employer {field} date could not be interpreted"]}
        if value:
            result["evidence"][field] = value
            if field == "posted" and config.get("max_age_days", 7) is not None:
                if not 0 <= (today - date.fromisoformat(value)).days <= config.get("max_age_days", 7):
                    return {**result, "status": "Excluded", "reasons": ["Employer posting date is outside the configured window"]}
            if field == "deadline" and date.fromisoformat(value) < today:
                return {**result, "status": "Excluded", "reasons": ["Employer application deadline has passed"]}
    if not result["evidence"].get("posted"):
        result["unknowns"].append("Employer posting date not supplied; recency uses the feed date")

    degree = evidence(
        r"\b(?:pursu\w+|enrolled|working towards?|studying).{0,160}(?:bachelor['’]?s?|undergraduate)\b|"
        r"\bundergraduate(?:\s+\([^)]{0,40}\))?\s+students?\b|"
        r"\bbachelor['’]?s?\b.{0,70}(?:students?|degree (?:program|in progress))", text)
    internship = evidence(r"\b(?:intern(?:ship)?s?|co[ -]?op)\b", page.get("title", "") + "\n" + text)
    for paragraph in re.split(r"\n|(?<=[.!?])\s+(?=[A-Z])", text):
        if re.search(r"(?:must|required|minimum|pursuing|enrolled).{0,100}(?:master['’]?s?|ph\.?d|doctoral|mba)", paragraph, re.I):
            if not re.search(r"bachelor|undergrad", paragraph, re.I):
                result["evidence"]["degree_restriction"] = paragraph[:500]
                return {**result, "status": "Excluded", "reasons": ["Description specifies an advanced-degree requirement"]}
    result["evidence"].update({"degree": degree, "internship": internship})
    if not degree:
        result["unknowns"].append("Undergraduate eligibility not confirmed in employer description")
    if not internship:
        result["unknowns"].append("Internship role not confirmed in employer description")

    citizenship = evidence(r"(?:must|require\w*|only).{0,65}(?:u\.?s\.?|united states) citizen|(?:u\.?s\.?|united states) citizenship (?:is )?required", text)
    no_sponsor = evidence(r"(?:no|not|cannot|unable|without).{0,60}sponsor|sponsor\w*.{0,40}(?:not available|not provided)", text)
    sponsor = evidence(r"(?:we|company|employer).{0,35}(?:offer|provide|support)\w*.{0,30}(?:visa )?sponsorship", text)
    international = evidence(r"international students.{0,45}(?:eligible|welcome|may apply)|(?:accept|welcome).{0,30}(?:cpt|opt)|(?:cpt|opt).{0,30}(?:accepted|eligible)", text)
    auth = citizenship or no_sponsor or international or sponsor
    if citizenship:
        result["authorization"] = "U.S. citizenship required"
    elif no_sponsor:
        result["authorization"] = "Employer states no sponsorship; student authorization must be checked"
    elif international:
        result["authorization"] = "Student work authorization mentioned; confirm individual eligibility with ISE"
    elif sponsor:
        result["authorization"] = "Employer mentions sponsorship; confirm coverage for this internship"
    else:
        result["unknowns"].append("International-student/work-authorization eligibility not confirmed")
    result["evidence"]["authorization"] = auth
    class_year = evidence(r"\b(?:freshm[ae]n|first[ -]years?|sophomores?|final[ -]year|"
                          r"(?:juniors?|seniors?)(?:\s+(?:standing|year|students?))|"
                          r"graduat\w*.{0,70}20\d\d)\b", text)
    if class_year:
        result["class_years"] = class_year
    else:
        result["unknowns"].append("Specific class-year requirements not stated")
    result["skills"] = [skill for skill in SKILLS if contains(skill, text)]
    result["pay"] = evidence(r"\$\s?\d[\d,.]*|\bpaid internship\b|\bstipend\b", text) or "Not specified"

    settings = config.get("screening", {})
    interests = settings.get("interests", DEFAULT_INTERESTS)
    matched = [term for term in interests if contains(term, row["title"] + "\n" + text)]
    result["evidence"]["interests"] = "; ".join(matched)
    if degree and internship:
        result["score"] += 50
        result["reasons"].append("Employer description supports undergraduate internship eligibility")
    if matched:
        result["score"] += min(25, len(matched) * 5)
        result["reasons"].append("Matches club interests: " + ", ".join(matched))
    else:
        result["unknowns"].append("No configured tech-interest match found")
    if result["skills"]:
        result["score"] += 10
        result["reasons"].append("Skills mentioned: " + ", ".join(result["skills"]))
    if result["pay"] != "Not specified":
        result["score"] += 5
    fit_terms = settings.get("davidson_fit_terms", DEFAULT_DAVIDSON_FIT_TERMS)
    fit_matches = [term for term in fit_terms if contains(term, text)]
    if fit_matches:
        result["score"] += min(int(settings.get("davidson_fit_bonus", 10)), len(fit_matches) * 2)
        result["priority_labels"].append("Davidson student fit")
        result["reasons"].append("Offers student-fit signals: " + ", ".join(fit_matches[:5]))
    if result["class_years"] != "Not specified":
        result["score"] += int(settings.get("class_year_bonus", 8))
        result["priority_labels"].append("Class-year fit")
        result["reasons"].append("States class-year guidance for undergraduates")
    davidson_score = davidson_priority_score(row, config.get("readme_priority", {}))
    result["davidson_priority"] = davidson_score
    if davidson_score:
        result["score"] += davidson_score
        if any(name.casefold() in row["organization"].casefold()
               for name in config.get("readme_priority", {}).get("davidson_employers", [])):
            result["priority_labels"].append("Davidson-connected employer")
            result["reasons"].append("Employer has a documented Davidson connection")
        else:
            result["priority_labels"].append("Davidson-region location")
            result["reasons"].append("Location is in North Carolina or a nearby state")
    distance_priority = source_priority(row, settings)
    if distance_priority == 3:
        result["score"] += int(settings.get("nearby_location_bonus", 20))
        result["priority_labels"].append("Davidson/Charlotte area")
        result["reasons"].append("Listed in the Davidson/Charlotte area")
    elif distance_priority == 2:
        result["score"] += int(settings.get("north_carolina_bonus", 12))
        result["priority_labels"].append("North Carolina")
        result["reasons"].append("Listed in North Carolina")
    elif distance_priority == 1:
        result["score"] += int(settings.get("remote_bonus", 5))
        result["priority_labels"].append("Remote")
        result["reasons"].append("Remote location listed; verify location restrictions")
    if result["evidence"].get("posted"):
        result["score"] += 5
    result["status"] = "Strong match" if degree and internship and matched and result["score"] >= settings.get("minimum_score", 65) else "Possible match"
    if not degree or not internship:
        result["status"] = "Needs review"
    return result


def screen_records(records: list[dict], reviews: dict, config: dict, output: Path, today: date,
                   refresh: bool = False) -> tuple[list[dict], dict]:
    settings = config.get("screening", {})
    budget = int(settings.get("max_pages_per_run", 120))
    limit = int(settings.get("max_email_items", 20))
    per_company = int(settings.get("max_per_organization", 2))
    if budget < 0 or limit < 1 or per_company < 1:
        raise ValueError("Page budget must be nonnegative; email and employer limits must be positive")
    cache_path = output / "page-cache.json"
    cache = read_json(cache_path, {})
    pages = {}
    candidates = []
    for row in records:
        decision = reviews.get(row["id"], {}).get("decision", "Pending")
        if decision in {"Skip", "Sent"} or availability(row, today, config.get("stale_after_days", 7)) != "Current":
            continue
        cached = cache.get(row["id"], {})
        if not refresh and cached.get("url") == row["url"] and cached.get("checked_on") == today.isoformat():
            pages[row["id"]] = cached
        else:
            candidates.append(row)
    candidates.sort(key=lambda row: (reviews.get(row["id"], {}).get("decision") == "Include",
                                     davidson_priority_score(row, config.get("readme_priority", {})),
                                     source_priority(row, settings), supported_ats(row["url"]),
                                     row["published_date"], row["id"]), reverse=True)
    reader = JobReader(timeout=int(settings.get("request_timeout_seconds", 12)))

    def fetch(row):
        try:
            page = reader.job(row)
        except Exception as error:
            page = {"error": f"Could not read employer page: {error}", "url": row["url"]}
        return {**page, "url": row["url"], "checked_on": today.isoformat()}

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch, row): row for row in candidates[:budget]}
        for future in as_completed(futures):
            row = futures[future]
            pages[row["id"]] = future.result()
            cache[row["id"]] = pages[row["id"]]
    current_ids = {row["id"] for row in records}
    write_json(cache_path, {key: value for key, value in cache.items() if key in current_ids})
    results = [assess(row, pages.get(row["id"], {}), config, today) for row in records]
    by_id = {row["id"]: row for row in records}
    for result in results:
        result["decision"] = reviews.get(result["id"], {}).get("decision", "Pending")
    results.sort(key=lambda item: (item["decision"] == "Include", item["davidson_priority"],
                                   item["score"], by_id[item["id"]]["published_date"], item["id"]), reverse=True)
    chosen, organizations, roles = [], Counter(), set()
    for result in results:
        if len(chosen) >= limit:
            break
        manual = result["decision"] == "Include"
        if result["decision"] in {"Skip", "Sent"} or result["status"] == "Excluded":
            continue
        role = (result["organization"].casefold(), re.sub(r"\W+", " ", result["title"].casefold()).strip())
        if result["status"] != "Strong match":
            continue
        if not manual and (organizations[result["organization"].casefold()] >= per_company or role in roles):
            continue
        row = by_id[result["id"]]
        if not eligible(row, config, today) or availability(row, today, config.get("stale_after_days", 7)) != "Current":
            continue
        result["selected"] = True
        explanation = ("Manually included. " if manual else "Automatically selected. ") + "; ".join(result["reasons"])
        compact = result["priority_labels"] + result["skills"][:3]
        if not compact:
            compact = ["Undergraduate tech internship"]
        chosen.append({**row, **reviews.get(row["id"], {}),
                       "deadline": result["evidence"].get("deadline") or row.get("deadline", ""),
                       "decision": "Include",
                       "notes": reviews.get(row["id"], {}).get("notes", ""), "availability": "Current",
                       "sources": "; ".join(row.get("active_sources", [])), "fit_reason": explanation,
                       "screening_notes": result["authorization"] + ". " + "; ".join(result["unknowns"]),
                       "class_years": result["class_years"], "skills": ", ".join(result["skills"]),
                       "email_summary": " · ".join(compact),
                       "authorization_summary": result["authorization"]})
        organizations[result["organization"].casefold()] += 1
        roles.add(role)
    report = {"date": today.isoformat(), "profile": "All undergraduate class years; tech internships",
              "method": "Employer page metadata and explicit text rules; scores are priorities, not acceptance probabilities",
              "checked_this_run": min(budget, len(candidates)), "cached": len(pages) - min(budget, len(candidates)),
              "counts": dict(Counter(result["status"] for result in results)), "target": limit,
              "selected": len(chosen), "shortfall": max(0, limit - len(chosen)), "results": results}
    write_json(output / "screening-report.json", report)
    write_report(report, output / "screening-report.html")
    return chosen, report


def write_report(report: dict, path: Path) -> None:
    esc = html.escape
    cards = []
    for row in report["results"]:
        facts = {"Class years": row["class_years"], "Skills mentioned": ", ".join(row["skills"]),
                 "Pay excerpt": row["pay"], "Authorization": row["authorization"]}
        proof = "".join(f"<dt>{esc(key)}</dt><dd>{esc(value)}</dd>" for key, value in row["evidence"].items() if value)
        cards.append(f'<details><summary>{"SELECTED · " if row["selected"] else ""}{esc(row["status"])} · {row["score"]} · {esc(row["title"])} — {esc(row["organization"])}</summary>'
                     f'<p>{esc("; ".join(row["reasons"]))}</p><p><strong>Unconfirmed:</strong> {esc("; ".join(row["unknowns"]) or "None identified by the rules")}</p>'
                     + "".join(f"<p><strong>{esc(key)}:</strong> {esc(value)}</p>" for key, value in facts.items())
                     + f'<p>Decision: {esc(row["decision"])} · Checked: {esc(row["checked_on"] or "Not checked")}</p><dl>{proof}</dl><a href="{esc(row["url"], quote=True)}">Employer application page</a></details>')
    path.write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Opportunity screening</title>'
                    '<style>body{max-width:960px;margin:40px auto;padding:0 20px;font:16px/1.5 system-ui;color:#17324d}details{padding:16px;border-bottom:1px solid #ccd}summary{cursor:pointer}dd{white-space:pre-wrap}dt{font-weight:bold}</style>'
                    f'<h1>Hack@Davidson shortlist</h1><p>{esc(report["date"])} · {report["selected"]} selected</p>'
                    '<p><a href="digest/email-preview.html">Open email draft</a></p>'
                    f'<p>{esc(report["method"])}</p><p>{esc(str(report["counts"]))}</p>'
                    '<p>Manual Include gets priority; Skip and Sent are excluded. Unchecked pages are never automatically selected. No work authorization is inferred.</p>'
                    + "".join(cards) + '</html>', encoding="utf-8")
