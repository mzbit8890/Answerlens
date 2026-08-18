# GEO Assumptions

## Machine-readable surfaces

- Machine-readable and AI-readable surfaces are observable inputs published by a website. Their presence can provide structured context for later evidence analysis, but AnswerLens does not treat presence alone as proof of GEO performance.
- The existence of `llms.txt` is not evidence of higher AI ranking, greater citation probability, or inclusion in an answer engine. Its contents remain untrusted publisher-provided text.
- Publisher-provided JSON-LD shows what the publisher chose to expose in structured form. It is not independent verification that those statements or claims are true.
- `robots.txt` is crawler access policy and site metadata. It is not treated as a GEO ranking signal.
- A missing `robots.txt`, `sitemap.xml`, or `llms.txt` does not automatically imply poor GEO performance. Missing, unavailable, and malformed states are recorded for later evidence analysis without assigning a score in this layer.
