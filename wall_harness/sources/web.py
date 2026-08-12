from __future__ import annotations

from html.parser import HTMLParser

from wall_harness.models import Item, SourceSpec

from .http import get


class MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_parts: list[str] = []
        self.description = ""
        self.paragraphs: list[str] = []
        self.in_paragraph = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "p":
            self.in_paragraph = True
        elif tag == "meta" and (attributes.get("name") or "").lower() == "description":
            self.description = attributes.get("content", "") or ""
        elif tag == "meta" and attributes.get("property") == "og:description":
            self.description = self.description or attributes.get("content", "") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        elif tag == "p":
            self.in_paragraph = False

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        elif self.in_paragraph and len(" ".join(self.paragraphs)) < 3000:
            self.paragraphs.append(text)


class WebSource:
    def fetch(self, spec: SourceSpec) -> list[Item]:
        response = get(str(spec.url), cache_ttl_minutes=spec.cache_ttl_minutes)
        parser = MetadataParser()
        parser.feed(response.text)
        title = " ".join(parser.title_parts) or spec.name or str(spec.url)
        summary = parser.description or " ".join(parser.paragraphs)
        return [
            Item.create(
                title=title,
                url=str(spec.url),
                summary=summary,
                source=spec.name or "Web",
                tags=spec.tags,
            )
        ]
