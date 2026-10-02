import os
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
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
from db.database import get_db, init_db
from db.models import Report, LabResult
from routers import auth as auth_router
from routers import reports as reports_router
from routers import analytics as analytics_router
from routers import qa as qa_router

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

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router.router)
app.include_router(reports_router.router)
app.include_router(analytics_router.router)
app.include_router(qa_router.router)

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


# ── DB persistence helper ─────────────────────────────────────────────────────

def _save_report_to_db(*, db, user_id, filename, eval_result, drop_count, model_used, formatted, analyzed, raw_text=""):
    try:
        report = Report(
            user_id=user_id,
            filename=filename,
            model_used=model_used,
            extraction_quality=eval_result.overall_quality,
            completeness_score=eval_result.completeness_score,
            plausibility_score=eval_result.plausibility_score,
            guardrail_drops=drop_count,
            raw_data=formatted,
            raw_text=raw_text,
        )
        db.add(report)
        db.flush()  # get report.id before committing

        if raw_text:
            _index_report_for_rag(report.id, filename, raw_text)

        for r in analyzed.get("latestResults", []):
            ref = r.get("referenceRange") or {}
            db.add(LabResult(
                report_id=report.id,
                test_name=r.get("testName", "unknown"),
                value=r.get("value"),
                unit=r.get("unit"),
                ref_min=ref.get("min"),
                ref_max=ref.get("max"),
                status=r.get("status"),
                category=r.get("category"),
                canonical_name=r.get("canonicalName"),
                test_date=r.get("date"),
            ))

        db.commit()
        logger.info("Report %s saved for user %s", report.id, user_id)
    except Exception as exc:
        db.rollback()
        logger.warning("DB save failed (non-fatal): %s", exc)


def _index_report_for_rag(report_id: str, filename: str, raw_text: str) -> None:
    """Chunk + embed + upsert this report's free text for the Q&A RAG pipeline. Non-fatal on failure."""
    try:
        from services.rag.chunker import chunk_text
        from services.rag.vector_store import upsert_chunks

        pieces = chunk_text(raw_text, chunk_tokens=400, overlap_tokens=60)
        if not pieces:
            return
        chunks = [p.text for p in pieces]
        metadatas = [
            {"corpus": "report", "source": filename, "report_id": report_id, "chunk_index": p.index}
            for p in pieces
        ]
        upsert_chunks(chunks, metadatas)
        logger.info("Indexed %d chunks for report %s into RAG store", len(chunks), report_id)
    except Exception as exc:
        logger.warning("RAG indexing failed (non-fatal): %s", exc)


# ── PDF upload ────────────────────────────────────────────────────────────────

_optional_bearer = HTTPBearer(auto_error=False)


def _optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    db=Depends(get_db),
):
    """Returns (user, db) when a valid JWT is present, else (None, db)."""
    if not credentials:
        return None, db
    try:
        from auth.dependencies import _resolve_user
        user = _resolve_user(credentials.credentials, db)
        return user, db
    except Exception:
        return None, db


@app.post("/api/upload", response_model=APIResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    user_db=Depends(_optional_user),
):
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

        # 4. LLM analysis
        analysis = claude_analyzer.analyze_medical_data(extracted)
        analyzed = analysis.data
        logger.info("Analysed with %s", analysis.provider)

        # 5. OUTPUT GUARDRAILS — clean and validate the LLM's output
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
            "model_used": analysis.provider,
            "input_truncated": analysis.input_truncated,
            "evaluation": eval_result.as_dict(),
            "guardrail_issues": guardrail_issues,
            "guardrail_drops": drop_count,
        }

        # 9. Persist to DB if user is authenticated
        current_user, db = user_db
        if current_user is not None:
            _save_report_to_db(
                db=db,
                user_id=current_user.id,
                filename=file.filename,
                eval_result=eval_result,
                drop_count=drop_count,
                model_used=analysis.provider,
                formatted=formatted,
                analyzed=analyzed,
                raw_text=extracted.get("text", ""),
            )

        logger.info("Done: %s", file.filename)
        return APIResponse(success=True, message="PDF processed successfully", data=formatted)

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            logger.info("Removed temp file: %s", temp_path)


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
    analysis = claude_analyzer.analyze_medical_data(extracted)
    analyzed, guardrail_issues, drop_count = output_guardrails.validate_and_clean(analysis.data)
    eval_result = evaluator.evaluate(analyzed)

    metrics_store.record_extraction(
        tests_extracted=eval_result.tests_extracted,
        quality=eval_result.overall_quality,
        guardrail_drops=drop_count,
    )

    formatted = data_formatter.format_for_frontend(analyzed)
    formatted["processing_metadata"] = {
        "model_used": analysis.provider,
        "input_truncated": analysis.input_truncated,
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
    logger.info("Database         : %s", Config.DATABASE_URL.split("://")[0])
    if not Config.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY is not set — PDF analysis will fail")
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    init_db()
    logger.info("Database tables ready")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Vitals Lab Report API")


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
