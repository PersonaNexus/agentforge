"""Forge API route — async pipeline execution with SSE streaming."""

from __future__ import annotations

import json
import re
import tempfile
import threading
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
    "methodology": "Extracting methodology & decision frameworks...",
    "map": "Mapping personality traits...",
    "culture": "Applying culture profile...",
    "generate": "Generating agent identity...",
    "analyze": "Running gap analysis...",
    "deep_analyze": "Running deep gap analysis...",
    "team_compose": "Composing agent team...",
}


def _get_store(request: Request) -> JobStore:
    return request.app.state.jobs


def _run_forge(
    job: Job,
    file_path: Path,
    mode: str,
    model: str,
    culture_path: Path | None,
    original_filename: str = "",
    trait_overrides: dict[str, float] | None = None,
    user_examples: str = "",
    user_frameworks: str = "",
    output_format: str = "claude_code",
) -> None:
    """Worker thread: runs the forge pipeline and emits SSE events."""
    try:
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
        if trait_overrides:
            context["trait_overrides"] = trait_overrides
        if user_examples:
            context["user_examples"] = user_examples
        if user_frameworks:
            context["user_frameworks"] = user_frameworks
        context["output_format"] = output_format

        context = pipeline.run(context)
        blueprint = pipeline.to_blueprint(context)

        # Derive download name from original uploaded filename
        stem = Path(original_filename).stem if original_filename else ""
        download_stem = re.sub(r'[^\w\-.]', '_', stem)[:100] if stem else ""

        # Build result
        sf = context.get("skill_folder")
        ch = context.get("clawhub_skill")
        result: dict[str, Any] = {
            "blueprint": json.loads(blueprint.model_dump_json()),
            "identity_yaml": context.get("identity_yaml", ""),
            "source_filename": download_stem,
            "traits": context.get("traits"),
            "coverage_score": context.get("coverage_score"),
            "coverage_gaps": context.get("coverage_gaps"),
            "skill_scores": context.get("skill_scores"),
            "skill_folder": {
                "skill_md": sf.skill_md,
                "skill_name": sf.skill_name,
            } if sf else None,
            "clawhub_skill": {
                "skill_md": ch.skill_md,
                "skill_name": ch.skill_name,
            } if ch else None,
        }

        # Include agent team composition
        agent_team = context.get("agent_team")
        if agent_team:
            result["agent_team"] = agent_team.to_dict()

        job.emit_done(result)

    except Exception:
        job.emit_error("Pipeline failed. Check server logs for details.")
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
    culture_file: UploadFile | None = File(None),
    trait_overrides: str = Form(""),
    user_examples: str = Form(""),
    user_frameworks: str = Form(""),
    output_format: str = Form("claude_code"),
) -> dict:
    """Start a forge pipeline job. Returns a job_id for SSE streaming."""
    filename = file.filename or "upload.txt"

    # Parse trait overrides (JSON string of {trait_name: float})
    parsed_traits: dict[str, float] | None = None
    if trait_overrides:
        try:
            raw = json.loads(trait_overrides)
            parsed_traits = {
                k: max(0.0, min(1.0, float(v)))
                for k, v in raw.items()
                if isinstance(k, str) and v is not None
            }
            if not parsed_traits:
                parsed_traits = None
        except (json.JSONDecodeError, TypeError, ValueError):
            parsed_traits = None
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
        args=(job, file_path, mode, model, culture_path, filename, parsed_traits,
              user_examples, user_frameworks, output_format),
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
        sf_data = job.result.get("skill_folder")
        if not sf_data:
            raise HTTPException(status_code=404, detail="No skill available")
        content = sf_data["skill_md"]
        source = job.result.get("source_filename", "")
        safe_name = source or re.sub(r'[^\w\-.]', '_', sf_data["skill_name"])[:100] or "skill"
        filename = f"{safe_name}_SKILL.md"
        media_type = "text/markdown"
    elif file_type == "clawhub":
        ch_data = job.result.get("clawhub_skill")
        if not ch_data:
            raise HTTPException(status_code=404, detail="No ClawHub skill available")
        content = ch_data["skill_md"]
        source = job.result.get("source_filename", "")
        safe_name = source or re.sub(r'[^\w\-.]', '_', ch_data["skill_name"])[:100] or "skill"
        filename = f"{safe_name}_clawhub_SKILL.md"
        media_type = "text/markdown"
    else:
        raise HTTPException(status_code=400, detail="Invalid file type")

    return PlainTextResponse(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
