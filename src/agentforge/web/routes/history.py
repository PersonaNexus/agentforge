"""History API routes — browse past jobs, identities, extractions, and culture profiles."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, Request

router = APIRouter(tags=["history"])

# Validation patterns for path parameters
_HEX_ID_RE = re.compile(r"^[a-f0-9]{8,32}$")
_VALID_STATUSES = {"pending", "running", "done", "error"}
_VALID_JOB_TYPES = {"forge", "import", "batch", "extract"}


def _validate_id(value: str, label: str = "ID") -> str:
    """Validate that a path parameter looks like a hex ID."""
    if not _HEX_ID_RE.match(value):
        raise HTTPException(status_code=422, detail=f"Invalid {label} format")
    return value


def _get_session_factory(request: Request):
    sf = getattr(request.app.state, "db_session_factory", None)
    if not sf:
        raise HTTPException(status_code=503, detail="Database not available")
    return sf


# ------------------------------------------------------------------
# Jobs
# ------------------------------------------------------------------


@router.get("/jobs")
async def list_jobs(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    job_type: str | None = Query(None),
) -> dict[str, Any]:
    """List all jobs with pagination and optional filtering."""
    if status and status not in _VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status: {status}")
    if job_type and job_type not in _VALID_JOB_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid job_type: {job_type}")

    from agentforge.web.db.repository import JobRepository

    sf = _get_session_factory(request)
    offset = (page - 1) * per_page

    with sf() as session:
        repo = JobRepository(session)
        jobs = repo.list_all(
            offset=offset,
            limit=per_page,
            status=status,
            job_type=job_type,
        )
        total = repo.get_count(status=status, job_type=job_type)

    return {
        "jobs": jobs,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict[str, Any]:
    """Get full job detail including result."""
    _validate_id(job_id, "job_id")
    from agentforge.web.db.repository import JobRepository

    sf = _get_session_factory(request)
    with sf() as session:
        repo = JobRepository(session)
        row = repo.get(job_id)
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")

        result = None
        if row.result_json:
            result = json.loads(row.result_json)
            # Strip internal refine context from API response
            result.pop("_refine_context", None)

        return {
            "id": row.id,
            "status": row.status,
            "job_type": row.job_type,
            "source_filename": row.source_filename,
            "mode": row.mode,
            "model": row.model,
            "output_format": row.output_format,
            "error": row.error,
            "result": result,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }


@router.get("/jobs/{job_id}/reload")
async def reload_job(job_id: str, request: Request) -> dict[str, Any]:
    """Reload a past job into memory for downloading or continued refinement."""
    _validate_id(job_id, "job_id")
    store = request.app.state.jobs
    job = store.get(job_id)
    if not job or not job.result:
        raise HTTPException(status_code=404, detail="Job not found or has no result")

    return {
        "job_id": job.id,
        "status": job.status,
        "message": "Job loaded into memory — downloads and refinement are available",
    }


# ------------------------------------------------------------------
# Identities
# ------------------------------------------------------------------


@router.get("/identities")
async def list_identities(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=200),
) -> dict[str, Any]:
    """List all saved identities with optional search."""
    from agentforge.web.db.repository import IdentityRepository

    sf = _get_session_factory(request)
    offset = (page - 1) * per_page

    with sf() as session:
        repo = IdentityRepository(session)
        identities = repo.list_all(offset=offset, limit=per_page, search=search)

    return {
        "identities": identities,
        "page": page,
        "per_page": per_page,
    }


@router.get("/identities/{identity_id}")
async def get_identity(identity_id: str, request: Request) -> dict[str, Any]:
    """Get full identity detail."""
    _validate_id(identity_id, "identity_id")
    from agentforge.web.db.repository import IdentityRepository

    sf = _get_session_factory(request)
    with sf() as session:
        repo = IdentityRepository(session)
        result = repo.get_full(identity_id)
        if not result:
            raise HTTPException(status_code=404, detail="Identity not found")
        return result


@router.delete("/identities/{identity_id}")
async def delete_identity(identity_id: str, request: Request) -> dict[str, str]:
    """Delete a saved identity."""
    _validate_id(identity_id, "identity_id")
    from agentforge.web.db.repository import IdentityRepository

    sf = _get_session_factory(request)
    with sf() as session:
        repo = IdentityRepository(session)
        if not repo.delete(identity_id):
            raise HTTPException(status_code=404, detail="Identity not found")
        return {"status": "deleted"}


# ------------------------------------------------------------------
# Extractions
# ------------------------------------------------------------------


@router.get("/extractions")
async def list_extractions(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """List all saved extractions."""
    from agentforge.web.db.repository import ExtractionRepository

    sf = _get_session_factory(request)
    offset = (page - 1) * per_page

    with sf() as session:
        repo = ExtractionRepository(session)
        extractions = repo.list_all(offset=offset, limit=per_page)

    return {
        "extractions": extractions,
        "page": page,
        "per_page": per_page,
    }


@router.get("/extractions/{extraction_id}")
async def get_extraction(extraction_id: str, request: Request) -> dict[str, Any]:
    """Get full extraction detail."""
    _validate_id(extraction_id, "extraction_id")
    from agentforge.web.db.repository import ExtractionRepository

    sf = _get_session_factory(request)
    with sf() as session:
        repo = ExtractionRepository(session)
        result = repo.get(extraction_id)
        if not result:
            raise HTTPException(status_code=404, detail="Extraction not found")
        return result


# ------------------------------------------------------------------
# Culture Profiles
# ------------------------------------------------------------------


@router.get("/culture-profiles")
async def list_culture_profiles(request: Request) -> dict[str, Any]:
    """List all saved culture profiles."""
    from agentforge.web.db.repository import CultureRepository

    sf = _get_session_factory(request)
    with sf() as session:
        repo = CultureRepository(session)
        profiles = repo.list_all()

    return {"profiles": profiles}


@router.delete("/culture-profiles/{profile_id}")
async def delete_culture_profile(
    profile_id: str, request: Request
) -> dict[str, str]:
    """Delete a saved culture profile."""
    _validate_id(profile_id, "profile_id")
    from agentforge.web.db.repository import CultureRepository

    sf = _get_session_factory(request)
    with sf() as session:
        repo = CultureRepository(session)
        if not repo.delete(profile_id):
            raise HTTPException(status_code=404, detail="Culture profile not found")
        return {"status": "deleted"}
