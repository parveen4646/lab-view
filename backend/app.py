import os
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
import uvicorn

from config import Config
from middleware.monitoring import MonitoringMiddleware
from services.pdf_extractor import PDFExtractor
from services.llm_analyzer import ClaudeAnalyzer
from services.data_formatter import DataFormatter
from services.evaluator import evaluator
from services.guardrails import input_guardrails, output_guardrails
from utils.file_handler import FileHandler
from utils.metrics import metrics_store
from utils.validators import ValidationError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Vitals — Lab Report API",
    description="Extract and structure medical lab data from PDFs using Claude AI",
    version="2.0.0",
)

# ── Middleware (order matters: CORS first, then monitoring) ───────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(MonitoringMiddleware)

# ── Services ──────────────────────────────────────────────────────────────────
pdf_extractor = PDFExtractor()
claude_analyzer = ClaudeAnalyzer()
data_formatter = DataFormatter()
file_handler = FileHandler(Config.UPLOAD_FOLDER)


# ── Request / response models ─────────────────────────────────────────────────

class TextAnalysisRequest(BaseModel):
    text: str
    tables: Optional[List[Dict[str, Any]]] = []


class APIResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Any] = None


def get_services() -> Dict[str, Any]:
    return {
        "pdf_extractor": pdf_extractor,
        "claude_analyzer": claude_analyzer,
        "data_formatter": data_formatter,
        "file_handler": file_handler,
    }


# ── Exception handlers ────────────────────────────────────────────────────────

@app.exception_handler(ValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"success": False, "error": str(exc)},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"},
    )


# ── Core endpoints ────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "name": "Vitals Lab Report API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
        "stats": "/api/stats",
        "metrics": "/metrics",
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "services": {
            "pdf_extractor": "available",
            "claude_api": "configured" if Config.ANTHROPIC_API_KEY else "missing ANTHROPIC_API_KEY",
            "guardrails": "active",
            "evaluator": "active",
            "monitoring": "active",
        },
        "models": {
            "extraction": Config.CLAUDE_EXTRACTION_MODEL,
            "qa": Config.CLAUDE_QA_MODEL,
        },
        "timestamp": datetime.now().isoformat(),
    }


# ── Monitoring endpoints ──────────────────────────────────────────────────────

@app.get("/api/stats", summary="API + extraction stats (JSON)")
async def api_stats():
    """Human-readable JSON stats: request counts, error rates, latency percentiles,
    extraction quality distribution, guardrail drop counts."""
    return metrics_store.to_json()


@app.get("/metrics", response_class=PlainTextResponse, summary="Prometheus metrics")
async def prometheus_metrics():
    """Prometheus text exposition format — scrape with Datadog agent or Prometheus."""
    return PlainTextResponse(
        content=metrics_store.to_prometheus(),
        media_type="text/plain; version=0.0.4",
    )


@app.get("/api/status")
async def get_status():
    return {
        "success": True,
        "status": {
            "pdf_extractor": "operational",
            "claude_api": "configured" if Config.ANTHROPIC_API_KEY else "missing key",
            "extraction_model": Config.CLAUDE_EXTRACTION_MODEL,
            "qa_model": Config.CLAUDE_QA_MODEL,
            "upload_folder": Config.UPLOAD_FOLDER,
            "max_file_size_mb": Config.MAX_CONTENT_LENGTH // (1024 * 1024),
            "guardrails": "active",
            "evaluator": "active",
        },
    }


@app.get("/api/models")
async def get_models():
    return APIResponse(
        success=True,
        data={
            "extraction_model": Config.CLAUDE_EXTRACTION_MODEL,
            "qa_model": Config.CLAUDE_QA_MODEL,
        },
    )


# ── PDF upload ────────────────────────────────────────────────────────────────

