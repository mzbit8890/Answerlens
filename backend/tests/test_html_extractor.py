from services.html_extractor import extract_html


HTML = """
<!doctype html>
<html>
  <head>
    <title> Example Product </title>
    <meta name="description" content="A useful product for teams.">
    <script type="application/ld+json">
      {"@context": "https://schema.org", "@type": "Organization", "name": "Example"}
    </script>
  </head>
  <body>
    <header>Repeated navigation</header>
    <main>
      <h1>Build better</h1>
      <h2>For every team</h2>
      <p>Useful evidence content.</p>
      <a href="/pricing">Pricing</a>
    </main>
    <footer>Cookie policy and legal links</footer>
  </body>
</html>
"""


def test_successful_html_and_metadata_extraction() -> None:
    extracted = extract_html(HTML)

    assert extracted.title == "Example Product"
    assert extracted.meta_description == "A useful product for teams."
    assert extracted.headings == ["Build better", "For every team"]
    assert extracted.content == "Build better For every team Useful evidence content. Pricing"
    assert extracted.links == ["/pricing"]
    assert "Repeated navigation" not in extracted.content
    assert "Cookie policy" not in extracted.content


def test_json_ld_extraction() -> None:
    extracted = extract_html(HTML)

    assert extracted.json_ld == [
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "Example",
        }
    ]


def test_invalid_json_ld_is_preserved_as_untrusted_text() -> None:
    extracted = extract_html(
        '<html><script type="application/ld+json">not-json</script><body>Text</body></html>'
    )

    assert extracted.json_ld == ["not-json"]
