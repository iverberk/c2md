import unittest

import httpx

from c2md.client import ConfluenceClient, ConfluenceError, parse_reference


class ClientTests(unittest.TestCase):
    def test_page_references(self):
        ref = parse_reference("https://example.com/confluence/pages/viewpage.action?pageId=123")
        self.assertEqual((ref.base_url, ref.page_id), ("https://example.com/confluence", "123"))
        ref = parse_reference("https://example.com/confluence/display/TEAM/Some+Page")
        self.assertEqual((ref.space, ref.title), ("TEAM", "Some Page"))
        self.assertEqual(parse_reference("https://example.com/spaces/TEAM/pages/123/Title").page_id, "123")
        self.assertEqual(parse_reference("123", "https://example.com/confluence").page_id, "123")

    def test_bad_page_references(self):
        for value in ("123", "not-a-url", "https://example.com/other", "https://example.com/pages/viewpage.action"):
            with self.subTest(value=value), self.assertRaises(ConfluenceError):
                parse_reference(value)

    def test_api_page_and_paginated_attachments(self):
        seen = []

        def handler(request):
            seen.append((str(request.url), request.headers.get("authorization")))
            if request.url.path.endswith("/content/12"):
                return httpx.Response(200, json={"id": "12", "body": {"storage": {"value": "<p>Hello</p>"}}})
            if request.url.path.endswith("/attachment"):
                if request.url.params.get("start"):
                    return httpx.Response(200, json={"results": [{"title": "b.png", "_links": {"download": "/confluence/download/b"}}]})
                return httpx.Response(200, json={"results": [{"title": "a.png"}], "_links": {"next": "/confluence/rest/api/content/12/child/attachment?start=1"}})
            return httpx.Response(200, content=b"image")

        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            client = ConfluenceClient("https://example.com/confluence", "secret", http)
            self.assertEqual(client.get_page(parse_reference("12", client.base_url))["id"], "12")
            self.assertEqual(set(client.attachments("12")), {"a.png", "b.png"})
            self.assertEqual(client.download({"_links": {"download": "/confluence/download/b"}}), b"image")
        self.assertTrue(all(auth == "Bearer secret" for _, auth in seen))


if __name__ == "__main__":
    unittest.main()
