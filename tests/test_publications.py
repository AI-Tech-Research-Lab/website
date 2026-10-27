import unittest
from unittest.mock import Mock

import requests
import script


def publication(**overrides):
    return {"title": "A paper", "year": 2026, "authors": "A Author", "venue": "Journal",
            "url": "https://example.org/paper", "doi": None, "preprint": False,
            "sources": ["OpenAlex"], "members": ["Member"], **overrides}


class PublicationsTests(unittest.TestCase):
    def test_merge_versions_and_keep_published_record(self):
        records = [publication(title="A PAPER!", preprint=True, year=2025, sources=["Scholar"]),
                   publication()]
        merged = script.deduplicate(records)
        self.assertEqual(len(merged), 1)
        self.assertFalse(merged[0]["preprint"])
        self.assertEqual(merged[0]["year"], 2026)
        self.assertEqual(merged[0]["sources"], ["OpenAlex", "Scholar"])

    def test_html_escapes_external_metadata_and_links(self):
        html = script.generate_html_list([publication(title='<script> & "Test"', authors="A & B")])
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("A &amp; B", html)
        with self.assertRaises(ValueError):
            script.generate_html_list([publication(url="javascript:alert(1)")])

    def test_invalid_or_empty_update_is_rejected(self):
        for content in ["no markers", script.END_MARKER + script.START_MARKER,
                        script.START_MARKER * 2 + script.END_MARKER]:
            with self.assertRaises(ValueError):
                script.updated_html(content, [publication()], 2017)
        with self.assertRaises(ValueError):
            script.updated_html(script.START_MARKER + script.END_MARKER, [], 2017)

    def test_openalex_pagination_and_member_attribution(self):
        work = {"id": "https://openalex.org/W1", "display_name": "Paper", "publication_year": 2026,
                "authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Member"}}]}
        session = Mock()
        session.get.return_value.json.side_effect = [
            {"results": [work], "meta": {"next_cursor": "page2"}},
            {"results": [{**work, "id": "https://openalex.org/W2"}], "meta": {"next_cursor": None}}]
        records, counts = script.fetch_openalex(session, [{"name": "Member", "openalex_id": "A1"}], 2017)
        self.assertEqual(len(records), 2)
        self.assertEqual(counts, {"Member": 2})
        self.assertEqual(session.get.call_count, 2)

    def test_scholar_block_is_rejected(self):
        with self.assertRaises(ValueError):
            script.parse_scholar_page("<html>CAPTCHA</html>")


if __name__ == "__main__":
    unittest.main()