@app.post("/api/upload", response_model=APIResponse)
async def upload_pdf(file: UploadFile = File(...)):
    """
    Full pipeline:
      PDF → extract text → INPUT GUARDRAILS → Claude → OUTPUT GUARDRAILS
      → EVALUATE → format → return
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    if not file_handler.is_allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    temp_path = os.path.join(Config.UPLOAD_FOLDER, f"{uuid.uuid4().hex}_{file.filename}")
    try:
        # 1. Save to disk
        content = await file.read()
        with open(temp_path, "wb") as f:
            f.write(content)

        # 2. Extract text
        logger.info("Extracting: %s", file.filename)
        extracted = pdf_extractor.extract_content(temp_path)
        if extracted.get("status") == "error":
            raise HTTPException(status_code=400, detail="Failed to extract PDF content")

        # 3. INPUT GUARDRAILS — validate the raw text before hitting Claude
        input_guardrails.validate_pdf_content(extracted)

        # 4. Claude analysis
        logger.info("Analysing with %s", Config.CLAUDE_EXTRACTION_MODEL)
        analyzed = claude_analyzer.analyze_medical_data(extracted)

        # 5. OUTPUT GUARDRAILS — clean and validate Claude's output
        analyzed, guardrail_issues, drop_count = output_guardrails.validate_and_clean(analyzed)
        if guardrail_issues:
            logger.warning(
                "%d guardrail correction(s) for %s: %s",
                len(guardrail_issues), file.filename, guardrail_issues,
            )

        # 6. EVALUATE — score the extraction quality
        eval_result = evaluator.evaluate(analyzed)
        logger.info(
            "Evaluation — quality=%s completeness=%.2f plausibility=%.2f tests=%d",
            eval_result.overall_quality,
            eval_result.completeness_score,
            eval_result.plausibility_score,
            eval_result.tests_extracted,
        )

        # 7. Record to metrics
        metrics_store.record_extraction(
            tests_extracted=eval_result.tests_extracted,
            quality=eval_result.overall_quality,
            guardrail_drops=drop_count,
            failed=eval_result.overall_quality == "failed",
        )

        # 8. Format for frontend
        formatted = data_formatter.format_for_frontend(analyzed)
        formatted["processing_metadata"] = {
            "filename": file.filename,
            "extraction_metadata": extracted.get("metadata", {}),
            "processing_timestamp": datetime.now().isoformat(),
            "model_used": Config.CLAUDE_EXTRACTION_MODEL,
            "evaluation": eval_result.as_dict(),
            "guardrail_issues": guardrail_issues,
            "guardrail_drops": drop_count,
        }

        logger.info("Done: %s", file.filename)
        return APIResponse(success=True, message="PDF processed successfully", data=formatted)

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ── Text analysis (testing / debugging) ──────────────────────────────────────

@app.post("/api/analyze", response_model=APIResponse)
async def analyze_text(request: TextAnalysisRequest):
    """Analyze raw text directly — useful for testing without a PDF."""
    extracted = {
        "text": request.text,
        "tables": request.tables,
        "metadata": {"text_length": len(request.text), "extraction_method": "direct_input"},
        "status": "success",
    }

    # Still run guardrails so the path is exercised the same way
    input_guardrails.validate_pdf_content(extracted)
    analyzed = claude_analyzer.analyze_medical_data(extracted)
    analyzed, guardrail_issues, drop_count = output_guardrails.validate_and_clean(analyzed)
    eval_result = evaluator.evaluate(analyzed)

    metrics_store.record_extraction(
        tests_extracted=eval_result.tests_extracted,
        quality=eval_result.overall_quality,
        guardrail_drops=drop_count,
    )

    formatted = data_formatter.format_for_frontend(analyzed)
    formatted["processing_metadata"] = {
        "evaluation": eval_result.as_dict(),
        "guardrail_issues": guardrail_issues,
        "guardrail_drops": drop_count,
    }

    return APIResponse(success=True, message="Text analyzed successfully", data=formatted)


# ── Patient stub ──────────────────────────────────────────────────────────────

@app.get("/api/patient/{patient_id}", response_model=APIResponse)
async def get_patient_data(patient_id: str):
    """Stub — returns mock data. Replace with a real DB lookup in Phase 2."""
    mock_data = {
        "patientInfo": {
            "id": patient_id,
            "name": "Demo Patient",
            "age": 40,
            "gender": "unknown",
            "dateOfBirth": None,
            "lastTestDate": datetime.now().strftime("%Y-%m-%d"),
        },
        "latestResults": [],
        "testCategories": data_formatter.default_categories,
        "trendData": {},
    }
    return APIResponse(success=True, data=mock_data)


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    logger.info("Starting Vitals Lab Report API v2.0")
    logger.info("Extraction model : %s", Config.CLAUDE_EXTRACTION_MODEL)
    logger.info("Q&A model        : %s", Config.CLAUDE_QA_MODEL)
    logger.info("Upload folder    : %s", Config.UPLOAD_FOLDER)
    if not Config.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY is not set — PDF analysis will fail")
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Vitals Lab Report API")


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
