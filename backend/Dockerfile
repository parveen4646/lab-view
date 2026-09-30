FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch — the default PyPI wheel pulls multi-GB CUDA builds Cloud Run never uses.
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Bake the RAG models into the image at build time. Without this, every cold
# start (Cloud Run scales to zero) re-downloads ~4-5GB from Hugging Face.
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "\
from FlagEmbedding import BGEM3FlagModel, FlagReranker; \
BGEM3FlagModel('BAAI/bge-m3', use_fp16=False); \
FlagReranker('BAAI/bge-reranker-v2-m3', use_fp16=False)"

COPY . .

RUN mkdir -p uploads

# Cloud Run injects $PORT (default 8080) and expects the container to listen on it.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
