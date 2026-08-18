import json
import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class ExtractedHTML:
    title: str | None
    meta_description: str | None
    headings: list[str]
    content: str
    links: list[str]
    json_ld: list[Any]


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def extract_html(html: str) -> ExtractedHTML:
    soup = BeautifulSoup(html, "html.parser")

    title = _clean_text(soup.title.get_text(" ", strip=True)) if soup.title else None
    description_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    description_value = description_tag.get("content") if description_tag else None
    meta_description = (
        _clean_text(str(description_value)) if description_value is not None else None
    )

    headings = [
        text
        for heading in soup.find_all(re.compile(r"^h[1-6]$"))
        if (text := _clean_text(heading.get_text(" ", strip=True)))
    ]
    links = [str(anchor["href"]).strip() for anchor in soup.find_all("a", href=True)]

    json_ld: list[Any] = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"^application/ld\+json$", re.I)}):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            json_ld.append(json.loads(raw))
        except json.JSONDecodeError:
            json_ld.append(raw.strip())

    for element in soup(["script", "style", "noscript", "template", "svg", "nav", "footer", "header", "aside", "form"]):
        element.decompose()

    main = soup.find("main") or soup.find("article") or soup.body or soup
    content = _clean_text(main.get_text(" ", strip=True))
    return ExtractedHTML(
        title=title,
        meta_description=meta_description,
        headings=headings,
        content=content,
        links=links,
        json_ld=json_ld,
    )
