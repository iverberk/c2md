import os
import tempfile
import unittest
from pathlib import Path

from c2md.cli import _export, main
from c2md.client import ConfluenceError


class FakeClient:
    base_url = "https://example.com/confluence"

    def attachments(self, page_id):
        assert page_id == "123"
        return {"pic.png": {"id": "42", "title": "pic.png", "_links": {"download": "/download/pic.png"}}}

    def download(self, attachment):
        return b"sample image"

    def page_link(self, space, title):
        return f"{self.base_url}/display/{space}/{title}"


class CliTests(unittest.TestCase):
    def test_export_downloads_and_refuses_overwrite(self):
        page = {
            "id": "123", "title": "Example", "space": {"key": "DOC"},
            "body": {"storage": {"value": '<h1>Example</h1><ac:image><ri:attachment ri:filename="pic.png"/></ac:image>'}},
        }
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            output = Path(temp) / "example.md"
            warnings, count = _export(FakeClient(), page, output, False)
            self.assertEqual((warnings, count), (0, 1))
            self.assertEqual((Path(temp) / "example_assets" / "pic.png").read_bytes(), b"sample image")
            self.assertIn("![pic.png](example_assets/pic.png)", output.read_text())
            with self.assertRaises(ConfluenceError):
                _export(FakeClient(), page, output, False)

    def test_export_missing_and_failed_attachments_have_no_markdown_warnings(self):
        class FailedClient(FakeClient):
            def attachments(self, page_id):
                return {"broken.png": {"id": "43"}}

            def download(self, attachment):
                raise ConfluenceError("download failed")

        page = {
            "id": "123", "space": {"key": "DOC"},
            "body": {"storage": {"value": (
                '<ac:image><ri:attachment ri:filename="missing.png"/></ac:image>'
                '<ac:image><ri:attachment ri:filename="broken.png"/></ac:image>'
            )}},
        }
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            output = Path(temp) / "example.md"
            warnings, count = _export(FailedClient(), page, output, False)
            self.assertEqual((warnings, count), (4, 0))
            self.assertEqual(output.read_text(), "missing.png\n\nbroken.png\n")

    def test_script_requires_token_without_terminal(self):
        old = os.environ.pop("C2MD_TOKEN", None)
        try:
            from unittest.mock import patch

            with patch("c2md.cli.sys.stdin.isatty", return_value=False), patch("c2md.cli._keyring", return_value=None):
                self.assertEqual(main(["123", "--base-url", "https://example.com"]), 1)
        finally:
            if old is not None:
                os.environ["C2MD_TOKEN"] = old


if __name__ == "__main__":
    unittest.main()
