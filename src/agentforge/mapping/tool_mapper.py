"""LLM-powered skill-to-tool mapping — determines what tools an agent needs."""

from __future__ import annotations

import json
import logging

from agentforge.llm.client import LLMClient
from agentforge.models.extracted_skills import ExtractionResult
from agentforge.models.tool_profile import AgentToolProfile

logger = logging.getLogger(__name__)

TOOL_MAPPING_SYSTEM_PROMPT = """You are an expert AI agent architect specializing in tool selection \
and workflow design. Given an extracted role and skill set, you determine exactly which tools, \
MCP servers, APIs, and CLI utilities an AI agent would need to perform this role effectively.

You think in terms of concrete tool calls — not abstract capabilities. Every tool you recommend \
should be something an agent can actually invoke via MCP, CLI, or API."""

TOOL_MAPPING_PROMPT = """Given this role extraction, determine what tools the agent needs.

ROLE: {title} ({seniority} level, {domain} domain)
PURPOSE: {purpose}

SKILLS:
{skills}

RESPONSIBILITIES:
{responsibilities}

Generate:

1. **tools**: A list of tools the agent needs. For each tool:
   - name: Short tool name (snake_case, e.g. "sql_query", "file_read", "web_search")
   - description: What this tool does (1 sentence)
   - category: One of: file_io, code_execution, data_query, web_search, communication, analysis, generation, deployment, monitoring, other
   - transport: How the agent calls it: "mcp_stdio" (MCP server via stdio), "mcp_sse" (MCP over HTTP), "cli" (shell command), "api" (REST/HTTP), "builtin" (built into the agent platform)
   - mcp_server: If transport is mcp_stdio or mcp_sse, the npm package or Python module name (e.g. "@anthropic/mcp-server-filesystem", "mcp_server_sqlite"). Empty string otherwise.
   - source_skills: List of skill names from the extraction that require this tool
   - parameters: Key parameters as {{param_name: description}} (3-5 most important params)
   - priority: "required" (agent can't function without it), "recommended" (significantly improves capability), or "optional" (nice-to-have)

2. **usage_patterns**: 3-6 workflows showing how tools are used together. For each:
   - name: Workflow name (e.g. "Data pipeline execution")
   - trigger: When this workflow runs (e.g. "When asked to analyze a dataset")
   - steps: Ordered list of tool calls, each with:
     - tool: Tool name (must match a tool from the list above)
     - action: What this step does
     - inputs: What data flows in
     - outputs: What data flows out
   - source_responsibility: Which responsibility this workflow addresses

Focus on REAL, EXISTING tools — especially well-known MCP servers (filesystem, git, sqlite, \
postgres, brave-search, puppeteer, etc.), standard CLI tools, and established APIs. \
Don't invent fictional tools. Prefer MCP transport where a server exists.

For a {domain} domain role at {seniority} level, select tools that match the actual \
complexity and scope of the work."""


class ToolMapper:
    """Maps extracted skills to concrete tool recommendations via LLM."""

    def __init__(self, client: LLMClient | None = None):
        self.client = client or LLMClient()

    def map_tools(self, extraction: ExtractionResult) -> AgentToolProfile:
        """Generate a tool profile from an extraction result."""
        role = extraction.role
        skills_text = "\n".join(
            f"- {s.name} ({s.category.value}, {s.proficiency.value}, {s.importance.value}): {s.context}"
            for s in extraction.skills
        )
        resp_text = "\n".join(f"- {r}" for r in extraction.responsibilities)

        prompt = TOOL_MAPPING_PROMPT.format(
            title=role.title,
            seniority=role.seniority.value,
            domain=role.domain,
            purpose=role.purpose,
            skills=skills_text,
            responsibilities=resp_text,
        )

        profile = self.client.structured_request(
            system=TOOL_MAPPING_SYSTEM_PROMPT,
            prompt=prompt,
            response_model=AgentToolProfile,
        )

        # Generate the MCP config from the mapped tools
        profile.mcp_config = profile.generate_mcp_json().get("mcpServers", {})

        return profile
