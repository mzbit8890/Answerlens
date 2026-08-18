from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CrawlStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class CrawledPage(BaseModel):
    requested_url: str
    final_url: str | None = None
    status: CrawlStatus
    failure: str | None = None
    title: str | None = None
    meta_description: str | None = None
    headings: list[str] = Field(default_factory=list)
    content: str = ""
    internal_links: list[str] = Field(default_factory=list)
    json_ld: list[Any] = Field(default_factory=list)


class CrawlResult(BaseModel):
    target_url: str
    pages: list[CrawledPage] = Field(default_factory=list)
