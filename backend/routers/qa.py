"""
RAG-grounded Q&A router.

POST /api/qa/ask
  Body: {"question": "...", "report_id": "optional-report-uuid"}

Retrieval scope:
  - No report_id, no year mentioned: searches only the general
    medical-reference corpus.
  - report_id given: the caller must own that report; search is scoped to
    that report's own chunks plus the medical-reference corpus.
  - A year is mentioned in the question (e.g. "my cholesterol in 2019") and
    the caller is signed in: search widens to ALL of that signed-in user's
    reports from that year (by user_id, taken from the verified JWT — never
    client-supplied), plus the medical-reference corpus, plus the specific
    report_id match above if one was given. Never blends chunks across
    different users' reports.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from qdrant_client import models
from sqlalchemy.orm import Session

from auth.dependencies import _resolve_user
from config import Config
from db.database import get_db
from db.models import Report, User
from services.rag.pipeline import build_context_block, retrieve

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/qa", tags=["qa"])

_optional_bearer = HTTPBearer(auto_error=False)


def _optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not credentials:
        return None
    try:
        return _resolve_user(credentials.credentials, db)
    except Exception:
        return None


class AskRequest(BaseModel):
    question: str
    report_id: Optional[str] = None


class Source(BaseModel):
    source: str
    corpus: str
    relevance: float


class AskResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    answer: str
    sources: List[Source]
    model_used: str


_DISCLAIMER = (
    "You are a medical-information assistant for a lab report app. Answer using ONLY the "
    "numbered context chunks below — if they don't contain the answer, say so plainly. "
    "This is general health education, not a diagnosis: don't tell the user what disease they "
    "have or prescribe treatment: describe what a marker generally means and suggest discussing "
    "specifics with a clinician. Cite chunk numbers like [1] for claims drawn from context."
)


_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _extract_year(question: str) -> Optional[int]:
    """Cheap stand-in for a full self-querying-retriever LLM extraction step
    (see e.g. LangChain's self-query retriever) — we only ever need to pull
    a single well-defined field (a year), so a regex does the job without
    an extra LLM call on every question."""
    match = _YEAR_RE.search(question)
    return int(match.group(0)) if match else None


def _build_filter(report_id: Optional[str], user_id: Optional[str], year: Optional[int]) -> models.Filter:
    should: list = [models.FieldCondition(key="corpus", match=models.MatchValue(value="medical_reference"))]

    if report_id:
        should.append(models.FieldCondition(key="report_id", match=models.MatchValue(value=report_id)))

    if year is not None and user_id:
        # A year was mentioned — widen beyond the single report_id the
        # frontend passed (always just the user's latest report) to all of
        # this signed-in user's reports from that year.
        should.append(
            models.Filter(
                must=[
                    models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id)),
                    models.FieldCondition(key="year", match=models.MatchValue(value=year)),
                ]
            )
        )

    if len(should) == 1:
        return models.Filter(must=should)
    return models.Filter(should=should)


@router.post("/ask", response_model=AskResponse)
async def ask(
    request: AskRequest,
    current_user: Optional[User] = Depends(_optional_user),
    db: Session = Depends(get_db),
):
    if request.report_id:
        if not current_user:
            raise HTTPException(status_code=401, detail="Sign in to ask about a specific report")
        owned = (
            db.query(Report)
            .filter(Report.id == request.report_id, Report.user_id == current_user.id)
            .first()
        )
        if not owned:
            raise HTTPException(status_code=404, detail="Report not found")

    year = _extract_year(request.question)
    query_filter = _build_filter(
        request.report_id, user_id=current_user.id if current_user else None, year=year
    )

    try:
        chunks: List[Dict[str, Any]] = retrieve(request.question, query_filter=query_filter)
    except RuntimeError as exc:
        # QDRANT_URL not configured, or collection not yet seeded
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not chunks:
        return AskResponse(
            answer="I don't have any indexed information to answer that yet.",
            sources=[],
            model_used="none",
        )

    context_block = build_context_block(chunks)
    prompt = f"{_DISCLAIMER}\n\nCONTEXT:\n{context_block}\n\nQUESTION:\n{request.question}\n\nANSWER:"

    from services.llm_router import build_router

    llm_router = build_router(claude_model=Config.CLAUDE_QA_MODEL)
    answer, model_used = llm_router.complete(prompt, max_tokens=800, json_mode=False)

    sources = [
        Source(
            source=c["metadata"].get("source", "unknown"),
            corpus=c["metadata"].get("corpus", "unknown"),
            relevance=round(c["relevance"], 3),
        )
        for c in chunks
    ]
    return AskResponse(answer=answer.strip(), sources=sources, model_used=model_used)
