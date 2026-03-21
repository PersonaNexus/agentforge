"""Batch API route — multi-file processing with SSE streaming."""

from __future__ import annotations

import io
import json
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from agentforge.utils import safe_filename
from agentforge.web.jobs import Job, JobStore

router = APIRouter(tags=["batch"])

_ALLOWED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".docx"}


def _get_store(request: Request) -> JobStore:
    return request.app.state.jobs


def _run_batch(
    job: Job,
    file_paths: list[Path],
    model: str,
    parallel: int,
    culture_path: Path | None,
    user_examples: str = "",
    user_frameworks: str = "",
) -> None:
    """Worker thread: processes multiple JDs and emits SSE progress events."""
    try:
        from agentforge.llm.client import LLMClient
        from agentforge.pipeline.batch import BatchProcessor
        from agentforge.pipeline.forge_pipeline import ForgePipeline

        job.status = "running"

        client = LLMClient(model=model)
        shared_context: dict[str, Any] = {"llm_client": client}
        if culture_path:
            shared_context["culture_path"] = str(culture_path)
        if user_examples:
            shared_context["user_examples"] = user_examples
        if user_frameworks:
            shared_context["user_frameworks"] = user_frameworks

        pipeline = ForgePipeline.default()
        processor = BatchProcessor(pipeline=pipeline, parallel=parallel)

        # Process files one at a time to emit per-file progress
        results_data: list[dict] = []
        output_files: dict[str, str] = {}
        total = len(file_paths)

        for i, fp in enumerate(file_paths):
            fname = fp.name
            job.emit("progress", {
                "completed": i,
                "total": total,
                "file": fname,
                "status": "processing",
            })

            result = processor._process_single(str(fp), dict(shared_context))

            entry: dict[str, Any] = {
                "file": fname,
                "success": result.success,
                "duration": round(result.duration, 1),
                "error": result.error,
            }
            if result.success and result.blueprint:
                bp = result.blueprint
                entry["agent_title"] = bp.extraction.role.title
                entry["skills_count"] = len(bp.extraction.skills)
                entry["coverage"] = int(bp.coverage_score * 100)
                # Store output files
                agent_id = safe_filename(bp.extraction.role.title.lower().replace(" ", "_"))
                yaml_name = f"{agent_id}.yaml"
                output_files[yaml_name] = bp.identity_yaml
                if bp.skill_file:
                    output_files[f"{agent_id}_SKILL.md"] = bp.skill_file
                if bp.skill_folder:
                    skill_name = safe_filename(bp.skill_folder.skill_name)
                    output_files[f"{skill_name}/SKILL.md"] = bp.skill_folder.skill_md
                    for rel_path, content in bp.skill_folder.supplementary_files.items():
                        safe_parts = [safe_filename(p) for p in Path(rel_path).parts]
                        safe_rel = "/".join(safe_parts)
                        output_files[f"{skill_name}/{safe_rel}"] = content

            results_data.append(entry)

        job.emit_done({"results": results_data, "files": output_files})

    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Batch processing failed")
        job.emit_error("Batch processing failed: an internal error occurred")
    finally:
        for fp in file_paths:
            fp.unlink(missing_ok=True)
        if culture_path:
            culture_path.unlink(missing_ok=True)


@router.post("/batch", status_code=202)
async def start_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    model: str = Form("claude-sonnet-4-20250514"),
    parallel: int = Form(1),
    culture_file: UploadFile | None = File(None),
    user_examples: str = Form(""),
    user_frameworks: str = Form(""),
) -> dict:
    """Start a batch processing job."""
    if not files:
        raise HTTPException(status_code=422, detail="No files provided")

    file_paths: list[Path] = []
    for f in files:
        fname = f.filename or "upload.txt"
        suffix = Path(fname).suffix.lower()
        if suffix not in _ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=422, detail=f"Unsupported file type: {suffix}")

        content = await f.read()
        _MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
        if len(content) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"File '{fname}' too large (max 20 MB)")
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix, prefix=Path(fname).stem + "_"
        )
        tmp.write(content)
        tmp.close()
        file_paths.append(Path(tmp.name))

    culture_path: Path | None = None
    if culture_file and culture_file.filename:
        culture_content = await culture_file.read()
        ctmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=Path(culture_file.filename).suffix.lower()
        )
        ctmp.write(culture_content)
        ctmp.close()
        culture_path = Path(ctmp.name)

    store = _get_store(request)
    job = store.create(
        job_type="batch",
        source_filename=f"{len(file_paths)} files",
        model=model,
    )

    thread = threading.Thread(
        target=_run_batch,
        args=(job, file_paths, model, max(1, parallel), culture_path),
        kwargs={"user_examples": user_examples, "user_frameworks": user_frameworks},
        daemon=True,
    )
    thread.start()

    return {"job_id": job.id}


@router.get("/batch/{job_id}/stream")
async def batch_stream(job_id: str, request: Request) -> StreamingResponse:
    """Stream SSE events for a batch job."""
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
                yield ": keepalive\n\n"
                if job.status in ("done", "error"):
                    break

    return StreamingResponse(_generate(), media_type="text/event-stream")


@router.get("/batch/{job_id}/download/zip")
async def batch_download_zip(job_id: str, request: Request) -> StreamingResponse:
    """Download all generated files as a ZIP."""
    store = _get_store(request)
    job = store.get(job_id)
    if not job or not job.result:
        raise HTTPException(status_code=404, detail="Job not found or not complete")

    output_files = job.result.get("files", {})
    if not output_files:
        raise HTTPException(status_code=404, detail="No output files available")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in output_files.items():
            zf.writestr(name, content)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="agentforge_batch.zip"'},
    )
