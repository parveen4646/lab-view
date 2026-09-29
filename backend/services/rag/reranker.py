"""
Rerankers — take the hybrid-retrieval candidates and re-score them against
the actual query for precision at the top of the list.

Two implementations, selected by Config.RAG_RERANKER:
  - "bge"  (default): bge-reranker-v2-m3, a local cross-encoder. Same model
    family as the BGE-M3 embedder, Apache-2.0, runs on CPU.
  - "jev": TypeSafe AI's Jev, via the `typesafe-sdk` package, following the
    official re-ranking cookbook (docs.typesafe.ai/cookbooks/rerank_typesafe) —
    one Noul (yes/no-as-probability) question per query/candidate pair, fired
    in parallel with a thread pool. Still treat this as experimental: it's
    built against the documented API shape but has not been exercised against
    a live TypeSafe account (install of typesafe-sdk was blocked in this
    session as an untrusted new package — see the PR description).
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import List, Tuple

from config import Config

logger = logging.getLogger(__name__)


class Reranker:
    def rerank(self, query: str, candidates: List[str], top_n: int) -> List[Tuple[int, float]]:
        """Return (original_index, relevance_score) pairs, sorted best-first."""
        raise NotImplementedError


@lru_cache(maxsize=1)
def _get_bge_model():
    from FlagEmbedding import FlagReranker

    logger.info("Loading bge-reranker-v2-m3 (first call downloads the model)")
    return FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=False)


class BGEReranker(Reranker):
    name = "bge"

    def rerank(self, query: str, candidates: List[str], top_n: int) -> List[Tuple[int, float]]:
        if not candidates:
            return []
        model = _get_bge_model()
        pairs = [(query, c) for c in candidates]
        scores = model.compute_score(pairs, normalize=True)
        if isinstance(scores, float):
            scores = [scores]
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return ranked[:top_n]


class JevReranker(Reranker):
    """
    Mirrors docs.typesafe.ai/cookbooks/rerank_typesafe: one Noul question per
    query/candidate pair, fired concurrently with a thread pool (the cookbook
    notes 1,200 calls cost ~$0.06, "cheap enough to fire all at once"). The
    Noul answer's `.noul` attribute is a single float in [0, 1] — the
    probability the candidate is relevant — used directly as the score.
    """

    name = "jev"

    def rerank(self, query: str, candidates: List[str], top_n: int) -> List[Tuple[int, float]]:
        if not candidates:
            return []
        if not Config.TYPESAFE_API_KEY:
            raise RuntimeError("TYPESAFE_API_KEY is not configured — required for RAG_RERANKER=jev")

        from typesafe_sdk import Noul, NoulCriteria, TypeSafeClient

        question = Noul(
            instructions="Does candidate_chunk directly help answer query?",
            criteria=NoulCriteria(
                true="candidate_chunk contains information that answers or strongly supports query.",
                false="candidate_chunk is off-topic or only loosely related to query.",
            ),
        )

        def _score_one(candidate: str) -> float:
            with TypeSafeClient() as client:
                response = client.system_one(
                    state={"query": query, "candidate_chunk": candidate},
                    questions={"relevance": question},
                    model=Config.JEV_MODEL,
                )
                return float(response.answers["relevance"].noul)

        with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as pool:
            scores = list(pool.map(_score_one, candidates))

        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return ranked[:top_n]


def get_reranker() -> Reranker:
    if Config.RAG_RERANKER == "jev":
        return JevReranker()
    return BGEReranker()
