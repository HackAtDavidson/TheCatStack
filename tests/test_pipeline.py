import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from opportunities.__main__ import collect
from opportunities.core import availability, canonical_url, eligible, merge, normalize
from opportunities.digest import prepare_digest
from opportunities.sources import simplify_rows
from opportunities.workbook import export_workbook, read_review

TODAY = date(2026, 9, 20)


def listing(**overrides):
    return normalize({"title": "Software Engineering Intern", "organization": "Example Company",
                      "category": "Internship", "url": "https://example.org/apply?id=123",
                      "source_url": "https://example.org/opportunities", **overrides})


def tracked(**overrides):
    return {**listing(), "first_seen": "2026-09-19", "last_seen": TODAY.isoformat(),
            "active_sources": ["Test source"], **overrides}


class CoreTests(unittest.TestCase):
    def test_tracking_dedup_keeps_distinct_application_ids(self):
        self.assertEqual(canonical_url("https://EXAMPLE.org/apply?id=123&utm_source=news"), canonical_url("https://example.org/apply?id=123"))
        self.assertNotEqual(listing()["id"], listing(url="https://example.org/apply?id=456")["id"])
        rows = merge([], {"one": [listing()], "two": [listing(url="https://example.org/apply?id=123&utm_source=news")]}, {"one", "two"}, TODAY)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["active_sources"], ["one", "two"])

    def test_rerun_preserves_first_seen_and_detects_missing(self):
        rows = merge([tracked()], {"Test source": [listing(title="Updated title")]}, {"Test source"}, TODAY)
        self.assertEqual(rows[0]["first_seen"], "2026-09-19")
        self.assertEqual(rows[0]["title"], "Updated title")
        missing = merge(rows, {"Test source": []}, {"Test source"}, TODAY)
        self.assertEqual(availability(missing[0], TODAY, 7), "Not in latest feed")

    def test_failed_source_retains_observation_until_stale(self):
        rows = merge([tracked()], {}, {"Test source"}, TODAY)
        self.assertEqual(rows[0]["active_sources"], ["Test source"])
        self.assertEqual(availability(rows[0], TODAY + timedelta(days=8), 7), "Needs recheck")

    def test_successful_other_source_cannot_remove_failed_membership(self):
        rows = merge([tracked(active_sources=["one", "two"])], {"one": []}, {"one", "two"}, TODAY)
        self.assertEqual(rows[0]["active_sources"], ["two"])

    def test_expiry_and_age_filters(self):
        self.assertFalse(eligible(listing(deadline="2026-09-19"), {}, TODAY))
        self.assertTrue(eligible(listing(deadline="2026-09-20"), {}, TODAY))
        self.assertFalse(eligible(listing(published_date="2025-01-01"), {}, TODAY))
        self.assertTrue(eligible(listing(), {}, TODAY))

    def test_rejects_non_web_links(self):
        with self.assertRaises(ValueError):
            listing(url="javascript:alert(1)")

    def test_simplify_filters_closed_and_degree_roles(self):
        raw = {"active": True, "is_visible": True, "title": "Intern", "url": "https://example.org/1", "locations": ["Remote"], "date_posted": 1789862400}
        payload = [raw, {**raw, "active": False}, {**raw, "is_visible": False}, {**raw, "is_advanced_degree": True}]
        result = simplify_rows(payload, {"category": "Internship", "homepage": "https://example.org"}, {})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["location"], "Remote")


class WorkbookAndDigestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "opportunities.xlsx"

    def export(self, records, reviews=None):
        export_workbook(records, reviews or {}, {"sources": []}, self.path, {}, TODAY)

    def test_roundtrip_including_dates_and_formula_like_text(self):
        row = tracked(title='=HYPERLINK("https://example.org", "click")', deadline="2026-10-01")
        self.export([row], {row["id"]: {"decision": "Include", "notes": "+hello"}})
        result = read_review(self.path)[0]
        self.assertEqual(result["title"], row["title"])
        self.assertEqual(result["deadline"], "2026-10-01")
        self.assertEqual(result["notes"], "+hello")
        self.assertEqual(result["decision"], "Include")

    def test_empty_workbook_roundtrip(self):
        self.export([])
        self.assertEqual(read_review(self.path), [])

    def test_digest_requires_explicit_selection(self):
        self.export([tracked()])
        with self.assertRaisesRegex(ValueError, "No current listings"):
            prepare_digest(read_review(self.path), self.root / "digest", "Club", TODAY)
        self.assertFalse((self.root / "digest").exists())

    def test_digest_escapes_html_and_excludes_expired_stale_and_sent(self):
        records = [tracked(title="<script>alert(1)</script>"),
                   tracked(**listing(url="https://example.org/expired", deadline="2026-09-19")),
                   tracked(**listing(url="https://example.org/stale"), last_seen="2026-09-01"),
                   tracked(**listing(url="https://example.org/sent"))]
        reviews = {row["id"]: {"decision": "Include", "notes": "<b>club note</b>"} for row in records}
        reviews[records[-1]["id"]]["decision"] = "Sent"
        self.export(records, reviews)
        out = self.root / "digest"
        self.assertEqual(prepare_digest(read_review(self.path), out, "Club", TODAY), 1)
        page = (out / "email-preview.html").read_text()
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("&lt;b&gt;club note&lt;/b&gt;", page)
        self.assertIn("Source:", page)
        self.assertEqual(len(json.loads((out / "digest-report.json").read_text())["skipped"]), 2)
        self.assertTrue((out / "email-draft.eml").exists())

    def test_duplicate_ids_rejected(self):
        self.export([tracked(), tracked()])
        with self.assertRaisesRegex(ValueError, "duplicate ID"):
            read_review(self.path)

    def test_long_digest_uses_copy_instead_of_long_mailto(self):
        row = tracked()
        self.export([row], {row["id"]: {"decision": "Include", "notes": "Long note " * 500}})
        prepare_digest(read_review(self.path), self.root / "digest", "Club", TODAY)
        page = (self.root / "digest/email-preview.html").read_text()
        self.assertNotIn('href="mailto:', page)

    def test_refresh_preserves_notes_and_decision(self):
        config = {"sources": [{"name": "Test source"}]}
        state = self.root / "state.json"
        row = tracked()
        self.export([row], {row["id"]: {"decision": "Include", "notes": "Great for sophomores"}})
        with patch("opportunities.__main__.collect_source", return_value=[listing()]):
            self.assertEqual(collect(config, self.root, state, self.root, TODAY), 0)
        result = read_review(self.path)[0]
        self.assertEqual(result["notes"], "Great for sophomores")
        self.assertEqual(result["decision"], "Include")

    def test_all_sources_failure_preserves_existing_files(self):
        self.export([tracked()])
        before = self.path.read_bytes()
        state = self.root / "state.json"
        state.write_text(json.dumps([tracked()]))
        with patch("opportunities.__main__.collect_source", side_effect=OSError("Unavailable")):
            with self.assertRaisesRegex(ValueError, "Every source failed"):
                collect({"sources": [{"name": "Test source"}]}, self.root, state, self.root, TODAY)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(json.loads(state.read_text()), [tracked()])

    def test_partial_source_failure_is_visible_and_retains_history(self):
        state = self.root / "state.json"
        state.write_text(json.dumps([tracked()]))
        config = {"sources": [{"name": "Test source"}, {"name": "Second source"}]}
        with patch("opportunities.__main__.collect_source", side_effect=[OSError("Unavailable"), []]):
            self.assertEqual(collect(config, self.root, state, self.root, TODAY), 1)
        self.assertEqual(json.loads(state.read_text())[0]["active_sources"], ["Test source"])
        self.assertEqual(json.loads((self.root / "collection-report.json").read_text())["sources"][0]["status"], "Failed")


if __name__ == "__main__":
    unittest.main()
