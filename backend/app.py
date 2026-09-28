import os
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

from config import Config
from services.pdf_extractor import PDFExtractor
from services.llm_analyzer import ClaudeAnalyzer
from services.data_formatter import DataFormatter
from utils.file_handler import FileHandler
from utils.validators import ValidationError
from models.schemas import ProcessingResponse, PatientInfo, LabResult

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Services — instantiated once at startup
pdf_extractor = PDFExtractor()
claude_analyzer = ClaudeAnalyzer()
data_formatter = DataFormatter()
file_handler = FileHandler(Config.UPLOAD_FOLDER)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class TextAnalysisRequest(BaseModel):
    text: str
    tables: Optional[List[Dict[str, Any]]] = []


class APIResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Any] = None
    details: Optional[str] = None


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

def get_services() -> Dict[str, Any]:
    return {
        "pdf_extractor": pdf_extractor,
        "claude_analyzer": claude_analyzer,
        "data_formatter": data_formatter,
        "file_handler": file_handler,
    }


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

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
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"success": False, "error": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {
        "name": "Vitals Lab Report API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health_check():
    api_key_set = bool(Config.ANTHROPIC_API_KEY)
    return {
        "status": "healthy",
        "services": {
            "pdf_extractor": "available",
            "claude_api": "configured" if api_key_set else "missing ANTHROPIC_API_KEY",
            "file_handler": "available",
        },
        "models": {
            "extraction": Config.CLAUDE_EXTRACTION_MODEL,
            "qa": Config.CLAUDE_QA_MODEL,
        },
        "timestamp": datetime.now().isoformat(),
    }


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
        },
    }


@app.post("/api/upload", response_model=APIResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    services=Depends(get_services),
):
    """Upload a lab report PDF and return structured lab data."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    if not file_handler.is_allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    temp_filename = f"{uuid.uuid4().hex}_{file.filename}"
    temp_filepath = os.path.join(Config.UPLOAD_FOLDER, temp_filename)

    try:
        content = await file.read()
        with open(temp_filepath, "wb") as f:
            f.write(content)

        logger.info("Extracting content from %s", file.filename)
        extracted = pdf_extractor.extract_content(temp_filepath)

        if extracted.get("status") == "error":
            raise HTTPException(status_code=400, detail="Failed to extract PDF content")

        logger.info("Analyzing with Claude (%s)", Config.CLAUDE_EXTRACTION_MODEL)
        analyzed = claude_analyzer.analyze_medical_data(extracted)

        formatted = data_formatter.format_for_frontend(analyzed)
        formatted["processing_metadata"] = {
            "filename": file.filename,
            "extraction_metadata": extracted.get("metadata", {}),
            "processing_timestamp": datetime.now().isoformat(),
            "model_used": Config.CLAUDE_EXTRACTION_MODEL,
        }

        logger.info("PDF processed successfully: %s", file.filename)
        return APIResponse(success=True, message="PDF processed successfully", data=formatted)

    finally:
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)


@app.post("/api/analyze", response_model=APIResponse)
async def analyze_text(request: TextAnalysisRequest):
    """Analyze raw text directly (useful for testing without a PDF)."""
    extracted = {
        "text": request.text,
        "tables": request.tables,
        "metadata": {"text_length": len(request.text), "extraction_method": "direct_input"},
        "status": "success",
    }

    analyzed = claude_analyzer.analyze_medical_data(extracted)
    formatted = data_formatter.format_for_frontend(analyzed)

    return APIResponse(success=True, message="Text analyzed successfully", data=formatted)


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


@app.get("/api/models")
async def get_models():
    """Return the Claude models currently configured."""
    return APIResponse(
        success=True,
        data={
            "extraction_model": Config.CLAUDE_EXTRACTION_MODEL,
            "qa_model": Config.CLAUDE_QA_MODEL,
        },
    )


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

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
