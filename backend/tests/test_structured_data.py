from schemas.crawl import CrawledPage, CrawlResult, CrawlStatus
from schemas.machine_readable import SurfaceStatus
from services.machine_readable import MAX_STRUCTURED_DATA_NODES, inspect_structured_data


def crawl_with_json_ld(*blocks: object, source: str = "https://example.com/page") -> CrawlResult:
    return CrawlResult(
        target_url="https://example.com/",
        pages=[
            CrawledPage(
                requested_url="https://example.com/requested",
                final_url=source,
                status=CrawlStatus.SUCCESS,
                json_ld=list(blocks),
            )
        ],
    )


def test_detects_required_and_unknown_types_in_nested_graphs() -> None:
    crawl = crawl_with_json_ld(
        {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "Organization", "name": "Example"},
                {"@type": "Product", "name": "Product"},
                {
                    "@type": "SoftwareApplication",
                    "mainEntity": {"@type": "FAQPage"},
                },
                {"@type": ["WebSite", "CustomPublisherType"]},
                {"nested": [{"@type": "WebPage"}]},
            ],
        }
    )

    result = inspect_structured_data(crawl)

    assert result.status is SurfaceStatus.PRESENT
    assert result.encountered_types == [
        "CustomPublisherType",
        "FAQPage",
        "Organization",
        "Product",
        "SoftwareApplication",
        "WebPage",
        "WebSite",
    ]
    assert result.node_limit_reached is False


def test_structured_data_supports_top_level_lists() -> None:
    result = inspect_structured_data(
        crawl_with_json_ld([{"@type": "Organization"}, {"@type": "Product"}])
    )

    assert {item_type for item in result.items for item_type in item.types} == {
        "Organization",
        "Product",
    }


def test_structured_data_preserves_source_page_attribution() -> None:
    result = inspect_structured_data(
        crawl_with_json_ld(
            {"@type": "Organization"}, source="https://example.com/about"
        )
    )

    assert result.pages_with_structured_data == 1
    assert result.items[0].source_page_url == "https://example.com/about"


def test_malformed_json_ld_never_becomes_trusted_schema_data() -> None:
    result = inspect_structured_data(crawl_with_json_ld("not-json"))

    assert result.status is SurfaceStatus.MALFORMED
    assert result.items == []
    assert result.encountered_types == []
    assert result.malformed_items[0].raw_text == "not-json"


def test_pages_without_json_ld_report_missing() -> None:
    result = inspect_structured_data(
        CrawlResult(target_url="https://example.com/", pages=[])
    )

    assert result.status is SurfaceStatus.MISSING
    assert result.pages_with_structured_data == 0


def test_wide_structured_data_stops_at_total_node_budget() -> None:
    wide_graph = [{} for _ in range(MAX_STRUCTURED_DATA_NODES + 10)]
    wide_graph.append({"@type": "MustNotBeVisited"})

    first = inspect_structured_data(crawl_with_json_ld(wide_graph))
    second = inspect_structured_data(crawl_with_json_ld(wide_graph))

    assert first.nodes_visited == MAX_STRUCTURED_DATA_NODES
    assert first.node_limit_reached is True
    assert first.encountered_types == []
    assert first.model_dump() == second.model_dump()
