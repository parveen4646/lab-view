import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Boolean, DateTime, Float, Integer, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    reports: Mapped[list["Report"]] = relationship("Report", back_populates="user", cascade="all, delete-orphan")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    upload_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    model_used: Mapped[Optional[str]] = mapped_column(String(100))
    extraction_quality: Mapped[Optional[str]] = mapped_column(String(20))
    completeness_score: Mapped[Optional[float]] = mapped_column(Float)
    plausibility_score: Mapped[Optional[float]] = mapped_column(Float)
    guardrail_drops: Mapped[int] = mapped_column(Integer, default=0)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON)
    raw_text: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped["User"] = relationship("User", back_populates="reports")
    lab_results: Mapped[list["LabResult"]] = relationship(
        "LabResult", back_populates="report", cascade="all, delete-orphan"
    )


class LabResult(Base):
    __tablename__ = "lab_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    report_id: Mapped[str] = mapped_column(String(36), ForeignKey("reports.id"), nullable=False, index=True)
    test_name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Float)
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    ref_min: Mapped[Optional[float]] = mapped_column(Float)
    ref_max: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[Optional[str]] = mapped_column(String(20))
    category: Mapped[Optional[str]] = mapped_column(String(50))
    test_date: Mapped[Optional[str]] = mapped_column(String(20))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    report: Mapped["Report"] = relationship("Report", back_populates="lab_results")
