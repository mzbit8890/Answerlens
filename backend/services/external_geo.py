from agents.evaluation_agent import evaluate_research_batch
from agents.query_agent import generate_recommendation_queries
from providers.base import StructuredOutputProvider
from providers.search import SearchProvider
from schemas.brand import BrandProfile
from schemas.evidence import ClaimEvidenceMap
from schemas.research import ExternalGeoEvaluation
from services.search import research_queries


async def run_external_geo_evaluation(
    brand_profile: BrandProfile,
    claim_evidence_map: ClaimEvidenceMap,
    target_url: str,
    provider: StructuredOutputProvider,
    search_provider: SearchProvider,
    known_competitors: list[str] | None = None,
) -> ExternalGeoEvaluation:
    """Run the bounded Task 7 vertical slice without workflow orchestration."""
    query_set = await generate_recommendation_queries(
        brand_profile,
        provider,
        known_competitors,
    )
    research = await research_queries(query_set, target_url, search_provider)
    evaluations = await evaluate_research_batch(
        query_set,
        brand_profile,
        claim_evidence_map,
        research,
        provider,
        known_competitors,
    )
    return ExternalGeoEvaluation(
        query_set=query_set,
        research=research,
        evaluations=evaluations,
    )
