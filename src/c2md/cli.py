"""Command line interface for Confluence Data Center page exports."""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

from .client import ConfluenceClient, ConfluenceError, parse_reference
from .convert import Converter


def _keyring():
    try:
        import keyring

        return keyring
    except ImportError:
        return None


def _token(base_url: str) -> str:
    token = os.environ.get("C2MD_TOKEN")
    ring = _keyring()
    if not token and ring:
        try:
            token = ring.get_password("c2md", base_url)
        except Exception:  # Optional integration must not prevent a one-off export.
            pass
    if not token:
        if not sys.stdin.isatty():
            raise ConfluenceError("No token available. Set C2MD_TOKEN or run in a terminal to enter a PAT.")
        print("Create a Personal access token in Confluence: avatar → Settings → Personal access tokens.", file=sys.stderr)
        token = getpass.getpass("Personal access token: ").strip()
        if not token:
            raise ConfluenceError("A personal access token is required.")
    return token


def _save_token(base_url: str, token: str) -> None:
    ring = _keyring()
    if not ring:
        raise ConfluenceError("Keyring support is not installed. Run: uv tool install '.[keyring]' --reinstall")
    try:
        ring.set_password("c2md", base_url, token)
    except Exception as exc:
        raise ConfluenceError(f"Could not save the token to the system keyring: {exc}") from exc


def _slug(title: str) -> str:
    return re.sub(r"[^\w.-]+", "-", title, flags=re.UNICODE).strip("-.")[:100] or "page"


def _export(client: ConfluenceClient, page: dict, output: Path, force: bool) -> tuple[int, int]:
    if output.exists() and not force:
        raise ConfluenceError(f"Output already exists: {output}. Pass --force to overwrite it.")
    directory = output.parent / (output.stem + "_assets")
    if directory.exists() and not force:
        raise ConfluenceError(f"Assets directory already exists: {directory}. Pass --force to reuse it.")
    page_id = page["id"]
    storage = page["body"]["storage"]["value"]
    attachments = client.attachments(page_id)
    used: dict[str, str | None] = {}
    filenames: set[str] = set()
    download_warnings: list[str] = []

    def save_attachment(filename: str) -> str | None:
        if filename in used:
            return used[filename]
        item = attachments.get(filename)
        if not item:
            used[filename] = None
            download_warnings.append(f"Attachment {filename!r} was not found.")
            return None
        safe = Path(filename.replace("\\", "/")).name
        safe = re.sub(r"[^\w .-]", "_", safe, flags=re.UNICODE).strip(" .") or "attachment"
        if safe in filenames:
            safe = f"{item['id']}-{safe}"
        filenames.add(safe)
        if (directory / safe).exists() and not force:
            raise ConfluenceError(f"Attachment file already exists: {directory / safe}. Pass --force to overwrite it.")
        try:
            content = client.download(item)
        except ConfluenceError as exc:
            used[filename] = None
            download_warnings.append(f"Could not download attachment {filename!r}: {exc}")
            return None
        directory.mkdir(parents=True, exist_ok=True)
        (directory / safe).write_bytes(content)
        used[filename] = quote(directory.name, safe="") + "/" + quote(safe)
        return used[filename]

    converter = Converter(client.base_url, page.get("space", {}).get("key", ""), client.page_link, save_attachment)
    markdown = converter.convert(storage)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    return len(converter.warnings) + len(download_warnings), len([name for name in used if used[name]])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert a Confluence Data Center page to Markdown.")
    parser.add_argument("page", help="Page URL or numeric page ID")
    parser.add_argument("--base-url", help="Confluence base URL (required with a page ID)")
    parser.add_argument("-o", "--output", type=Path, help="Markdown file (default: page title.md)")
    parser.add_argument("--save-token", action="store_true", help="Save PAT in the OS keyring (install the keyring extra)")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output file and reuse its assets directory")
    args = parser.parse_args(argv)
    try:
        ref = parse_reference(args.page, args.base_url)
        token = _token(ref.base_url)
        client = ConfluenceClient(ref.base_url, token)
        try:
            page = client.get_page(ref)
            if args.save_token:
                _save_token(ref.base_url, token)
            output = args.output or Path(_slug(page.get("title", "page")) + ".md")
            warnings, downloaded = _export(client, page, output, args.force)
        finally:
            client.close()
        print(f"Wrote {output} ({downloaded} attachments, {warnings} conversion warnings)")
        return 0
    except (ConfluenceError, OSError, KeyError, ValueError) as exc:
        print(f"c2md: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
