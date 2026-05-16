"""Build PersonaNexus deployment-ready agent packages.

The normal AgentForge output is a PersonaNexus identity plus optional skill files.
This module packages that identity with the compiled prompt, a deployment manifest,
and operator instructions so the artifact can be validated and deployed without a
manual AgentForge → PersonaNexus handoff.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import yaml
from personanexus.compiler import compile_identity
from pydantic import BaseModel, Field

from agentforge.generation.skill_folder import SkillFolderResult
from agentforge.models.extracted_skills import ExtractionResult, MethodologyExtraction


class PersonaNexusDeploymentOutput(BaseModel):
    """Container for PersonaNexus deployment-ready files."""

    agent_name: str = Field(..., description="Agent identifier (slug)")
    identity_yaml: str = Field(..., description="PersonaNexus identity YAML")
    compiled_prompt_md: str = Field(..., description="Compiled PersonaNexus text prompt")
    deployment_yaml: str = Field(..., description="Deployment manifest")
    readme_md: str = Field(..., description="Operator README")
    skill_folder: SkillFolderResult | None = Field(
        None, description="Optional Claude Code skill folder"
    )

    def file_map(self) -> dict[str, str]:
        """Return {relative_path: content} for all package files."""
        files = {
            "agent_identity.yaml": self.identity_yaml,
            "compiled_prompt.md": self.compiled_prompt_md,
            "deployment.yaml": self.deployment_yaml,
            "README.md": self.readme_md,
        }

        if self.skill_folder:
            prefix = f"{self.agent_name}-skills"
            files[f"{prefix}/SKILL.md"] = self.skill_folder.skill_md_with_references()
            for rel_path, content in self.skill_folder.supplementary_files.items():
                files[f"{prefix}/{rel_path}"] = content

        return files


class PersonaNexusDeploymentCompiler:
    """Compile pipeline output into a PersonaNexus deployment package."""

    def compile(
        self,
        extraction: ExtractionResult,
        identity_yaml: str,
        identity: Any,
        methodology: MethodologyExtraction | None = None,
        skill_folder: SkillFolderResult | None = None,
    ) -> PersonaNexusDeploymentOutput:
        """Build deployment-ready PersonaNexus files from pipeline context."""
        from agentforge.utils import make_skill_slug

        agent_name = make_skill_slug(extraction.role.title)
        compiled_prompt = compile_identity(identity, target="text")
        if not isinstance(compiled_prompt, str):
            compiled_prompt = yaml.safe_dump(compiled_prompt, sort_keys=False)

        deployment_yaml = self._build_deployment_yaml(
            extraction=extraction,
            identity=identity,
            agent_name=agent_name,
            methodology=methodology,
            has_skill_folder=bool(skill_folder),
        )
        readme_md = self._build_readme_md(
            extraction, agent_name, has_skill_folder=bool(skill_folder)
        )

        return PersonaNexusDeploymentOutput(
            agent_name=agent_name,
            identity_yaml=identity_yaml,
            compiled_prompt_md=compiled_prompt,
            deployment_yaml=deployment_yaml,
            readme_md=readme_md,
            skill_folder=skill_folder,
        )

    def _build_deployment_yaml(
        self,
        extraction: ExtractionResult,
        identity: Any,
        agent_name: str,
        methodology: MethodologyExtraction | None,
        has_skill_folder: bool,
    ) -> str:
        """Build a small manifest that describes how to validate/deploy the package."""
        files: dict[str, str] = {
            "identity": "agent_identity.yaml",
            "compiled_prompt": "compiled_prompt.md",
            "readme": "README.md",
        }
        if has_skill_folder:
            files["skill_folder"] = f"{agent_name}-skills/"

        manifest: dict[str, Any] = {
            "schema_version": "1.0",
            "runtime": "personanexus",
            "generated_by": "agentforge",
            "generated_at": datetime.now(UTC).isoformat(),
            "agent": {
                "id": getattr(getattr(identity, "metadata", None), "id", agent_name),
                "name": getattr(getattr(identity, "metadata", None), "name", extraction.role.title),
                "slug": agent_name,
                "role": extraction.role.title,
                "domain": extraction.role.domain,
            },
            "files": files,
            "commands": {
                "validate": "personanexus validate agent_identity.yaml",
                "compile": "personanexus compile agent_identity.yaml --target text",
                "analyze": "personanexus analyze agent_identity.yaml",
            },
            "readiness_checks": [
                "Run the validate command before deployment.",
                "Review compiled_prompt.md for role fit and guardrail coverage.",
                "Attach or install the skill folder when the target runtime supports skills.",
            ],
        }

        if methodology and methodology.has_content():
            manifest["methodology"] = {
                "heuristics": len(methodology.heuristics),
                "trigger_mappings": len(methodology.trigger_mappings),
                "output_templates": len(methodology.output_templates),
                "quality_criteria": len(methodology.quality_criteria),
            }

        return yaml.safe_dump(manifest, sort_keys=False)

    def _build_readme_md(
        self,
        extraction: ExtractionResult,
        agent_name: str,
        has_skill_folder: bool,
    ) -> str:
        """Build operator-facing deployment instructions."""
        lines = [
            f"# {extraction.role.title} — PersonaNexus Deployment Package",
            "",
            f"> {extraction.role.purpose}",
            "",
            "This package was generated by AgentForge for PersonaNexus-first deployment.",
            "It includes the source identity, a compiled prompt artifact, and a manifest",
            "with validation/compile commands.",
            "",
            "## Files",
            "",
            "- `agent_identity.yaml` — canonical PersonaNexus identity",
            "- `compiled_prompt.md` — compiled text prompt for runtimes that need a prompt file",
            "- `deployment.yaml` — deployment manifest and readiness checklist",
        ]
        if has_skill_folder:
            lines.append(
                f"- `{agent_name}-skills/` — optional skill folder for skill-capable runtimes"
            )
        lines.extend(
            [
                "",
                "## Validate",
                "",
                "```bash",
                "personanexus validate agent_identity.yaml",
                "personanexus analyze agent_identity.yaml",
                "```",
                "",
                "## Compile or refresh the prompt",
                "",
                "```bash",
                "personanexus compile agent_identity.yaml --target text",
                "```",
                "",
                "## Deploy",
                "",
                "1. Validate `agent_identity.yaml`.",
                "2. Review `compiled_prompt.md` and any skill-folder instructions.",
                "3. Install the identity/prompt into the target runtime using that runtime's "
                "normal deploy path.",
                "",
                "## Role scope",
                "",
                f"- Domain: {extraction.role.domain}",
            ]
        )
        for item in extraction.role.scope_primary:
            lines.append(f"- {item}")
        lines.append("")
        return "\n".join(lines)
