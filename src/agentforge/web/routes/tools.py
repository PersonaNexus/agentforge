"""Tools API route — standalone tool profile generation and MCP config export."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["tools"])

logger = logging.getLogger(__name__)


class ToolMapRequest(BaseModel):
    """Request body for generating a tool profile from a job_id."""

    job_id: str
    model: str = Field(default="claude-sonnet-4-20250514")


class ToolEditRequest(BaseModel):
    """Request body for editing a tool profile."""

    job_id: str
    tools: list[dict] = Field(default_factory=list, description="Updated tool list")
    usage_patterns: list[dict] = Field(default_factory=list, description="Updated patterns")


@router.post("/tools/map")
async def map_tools(request: Request, body: ToolMapRequest) -> dict:
    """Generate a tool profile from an existing forge job's extraction.

    This lets users generate/regenerate tool mappings after a forge completes,
    or for jobs that ran before tool mapping was added.
    """
    from agentforge.llm.client import LLMClient
    from agentforge.mapping.tool_mapper import ToolMapper
    from agentforge.models.extracted_skills import ExtractionResult

    store = request.app.state.jobs
    job = store.get(body.job_id)
    if not job or not job.result:
        raise HTTPException(status_code=404, detail="Job not found or not complete")

    # Get extraction from refine context or blueprint
    refine_ctx = job.result.get("_refine_context", {})
    extraction_data = refine_ctx.get("extraction")
    if not extraction_data:
        bp = job.result.get("blueprint", {})
        extraction_data = bp.get("extraction")
    if not extraction_data:
        raise HTTPException(status_code=400, detail="No extraction data available for this job")

    extraction = ExtractionResult.model_validate(extraction_data)
    client = LLMClient(model=body.model)
    mapper = ToolMapper(client=client)
    profile = mapper.map_tools(extraction)

    result = profile.model_dump(mode="json")

    # Store in job result
    job.result["tool_profile"] = result
    store.persist_result(job)

    return result


@router.post("/tools/edit")
async def edit_tools(request: Request, body: ToolEditRequest) -> dict:
    """Save user edits to a tool profile and regenerate MCP config."""
    from agentforge.models.tool_profile import AgentToolProfile

    store = request.app.state.jobs
    job = store.get(body.job_id)
    if not job or not job.result:
        raise HTTPException(status_code=404, detail="Job not found or not complete")

    # Rebuild profile from user edits
    profile = AgentToolProfile(
        tools=body.tools,
        usage_patterns=body.usage_patterns,
    )
    profile.mcp_config = profile.generate_mcp_json().get("mcpServers", {})

    result = profile.model_dump(mode="json")
    job.result["tool_profile"] = result
    store.persist_result(job)

    return result


@router.get("/tools/{job_id}")
async def get_tool_profile(job_id: str, request: Request) -> dict:
    """Get the tool profile for a completed forge job."""
    store = request.app.state.jobs
    job = store.get(job_id)
    if not job or not job.result:
        raise HTTPException(status_code=404, detail="Job not found or not complete")

    profile = job.result.get("tool_profile")
    if not profile:
        raise HTTPException(status_code=404, detail="No tool profile available — run tool mapping first")

    return profile


@router.get("/tools/{job_id}/mcp-config")
async def get_mcp_config(job_id: str, request: Request) -> dict:
    """Export the tool profile as a .mcp.json config."""
    store = request.app.state.jobs
    job = store.get(job_id)
    if not job or not job.result:
        raise HTTPException(status_code=404, detail="Job not found or not complete")

    profile_data = job.result.get("tool_profile")
    if not profile_data:
        raise HTTPException(status_code=404, detail="No tool profile available")

    from agentforge.models.tool_profile import AgentToolProfile

    profile = AgentToolProfile.model_validate(profile_data)
    return profile.generate_mcp_json()
