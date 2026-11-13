"""Confluence REST API access and page URL parsing."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, quote, unquote, urljoin, urlsplit, urlunsplit

import httpx


class ConfluenceError(Exception):
    """A user-facing Confluence or input error."""


@dataclass(frozen=True)
class PageReference:
    base_url: str
    page_id: str | None = None
    space: str | None = None
    title: str | None = None


def parse_reference(value: str, base_url: str | None = None) -> PageReference:
    """Accept a page ID, a viewpage URL, a /display/ URL, or a /spaces/ URL."""
    if value.isdecimal():
        if not base_url:
            raise ConfluenceError("A page ID requires --base-url.")
        return PageReference(_validate_base_url(base_url), page_id=value)

    url = urlsplit(value)
    if url.scheme not in {"http", "https"} or not url.netloc:
        raise ConfluenceError("Provide a Confluence page URL or a numeric page ID.")
    path = unquote(url.path)
    markers = ("/pages/viewpage.action", "/display/", "/spaces/")
    matches = [(path.index(marker), marker) for marker in markers if marker in path]
    if not matches:
        raise ConfluenceError("Unsupported page URL; use a viewpage, display, or spaces URL.")
    index, marker = min(matches)
    origin = urlunsplit((url.scheme, url.netloc, path[:index], "", ""))
    base = _validate_base_url(base_url or origin)
    if marker == "/pages/viewpage.action":
        ids = parse_qs(url.query).get("pageId", [])
        if len(ids) != 1 or not ids[0].isdecimal():
            raise ConfluenceError("The viewpage URL has no valid pageId.")
        return PageReference(base, page_id=ids[0])
    suffix = path[index + len(marker) :].strip("/").split("/")
    if marker == "/spaces/":
        if len(suffix) >= 3 and suffix[1] == "pages" and suffix[2].isdecimal():
            return PageReference(base, page_id=suffix[2])
    elif len(suffix) >= 2 and suffix[0] and suffix[1]:
        return PageReference(base, space=suffix[0], title="/".join(suffix[1:]).replace("+", " "))
    raise ConfluenceError("Cannot determine a page from this URL; use a page ID instead.")


def _validate_base_url(value: str) -> str:
    parsed = urlsplit(value.rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ConfluenceError("--base-url must be an http(s) URL without credentials.")
    if parsed.query or parsed.fragment:
        raise ConfluenceError("--base-url cannot contain a query or fragment.")
    return value.rstrip("/")


class ConfluenceClient:
    def __init__(self, base_url: str, token: str | None = None, client: httpx.Client | None = None):
        self.base_url = _validate_base_url(base_url)
        self.http = client or httpx.Client(timeout=30.0, follow_redirects=True)
        self.http.headers.update({"Accept": "application/json"})
        if token:
            self.http.headers["Authorization"] = f"Bearer {token}"

    def close(self) -> None:
        self.http.close()

    def _request(self, url: str, **kwargs: object) -> httpx.Response:
        try:
            response = self.http.get(url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 401:
                raise ConfluenceError("Authentication failed. Check your personal access token.") from exc
            if status == 403:
                raise ConfluenceError("Access denied. Check your page permissions and token.") from exc
            if status == 404:
                raise ConfluenceError("Page or attachment not found (or not visible to this user).") from exc
            raise ConfluenceError(f"Confluence returned HTTP {status}.") from exc
        except httpx.RequestError as exc:
            raise ConfluenceError(f"Could not connect to Confluence: {exc}") from exc

    def _api(self, path: str, **kwargs: object) -> dict:
        result = self._request(f"{self.base_url}/rest/api/{path}", **kwargs).json()
        if not isinstance(result, dict):
            raise ConfluenceError("Unexpected Confluence API response.")
        return result

    def get_page(self, ref: PageReference) -> dict:
        if ref.page_id:
            return self._api(f"content/{ref.page_id}", params={"expand": "body.storage,space"})
        results = self._api(
            "content", params={"spaceKey": ref.space, "title": ref.title, "expand": "body.storage,space"}
        ).get("results", [])
        if not results:
            raise ConfluenceError("Page not found (or not visible to this user).")
        return results[0]

    def attachments(self, page_id: str) -> dict[str, dict]:
        """Index all page attachments by filename, including paginated results."""
        result: dict[str, dict] = {}
        url = f"{self.base_url}/rest/api/content/{page_id}/child/attachment?limit=200"
        while url:
            payload = self._request(url).json()
            for item in payload.get("results", []):
                result[item["title"]] = item
            next_page = payload.get("_links", {}).get("next")
            if next_page:
                parsed = urlsplit(urljoin(self.base_url + "/", next_page))
                base = urlsplit(self.base_url)
                if (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
                    raise ConfluenceError("Confluence returned an unsafe attachment pagination URL.")
                url = parsed.geturl()
            else:
                url = ""
        return result

    def download(self, attachment: dict) -> bytes:
        path = attachment.get("_links", {}).get("download")
        if not path:
            raise ConfluenceError("Attachment has no download URL.")
        url = urljoin(self.base_url + "/", path)
        parsed, base = urlsplit(url), urlsplit(self.base_url)
        if (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
            raise ConfluenceError("Attachment download URL points outside Confluence.")
        return self._request(url).content

    def page_link(self, space: str, title: str) -> str:
        return f"{self.base_url}/display/{quote(space, safe='')}/{quote(title, safe='').replace('%20', '+')}"
