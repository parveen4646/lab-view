from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from db.database import get_db
from db.models import User, Report, LabResult

router = APIRouter(prefix="/api/reports", tags=["reports"])


class ReportSummary(BaseModel):
    id: str
    filename: str
    upload_at: str
    extraction_quality: str | None
    completeness_score: float | None
    plausibility_score: float | None
    tests_count: int

    model_config = {"from_attributes": True}


@router.get("/", summary="List all reports for the authenticated user")
def list_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reports = (
        db.query(Report)
        .filter(Report.user_id == current_user.id)
        .order_by(Report.upload_at.desc())
        .all()
    )
    result = []
    for r in reports:
        result.append({
            "id": r.id,
            "filename": r.filename,
            "upload_at": r.upload_at.isoformat(),
            "extraction_quality": r.extraction_quality,
            "completeness_score": r.completeness_score,
            "plausibility_score": r.plausibility_score,
            "tests_count": len(r.lab_results),
        })
    return {"success": True, "data": result, "total": len(result)}


@router.get("/{report_id}", summary="Get a single report with lab results")
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = (
        db.query(Report)
        .filter(Report.id == report_id, Report.user_id == current_user.id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return {
        "success": True,
        "data": {
            "id": report.id,
            "filename": report.filename,
            "upload_at": report.upload_at.isoformat(),
            "extraction_quality": report.extraction_quality,
            "completeness_score": report.completeness_score,
            "plausibility_score": report.plausibility_score,
            "guardrail_drops": report.guardrail_drops,
            "model_used": report.model_used,
            "formatted_data": report.raw_data,
            "lab_results": [
                {
                    "id": lr.id,
                    "test_name": lr.test_name,
                    "value": lr.value,
                    "unit": lr.unit,
                    "ref_min": lr.ref_min,
                    "ref_max": lr.ref_max,
                    "status": lr.status,
                    "category": lr.category,
                    "test_date": lr.test_date,
                }
                for lr in report.lab_results
            ],
        },
    }


@router.delete("/{report_id}", status_code=204)
def delete_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = (
        db.query(Report)
        .filter(Report.id == report_id, Report.user_id == current_user.id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    db.delete(report)
    db.commit()
