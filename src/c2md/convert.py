"""Best-effort conversion of Confluence storage XHTML to plain Markdown."""

from __future__ import annotations

import re
from collections.abc import Callable

from bs4 import BeautifulSoup, NavigableString, Tag


def _name(node: Tag) -> str:
    return node.name.lower()


def _escape(value: str) -> str:
    return re.sub(r"([\\`*_\[\]<>])", r"\\\1", value)


class Converter:
    def __init__(
        self,
        base_url: str,
        space: str,
        page_link: Callable[[str, str], str],
        attachment: Callable[[str], str | None],
    ):
        self.base_url = base_url
        self.space = space
        self.page_link = page_link
        self.attachment = attachment
        self.warnings: list[str] = []

    def _warn(self, message: str) -> str:
        self.warnings.append(message)
        return ""

    def convert(self, storage: str) -> str:
        soup = BeautifulSoup(storage, "html.parser")
        return self._blocks(soup.contents).strip() + "\n"

    def _blocks(self, nodes: list) -> str:
        return "\n\n".join(part for node in nodes if (part := self._block(node).strip()))

    def _block(self, node: Tag | NavigableString) -> str:
        if isinstance(node, NavigableString):
            return _escape(str(node).strip())
        name = _name(node)
        if name in {"p", "div", "ac:rich-text-body", "body", "html"}:
            if any(isinstance(c, Tag) and _name(c) in {"p", "div", "ul", "ol", "table", "pre", "ac:structured-macro"} for c in node.children):
                return self._blocks(list(node.children))
            return self._inline_children(node).strip()
        if re.fullmatch(r"h[1-6]", name):
            return "#" * int(name[1]) + " " + self._inline_children(node).strip()
        if name in {"ul", "ol"}:
            return self._list(node)
        if name == "blockquote":
            return "\n".join("> " + line for line in self._blocks(list(node.children)).splitlines())
        if name == "pre":
            code = node.get_text().rstrip("\n")
            fence = "`" * max(3, max((len(m.group()) for m in re.finditer(r"`+", code)), default=0) + 1)
            return f"{fence}\n{code}\n{fence}"
        if name == "hr":
            return "---"
        if name == "table":
            return self._table(node)
        if name == "ac:structured-macro":
            return self._macro(node)
        if name == "ac:layout":
            return self._layout(node)
        if name == "ac:task-list":
            return self._tasks(node)
        if name in {"script", "style"}:
            return self._warn(f"Skipped unsupported {name} element.")
        if name in {"ac:image", "ac:link", "img"}:
            return self._inline(node)
        text = self._blocks(list(node.children)) if node.contents else _escape(node.get_text(" ", strip=True))
        self._warn(f"Unsupported {name} element; check its formatting.")
        return text

    def _inline_children(self, node: Tag) -> str:
        return "".join(self._inline(child) for child in node.children)

    def _inline(self, node: Tag | NavigableString) -> str:
        if isinstance(node, NavigableString):
            return _escape(str(node).replace("\n", " "))
        name = _name(node)
        if name == "ac:link":
            return self._link(node)
        if name == "ac:image":
            return self._image(node)
        if name == "img":
            return f"![{_escape(node.get('alt', ''))}]({node.get('src', '')})"
        if name == "br":
            return "  \n"
        if name == "ac:emoticon":
            return _escape(node.get("ac:emoji-shortname") or node.get("ac:name", ""))
        if name == "ac:structured-macro":
            return self._macro(node)
        if name == "code":
            raw = node.get_text()
            fence = "`" * (max((len(m.group()) for m in re.finditer(r"`+", raw)), default=0) + 1)
            return f"{fence}{raw}{fence}"
        content = self._inline_children(node)
        if name in {"strong", "b"}:
            return f"**{content.strip()}**" if content.strip() else ""
        if name in {"em", "i"}:
            return f"*{content.strip()}*" if content.strip() else ""
        if name in {"s", "del", "strike"}:
            return f"~~{content.strip()}~~"
        if name == "a":
            href = node.get("href", "")
            return f"[{content or _escape(href)}]({href.replace(' ', '%20')})" if href else content
        if name in {"span", "ac:plain-text-link-body", "ac:link-body", "sub", "sup"}:
            return content
        if name == "ac:placeholder":
            self._warn("Placeholder content may need editing.")
            return content
        self._warn(f"Unsupported inline {name} element; check its formatting.")
        return content

    def _link(self, node: Tag) -> str:
        body = node.find(["ac:plain-text-link-body", "ac:link-body"], recursive=False)
        page = node.find("ri:page", recursive=False)
        attachment = node.find("ri:attachment", recursive=False)
        url = node.find("ri:url", recursive=False)
        label = self._inline_children(body).strip() if body else ""
        target = ""
        if page:
            title = page.get("ri:content-title", "")
            target = self.page_link(page.get("ri:space-key", self.space), title)
            label = label or _escape(title)
        elif attachment:
            filename = attachment.get("ri:filename", "")
            target = self.attachment(filename) or ""
            label = label or _escape(filename)
        elif url:
            target = url.get("ri:value", "")
            label = label or _escape(target)
        if not target:
            self._warn("Link target could not be resolved.")
            return label
        anchor = node.get("ac:anchor", "")
        if anchor:
            target += "#" + anchor.replace(" ", "%20")
        return f"[{label}]({target.replace(' ', '%20')})"

    def _image(self, node: Tag) -> str:
        attachment = node.find("ri:attachment", recursive=False)
        url = node.find("ri:url", recursive=False)
        alt = _escape(node.get("ac:alt", ""))
        if attachment:
            filename = attachment.get("ri:filename", "")
            target = self.attachment(filename)
            if not target:
                self._warn(f"Image attachment {filename!r} was not available.")
                return _escape(filename)
            return f"![{alt or _escape(filename)}]({target})"
        if url:
            return f"![{alt}]({url.get('ri:value', '')})"
        return self._warn("Image source could not be resolved.")

    def _list(self, node: Tag, depth: int = 0) -> str:
        lines = []
        for item in node.find_all("li", recursive=False):
            children = list(item.children)
            nested = [c for c in children if isinstance(c, Tag) and _name(c) in {"ul", "ol"}]
            content = "".join(self._inline(c) for c in children if c not in nested).strip()
            marker = "1." if _name(node) == "ol" else "-"
            lines.append("  " * depth + marker + " " + content)
            lines.extend(self._list(child, depth + 1) for child in nested)
        return "\n".join(lines)

    def _table(self, table: Tag) -> str:
        rows = table.find_all("tr")
        if not rows:
            return ""
        merged = any(cell.has_attr("colspan") or cell.has_attr("rowspan") for row in rows for cell in row.find_all(["td", "th"], recursive=False))
        data = []
        for row in rows:
            cells = row.find_all(["td", "th"], recursive=False)
            data.append([self._table_cell(cell) for cell in cells])
        width = max(map(len, data), default=0)
        if not width:
            return ""
        data = [row + [""] * (width - len(row)) for row in data]
        first_row = rows[0].find_all(["td", "th"], recursive=False)
        has_header = any(_name(cell) == "th" for cell in first_row)
        header = data[0] if has_header else [""] * width
        lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * width) + " |"]
        lines.extend("| " + " | ".join(row) + " |" for row in (data[1:] if has_header else data))
        if merged:
            self._warn("Table has merged cells; verify its columns and rows.")
        if table.find(["table", "ac:structured-macro", "ac:image"]):
            self._warn("Table contains rich content that may not be preserved.")
        return "\n".join(lines)

    def _table_cell(self, cell: Tag) -> str:
        content = "".join(
            self._inline_children(child) + " " if isinstance(child, Tag) and _name(child) in {"p", "div"}
            else self._inline(child)
            for child in cell.children
        )
        return re.sub(r"\s+", " ", content).strip().replace("|", r"\|")

    def _macro(self, node: Tag) -> str:
        name = node.get("ac:name", "unknown")
        plain = node.find("ac:plain-text-body", recursive=False)
        rich = node.find("ac:rich-text-body", recursive=False)
        if name == "code" and plain:
            code = plain.get_text().rstrip("\n")
            language = next((p.get_text(strip=True) for p in node.find_all("ac:parameter") if p.get("ac:name") == "language"), "")
            fence = "`" * max(3, max((len(m.group()) for m in re.finditer(r"`+", code)), default=0) + 1)
            return f"{fence}{language}\n{code}\n{fence}"
        text = self._blocks(list(rich.children)) if rich else _escape(plain.get_text()) if plain else ""
        if name in {"info", "note", "tip", "warning", "panel"}:
            self._warn(f"{name} panel styling was simplified.")
            return f"**{name.capitalize()}:** {text}"
        self._warn(f"Macro {name!r} may need manual conversion.")
        return text

    def _layout(self, node: Tag) -> str:
        sections = []
        for section in node.find_all("ac:layout-section", recursive=False):
            columns = section.find_all("ac:layout-cell", recursive=False)
            sections.append("\n\n".join(self._blocks(list(col.children)) for col in columns))
        self._warn("Multi-column layout was flattened into reading order.")
        return "\n\n".join(filter(None, sections))

    def _tasks(self, node: Tag) -> str:
        lines = []
        for task in node.find_all("ac:task", recursive=False):
            status = task.find("ac:task-status")
            body = task.find("ac:task-body")
            mark = "x" if status and status.get_text(strip=True).lower() == "complete" else " "
            lines.append(f"- [{mark}] {self._inline_children(body).strip() if body else ''}")
        return "\n".join(lines)
