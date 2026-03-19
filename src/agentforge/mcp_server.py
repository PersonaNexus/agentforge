"""AgentForge MCP server — exposes forge/extract/batch as tools for agent-to-agent use.

Run with:
    python -m agentforge.mcp_server

Or add to Claude Code's MCP config:
    {
      "mcpServers": {
        "agentforge": {
          "command": "python",
          "args": ["-m", "agentforge.mcp_server"]
        }
      }
    }
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _ensure_mcp() -> None:
    """Check mcp SDK is installed."""
    try:
        import mcp  # noqa: F401
    except ImportError:
        print(
            "MCP SDK not installed. Install it with:\n"
            "  pip install mcp\n",
            file=sys.stderr,
        )
        sys.exit(1)


# --- Tool input schemas ---


class ExtractInput(BaseModel):
    """Input for the extract tool."""

    jd_text: str = Field(description="Full text of the job description to analyze")
    model: str = Field(
        default="claude-sonnet-4-20250514",
        description="LLM model to use for extraction",
    )


class ForgeInput(BaseModel):
    """Input for the forge tool."""

    jd_text: str = Field(description="Full text of the job description")
    model: str = Field(
        default="claude-sonnet-4-20250514",
        description="LLM model to use",
    )
    quick: bool = Field(default=False, description="Skip culture, mapping, and gap analysis")
    deep: bool = Field(default=False, description="Enhanced gap analysis with skill-level scoring")
    culture_yaml: str | None = Field(
        default=None,
        description="Optional culture profile YAML content to infuse",
    )
    user_examples: str = Field(
        default="",
        description="Work samples or examples text to enrich methodology extraction",
    )
    user_frameworks: str = Field(
        default="",
        description="Frameworks or methodologies text to enrich methodology extraction",
    )


class ForgeFileInput(BaseModel):
    """Input for forging from a file path."""

    jd_path: str = Field(description="Path to a job description file (txt, md, pdf, docx)")
    model: str = Field(
        default="claude-sonnet-4-20250514",
        description="LLM model to use",
    )
    quick: bool = Field(default=False, description="Skip culture, mapping, and gap analysis")
    user_examples: str = Field(
        default="",
        description="Work samples or examples text to enrich methodology extraction",
    )
    user_frameworks: str = Field(
        default="",
        description="Frameworks or methodologies text to enrich methodology extraction",
    )


def _create_server():  # noqa: ANN202
    """Create the MCP server with registered tools."""
    from mcp.server import Server
    import mcp.types as types

    server = Server("agentforge")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="agentforge_extract",
                description=(
                    "Extract skills, role info, personality traits, and automation potential "
                    "from a job description. Returns structured JSON with skills, role metadata, "
                    "suggested PersonaNexus traits, and automation assessment."
                ),
                inputSchema=ExtractInput.model_json_schema(),
            ),
            types.Tool(
                name="agentforge_forge",
                description=(
                    "Run the full AgentForge pipeline: extract skills from a job description, "
                    "map to PersonaNexus traits, generate an identity YAML, Claude Code skill "
                    "folder, and gap analysis. Returns the complete agent blueprint as JSON."
                ),
                inputSchema=ForgeInput.model_json_schema(),
            ),
            types.Tool(
                name="agentforge_forge_file",
                description=(
                    "Forge an agent blueprint from a job description file on disk "
                    "(supports txt, md, pdf, docx). Returns the agent blueprint as JSON."
                ),
                inputSchema=ForgeFileInput.model_json_schema(),
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        try:
            if name == "agentforge_extract":
                result = _do_extract(arguments)
            elif name == "agentforge_forge":
                result = _do_forge(arguments)
            elif name == "agentforge_forge_file":
                result = _do_forge_file(arguments)
            else:
                return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        except Exception as e:
            logger.exception("Tool %s failed", name)
            return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]

    return server


def _make_client(model: str):  # noqa: ANN202
    from agentforge.llm.client import LLMClient

    return LLMClient(model=model)


def _text_to_jd(text: str):  # noqa: ANN202
    from agentforge.models.job_description import JobDescription, JDSection

    return JobDescription(
        title="(provided via MCP)",
        raw_text=text,
        sections=[JDSection(heading="Full Description", content=text)],
    )


def _do_extract(args: dict) -> dict:
    inp = ExtractInput(**args)
    from agentforge.extraction.skill_extractor import SkillExtractor

    client = _make_client(inp.model)
    extractor = SkillExtractor(client=client)
    jd = _text_to_jd(inp.jd_text)
    result = extractor.extract(jd)
    return json.loads(result.model_dump_json())


def _do_forge(args: dict) -> dict:
    inp = ForgeInput(**args)
    from agentforge.pipeline.forge_pipeline import ForgePipeline

    if inp.quick:
        pipeline = ForgePipeline.quick()
    elif inp.deep:
        pipeline = ForgePipeline.deep_analysis()
    else:
        pipeline = ForgePipeline.default()

    client = _make_client(inp.model)
    jd = _text_to_jd(inp.jd_text)

    context: dict = {"jd": jd, "llm_client": client}

    if inp.user_examples:
        context["user_examples"] = inp.user_examples
    if inp.user_frameworks:
        context["user_frameworks"] = inp.user_frameworks

    if inp.culture_yaml:
        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False)
        tmp.write(inp.culture_yaml)
        tmp.close()
        context["culture_path"] = tmp.name

    # Skip ingest since we already have the JD
    pipeline.skip_stage("ingest")
    context = pipeline.run(context)

    return _context_to_result(context)


def _do_forge_file(args: dict) -> dict:
    inp = ForgeFileInput(**args)
    from agentforge.pipeline.forge_pipeline import ForgePipeline

    path = Path(inp.jd_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {inp.jd_path}")

    if inp.quick:
        pipeline = ForgePipeline.quick()
    else:
        pipeline = ForgePipeline.default()

    client = _make_client(inp.model)
    context: dict = {"input_path": str(path), "llm_client": client}
    if inp.user_examples:
        context["user_examples"] = inp.user_examples
    if inp.user_frameworks:
        context["user_frameworks"] = inp.user_frameworks
    context = pipeline.run(context)

    return _context_to_result(context)


def _context_to_result(context: dict) -> dict:
    """Convert pipeline context to a serializable result dict."""
    result: dict = {}

    if "extraction" in context:
        result["extraction"] = json.loads(context["extraction"].model_dump_json())

    if "identity_yaml" in context:
        result["identity_yaml"] = context["identity_yaml"]

    if "skill_file" in context:
        result["skill_file"] = context["skill_file"]

    if "skill_folder" in context:
        sf = context["skill_folder"]
        result["skill_folder"] = {
            "skill_name": sf.skill_name,
            "skill_md": sf.skill_md_with_references(),
            "supplementary_files": sf.supplementary_files,
        }

    if "coverage_score" in context:
        result["coverage_score"] = context["coverage_score"]
        result["coverage_gaps"] = context.get("coverage_gaps", [])

    if "skill_scores" in context:
        result["skill_scores"] = context["skill_scores"]

    blueprint = None
    if "extraction" in context:
        from agentforge.pipeline.forge_pipeline import ForgePipeline

        try:
            blueprint = ForgePipeline.default().to_blueprint(context)
            result["blueprint"] = json.loads(blueprint.model_dump_json())
        except Exception:
            pass

    return result


def main() -> None:
    """Run the MCP server over stdio."""
    import asyncio

    _ensure_mcp()

    from mcp.server.stdio import stdio_server

    server = _create_server()

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
