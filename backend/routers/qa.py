"""
RAG-grounded Q&A router.

POST /api/qa/ask
  Body: {"question": "...", "report_id": "optional-report-uuid"}

Retrieval scope:
  - No report_id: searches only the general medical-reference corpus.
  - report_id given: the caller must own that report; search is scoped to
    that report's own chunks plus the medical-reference corpus. Never
    blends chunks across different users' reports.
"""
from __future__ import annotations

import logging
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


def _build_filter(report_id: Optional[str]) -> models.Filter:
    if report_id:
        return models.Filter(
            should=[
                models.FieldCondition(key="report_id", match=models.MatchValue(value=report_id)),
                models.FieldCondition(key="corpus", match=models.MatchValue(value="medical_reference")),
            ]
        )
    return models.Filter(
        must=[models.FieldCondition(key="corpus", match=models.MatchValue(value="medical_reference"))]
    )


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

    query_filter = _build_filter(request.report_id)

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
