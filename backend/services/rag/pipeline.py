"""Orchestrates hybrid retrieval + reranking into one call."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from qdrant_client import models

from services.rag.reranker import get_reranker
from services.rag.vector_store import RetrievedChunk, hybrid_search

logger = logging.getLogger(__name__)

# Reranking Jev-style costs one API call per candidate, so keep the
# candidate pool retrieval hands the reranker deliberately small.
RETRIEVE_TOP_K = 15
RERANK_TOP_N = 5


def retrieve(
    query: str,
    query_filter: Optional[models.Filter] = None,
    top_n: int = RERANK_TOP_N,
) -> List[Dict[str, Any]]:
    """Hybrid-search then rerank; returns top_n chunks with text + metadata."""
    candidates: List[RetrievedChunk] = hybrid_search(query, limit=RETRIEVE_TOP_K, query_filter=query_filter)
    if not candidates:
        return []

    reranker = get_reranker()
    ranked = reranker.rerank(query, [c.text for c in candidates], top_n=top_n)

    results = []
    for original_index, relevance in ranked:
        chunk = candidates[original_index]
        results.append(
            {
                "text": chunk.text,
                "relevance": relevance,
                "retrieval_score": chunk.score,
                "metadata": chunk.metadata,
            }
        )
    return results


def build_context_block(chunks: List[Dict[str, Any]]) -> str:
    """Render retrieved chunks as a numbered, cited context block for the prompt."""
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        source = chunk["metadata"].get("source", "unknown")
        parts.append(f"[{i}] (source: {source})\n{chunk['text']}")
    return "\n\n".join(parts)
