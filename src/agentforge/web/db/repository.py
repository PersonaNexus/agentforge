"""Data access layer for AgentForge persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentforge.web.db.models import (
    BatchRunRow,
    CultureProfileRow,
    ExtractionRow,
    IdentityRow,
    JobRow,
)


# ------------------------------------------------------------------
# Job Repository
# ------------------------------------------------------------------


class JobRepository:
    """Data access for jobs."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        job_id: str,
        job_type: str = "forge",
        source_filename: str | None = None,
        mode: str | None = None,
        model: str | None = None,
        output_format: str | None = None,
    ) -> JobRow:
        row = JobRow(
            id=job_id,
            job_type=job_type,
            source_filename=source_filename,
            mode=mode,
            model=model,
            output_format=output_format,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def get(self, job_id: str) -> JobRow | None:
        return self.session.get(JobRow, job_id)

    def update_result(
        self,
        job_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        row = self.session.get(JobRow, job_id)
        if not row:
            return
        row.status = status
        row.result_json = json.dumps(result) if result is not None else None
        row.error = error
        if status in ("done", "error"):
            row.completed_at = datetime.now(timezone.utc)
        self.session.commit()

    def list_all(
        self,
        offset: int = 0,
        limit: int = 50,
        status: str | None = None,
        job_type: str | None = None,
    ) -> list[dict[str, Any]]:
        stmt = select(JobRow).order_by(JobRow.created_at.desc())
        if status:
            stmt = stmt.where(JobRow.status == status)
        if job_type:
            stmt = stmt.where(JobRow.job_type == job_type)
        stmt = stmt.offset(offset).limit(limit)
        rows = self.session.execute(stmt).scalars().all()
        return [
            {
                "id": r.id,
                "status": r.status,
                "job_type": r.job_type,
                "source_filename": r.source_filename,
                "mode": r.mode,
                "model": r.model,
                "output_format": r.output_format,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in rows
        ]

    def get_count(self, status: str | None = None, job_type: str | None = None) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(JobRow)
        if status:
            stmt = stmt.where(JobRow.status == status)
        if job_type:
            stmt = stmt.where(JobRow.job_type == job_type)
        return self.session.execute(stmt).scalar() or 0

    def get_full_result(self, job_id: str) -> dict[str, Any] | None:
        row = self.session.get(JobRow, job_id)
        if not row or not row.result_json:
            return None
        return json.loads(row.result_json)

    def mark_stale_running_as_error(self) -> int:
        """Mark any 'running' jobs as error (server restart recovery)."""
        from sqlalchemy import update

        stmt = (
            update(JobRow)
            .where(JobRow.status == "running")
            .values(
                status="error",
                error="Server restarted during execution",
                completed_at=datetime.now(timezone.utc),
            )
        )
        result = self.session.execute(stmt)
        self.session.commit()
        return result.rowcount


# ------------------------------------------------------------------
# Identity Repository
# ------------------------------------------------------------------


class IdentityRepository:
    """Data access for identities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(
        self,
        name: str,
        identity_yaml: str,
        source: str = "forge",
        job_id: str | None = None,
        extraction_json: dict | None = None,
        methodology_json: dict | None = None,
    ) -> IdentityRow:
        row = IdentityRow(
            name=name,
            identity_yaml=identity_yaml,
            source=source,
            job_id=job_id,
            extraction_json=json.dumps(extraction_json) if extraction_json else None,
            methodology_json=json.dumps(methodology_json) if methodology_json else None,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def get(self, identity_id: str) -> IdentityRow | None:
        return self.session.get(IdentityRow, identity_id)

    def list_all(
        self,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        stmt = select(IdentityRow).order_by(IdentityRow.created_at.desc())
        if search:
            stmt = stmt.where(IdentityRow.name.ilike(f"%{search}%"))
        stmt = stmt.offset(offset).limit(limit)
        rows = self.session.execute(stmt).scalars().all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "source": r.source,
                "job_id": r.job_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def get_full(self, identity_id: str) -> dict[str, Any] | None:
        row = self.session.get(IdentityRow, identity_id)
        if not row:
            return None
        return {
            "id": row.id,
            "name": row.name,
            "source": row.source,
            "job_id": row.job_id,
            "identity_yaml": row.identity_yaml,
            "extraction_json": json.loads(row.extraction_json) if row.extraction_json else None,
            "methodology_json": json.loads(row.methodology_json) if row.methodology_json else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def delete(self, identity_id: str) -> bool:
        row = self.session.get(IdentityRow, identity_id)
        if not row:
            return False
        self.session.delete(row)
        self.session.commit()
        return True


# ------------------------------------------------------------------
# Culture Profile Repository
# ------------------------------------------------------------------


class CultureRepository:
    """Data access for culture profiles."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(
        self,
        name: str,
        profile_json: dict,
        description: str = "",
        source_file: str | None = None,
        is_builtin: bool = False,
    ) -> CultureProfileRow:
        row = CultureProfileRow(
            name=name,
            description=description,
            profile_json=json.dumps(profile_json),
            source_file=source_file,
            is_builtin=is_builtin,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def get(self, profile_id: str) -> dict[str, Any] | None:
        row = self.session.get(CultureProfileRow, profile_id)
        if not row:
            return None
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "profile_json": json.loads(row.profile_json),
            "source_file": row.source_file,
            "is_builtin": row.is_builtin,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def list_all(self) -> list[dict[str, Any]]:
        stmt = select(CultureProfileRow).order_by(CultureProfileRow.created_at.desc())
        rows = self.session.execute(stmt).scalars().all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "source_file": r.source_file,
                "is_builtin": r.is_builtin,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def delete(self, profile_id: str) -> bool:
        row = self.session.get(CultureProfileRow, profile_id)
        if not row:
            return False
        self.session.delete(row)
        self.session.commit()
        return True


# ------------------------------------------------------------------
# Extraction Repository
# ------------------------------------------------------------------


class ExtractionRepository:
    """Data access for extractions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(
        self,
        role_title: str,
        extraction_json: dict,
        domain: str = "general",
        job_id: str | None = None,
        coverage_score: float | None = None,
    ) -> ExtractionRow:
        row = ExtractionRow(
            role_title=role_title,
            domain=domain,
            extraction_json=json.dumps(extraction_json),
            job_id=job_id,
            coverage_score=coverage_score,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def get(self, extraction_id: str) -> dict[str, Any] | None:
        row = self.session.get(ExtractionRow, extraction_id)
        if not row:
            return None
        return {
            "id": row.id,
            "role_title": row.role_title,
            "domain": row.domain,
            "extraction_json": json.loads(row.extraction_json),
            "coverage_score": row.coverage_score,
            "job_id": row.job_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def list_all(
        self, offset: int = 0, limit: int = 50
    ) -> list[dict[str, Any]]:
        stmt = (
            select(ExtractionRow)
            .order_by(ExtractionRow.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = self.session.execute(stmt).scalars().all()
        return [
            {
                "id": r.id,
                "role_title": r.role_title,
                "domain": r.domain,
                "coverage_score": r.coverage_score,
                "job_id": r.job_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


# ------------------------------------------------------------------
# Batch Run Repository
# ------------------------------------------------------------------


class BatchRepository:
    """Data access for batch runs."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(
        self,
        job_id: str,
        file_count: int,
    ) -> BatchRunRow:
        row = BatchRunRow(job_id=job_id, file_count=file_count)
        self.session.add(row)
        self.session.commit()
        return row

    def update_progress(
        self,
        batch_id: str,
        completed_count: int,
        results_json: dict | None = None,
    ) -> None:
        row = self.session.get(BatchRunRow, batch_id)
        if not row:
            return
        row.completed_count = completed_count
        if results_json is not None:
            row.results_json = json.dumps(results_json)
        self.session.commit()

    def get_by_job_id(self, job_id: str) -> dict[str, Any] | None:
        stmt = select(BatchRunRow).where(BatchRunRow.job_id == job_id)
        row = self.session.execute(stmt).scalar_one_or_none()
        if not row:
            return None
        return {
            "id": row.id,
            "job_id": row.job_id,
            "file_count": row.file_count,
            "completed_count": row.completed_count,
            "results_json": json.loads(row.results_json) if row.results_json else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
