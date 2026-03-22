"""Data models for agent tool profiles — tool inventory, usage patterns, and MCP config."""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field, field_validator


class ToolTransport(enum.StrEnum):
    MCP_STDIO = "mcp_stdio"
    MCP_SSE = "mcp_sse"
    CLI = "cli"
    API = "api"
    BUILTIN = "builtin"


class ToolCategory(enum.StrEnum):
    FILE_IO = "file_io"
    CODE_EXECUTION = "code_execution"
    DATA_QUERY = "data_query"
    WEB_SEARCH = "web_search"
    COMMUNICATION = "communication"
    ANALYSIS = "analysis"
    GENERATION = "generation"
    DEPLOYMENT = "deployment"
    MONITORING = "monitoring"
    OTHER = "other"


class AgentTool(BaseModel):
    """A single tool an agent needs access to."""

    name: str = Field(..., description="Tool name (e.g. 'sql_query', 'file_read')")
    description: str = Field(..., description="What the tool does")
    category: ToolCategory = ToolCategory.OTHER
    transport: ToolTransport = ToolTransport.BUILTIN
    mcp_server: str = Field(default="", description="MCP server name if transport is MCP")
    source_skills: list[str] = Field(
        default_factory=list,
        description="Which extracted skills require this tool",
    )
    parameters: dict[str, str] = Field(
        default_factory=dict,
        description="Key parameter names and their descriptions",
    )
    priority: str = Field(default="recommended", description="required | recommended | optional")

    @field_validator("category", mode="before")
    @classmethod
    def coerce_category(cls, v: object) -> ToolCategory:
        if v is None:
            return ToolCategory.OTHER
        try:
            return ToolCategory(str(v).strip().lower().replace(" ", "_").replace("-", "_"))
        except ValueError:
            return ToolCategory.OTHER

    @field_validator("transport", mode="before")
    @classmethod
    def coerce_transport(cls, v: object) -> ToolTransport:
        if v is None:
            return ToolTransport.BUILTIN
        try:
            return ToolTransport(str(v).strip().lower().replace(" ", "_").replace("-", "_"))
        except ValueError:
            return ToolTransport.BUILTIN

    @field_validator("mcp_server", "description", mode="before")
    @classmethod
    def coerce_none_str(cls, v: object) -> str:
        return "" if v is None else str(v)

    @field_validator("source_skills", mode="before")
    @classmethod
    def coerce_none_list(cls, v: object) -> list:
        if v is None or v == "":
            return []
        return v

    @field_validator("parameters", mode="before")
    @classmethod
    def coerce_none_dict(cls, v: object) -> dict:
        if v is None or v == "":
            return {}
        return v


class ToolUsageStep(BaseModel):
    """A single step in a tool usage workflow."""

    tool: str = Field(..., description="Tool name to call")
    action: str = Field(..., description="What this step does")
    inputs: str = Field(default="", description="What data flows into this step")
    outputs: str = Field(default="", description="What data flows out")

    @field_validator("inputs", "outputs", "action", mode="before")
    @classmethod
    def coerce_none_str(cls, v: object) -> str:
        return "" if v is None else str(v)


class ToolUsagePattern(BaseModel):
    """A workflow showing how tools are used together for a task."""

    name: str = Field(..., description="Workflow name (e.g. 'Data cleaning pipeline')")
    trigger: str = Field(..., description="When this workflow is invoked")
    steps: list[ToolUsageStep] = Field(default_factory=list)
    source_responsibility: str = Field(default="", description="The responsibility this maps to")

    @field_validator("source_responsibility", mode="before")
    @classmethod
    def coerce_none_str(cls, v: object) -> str:
        return "" if v is None else str(v)

    @field_validator("steps", mode="before")
    @classmethod
    def coerce_none_list(cls, v: object) -> list:
        if v is None or v == "":
            return []
        return v


class AgentToolProfile(BaseModel):
    """Complete tool profile for an agent — inventory, workflows, and config."""

    tools: list[AgentTool] = Field(default_factory=list)
    usage_patterns: list[ToolUsagePattern] = Field(default_factory=list)
    mcp_config: dict[str, dict] = Field(
        default_factory=dict,
        description="Generated .mcp.json content — server name → config",
    )

    @field_validator("tools", "usage_patterns", mode="before")
    @classmethod
    def coerce_none_to_list(cls, v: object) -> list:
        if v is None or v == "":
            return []
        return v

    @field_validator("mcp_config", mode="before")
    @classmethod
    def coerce_none_to_dict(cls, v: object) -> dict:
        if v is None or v == "":
            return {}
        return v

    def required_tools(self) -> list[AgentTool]:
        return [t for t in self.tools if t.priority == "required"]

    def tools_by_category(self) -> dict[str, list[AgentTool]]:
        result: dict[str, list[AgentTool]] = {}
        for tool in self.tools:
            result.setdefault(tool.category.value, []).append(tool)
        return result

    def generate_mcp_json(self) -> dict:
        """Generate a .mcp.json config from tools that use MCP transport."""
        servers: dict[str, dict] = {}
        for tool in self.tools:
            if tool.transport in (ToolTransport.MCP_STDIO, ToolTransport.MCP_SSE) and tool.mcp_server:
                if tool.mcp_server not in servers:
                    servers[tool.mcp_server] = {
                        "command": "npx" if "mcp-server" in tool.mcp_server else "python",
                        "args": ["-m", tool.mcp_server] if "." in tool.mcp_server else ["-y", tool.mcp_server],
                    }
        return {"mcpServers": servers}
