"""SQLAlchemy ORM models for AgentForge persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class JobRow(Base):
    """Persisted forge/batch/extract job."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    job_type: Mapped[str] = mapped_column(String(20), default="forge")
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    output_format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    identities: Mapped[list[IdentityRow]] = relationship(back_populates="job", cascade="all")

    def __repr__(self) -> str:
        return f"<Job {self.id} [{self.status}] {self.job_type}>"


class IdentityRow(Base):
    """Persisted PersonaNexus identity."""

    __tablename__ = "identities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str | None] = mapped_column(
        String(12), ForeignKey("jobs.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    identity_yaml: Mapped[str] = mapped_column(Text)
    extraction_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    methodology_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="forge")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    job: Mapped[JobRow | None] = relationship(back_populates="identities")

    def __repr__(self) -> str:
        return f"<Identity {self.id[:8]} '{self.name}'>"


class CultureProfileRow(Base):
    """Persisted culture profile."""

    __tablename__ = "culture_profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    profile_json: Mapped[str] = mapped_column(Text)
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    def __repr__(self) -> str:
        return f"<CultureProfile {self.id[:8]} '{self.name}'>"


class ExtractionRow(Base):
    """Persisted extraction result."""

    __tablename__ = "extractions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str | None] = mapped_column(
        String(12), ForeignKey("jobs.id"), nullable=True
    )
    role_title: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(100), default="general")
    extraction_json: Mapped[str] = mapped_column(Text)
    coverage_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    def __repr__(self) -> str:
        return f"<Extraction {self.id[:8]} '{self.role_title}'>"


class BatchRunRow(Base):
    """Persisted batch processing run."""

    __tablename__ = "batch_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str | None] = mapped_column(
        String(12), ForeignKey("jobs.id"), nullable=True
    )
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    results_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    def __repr__(self) -> str:
        return f"<BatchRun {self.id[:8]} {self.completed_count}/{self.file_count}>"
