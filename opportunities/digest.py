from __future__ import annotations

import html
from datetime import date
from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path
from urllib.parse import urlencode

from .core import posted_recently, undergraduate_internship, web_url, write_json


def compact_authorization(value: str) -> str:
    lowered = value.casefold()
    if "citizenship required" in lowered:
        return "U.S. citizenship required"
    if "no sponsorship" in lowered:
        return "No sponsorship stated"
    if "mentions sponsorship" in lowered:
        return "Sponsorship mentioned—verify"
    if "work authorization mentioned" in lowered:
        return "Work authorization mentioned—verify"
    return "Work authorization not stated"


def prepare_digest(rows: list[dict], output: Path, club: str, today: date, stale_days: int = 7,
                   max_age_days: int | None = 7, allow_empty: bool = False) -> int:
    selected, skipped = [], []
    for row in rows:
        if row["decision"] != "Include":
            continue
        reason = ""
        if not undergraduate_internship(row):
            reason = "Not an undergraduate internship"
        elif row["availability"] != "Current":
            reason = row["availability"]
        elif row["deadline"] and date.fromisoformat(row["deadline"]) < today:
            reason = "Expired"
        elif (today - date.fromisoformat(row["last_seen"])).days > stale_days:
            reason = "Needs recheck"
        elif not posted_recently(row, today, max_age_days):
            reason = "Outside posting-date window or missing posting date"
        if reason:
            skipped.append({"id": row["id"], "title": row["title"], "reason": reason})
        else:
            selected.append(row)
    if not selected:
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / "digest-report.json", {"date": today.isoformat(), "included": 0, "included_ids": [], "skipped": skipped})
        (output / "email-preview.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>No matches</title><h1>No email draft this run</h1><p>No current eligible listings were selected. Review the <a href="../screening-report.html">screening report</a>, or mark eligible listings Include in the workbook.</p></html>', encoding="utf-8")
        (output / "email.txt").write_text("No current eligible listings selected. No email draft this run.\n", encoding="utf-8")
        (output / "email-draft.eml").unlink(missing_ok=True)
        if allow_empty:
            return 0
        raise ValueError("No current listings marked Include. Review the workbook and try again; no email draft was written.")
    subject = f"{club} tech opportunities — {today:%B %d, %Y}"
    intro = "Here are this week's opportunities. Check each application page for eligibility and the latest deadline."
    text_parts = [subject, "", intro]
    cards = []
    esc = html.escape
    for number, row in enumerate(selected, 1):
        title = f'{row["title"]} — {row["organization"]}' if row["organization"] else row["title"]
        facts = [row["location"], f'Posted {row["published_date"]}']
        if row["deadline"]:
            facts.append(f'Deadline {row["deadline"]}')
        if row.get("email_summary"):
            facts.append(row["email_summary"])
        facts.append(compact_authorization(row.get("authorization_summary", "")))
        details = " · ".join(value for value in facts if value)
        web_url(row["url"])
        web_url(row["source_url"])
        text_parts.extend(["", f"{number}. {title}", details])
        if row["notes"]:
            text_parts.append("Note: " + row["notes"])
        text_parts.append(f'Apply: {row["url"]}')
        note = f'<br><em>{esc(row["notes"]).replace(chr(10), " ")}</em>' if row["notes"] else ""
        cards.append(f'<li style="margin:0 0 12px"><strong>{esc(title)}</strong><br>'
                     f'<span style="color:#43556a;font-size:14px">{esc(details)}</span>{note}<br>'
                     f'<a href="{esc(row["url"], quote=True)}">Apply</a></li>')
    body = f'<main style="max-width:760px;margin:24px auto;font-family:Arial,sans-serif;line-height:1.35;color:#17324d"><h1 style="font-size:24px;margin-bottom:4px">{esc(club)} tech opportunities</h1><p style="margin-top:0">{today:%B %d, %Y}</p><p>{esc(intro)}</p><ol style="padding-left:24px">{"".join(cards)}</ol></main>'
    text = "\n".join(text_parts) + "\n"
    mailto = "mailto:?" + urlencode({"subject": subject, "body": text})
    # Long mailto links are unreliable across clients; use the formatted copy path.
    launch = f'<a href="{esc(mailto, quote=True)}">Open a plain-text draft in your mail app</a>' if len(mailto) <= 1800 else "This digest is too long for a reliable email link. Copy the formatted message below into your email editor."
    preview = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Email preview</title><body>'
    preview += f'<aside style="max-width:720px;margin:24px auto;font:16px Arial;background:#edf5ff;padding:20px"><strong>Email draft — {len(selected)} opportunities</strong><p>{launch}</p><p>Select and copy the formatted message below, then paste it into your email editor. Add your club recipient and review before sending.</p><p>Subject: {esc(subject)}</p></aside>{body}</body></html>'
    preview = preview.replace('</aside>', '<p><button onclick="copyEmail()">Copy formatted email</button> <span id="copy-status" role="status"></span></p></aside>')
    preview = preview.replace('</body>', '''<script>
async function copyEmail() {
  const message = document.querySelector('main');
  const status = document.getElementById('copy-status');
  try {
    await navigator.clipboard.write([new ClipboardItem({
      'text/html': new Blob([message.outerHTML], {type: 'text/html'}),
      'text/plain': new Blob([message.innerText], {type: 'text/plain'})
    })]);
    status.textContent = 'Copied. Paste into your email editor.';
  } catch (_) {
    const range = document.createRange(); range.selectNode(message);
    const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
    status.textContent = 'Message selected. Press Command+C or Ctrl+C to copy.';
  }
}
</script></body>''')
    message = EmailMessage(policy=SMTP)
    message["Subject"] = subject
    message["X-Unsent"] = "1"
    message.set_content(text)
    message.add_alternative(body, subtype="html")
    output.mkdir(parents=True, exist_ok=True)
    (output / "email-preview.html").write_text(preview, encoding="utf-8")
    (output / "email.txt").write_text(text, encoding="utf-8")
    (output / "email-draft.eml").write_bytes(message.as_bytes())
    write_json(output / "digest-report.json", {"date": today.isoformat(), "included": len(selected),
                                             "included_ids": [row["id"] for row in selected], "skipped": skipped})
    return len(selected)
