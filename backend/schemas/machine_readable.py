from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SurfaceStatus(StrEnum):
    PRESENT = "present"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"
    MALFORMED = "malformed"


class ParseStatus(StrEnum):
    PARSED = "parsed"
    MALFORMED = "malformed"
    NOT_APPLICABLE = "not_applicable"


class RobotsRule(BaseModel):
    user_agent: str
    directive: str
    path: str


class RobotsInspection(BaseModel):
    source_url: str
    final_url: str | None = None
    status: SurfaceStatus
    parse_status: ParseStatus = ParseStatus.NOT_APPLICABLE
    raw_text: str = ""
    sitemap_urls: list[str] = Field(default_factory=list)
    sitemap_limit_reached: bool = False
    rules: list[RobotsRule] = Field(default_factory=list)
    malformed_lines: int = 0
    error: str | None = None


class SitemapDocument(BaseModel):
    source_url: str
    final_url: str | None = None
    status: SurfaceStatus
    kind: str | None = None
    error: str | None = None


class SitemapInspection(BaseModel):
    status: SurfaceStatus
    documents: list[SitemapDocument] = Field(default_factory=list)
    discovered_urls: list[str] = Field(default_factory=list)
    rejected_urls: list[str] = Field(default_factory=list)
    document_limit_reached: bool = False
    url_limit_reached: bool = False


class LlmsLink(BaseModel):
    url: str
    internal: bool


class LlmsTxtInspection(BaseModel):
    source_url: str
    final_url: str | None = None
    status: SurfaceStatus
    raw_text: str = ""
    title: str | None = None
    summary: str | None = None
    links: list[LlmsLink] = Field(default_factory=list)
    rejected_links: list[str] = Field(default_factory=list)
    link_limit_reached: bool = False
    error: str | None = None


class StructuredDataItem(BaseModel):
    source_page_url: str
    types: list[str]
    data: dict[str, Any]


class MalformedStructuredData(BaseModel):
    source_page_url: str
    raw_text: str


class StructuredDataInspection(BaseModel):
    status: SurfaceStatus
    pages_with_structured_data: int = 0
    encountered_types: list[str] = Field(default_factory=list)
    items: list[StructuredDataItem] = Field(default_factory=list)
    malformed_items: list[MalformedStructuredData] = Field(default_factory=list)
    item_limit_reached: bool = False
    nodes_visited: int = 0
    node_limit_reached: bool = False


class MachineReadableSummary(BaseModel):
    robots_status: SurfaceStatus
    sitemap_status: SurfaceStatus
    sitemap_urls_discovered: int
    llms_txt_status: SurfaceStatus
    llms_txt_links_discovered: int
    structured_data_status: SurfaceStatus
    structured_data_pages: int
    structured_data_types: list[str] = Field(default_factory=list)


class MachineReadableAudit(BaseModel):
    target_url: str
    robots: RobotsInspection
    sitemap: SitemapInspection
    llms_txt: LlmsTxtInspection
    structured_data: StructuredDataInspection
    summary: MachineReadableSummary
