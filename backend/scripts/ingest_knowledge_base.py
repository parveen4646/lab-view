"""
One-off ingestion: chunk + embed + upsert the curated medical knowledge base
into Qdrant.

Run from backend/:
    python -m scripts.ingest_knowledge_base
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.rag.chunker import chunk_text
from services.rag.knowledge_base import KNOWLEDGE_BASE
from services.rag.vector_store import upsert_chunks

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    all_chunks: list[str] = []
    all_metadata: list[dict] = []

    for doc in KNOWLEDGE_BASE:
        pieces = chunk_text(doc["text"], chunk_tokens=400, overlap_tokens=60)
        for piece in pieces:
            all_chunks.append(piece.text)
            all_metadata.append(
                {
                    "corpus": "medical_reference",
                    "source": doc["title"],
                    "biomarker_id": doc["id"],
                    "chunk_index": piece.index,
                }
            )

    logger.info("Embedding + upserting %d chunks from %d documents", len(all_chunks), len(KNOWLEDGE_BASE))
    ids = upsert_chunks(all_chunks, all_metadata)
    logger.info("Done — %d points upserted into Qdrant", len(ids))


if __name__ == "__main__":
    main()
