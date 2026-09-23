import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from opportunities.core import eligible, normalize
from opportunities.workbook import export_workbook, read_review


TODAY = date(2026, 9, 23)


def listing(**overrides):
    return normalize({
        "title": "Software Engineering Intern",
        "organization": "Example",
        "category": "Internship",
        "eligibility": "Bachelor's students",
        "url": "https://example.org/intern",
        "source_url": "https://example.org/source",
        "published_date": TODAY.isoformat(),
        **overrides,
    })


class CollectionTests(unittest.TestCase):
    def test_undergraduate_internship_and_seven_day_window(self):
        config = {"max_age_days": 7}
        self.assertTrue(eligible(listing(), config, TODAY))
        self.assertTrue(eligible(listing(published_date=(TODAY - timedelta(days=7)).isoformat()), config, TODAY))
        self.assertFalse(eligible(listing(published_date=(TODAY - timedelta(days=8)).isoformat()), config, TODAY))

    def test_workbook_round_trip_preserves_review_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "opportunities.xlsx"
            row = {**listing(), "first_seen": TODAY.isoformat(), "last_seen": TODAY.isoformat(),
                   "active_sources": ["Test"]}
            export_workbook([row], {row["id"]: {"decision": "Include", "notes": "Review this"}},
                            {"sources": []}, path, {}, TODAY)
            review = read_review(path)
            self.assertEqual(review[0]["decision"], "Include")
            self.assertEqual(review[0]["notes"], "Review this")


if __name__ == "__main__":
    unittest.main()
