import json
import ssl
import tempfile
import unittest
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from opportunities.__main__ import collect
from opportunities.core import availability, canonical_url, eligible, merge, normalize, undergraduate_internship
from opportunities.digest import prepare_digest
from opportunities.sources import fetch_json, simplify_rows
from opportunities.workbook import export_workbook, read_review

TODAY = date(2026, 9, 20)


def listing(**overrides):
    return normalize({"title": "Software Engineering Intern", "organization": "Example Company",
                      "category": "Internship", "url": "https://example.org/apply?id=123",
                      "eligibility": "Bachelor's students",
                      "published_date": TODAY.isoformat(),
                      "source_url": "https://example.org/opportunities", **overrides})


def tracked(**overrides):
    return {**listing(), "first_seen": "2026-09-19", "last_seen": TODAY.isoformat(),
            "active_sources": ["Test source"], **overrides}


class CoreTests(unittest.TestCase):
    def test_fetch_json_verifies_tls_without_system_certificates(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertEqual(context.cert_store_stats()["x509_ca"], 0)

        def verified_response(request, **kwargs):
            configured = kwargs.get("context")
            self.assertIsNotNone(configured, "Feed requests need an explicit trusted TLS context")
            self.assertGreater(configured.cert_store_stats()["x509_ca"], 0)
            self.assertTrue(configured.check_hostname)
            self.assertEqual(configured.verify_mode, ssl.CERT_REQUIRED)
            return BytesIO(b"[]")

        with patch("ssl.create_default_context", return_value=context), \
                patch("opportunities.sources.urlopen", side_effect=verified_response):
            self.assertEqual(fetch_json("https://example.org/listings.json"), [])

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

    def test_posting_window_boundaries(self):
        for age, accepted in [(-1, False), (0, True), (6, True), (7, True), (8, False)]:
            with self.subTest(age=age):
                published = (TODAY - timedelta(days=age)).isoformat()
                self.assertEqual(eligible(listing(published_date=published), {}, TODAY), accepted)
        self.assertFalse(eligible(listing(published_date=""), {}, TODAY))
        self.assertFalse(eligible(listing(published_date="2026-09-14"), {"max_age_days": 5}, TODAY))
        self.assertTrue(eligible(listing(published_date=""), {"max_age_days": None}, TODAY))

    def test_rejects_non_web_links(self):
        with self.assertRaises(ValueError):
            listing(url="javascript:alert(1)")

    def test_simplify_filters_closed_and_degree_roles(self):
        raw = {"active": True, "is_visible": True, "title": "Intern", "url": "https://example.org/1", "locations": ["Remote"], "date_posted": 1789862400, "degrees": ["Bachelor's"]}
        payload = [raw, {**raw, "active": False}, {**raw, "is_visible": False}, {**raw, "is_advanced_degree": True}]
        result = simplify_rows(payload, {"category": "Internship", "homepage": "https://example.org"}, {})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["location"], "Remote")

    def test_simplify_requires_undergraduate_degree_metadata(self):
        raw = {"active": True, "title": "Software Engineering Intern", "url": "https://example.org/1"}
        source = {"category": "Internship", "homepage": "https://example.org"}
        for degrees, accepted in [([], False), (["Master's"], False), (["PhD"], False),
                                  (["MBA"], False), (["Bachelor's"], True),
                                  (["Bachelor's", "Master's"], True)]:
            with self.subTest(degrees=degrees):
                rows = simplify_rows([{**raw, "degrees": degrees}], source, {})
                self.assertEqual(bool(rows), accepted)
                if accepted:
                    self.assertIn("Bachelor's", rows[0]["eligibility"])
        self.assertEqual(simplify_rows([raw], source, {}), [])

    def test_simplify_undergraduate_feed_accepts_feed_scoped_eligibility(self):
        raw = {"active": True, "is_visible": True, "title": "Software Engineering Intern",
               "url": "https://example.org/1", "locations": ["Charlotte, NC"],
               "date_posted": TODAY.isoformat(), "company_name": "Example", "sponsorship": "Other"}
        source = {"category": "Internship", "homepage": "https://example.org",
                  "undergraduate_feed": True}
        rows = simplify_rows([raw], source, {})
        self.assertEqual(len(rows), 1)
        self.assertIn("Undergraduate internship feed", rows[0]["eligibility"])

    def test_undergraduate_internship_scope(self):
        for title in ["Software Engineering Intern", "Undergraduate Internship", "Engineering Co-op",
                      "Material Master Data Intern"]:
            with self.subTest(title=title):
                self.assertTrue(undergraduate_internship(listing(title=title)))
        for title in ["Software Engineer", "Full-Time Software Engineer", "Full Time Intern",
                      "Graduate Intern", "New Grad Intern", "Postgraduate Intern", "Post-Graduate Intern",
                      "PhD Intern", "Ph.D. Intern", "Postdoctoral Intern", "Post-Doctoral Intern",
                      "Master's Intern", "Master’s Intern", "Masters Intern", "MS Intern",
                      "M.S. Intern", "MBA Intern", "Doctoral Intern"]:
            with self.subTest(title=title):
                self.assertFalse(eligible(listing(title=title), {}, TODAY))
        self.assertFalse(eligible(listing(category="New graduate role"), {}, TODAY))
        self.assertFalse(eligible(listing(eligibility="Check application page"), {}, TODAY))
        self.assertFalse(eligible(listing(eligibility="Master's or PhD students"), {}, TODAY))
        self.assertTrue(eligible(listing(eligibility="Undergraduate students"), {}, TODAY))


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
        self.assertEqual(json.loads((self.root / "digest/digest-report.json").read_text())["included"], 0)
        self.assertFalse((self.root / "digest/email-draft.eml").exists())

    def test_digest_escapes_html_and_excludes_expired_stale_and_sent(self):
        records = [tracked(title="<script>alert(1)</script> Intern"),
                   tracked(**listing(url="https://example.org/expired", deadline="2026-09-19")),
                   tracked(**listing(url="https://example.org/stale"), last_seen="2026-09-01"),
                   tracked(**listing(url="https://example.org/sent"))]
        reviews = {row["id"]: {"decision": "Include", "notes": "<b>club note</b>"} for row in records}
        reviews[records[-1]["id"]]["decision"] = "Sent"
        self.export(records, reviews)
        out = self.root / "digest"
        self.assertEqual(prepare_digest(read_review(self.path), out, "Club", TODAY), 1)
        page = (out / "email-preview.html").read_text()
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("&lt;b&gt;club note&lt;/b&gt;", page)
        self.assertIn(">Apply</a>", page)
        self.assertNotIn("Source:", page)
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

    def test_refresh_hides_out_of_scope_records_and_preserves_reviews(self):
        keep = tracked()
        graduate = tracked(**listing(url="https://example.org/grad", category="New graduate role"))
        unknown = tracked(**listing(url="https://example.org/unknown", eligibility="Check the application page"))
        records = [keep, graduate, unknown]
        self.export(records, {row["id"]: {"decision": "Include", "notes": "Keep this note"} for row in records})
        state = self.root / "state.json"
        state.write_text(json.dumps(records))
        config = {"sources": [{"name": "Test source"}, {"name": "Club submissions"}]}
        # Even during a feed outage, old full-time/unknown-degree rows stay out of exports.
        with patch("opportunities.__main__.collect_source", side_effect=[OSError("Unavailable"), []]):
            self.assertEqual(collect(config, self.root, state, self.root, TODAY), 1)
        result = read_review(self.path)
        self.assertEqual([row["id"] for row in result], [keep["id"]])
        self.assertEqual(result[0]["notes"], "Keep this note")
        self.assertEqual(len(json.loads(state.read_text())), 1)
        reviews = json.loads((self.root / "reviews.json").read_text())
        self.assertEqual(reviews[graduate["id"]]["notes"], "Keep this note")
        self.assertNotIn(graduate["url"], (self.root / "opportunities.csv").read_text())

    def test_digest_rejects_out_of_scope_rows_in_old_workbooks(self):
        records = [tracked(), tracked(**listing(url="https://example.org/grad", category="New graduate role")),
                   tracked(**listing(url="https://example.org/phd", title="PhD Intern")),
                   tracked(**listing(url="https://example.org/unknown", eligibility="Check application page"))]
        self.export(records, {row["id"]: {"decision": "Include"} for row in records})
        out = self.root / "digest"
        self.assertEqual(prepare_digest(read_review(self.path), out, "Club", TODAY), 1)
        report = json.loads((out / "digest-report.json").read_text())
        self.assertEqual(len(report["skipped"]), 3)
        self.assertTrue(all(row["reason"] == "Not an undergraduate internship" for row in report["skipped"]))

    def test_refresh_removes_old_and_undated_automatic_listings(self):
        recent = tracked()
        old = tracked(**listing(url="https://example.org/old", published_date="2026-09-09"))
        undated = {**tracked(**listing(url="https://example.org/undated", published_date="")),
                   "community_record": True}
        records = [recent, old, undated]
        self.export(records, {row["id"]: {"decision": "Include", "notes": "Saved note"} for row in records})
        state = self.root / "state.json"
        state.write_text(json.dumps(records))
        with patch("opportunities.__main__.collect_source", return_value=records):
            self.assertEqual(collect({"sources": [{"name": "Test source"}]}, self.root,
                                     state, self.root, TODAY), 0)
        rows = read_review(self.path)
        self.assertEqual([row["id"] for row in rows], [recent["id"]])
        self.assertEqual(rows[0]["notes"], "Saved note")
        self.assertEqual(len(json.loads(state.read_text())), 2)
        reviews = json.loads((self.root / "reviews.json").read_text())
        self.assertEqual(reviews[old["id"]]["notes"], "Saved note")
        self.assertNotIn(old["url"], (self.root / "opportunities.csv").read_text())

    def test_digest_rechecks_posting_dates_in_saved_workbooks(self):
        records = [tracked(**listing(url=f"https://example.org/{age}",
                                    published_date=(TODAY - timedelta(days=age)).isoformat()))
                   for age in [0, 7, 8, -1]]
        records.append(tracked(**listing(url="https://example.org/undated", published_date="")))
        self.export(records, {row["id"]: {"decision": "Include"} for row in records})
        out = self.root / "digest"
        self.assertEqual(prepare_digest(read_review(self.path), out, "Club", TODAY), 2)
        report = json.loads((out / "digest-report.json").read_text())
        self.assertEqual(len(report["skipped"]), 3)
        self.assertEqual(prepare_digest(read_review(self.path), out, "Club", TODAY, max_age_days=5), 1)

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

    def test_partial_source_failure_is_visible_and_retains_current_record(self):
        state = self.root / "state.json"
        state.write_text(json.dumps([tracked()]))
        config = {"sources": [{"name": "Test source"}, {"name": "Second source"}]}
        with patch("opportunities.__main__.collect_source", side_effect=[OSError("Unavailable"), []]):
            self.assertEqual(collect(config, self.root, state, self.root, TODAY), 1)
        self.assertEqual(json.loads(state.read_text())[0]["active_sources"], ["Test source"])
        self.assertEqual(json.loads((self.root / "collection-report.json").read_text())["sources"][0]["status"], "Failed")


if __name__ == "__main__":
    unittest.main()
