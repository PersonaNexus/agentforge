"""Compile AgentForge output into OpenClaw-ready deployment files.

Generates the full set of files OpenClaw expects:
  - {agent}.SOUL.md       — system prompt / persona definition
  - {agent}.STYLE.md      — communication style guide
  - {agent}.personality.json — trait values for runtime personality engine
  - {agent}-skills/       — Claude Code skill folder (SKILL.md + supplementary)

This replaces the manual AgentForge → PersonaNexus → compile → OpenClaw handoff
with a single pipeline step.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from agentforge.generation.skill_folder import SkillFolderResult
from agentforge.models.extracted_skills import (
    ExtractionResult,
    MethodologyExtraction,
)


class OpenClawOutput(BaseModel):
    """Container for all OpenClaw-ready deployment files."""

    agent_name: str = Field(..., description="Agent identifier (slug)")
    soul_md: str = Field(..., description="SOUL.md system prompt content")
    style_md: str = Field(..., description="STYLE.md communication guide")
    personality_json: str = Field(..., description="personality.json serialized content")
    skill_folder: SkillFolderResult | None = Field(
        None, description="Claude Code skill folder if generated"
    )
    openclaw_json: str = Field(default="", description="openclaw.json agent config")

    def file_map(self) -> dict[str, str]:
        """Return {relative_path: content} for all output files."""
        files: dict[str, str] = {}
        files[f"{self.agent_name}.SOUL.md"] = self.soul_md
        files[f"{self.agent_name}.STYLE.md"] = self.style_md
        files[f"{self.agent_name}.personality.json"] = self.personality_json
        if self.openclaw_json:
            files[f"{self.agent_name}.openclaw.json"] = self.openclaw_json

        if self.skill_folder:
            prefix = f"{self.agent_name}-skills"
            files[f"{prefix}/SKILL.md"] = self.skill_folder.skill_md_with_references()
            for rel_path, content in self.skill_folder.supplementary_files.items():
                files[f"{prefix}/{rel_path}"] = content

        return files


class OpenClawCompiler:
    """Compiles extraction + identity + methodology into OpenClaw deployment files."""

    def compile(
        self,
        extraction: ExtractionResult,
        identity_yaml: str,
        identity: Any,
        methodology: MethodologyExtraction | None = None,
        skill_folder: SkillFolderResult | None = None,
        schedule: str | None = None,
        cron_config: dict | None = None,
    ) -> OpenClawOutput:
        """Compile all OpenClaw files from pipeline context.

        Args:
            extraction: LLM-extracted role/skills.
            identity_yaml: Serialized PersonaNexus identity YAML.
            identity: Validated PersonaNexus AgentIdentity.
            methodology: Optional methodology extraction.
            skill_folder: Optional Claude Code skill folder.
            schedule: Optional cron schedule expression.
            cron_config: Optional cron configuration dict.
        """
        from agentforge.utils import make_skill_slug

        agent_name = make_skill_slug(extraction.role.title)

        soul_md = self._build_soul_md(extraction, identity, methodology)
        style_md = self._build_style_md(extraction, identity)
        personality_json = self._build_personality_json(extraction, identity)
        openclaw_json = self._build_openclaw_json(
            extraction, agent_name, schedule, cron_config,
        )

        return OpenClawOutput(
            agent_name=agent_name,
            soul_md=soul_md,
            style_md=style_md,
            personality_json=personality_json,
            skill_folder=skill_folder,
            openclaw_json=openclaw_json,
        )

    def _build_soul_md(
        self,
        extraction: ExtractionResult,
        identity: Any,
        methodology: MethodologyExtraction | None,
    ) -> str:
        """Build SOUL.md — the agent's system prompt and persona definition."""
        lines: list[str] = []

        lines.append(f"# {extraction.role.title}")
        lines.append("")
        lines.append(f"> {extraction.role.purpose}")
        lines.append("")

        # Identity
        lines.append("## Identity")
        lines.append("")
        lines.append(
            f"You are a {extraction.role.seniority.value}-level "
            f"{extraction.role.title} specializing in {extraction.role.domain}."
        )
        lines.append("")

        # Responsibilities
        if extraction.responsibilities:
            lines.append("## Core Responsibilities")
            lines.append("")
            for resp in extraction.responsibilities:
                lines.append(f"- {resp}")
            lines.append("")

        # Methodology
        has_meth = methodology and methodology.has_content()
        if has_meth:
            if methodology.heuristics:
                lines.append("## Decision Frameworks")
                lines.append("")
                for h in methodology.heuristics:
                    lines.append(f"### {h.trigger}")
                    lines.append("")
                    lines.append(h.procedure)
                    lines.append("")

            if methodology.trigger_mappings:
                lines.append("## Routing")
                lines.append("")
                for m in methodology.trigger_mappings:
                    lines.append(f"**{m.trigger_pattern}** -> {m.technique}")
                    if m.output_format:
                        lines.append(f"  Output: {m.output_format}")
                lines.append("")

        # Expertise
        if extraction.role.scope_primary:
            lines.append("## Scope")
            lines.append("")
            for item in extraction.role.scope_primary:
                lines.append(f"- {item}")
            lines.append("")

        # Guardrails
        lines.append("## Guardrails")
        lines.append("")
        lines.append(f"- Stay within {extraction.role.domain} domain expertise")
        lines.append("- Acknowledge limitations outside core competencies")
        lines.append("- Never fabricate data or sources")
        lines.append("")

        lines.append("---")
        lines.append(
            f"*Generated by AgentForge → OpenClaw | "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}*"
        )
        lines.append("")
        return "\n".join(lines)

    def _build_style_md(
        self,
        extraction: ExtractionResult,
        identity: Any,
    ) -> str:
        """Build STYLE.md — communication style guide."""
        lines: list[str] = []

        lines.append(f"# Communication Style — {extraction.role.title}")
        lines.append("")

        defined = extraction.suggested_traits.defined_traits()
        if defined:
            lines.append("## Personality Traits")
            lines.append("")
            sorted_traits = sorted(defined.items(), key=lambda x: x[1], reverse=True)
            for trait_name, value in sorted_traits:
                display = trait_name.replace("_", " ").title()
                lines.append(f"- **{display}**: {value:.0%}")
            lines.append("")

            # Derive style guidance
            lines.append("## Style Guidance")
            lines.append("")
            rigor = defined.get("rigor", 0.5)
            directness = defined.get("directness", 0.5)
            warmth = defined.get("warmth", 0.5)
            verbosity = defined.get("verbosity", 0.5)

            if rigor >= 0.65:
                lines.append("- Prioritize accuracy and precision in all outputs")
            if directness >= 0.65:
                lines.append("- Be clear and direct; avoid hedging or filler")
            if warmth >= 0.65:
                lines.append("- Maintain a warm, approachable tone")
            elif warmth < 0.35:
                lines.append("- Keep communications professional and objective")
            if verbosity >= 0.65:
                lines.append("- Provide thorough, detailed explanations")
            elif verbosity < 0.35:
                lines.append("- Keep responses concise and focused")
            lines.append("")
        else:
            lines.append("Use a balanced, professional communication style.")
            lines.append("")

        # Audience
        if extraction.role.audience:
            lines.append("## Audience")
            lines.append("")
            for aud in extraction.role.audience:
                lines.append(f"- {aud}")
            lines.append("")

        return "\n".join(lines)

    def _build_personality_json(
        self,
        extraction: ExtractionResult,
        identity: Any,
    ) -> str:
        """Build personality.json — trait values for runtime engine."""
        defined = extraction.suggested_traits.defined_traits()

        personality = {
            "agent_name": extraction.role.title,
            "domain": extraction.role.domain,
            "seniority": extraction.role.seniority.value,
            "traits": defined,
            "communication": {
                "audience": extraction.role.audience,
                "scope_primary": extraction.role.scope_primary,
                "scope_secondary": extraction.role.scope_secondary,
            },
        }

        return json.dumps(personality, indent=2)

    def _build_openclaw_json(
        self,
        extraction: ExtractionResult,
        agent_name: str,
        schedule: str | None = None,
        cron_config: dict | None = None,
    ) -> str:
        """Build openclaw.json — agent configuration for the OpenClaw runtime."""
        config: dict[str, Any] = {
            "name": agent_name,
            "display_name": extraction.role.title,
            "domain": extraction.role.domain,
            "files": {
                "soul": f"{agent_name}.SOUL.md",
                "style": f"{agent_name}.STYLE.md",
                "personality": f"{agent_name}.personality.json",
                "skills": f"{agent_name}-skills/",
            },
        }

        if schedule:
            config["schedule"] = schedule
        if cron_config:
            config["cron"] = cron_config

        return json.dumps(config, indent=2)
