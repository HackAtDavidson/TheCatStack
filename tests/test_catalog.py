import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from opportunities.catalog import render_catalog, update_readme


class CatalogTests(unittest.TestCase):
    def test_catalog_groups_sections_and_marks_deadlines(self):
        rows = [
            {
                "title": "Software Engineering Intern",
                "organization": "Davidson Labs",
                "category": "Internship",
                "location": "Charlotte, NC",
                "deadline": "2026-09-25",
                "published_date": "2026-09-23",
                "url": "https://example.org/apply?track=tech",
            },
            {
                "title": "Undergraduate Research Fellowship",
                "organization": "Davidson College",
                "category": "Research Program",
                "location": "Davidson, NC",
                "deadline": "",
                "published_date": "",
                "url": "https://example.org/research",
            },
        ]
        catalog = render_catalog(rows, date(2026, 9, 23))
        self.assertIn("## Undergraduate Internships", catalog)
        self.assertIn("## Research Opportunities", catalog)
        self.assertIn("🔥 [CLOSING SOON]", catalog)
        self.assertIn("Community record", catalog)
        self.assertIn("[Apply](https://example.org/apply?track=tech)", catalog)

    def test_catalog_escapes_table_delimiters(self):
        row = {
            "title": "Data | Research Intern",
            "organization": "A | B",
            "category": "Internship",
            "location": "Remote | US",
            "url": "https://example.org",
            "published_date": "2026-09-23",
        }
        catalog = render_catalog([row], date(2026, 9, 23))
        self.assertIn("Data \\| Research Intern", catalog)
        self.assertIn("A \\| B", catalog)

    def test_readme_updates_only_the_generated_section(self):
        row = {
            "title": "Software Engineering Intern",
            "organization": "Davidson Labs",
            "category": "Internship",
            "location": "Charlotte, NC",
            "url": "https://example.org/apply",
            "published_date": "2026-09-23",
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "README.md"
            path.write_text("# Landing\n\n<!-- BEGIN CURRENT OPPORTUNITIES -->\nold\n<!-- END CURRENT OPPORTUNITIES -->\n\nKeep this.\n", encoding="utf-8")
            update_readme(path, [row], date(2026, 9, 23))
            content = path.read_text(encoding="utf-8")
        self.assertIn("# Landing", content)
        self.assertIn("Software Engineering Intern", content)
        self.assertIn("Keep this.", content)
        self.assertNotIn("\nold\n", content)


if __name__ == "__main__":
    unittest.main()
