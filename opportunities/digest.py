from __future__ import annotations

import html
from datetime import date
from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path
from urllib.parse import urlencode

from .core import web_url, write_json


def prepare_digest(rows: list[dict], output: Path, club: str, today: date, stale_days: int = 7) -> int:
    selected, skipped = [], []
    for row in rows:
        if row["decision"] != "Include":
            continue
        reason = ""
        if row["availability"] != "Current":
            reason = row["availability"]
        elif row["deadline"] and date.fromisoformat(row["deadline"]) < today:
            reason = "Expired"
        elif (today - date.fromisoformat(row["last_seen"])).days > stale_days:
            reason = "Needs recheck"
        if reason:
            skipped.append({"id": row["id"], "title": row["title"], "reason": reason})
        else:
            selected.append(row)
    if not selected:
        raise ValueError("No current listings marked Include. Review the workbook and try again; no new draft was written.")
    subject = f"{club} tech opportunities — {today:%B %d, %Y}"
    intro = "Here are this week's opportunities. Check each application page for eligibility and the latest deadline."
    text_parts = [subject, "", intro]
    cards = []
    esc = html.escape
    for row in selected:
        title = f'{row["title"]} — {row["organization"]}' if row["organization"] else row["title"]
        details = f'{row["category"]} · {row["location"]} · Deadline: {row["deadline"] or "not provided"}'
        source_name = row.get("sources") or "Original listing"
        web_url(row["url"])
        web_url(row["source_url"])
        text_parts.extend(["", title, details, row["eligibility"]])
        if row["notes"]:
            text_parts.append(row["notes"])
        text_parts.extend([f'Apply: {row["url"]}', f'Source: {source_name} — {row["source_url"]}'])
        note = f'<p>{esc(row["notes"]).replace(chr(10), "<br>")}</p>' if row["notes"] else ""
        cards.append(f'<section style="padding:20px 0;border-bottom:1px solid #dbe2ea"><h2 style="font-size:19px;margin:0 0 8px">{esc(title)}</h2>'
                     f'<p style="color:#43556a">{esc(details)}</p><p>{esc(row["eligibility"])}</p>{note}'
                     f'<p><a href="{esc(row["url"], quote=True)}">View opportunity and apply</a></p>'
                     f'<p style="font-size:12px">Source: <a href="{esc(row["source_url"], quote=True)}">{esc(source_name)}</a></p></section>')
    body = f'<main style="max-width:720px;margin:24px auto;font-family:Arial,sans-serif;line-height:1.5;color:#17324d"><h1>{esc(club)} tech opportunities</h1><p>{today:%B %d, %Y}</p><p>{esc(intro)}</p>{"".join(cards)}</main>'
    text = "\n".join(text_parts) + "\n"
    mailto = "mailto:?" + urlencode({"subject": subject, "body": text})
    # Long mailto links are unreliable across clients; use the formatted copy path.
    launch = f'<a href="{esc(mailto, quote=True)}">Open a plain-text draft in your mail app</a>' if len(mailto) <= 1800 else "This digest is too long for a reliable email link. Copy the formatted message below into your email editor."
    preview = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Email preview</title><body>'
    preview += f'<aside style="max-width:720px;margin:24px auto;font:16px Arial;background:#edf5ff;padding:20px"><strong>Email draft — {len(selected)} opportunities</strong><p>{launch}</p><p>Select and copy the formatted message below, then paste it into your email editor. Add your club recipient and review before sending.</p><p>Subject: {esc(subject)}</p></aside>{body}</body></html>'
    message = EmailMessage(policy=SMTP)
    message["Subject"] = subject
    message["X-Unsent"] = "1"
    message.set_content(text)
    message.add_alternative(body, subtype="html")
    output.mkdir(parents=True, exist_ok=True)
    (output / "email-preview.html").write_text(preview, encoding="utf-8")
    (output / "email.txt").write_text(text, encoding="utf-8")
    (output / "email-draft.eml").write_bytes(message.as_bytes())
    write_json(output / "digest-report.json", {"date": today.isoformat(), "included": len(selected), "skipped": skipped})
    return len(selected)
