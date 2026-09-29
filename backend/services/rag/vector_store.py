"""
Qdrant-backed hybrid vector store.

One collection holds two named vectors per point — "dense" (BGE-M3 dense
embedding) and "sparse" (BGE-M3 lexical weights) — so a single query can
fuse dense (semantic) and sparse (keyword) retrieval with Reciprocal Rank
Fusion, server-side, in one round trip.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient, models

from config import Config
from services.rag.embeddings import DENSE_DIM, EmbeddedChunk, embed, embed_one

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    id: str
    text: str
    score: float
    metadata: Dict[str, Any]


@lru_cache(maxsize=1)
def _get_client() -> QdrantClient:
    if not Config.QDRANT_URL:
        raise RuntimeError("QDRANT_URL is not configured — set QDRANT_URL/QDRANT_API_KEY in .env")
    return QdrantClient(url=Config.QDRANT_URL, api_key=Config.QDRANT_API_KEY or None)


def ensure_collection() -> None:
    client = _get_client()
    if client.collection_exists(Config.RAG_COLLECTION):
        return
    client.create_collection(
        collection_name=Config.RAG_COLLECTION,
        vectors_config={
            "dense": models.VectorParams(size=DENSE_DIM, distance=models.Distance.COSINE),
        },
        sparse_vectors_config={
            "sparse": models.SparseVectorParams(),
        },
    )
    logger.info("Created Qdrant collection %s", Config.RAG_COLLECTION)


def upsert_chunks(chunks: List[str], metadatas: List[Dict[str, Any]]) -> List[str]:
    """Embed and upsert chunks; returns the generated point ids."""
    if len(chunks) != len(metadatas):
        raise ValueError("chunks and metadatas must be the same length")
    if not chunks:
        return []

    ensure_collection()
    embedded: List[EmbeddedChunk] = embed(chunks)
    ids = [str(uuid.uuid4()) for _ in chunks]

    points = [
        models.PointStruct(
            id=ids[i],
            vector={
                "dense": embedded[i].dense,
                "sparse": models.SparseVector(
                    indices=embedded[i].sparse_indices,
                    values=embedded[i].sparse_values,
                ),
            },
            payload={**metadatas[i], "text": chunks[i]},
        )
        for i in range(len(chunks))
    ]

    _get_client().upsert(collection_name=Config.RAG_COLLECTION, points=points)
    return ids


def hybrid_search(
    query: str,
    limit: int = 20,
    query_filter: Optional[models.Filter] = None,
) -> List[RetrievedChunk]:
    """Dense + sparse retrieval fused server-side with RRF."""
    ensure_collection()
    embedded = embed_one(query)

    result = _get_client().query_points(
        collection_name=Config.RAG_COLLECTION,
        prefetch=[
            models.Prefetch(
                query=embedded.dense,
                using="dense",
                limit=limit,
                filter=query_filter,
            ),
            models.Prefetch(
                query=models.SparseVector(
                    indices=embedded.sparse_indices,
                    values=embedded.sparse_values,
                ),
                using="sparse",
                limit=limit,
                filter=query_filter,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=limit,
        with_payload=True,
    )

    out: List[RetrievedChunk] = []
    for point in result.points:
        payload = dict(point.payload or {})
        text = payload.pop("text", "")
        out.append(RetrievedChunk(id=str(point.id), text=text, score=point.score, metadata=payload))
    return out


def delete_by_filter(query_filter: models.Filter) -> None:
    _get_client().delete(
        collection_name=Config.RAG_COLLECTION,
        points_selector=models.FilterSelector(filter=query_filter),
    )
