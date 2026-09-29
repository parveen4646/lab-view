"""
BGE-M3 embeddings — a single self-hosted model producing both the dense
vector and the sparse (lexical) vector each chunk needs for hybrid search.

Loaded lazily and cached: the ~2.2GB model is pulled from Hugging Face on
first use and then cached under ~/.cache/huggingface.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import List

logger = logging.getLogger(__name__)

_MODEL_NAME = "BAAI/bge-m3"


@dataclass
class EmbeddedChunk:
    dense: List[float]
    sparse_indices: List[int]
    sparse_values: List[float]


@lru_cache(maxsize=1)
def _get_model():
    from FlagEmbedding import BGEM3FlagModel

    logger.info("Loading BGE-M3 (first call downloads the model — this can take a while)")
    return BGEM3FlagModel(_MODEL_NAME, use_fp16=False)


def embed(texts: List[str]) -> List[EmbeddedChunk]:
    """Embed a batch of texts, returning dense + sparse vectors for each."""
    if not texts:
        return []

    model = _get_model()
    result = model.encode(
        texts,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )

    dense_vecs = result["dense_vecs"]
    lexical_weights = result["lexical_weights"]

    out: List[EmbeddedChunk] = []
    for dense, weights in zip(dense_vecs, lexical_weights):
        indices = [int(tok_id) for tok_id in weights.keys()]
        values = [float(w) for w in weights.values()]
        out.append(EmbeddedChunk(dense=dense.tolist(), sparse_indices=indices, sparse_values=values))
    return out


def embed_one(text: str) -> EmbeddedChunk:
    return embed([text])[0]


DENSE_DIM = 1024  # BGE-M3's fixed dense output dimension
