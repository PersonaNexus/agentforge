"""Generate ClawHub-compatible skill files from extraction results.

Produces a SKILL.md file matching the ClawHub/OpenClaw skill format:
  - YAML frontmatter with name, description, version, metadata.openclaw
  - Concise, action-oriented markdown body (no persona layer)
  - Methodology-first: decision frameworks, trigger routing, templates
  - "The context window is a public good" — minimal token footprint

ClawHub spec reference:
    https://github.com/openclaw/clawhub/blob/main/docs/skill-format.md
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from agentforge.models.extracted_skills import (
    ExtractionResult,
    MethodologyExtraction,
    SkillCategory,
)
from agentforge.models.job_description import JobDescription
from agentforge.utils import safe_filename


class ClawHubSkillResult(BaseModel):
    """Container for ClawHub-compatible skill content."""

    skill_name: str = Field(..., description="Slug name for the skill")
    skill_md: str = Field(..., description="SKILL.md content with ClawHub frontmatter")


class ClawHubSkillGenerator:
    """Generates ClawHub/OpenClaw-compatible skill files.

    Key differences from Claude Code skill output:
      - No persona/identity layer (pure procedure)
      - `version` field in frontmatter
      - `metadata.openclaw` block for runtime requirements
      - Concise, action-oriented body
      - Methodology sections without personality framing
    """

    def generate(
        self,
        extraction: ExtractionResult,
        jd: JobDescription | None = None,
        methodology: MethodologyExtraction | None = None,
    ) -> ClawHubSkillResult:
        skill_name = self._make_skill_name(extraction)
        return ClawHubSkillResult(
            skill_name=skill_name,
            skill_md=self._render(extraction, jd, methodology, skill_name),
        )

    def _make_skill_name(self, extraction: ExtractionResult) -> str:
        """ClawHub slug: lowercase, hyphens, ^[a-z0-9][a-z0-9-]*$."""
        raw = safe_filename(extraction.role.title).lower().replace("_", "-")
        raw = re.sub(r"-+", "-", raw).strip("-")
        # Remove leading non-alphanumeric
        raw = re.sub(r"^[^a-z0-9]+", "", raw)
        if len(raw) > 64:
            raw = raw[:64].rstrip("-")
        return raw or "generated-skill"

    def _render(
        self,
        extraction: ExtractionResult,
        jd: JobDescription | None,
        methodology: MethodologyExtraction | None,
        skill_name: str,
    ) -> str:
        lines: list[str] = []
        self._render_frontmatter(lines, extraction, skill_name)
        self._render_body(lines, extraction, jd, methodology)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Frontmatter
    # ------------------------------------------------------------------

    def _render_frontmatter(
        self,
        lines: list[str],
        extraction: ExtractionResult,
        skill_name: str,
    ) -> None:
        description = extraction.role.purpose
        if len(description) > 200:
            description = description[:197] + "..."
        description = description.replace('"', '\\"')

        lines.append("---")
        lines.append(f"name: {skill_name}")
        lines.append(f'description: "{description}"')
        lines.append("version: 1.0.0")

        # Build metadata.openclaw block
        bins = self._infer_required_bins(extraction)
        env_vars = self._infer_env_vars(extraction)

        if bins or env_vars:
            lines.append("metadata:")
            lines.append("  openclaw:")
            if env_vars:
                lines.append("    requires:")
                lines.append("      env:")
                for var in env_vars:
                    lines.append(f"        - {var}")
                lines.append(f"    primaryEnv: {env_vars[0]}")
            if bins:
                if not env_vars:
                    lines.append("    requires:")
                lines.append("      bins:")
                for b in bins:
                    lines.append(f"        - {b}")

        lines.append("---")
        lines.append("")

    def _infer_required_bins(self, extraction: ExtractionResult) -> list[str]:
        """Infer required CLI binaries from tool/hard skills."""
        bin_map = {
            "python": "python3",
            "node": "node",
            "node.js": "node",
            "docker": "docker",
            "kubernetes": "kubectl",
            "git": "git",
            "terraform": "terraform",
            "aws": "aws",
            "gcp": "gcloud",
            "azure": "az",
            "postgresql": "psql",
            "mysql": "mysql",
            "redis": "redis-cli",
            "go": "go",
            "rust": "cargo",
            "java": "java",
        }
        bins: list[str] = []
        for skill in extraction.skills:
            if skill.category in (SkillCategory.TOOL, SkillCategory.HARD):
                key = skill.name.lower()
                if key in bin_map and bin_map[key] not in bins:
                    bins.append(bin_map[key])
        return bins

    def _infer_env_vars(self, extraction: ExtractionResult) -> list[str]:
        """Infer environment variables from tool skills."""
        env_map = {
            "aws": "AWS_ACCESS_KEY_ID",
            "gcp": "GOOGLE_APPLICATION_CREDENTIALS",
            "azure": "AZURE_SUBSCRIPTION_ID",
            "openai": "OPENAI_API_KEY",
            "github": "GITHUB_TOKEN",
            "slack": "SLACK_TOKEN",
            "datadog": "DD_API_KEY",
        }
        envs: list[str] = []
        for skill in extraction.skills:
            key = skill.name.lower()
            if key in env_map and env_map[key] not in envs:
                envs.append(env_map[key])
        return envs

    # ------------------------------------------------------------------
    # Body
    # ------------------------------------------------------------------

    def _render_body(
        self,
        lines: list[str],
        extraction: ExtractionResult,
        jd: JobDescription | None,
        methodology: MethodologyExtraction | None,
    ) -> None:
        """Render concise, action-oriented body. No persona layer."""
        # Title + one-line purpose
        lines.append(f"# {extraction.role.title}")
        lines.append("")
        lines.append(extraction.role.purpose)
        lines.append("")

        has_methodology = methodology and (
            methodology.heuristics
            or methodology.trigger_mappings
            or methodology.output_templates
            or methodology.quality_criteria
        )

        if has_methodology:
            self._render_trigger_router(lines, methodology)
            self._render_decision_rules(lines, methodology)
            self._render_templates(lines, methodology)
            self._render_quality_bar(lines, methodology)
        else:
            self._render_simple_workflows(lines, extraction)

        self._render_skills_compact(lines, extraction)
        self._render_scope_compact(lines, extraction)
        self._render_footer(lines, extraction, jd)

    def _render_trigger_router(
        self, lines: list[str], methodology: MethodologyExtraction
    ) -> None:
        if not methodology.trigger_mappings:
            return
        lines.append("## Routing")
        lines.append("")
        for m in methodology.trigger_mappings:
            lines.append(f"**{m.trigger_pattern}** -> {m.technique}")
            if m.output_format:
                lines.append(f"  Output: {m.output_format}")
        lines.append("")

    def _render_decision_rules(
        self, lines: list[str], methodology: MethodologyExtraction
    ) -> None:
        if not methodology.heuristics:
            return
        lines.append("## Decision Rules")
        lines.append("")
        for h in methodology.heuristics:
            lines.append(f"### {h.trigger}")
            lines.append("")
            lines.append(h.procedure)
            lines.append("")

    def _render_templates(
        self, lines: list[str], methodology: MethodologyExtraction
    ) -> None:
        if not methodology.output_templates:
            return
        lines.append("## Templates")
        lines.append("")
        for t in methodology.output_templates:
            lines.append(f"### {t.name}")
            if t.when_to_use:
                lines.append(f"Use when: {t.when_to_use}")
            lines.append("")
            lines.append("```")
            lines.append(t.template)
            lines.append("```")
            lines.append("")

    def _render_quality_bar(
        self, lines: list[str], methodology: MethodologyExtraction
    ) -> None:
        if not methodology.quality_criteria:
            return
        lines.append("## Quality Bar")
        lines.append("")
        for c in methodology.quality_criteria:
            line = f"- [ ] {c.criterion}"
            if c.description:
                line += f" -- {c.description}"
            lines.append(line)
        lines.append("")

    def _render_simple_workflows(
        self, lines: list[str], extraction: ExtractionResult
    ) -> None:
        """Minimal workflow section when methodology is absent."""
        if not extraction.responsibilities:
            return
        lines.append("## Workflows")
        lines.append("")
        for resp in extraction.responsibilities:
            lines.append(f"- {resp}")
        lines.append("")

    def _render_skills_compact(
        self, lines: list[str], extraction: ExtractionResult
    ) -> None:
        """Compact skills listing — domain + tools only."""
        relevant = [
            s for s in extraction.skills
            if s.category in (SkillCategory.HARD, SkillCategory.TOOL, SkillCategory.DOMAIN)
        ]
        if not relevant:
            return
        lines.append("## Skills")
        lines.append("")
        for s in relevant:
            prof = s.proficiency.value
            line = f"- **{s.name}** ({prof})"
            if s.context:
                line += f" -- {s.context}"
            lines.append(line)
        lines.append("")

    def _render_scope_compact(
        self, lines: list[str], extraction: ExtractionResult
    ) -> None:
        """Compact scope: in-scope + guardrails."""
        if not extraction.role.scope_primary:
            return
        lines.append("## Scope")
        lines.append("")
        for item in extraction.role.scope_primary:
            lines.append(f"- {item}")
        if extraction.role.scope_secondary:
            lines.append("")
            lines.append("Secondary (defer when possible):")
            for item in extraction.role.scope_secondary:
                lines.append(f"- {item}")
        lines.append("")

    def _render_footer(
        self,
        lines: list[str],
        extraction: ExtractionResult,
        jd: JobDescription | None,
    ) -> None:
        source = "Unknown"
        if jd:
            source = jd.title
            if jd.company:
                source += f" at {jd.company}"
        lines.append("---")
        lines.append(
            f"*Generated by AgentForge | {source} | "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}*"
        )
        lines.append("")
