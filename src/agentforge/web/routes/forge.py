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

from agentforge.utils import safe_filename
from agentforge.web.jobs import Job, JobStore

router = APIRouter(tags=["forge"])

_ALLOWED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".docx"}

_STAGE_MESSAGES = {
    "ingest": "Parsing file...",
    "anonymize": "Anonymizing company names...",
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
    anonymize: bool = False,
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
        if anonymize:
            context["anonymize"] = True

        context = pipeline.run(context)
        blueprint = pipeline.to_blueprint(context)

        # Derive download name from original uploaded filename
        stem = Path(original_filename).stem if original_filename else ""
        download_stem = safe_filename(stem)[:100] if stem else ""

        # Run skill quality review
        from agentforge.analysis.skill_reviewer import SkillReviewer

        reviewer = SkillReviewer()
        extraction = context.get("extraction")
        methodology = context.get("methodology")
        skill_gaps = reviewer.review_to_dict(
            extraction,
            methodology=methodology,
            has_examples=bool(user_examples),
            has_frameworks=bool(user_frameworks),
        ) if extraction else []

        # Build result
        sf = context.get("skill_folder")
        ch = context.get("clawhub_skill")
        result: dict[str, Any] = {
            "blueprint": blueprint.model_dump(mode="json"),
            "identity_yaml": context.get("identity_yaml", ""),
            "source_filename": download_stem,
            "traits": context.get("traits"),
            "coverage_score": context.get("coverage_score"),
            "coverage_gaps": context.get("coverage_gaps"),
            "skill_scores": context.get("skill_scores"),
            "skill_folder": {
                "skill_md": sf.skill_md,
                "skill_name": sf.skill_name,
                "supplementary_files": dict(sf.supplementary_files),
            } if sf else None,
            "clawhub_skill": {
                "skill_md": ch.skill_md,
                "skill_name": ch.skill_name,
            } if ch else None,
            "skill_gaps": skill_gaps,
        }

        # Store pipeline context for refinement (serializable copies)
        result["_refine_context"] = {
            "extraction": extraction.model_dump(mode="json") if extraction else None,
            "methodology": methodology.model_dump(mode="json") if methodology else None,
            "identity_yaml": context.get("identity_yaml", ""),
            "output_format": context.get("output_format", "claude_code"),
            "user_examples": user_examples,
            "user_frameworks": user_frameworks,
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
    anonymize: str = Form(""),
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

    if output_format not in ("claude_code", "clawhub", "both"):
        raise HTTPException(status_code=422, detail=f"Invalid output_format: {output_format}")

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

    do_anonymize = anonymize.lower() in ("true", "1", "on", "yes")

    thread = threading.Thread(
        target=_run_forge,
        args=(job, file_path, mode, model, culture_path, filename, parsed_traits,
              user_examples, user_frameworks, output_format, do_anonymize),
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
        safe_name = source or safe_filename(sf_data["skill_name"])[:100] or "skill"
        filename = f"{safe_name}_SKILL.md"
        media_type = "text/markdown"
    elif file_type == "clawhub":
        ch_data = job.result.get("clawhub_skill")
        if not ch_data:
            raise HTTPException(status_code=404, detail="No ClawHub skill available")
        content = ch_data["skill_md"]
        source = job.result.get("source_filename", "")
        safe_name = source or safe_filename(ch_data["skill_name"])[:100] or "skill"
        filename = f"{safe_name}_clawhub_SKILL.md"
        media_type = "text/markdown"
    else:
        raise HTTPException(status_code=400, detail="Invalid file type")

    return PlainTextResponse(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/forge/{job_id}/download/zip")
async def forge_download_zip(job_id: str, request: Request) -> StreamingResponse:
    """Download the skill folder as a ZIP with SKILL.md + reference files."""
    store = _get_store(request)
    job = store.get(job_id)
    if not job or not job.result:
        raise HTTPException(status_code=404, detail="Job not found or not complete")

    sf_data = job.result.get("skill_folder")
    if not sf_data:
        raise HTTPException(status_code=404, detail="No skill folder available")

    skill_name = sf_data.get("skill_name", "skill")
    source = job.result.get("source_filename", "")
    zip_name = source or safe_filename(skill_name)[:100] or "skill"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Main SKILL.md
        zf.writestr(f"{skill_name}/SKILL.md", sf_data["skill_md"])

        # Supplementary reference files
        for rel_path, content in sf_data.get("supplementary_files", {}).items():
            zf.writestr(f"{skill_name}/{rel_path}", content)

        # ClawHub skill if available
        ch_data = job.result.get("clawhub_skill")
        if ch_data:
            zf.writestr(f"{skill_name}/CLAWHUB_SKILL.md", ch_data["skill_md"])

        # Identity YAML
        identity_yaml = job.result.get("identity_yaml", "")
        if identity_yaml:
            zf.writestr(f"{skill_name}/agent_identity.yaml", identity_yaml)

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_name}_skill.zip"'
        },
    )


@router.post("/forge/{job_id}/refine")
async def refine_skill(job_id: str, request: Request) -> dict:
    """Refine a generated skill by merging user edits into gap areas.

    Accepts either:
    - JSON body: {"edits": {"category": "user text", ...}}
    - Multipart form: edits (JSON string) + files (uploaded work samples)

    Merges edits into the stored extraction/methodology, regenerates
    the skill files, and returns the updated result with a fresh review.
    """
    from agentforge.analysis.skill_refiner import SkillRefiner
    from agentforge.analysis.skill_reviewer import SkillReviewer
    from agentforge.generation.identity_generator import IdentityGenerator
    from agentforge.generation.skill_folder import SkillFolderGenerator
    from agentforge.models.extracted_skills import (
        ExtractionResult,
        MethodologyExtraction,
    )

    store = _get_store(request)
    job = store.get(job_id)
    if not job or not job.result:
        raise HTTPException(status_code=404, detail="Job not found or not complete")

    refine_ctx = job.result.get("_refine_context")
    if not refine_ctx or not refine_ctx.get("extraction"):
        raise HTTPException(status_code=400, detail="No refinement context available")

    # Parse edits and files from either JSON or multipart form
    uploaded_files: dict[str, str] = {}
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        edits_raw = form.get("edits", "{}")
        try:
            edits = json.loads(edits_raw)
        except (json.JSONDecodeError, TypeError):
            edits = {}
        # Read uploaded files
        for key in form:
            if key == "files":
                file_items = form.getlist("files")
                for upload in file_items:
                    if hasattr(upload, "read"):
                        file_content = await upload.read()
                        filename = getattr(upload, "filename", "file.txt") or "file.txt"
                        try:
                            uploaded_files[filename] = file_content.decode("utf-8")
                        except UnicodeDecodeError:
                            uploaded_files[filename] = file_content.decode("latin-1")
    else:
        body = await request.json()
        edits = body.get("edits", {})

    if not edits and not uploaded_files:
        raise HTTPException(status_code=400, detail="No edits or files provided")

    # Reconstruct models from stored JSON
    extraction = ExtractionResult.model_validate(refine_ctx["extraction"])
    methodology = (
        MethodologyExtraction.model_validate(refine_ctx["methodology"])
        if refine_ctx.get("methodology")
        else None
    )

    # Merge user edits (may produce supplementary reference files)
    refiner = SkillRefiner()
    extraction, methodology, new_files = refiner.merge(
        extraction, methodology, edits,
        uploaded_files=uploaded_files or None,
    )

    # Accumulate supplementary files across refine cycles
    existing_files: dict[str, str] = refine_ctx.get("supplementary_files", {})
    existing_files.update(new_files)

    # Regenerate identity + skill files with enriched data
    generator = IdentityGenerator()
    identity, yaml_str = generator.generate(extraction)

    output_format = refine_ctx.get("output_format", "claude_code")
    user_examples = refine_ctx.get("user_examples", "")
    user_frameworks = refine_ctx.get("user_frameworks", "")

    result_update: dict[str, Any] = {
        "identity_yaml": yaml_str,
    }

    if output_format in ("claude_code", "both"):
        skill_folder_gen = SkillFolderGenerator()
        sf = skill_folder_gen.generate(
            extraction, identity,
            jd=None,
            methodology=methodology,
            user_examples=user_examples,
            user_frameworks=user_frameworks,
        )
        sf.supplementary_files = existing_files
        result_update["skill_folder"] = {
            "skill_md": sf.skill_md_with_references(),
            "skill_name": sf.skill_name,
            "supplementary_files": sf.supplementary_files,
        }

    if output_format in ("clawhub", "both"):
        from agentforge.generation.clawhub_skill import ClawHubSkillGenerator

        clawhub_gen = ClawHubSkillGenerator()
        ch = clawhub_gen.generate(
            extraction, jd=None, methodology=methodology,
        )
        result_update["clawhub_skill"] = {
            "skill_md": ch.skill_md,
            "skill_name": ch.skill_name,
        }

    # Re-run skill quality review
    reviewer = SkillReviewer()
    skill_gaps = reviewer.review_to_dict(
        extraction,
        methodology=methodology,
        has_examples=bool(user_examples) or "examples" in edits,
        has_frameworks=bool(user_frameworks) or "frameworks" in edits,
    )
    result_update["skill_gaps"] = skill_gaps

    # Update stored job result
    job.result.update(result_update)

    # Also update the refine context for further refinements
    job.result["_refine_context"]["extraction"] = extraction.model_dump(mode="json")
    job.result["_refine_context"]["methodology"] = methodology.model_dump(mode="json")
    job.result["_refine_context"]["supplementary_files"] = existing_files

    # Track whether skill folder has reference files (for zip download)
    has_references = bool(existing_files)

    # Return only the updated fields to the frontend
    return {
        "skill_folder": result_update.get("skill_folder"),
        "clawhub_skill": result_update.get("clawhub_skill"),
        "skill_gaps": skill_gaps,
        "identity_yaml": yaml_str,
        "has_references": has_references,
    }
