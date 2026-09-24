import tempfile
import unittest
from datetime import date
from pathlib import Path

from opportunities.digest import prepare_digest


class DigestTests(unittest.TestCase):
    def test_prepare_digest_writes_compact_application_links(self):
        row = {
            "id": "one", "title": "Software Engineering Intern", "organization": "Example",
            "category": "Internship", "location": "Charlotte, NC", "deadline": "",
            "published_date": "2026-09-22", "last_seen": "2026-09-23", "availability": "Current",
            "decision": "Include", "notes": "", "url": "https://example.org/apply",
            "source_url": "https://example.org/source", "eligibility": "Bachelor's students",
            "sources": "Test",
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.assertEqual(prepare_digest([row], output, "Club", date(2026, 9, 23)), 1)
            preview = (output / "email-preview.html").read_text()
            self.assertIn(">Apply</a>", preview)


if __name__ == "__main__":
    unittest.main()
