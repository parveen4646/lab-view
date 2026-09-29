"""
Analytics router — population percentile scoring endpoint.

POST /api/analytics/percentile
  Body: {"results": [{"testName": "...", "value": 5.5}, ...]}
  Returns: enriched results with percentile_rank, interpretation, z_score,
           an overall_health_score, and a human-readable summary.

No authentication required.
"""

from typing import Any, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from services.population_stats import get_percentile

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class LabResultInput(BaseModel):
    testName: str
    value: float


class PercentileRequest(BaseModel):
    results: List[LabResultInput]


class EnrichedResult(BaseModel):
    testName: str
    value: float
    percentile_rank: Optional[float] = None
    interpretation: Optional[str] = None
    z_score: Optional[float] = None
    direction: Optional[str] = None


class PercentileResponse(BaseModel):
    enriched: List[EnrichedResult]
    overall_health_score: Optional[float]
    summary: str


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _summary(score: float) -> str:
    if score >= 80:
        return "Excellent health markers"
    if score >= 60:
        return "Good overall health"
    if score >= 40:
        return "Some areas for attention"
    return "Several markers need review"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/percentile", response_model=PercentileResponse)
async def compute_percentiles(request: PercentileRequest) -> PercentileResponse:
    """
    Enrich a list of lab results with NHANES-based population percentile ranks.
    """
    enriched: List[EnrichedResult] = []
    found_ranks: List[float] = []

    for item in request.results:
        result = get_percentile(item.testName, item.value)
        if result is not None:
            found_ranks.append(result["percentile_rank"])
            enriched.append(EnrichedResult(
                testName=item.testName,
                value=item.value,
                percentile_rank=result["percentile_rank"],
                interpretation=result["interpretation"],
                z_score=result["z_score"],
                direction=result["direction"],
            ))
        else:
            enriched.append(EnrichedResult(
                testName=item.testName,
                value=item.value,
            ))

    if found_ranks:
        overall = round(sum(found_ranks) / len(found_ranks), 1)
        summary = _summary(overall)
    else:
        overall = None
        summary = "No recognized biomarkers found"

    return PercentileResponse(
        enriched=enriched,
        overall_health_score=overall,
        summary=summary,
    )
