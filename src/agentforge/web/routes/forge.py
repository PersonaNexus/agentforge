"""Forge API route — async pipeline execution with SSE streaming."""

from __future__ import annotations

import io
import json
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse

from agentforge.web.jobs import Job, JobStore

router = APIRouter(tags=["forge"])

_ALLOWED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".docx"}

_STAGE_MESSAGES = {
    "ingest": "Parsing file...",
    "extract": "Extracting skills via LLM...",
    "map": "Mapping personality traits...",
    "culture": "Applying culture profile...",
    "generate": "Generating agent identity...",
    "analyze": "Running gap analysis...",
    "deep_analyze": "Running deep gap analysis...",
}


def _get_store(request: Request) -> JobStore:
    return request.app.state.jobs


def _run_forge(
    job: Job,
    file_path: Path,
    mode: str,
    model: str,
    culture_path: Path | None,
    no_skill_file: bool,
) -> None:
    """Worker thread: runs the forge pipeline and emits SSE events."""
    try:
        from agentforge.cli import _ingest_file
        from agentforge.llm.client import LLMClient
        from agentforge.pipeline.forge_pipeline import ForgePipeline

        job.status = "running"

        # Build pipeline
        if mode == "quick":
            pipeline = ForgePipeline.quick()
        elif mode == "deep":
            pipeline = ForgePipeline.deep_analysis()
        else:
            pipeline = ForgePipeline.default()

        # Emit stage events by wrapping each stage's run method
        original_stages = list(pipeline.stages)
        for stage in original_stages:
            original_run = stage.run

            def _wrapped_run(ctx: dict, _stage=stage, _orig=original_run) -> dict:
                msg = _STAGE_MESSAGES.get(_stage.name, f"Running {_stage.name}...")
                job.emit_stage(_stage.name, msg)
                return _orig(ctx)

            stage.run = _wrapped_run  # type: ignore[assignment]

        # Build context
        client = LLMClient(model=model)
        context: dict[str, Any] = {
            "input_path": str(file_path),
            "llm_client": client,
        }
        if culture_path:
            context["culture_path"] = str(culture_path)

        context = pipeline.run(context)
        blueprint = pipeline.to_blueprint(context)

        # Build result
        result: dict[str, Any] = {
            "blueprint": json.loads(blueprint.model_dump_json()),
            "identity_yaml": context.get("identity_yaml", ""),
            "skill_file": context.get("skill_file", "") if not no_skill_file else "",
            "traits": context.get("traits"),
            "coverage_score": context.get("coverage_score"),
            "coverage_gaps": context.get("coverage_gaps"),
            "skill_scores": context.get("skill_scores"),
        }

        # Include skill folder data for download
        if not no_skill_file and "skill_folder" in context:
            sf = context["skill_folder"]
            result["skill_folder"] = {
                "skill_md": sf.skill_md,
                "skill_name": sf.skill_name,
            }

        job.emit_done(result)

    except Exception as e:
        job.emit_error(str(e))
    finally:
        file_path.unlink(missing_ok=True)
        if culture_path:
            culture_path.unlink(missing_ok=True)


@router.post("/forge", status_code=202)
async def start_forge(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("default"),
    model: str = Form("claude-sonnet-4-20250514"),
    no_skill_file: bool = Form(False),
    culture_file: UploadFile | None = File(None),
) -> dict:
    """Start a forge pipeline job. Returns a job_id for SSE streaming."""
    filename = file.filename or "upload.txt"
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"Unsupported file type: {suffix}")

    if mode not in ("default", "quick", "deep"):
        raise HTTPException(status_code=422, detail=f"Invalid mode: {mode}")

    # Save uploaded file
    content = await file.read()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(content)
    tmp.close()
    file_path = Path(tmp.name)

    # Save culture file if provided
    culture_path: Path | None = None
    if culture_file and culture_file.filename:
        culture_content = await culture_file.read()
        culture_suffix = Path(culture_file.filename).suffix.lower()
        ctmp = tempfile.NamedTemporaryFile(delete=False, suffix=culture_suffix)
        ctmp.write(culture_content)
        ctmp.close()
        culture_path = Path(ctmp.name)

    store = _get_store(request)
    job = store.create()

    thread = threading.Thread(
        target=_run_forge,
        args=(job, file_path, mode, model, culture_path, no_skill_file),
        daemon=True,
    )
    thread.start()

    return {"job_id": job.id}


@router.get("/forge/{job_id}/stream")
async def forge_stream(job_id: str, request: Request) -> StreamingResponse:
    """Stream SSE events for a forge job."""
    store = _get_store(request)
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    def _generate():
        import queue as q

        while True:
            try:
                event_data = job.events.get(timeout=1)
                yield f"data: {event_data}\n\n"
                parsed = json.loads(event_data)
                if parsed.get("event") in ("done", "error"):
                    break
            except q.Empty:
                # Send keepalive
                yield ": keepalive\n\n"
                if job.status in ("done", "error"):
                    break

    return StreamingResponse(_generate(), media_type="text/event-stream")


@router.get("/forge/{job_id}/download/{file_type}")
async def forge_download(job_id: str, file_type: str, request: Request):
    """Download a generated file from a completed forge job."""
    store = _get_store(request)
    job = store.get(job_id)
    if not job or not job.result:
        raise HTTPException(status_code=404, detail="Job not found or not complete")

    if file_type == "yaml":
        content = job.result.get("identity_yaml", "")
        filename = "agent_identity.yaml"
        media_type = "text/yaml"
    elif file_type == "skill":
        content = job.result.get("skill_file", "")
        filename = "SKILL.md"
        media_type = "text/markdown"
    elif file_type == "skill-folder":
        sf_data = job.result.get("skill_folder")
        if not sf_data:
            raise HTTPException(status_code=404, detail="No skill folder available")

        buffer = io.BytesIO()
        skill_name = sf_data["skill_name"]
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{skill_name}/SKILL.md", sf_data["skill_md"])
        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{skill_name}_skill.zip"'},
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid file type")

    return PlainTextResponse(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
