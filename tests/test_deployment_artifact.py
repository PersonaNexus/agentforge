"""Validation tests for AgentForge → PersonaNexus public deployment artifacts.

Initiative: AgentForge templates that emit PersonaNexus deployment-ready agents
            (initiative id: 2b48116f, packet id: 6547f542)

What this covers
----------------
AgentForge's ``OpenClawCompiler`` produces an ``OpenClawOutput`` that is
intended to be a *public-deployment artifact* — a set of files that can be
dropped straight into an OpenClaw/PersonaNexus agent deployment without
manual fixup.

"Public deployment" means:

1. **Structural completeness** — all four required files are present:
   ``{agent}.SOUL.md``, ``{agent}.STYLE.md``, ``{agent}.personality.json``,
   ``{agent}.openclaw.json``.

2. **PersonaNexus schema compliance** — the generated identity YAML
   validates cleanly through ``PersonaNexus.IdentityValidator`` with no
   errors (warnings are acceptable for draft agents).

3. **SOUL.md sections** — a deployed agent must have at minimum ``Identity``,
   ``Guardrails``, and the role title heading so OpenClaw's runtime can parse
   the system prompt.

4. **openclaw.json contract** — the config JSON must carry ``name``,
   ``display_name``, ``domain``, and a ``files`` mapping so OpenClaw knows
   which files to load.

5. **personality.json contract** — must be valid JSON, include ``traits``
   (dict), ``domain``, and ``seniority``.

6. **Agent slug safety** — ``agent_name`` must not contain spaces or
   uppercase letters (slug is used as a directory name and file prefix).

7. **Methodology enrichment** — adding methodology should keep the artifact
   deployment-valid and enrich the SOUL.md with decision frameworks.

8. **Reference fixture round-trip** — the reference YAML fixture at
   ``tests/fixtures/senior_data_engineer_identity.yaml`` validates
   through PersonaNexus, confirming the fixture itself is a correct
   deployment baseline.
"""

from __future__ import annotations

import json
import re

import pytest
import yaml

from personanexus.validator import IdentityValidator

from agentforge.generation.openclaw_compiler import OpenClawOutput


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _file_by_suffix(output: OpenClawOutput, suffix: str) -> str:
    """Return content of the file in output.file_map() whose key ends with *suffix*."""
    files = output.file_map()
    matches = [v for k, v in files.items() if k.endswith(suffix)]
    assert matches, f"No file ending with {suffix!r} found in {list(files.keys())}"
    return matches[0]


# ---------------------------------------------------------------------------
# 1. Structural completeness
# ---------------------------------------------------------------------------

class TestDeploymentArtifactStructure:
    """Every public deployment artifact must contain all four required files."""

    def test_soul_md_present(self, deployment_artifact: OpenClawOutput) -> None:
        files = deployment_artifact.file_map()
        assert any(k.endswith(".SOUL.md") for k in files), \
            "SOUL.md missing from deployment artifact"

    def test_style_md_present(self, deployment_artifact: OpenClawOutput) -> None:
        files = deployment_artifact.file_map()
        assert any(k.endswith(".STYLE.md") for k in files), \
            "STYLE.md missing from deployment artifact"

    def test_personality_json_present(self, deployment_artifact: OpenClawOutput) -> None:
        files = deployment_artifact.file_map()
        assert any(k.endswith(".personality.json") for k in files), \
            "personality.json missing from deployment artifact"

    def test_openclaw_json_present(self, deployment_artifact: OpenClawOutput) -> None:
        files = deployment_artifact.file_map()
        assert any(k.endswith(".openclaw.json") for k in files), \
            "openclaw.json missing from deployment artifact"

    def test_all_four_required_files_present(self, deployment_artifact: OpenClawOutput) -> None:
        """Convenience: assert all four files at once so failure is unambiguous."""
        files = deployment_artifact.file_map()
        suffixes = {".SOUL.md", ".STYLE.md", ".personality.json", ".openclaw.json"}
        found = {s for s in suffixes if any(k.endswith(s) for k in files)}
        missing = suffixes - found
        assert not missing, f"Missing deployment files: {missing}"

    def test_file_map_keys_share_agent_slug(self, deployment_artifact: OpenClawOutput) -> None:
        """All file keys should be prefixed with the same agent slug."""
        files = deployment_artifact.file_map()
        slug = deployment_artifact.agent_name
        for key in files:
            assert key.startswith(slug), \
                f"File key {key!r} does not start with agent slug {slug!r}"

    def test_no_extra_required_files_without_skill_folder(
        self, deployment_artifact: OpenClawOutput
    ) -> None:
        """Without a skill folder, exactly four files should be in file_map()."""
        assert deployment_artifact.skill_folder is None, \
            "This test targets the no-skill-folder path"
        assert len(deployment_artifact.file_map()) == 4


# ---------------------------------------------------------------------------
# 2. PersonaNexus schema compliance
# ---------------------------------------------------------------------------

class TestPersonaNexusSchemaCompliance:
    """The identity YAML produced by AgentForge must pass PersonaNexus validation."""

    def test_identity_yaml_validates_via_personanexus(
        self, compiled_identity  # type: ignore[override]
    ) -> None:
        """identity YAML round-trips through PersonaNexus IdentityValidator
        with no errors (semantic warnings are allowed for draft agents).
        """
        _, yaml_str = compiled_identity
        data = yaml.safe_load(yaml_str)
        validator = IdentityValidator()
        result = validator.validate_dict(data)
        assert result.valid, \
            f"PersonaNexus validation failed:\n" + "\n".join(result.errors)

    def test_identity_yaml_has_correct_schema_version(
        self, compiled_identity  # type: ignore[override]
    ) -> None:
        _, yaml_str = compiled_identity
        data = yaml.safe_load(yaml_str)
        assert data.get("schema_version") == "1.0"

    def test_identity_yaml_has_required_sections(
        self, compiled_identity  # type: ignore[override]
    ) -> None:
        _, yaml_str = compiled_identity
        data = yaml.safe_load(yaml_str)
        for section in ("metadata", "role", "personality", "communication",
                        "principles", "guardrails"):
            assert section in data, f"Required PersonaNexus section {section!r} missing from identity YAML"

    def test_identity_has_valid_agent_id(
        self, compiled_identity  # type: ignore[override]
    ) -> None:
        """Metadata id must match PersonaNexus pattern ``agt_<slug>``."""
        _, yaml_str = compiled_identity
        data = yaml.safe_load(yaml_str)
        agent_id = data["metadata"]["id"]
        assert re.match(r"^agt_[a-zA-Z0-9_]+$", agent_id), \
            f"Invalid PersonaNexus agent id: {agent_id!r}"

    def test_identity_has_at_least_one_principle(
        self, compiled_identity  # type: ignore[override]
    ) -> None:
        _, yaml_str = compiled_identity
        data = yaml.safe_load(yaml_str)
        assert len(data.get("principles", [])) >= 1, \
            "PersonaNexus requires at least one principle"

    def test_identity_has_at_least_one_hard_guardrail(
        self, compiled_identity  # type: ignore[override]
    ) -> None:
        _, yaml_str = compiled_identity
        data = yaml.safe_load(yaml_str)
        hard = data.get("guardrails", {}).get("hard", [])
        assert len(hard) >= 1, \
            "Deployment artifact must include at least one hard guardrail"


# ---------------------------------------------------------------------------
# 3. SOUL.md section requirements
# ---------------------------------------------------------------------------

class TestSoulMdSections:
    """SOUL.md must contain the sections required by the OpenClaw runtime."""

    def test_soul_md_contains_role_title(self, deployment_artifact: OpenClawOutput) -> None:
        assert "Senior Data Engineer" in deployment_artifact.soul_md

    def test_soul_md_has_identity_section(self, deployment_artifact: OpenClawOutput) -> None:
        assert "## Identity" in deployment_artifact.soul_md

    def test_soul_md_has_guardrails_section(self, deployment_artifact: OpenClawOutput) -> None:
        assert "## Guardrails" in deployment_artifact.soul_md

    def test_soul_md_has_responsibilities_section(
        self, deployment_artifact: OpenClawOutput
    ) -> None:
        assert "## Core Responsibilities" in deployment_artifact.soul_md

    def test_soul_md_has_agentforge_generation_footer(
        self, deployment_artifact: OpenClawOutput
    ) -> None:
        assert "Generated by AgentForge" in deployment_artifact.soul_md

    def test_soul_md_not_empty(self, deployment_artifact: OpenClawOutput) -> None:
        assert len(deployment_artifact.soul_md.strip()) > 100


# ---------------------------------------------------------------------------
# 4. openclaw.json contract
# ---------------------------------------------------------------------------

class TestOpenClawJsonContract:
    """openclaw.json must carry the fields the OpenClaw runtime expects."""

    def _config(self, output: OpenClawOutput) -> dict:
        return json.loads(output.openclaw_json)

    def test_openclaw_json_is_valid_json(self, deployment_artifact: OpenClawOutput) -> None:
        # Will raise if invalid
        json.loads(deployment_artifact.openclaw_json)

    def test_openclaw_json_has_name(self, deployment_artifact: OpenClawOutput) -> None:
        config = self._config(deployment_artifact)
        assert "name" in config
        assert config["name"] == deployment_artifact.agent_name

    def test_openclaw_json_has_display_name(self, deployment_artifact: OpenClawOutput) -> None:
        config = self._config(deployment_artifact)
        assert "display_name" in config
        assert len(config["display_name"]) > 0

    def test_openclaw_json_has_domain(self, deployment_artifact: OpenClawOutput) -> None:
        config = self._config(deployment_artifact)
        assert "domain" in config

    def test_openclaw_json_has_files_mapping(self, deployment_artifact: OpenClawOutput) -> None:
        config = self._config(deployment_artifact)
        assert "files" in config
        files = config["files"]
        for key in ("soul", "style", "personality", "skills"):
            assert key in files, f"openclaw.json files mapping missing {key!r}"

    def test_openclaw_json_files_reference_agent_slug(
        self, deployment_artifact: OpenClawOutput
    ) -> None:
        config = self._config(deployment_artifact)
        slug = deployment_artifact.agent_name
        for key, path in config["files"].items():
            assert path.startswith(slug), \
                f"openclaw.json files.{key}={path!r} doesn't reference agent slug {slug!r}"

    def test_openclaw_json_schedule_absent_by_default(
        self, deployment_artifact: OpenClawOutput
    ) -> None:
        """No schedule key should appear in the config unless one was provided."""
        config = self._config(deployment_artifact)
        assert "schedule" not in config


# ---------------------------------------------------------------------------
# 5. personality.json contract
# ---------------------------------------------------------------------------

class TestPersonalityJsonContract:
    """personality.json must be valid JSON with the required runtime fields."""

    def _data(self, output: OpenClawOutput) -> dict:
        return json.loads(output.personality_json)

    def test_personality_json_is_valid_json(self, deployment_artifact: OpenClawOutput) -> None:
        json.loads(deployment_artifact.personality_json)

    def test_personality_json_has_traits(self, deployment_artifact: OpenClawOutput) -> None:
        data = self._data(deployment_artifact)
        assert "traits" in data
        assert isinstance(data["traits"], dict)
        assert len(data["traits"]) >= 1

    def test_personality_json_has_domain(self, deployment_artifact: OpenClawOutput) -> None:
        data = self._data(deployment_artifact)
        assert "domain" in data
        assert len(data["domain"]) > 0

    def test_personality_json_has_seniority(self, deployment_artifact: OpenClawOutput) -> None:
        data = self._data(deployment_artifact)
        assert "seniority" in data

    def test_personality_json_traits_in_valid_range(
        self, deployment_artifact: OpenClawOutput
    ) -> None:
        """All trait values must be in [0.0, 1.0] — PersonaNexus enforces this."""
        data = self._data(deployment_artifact)
        for trait_name, value in data.get("traits", {}).items():
            assert 0.0 <= value <= 1.0, \
                f"Trait {trait_name}={value} is outside PersonaNexus [0, 1] range"

    def test_personality_json_has_communication_block(
        self, deployment_artifact: OpenClawOutput
    ) -> None:
        data = self._data(deployment_artifact)
        assert "communication" in data


# ---------------------------------------------------------------------------
# 6. Agent slug safety
# ---------------------------------------------------------------------------

class TestAgentSlugSafety:
    """agent_name is used as a filesystem prefix and must be a clean slug."""

    def test_agent_name_has_no_spaces(self, deployment_artifact: OpenClawOutput) -> None:
        assert " " not in deployment_artifact.agent_name, \
            f"agent_name {deployment_artifact.agent_name!r} contains spaces"

    def test_agent_name_is_lowercase(self, deployment_artifact: OpenClawOutput) -> None:
        assert deployment_artifact.agent_name == deployment_artifact.agent_name.lower(), \
            f"agent_name {deployment_artifact.agent_name!r} is not lowercase"

    def test_agent_name_is_safe_path(self, deployment_artifact: OpenClawOutput) -> None:
        """agent_name should only contain alphanumeric chars and hyphens."""
        assert re.fullmatch(r"[a-z0-9][a-z0-9\-]*", deployment_artifact.agent_name), \
            f"agent_name {deployment_artifact.agent_name!r} contains unsafe path characters"

    def test_agent_name_matches_sample_role(self, deployment_artifact: OpenClawOutput) -> None:
        """Senior Data Engineer should become 'senior-data-engineer'."""
        assert deployment_artifact.agent_name == "senior-data-engineer"


# ---------------------------------------------------------------------------
# 7. Methodology enrichment preserves deployment validity
# ---------------------------------------------------------------------------

class TestMethodologyEnrichment:
    """Adding methodology context must keep the artifact deployment-valid."""

    def test_all_four_files_still_present(
        self, deployment_artifact_with_methodology: OpenClawOutput
    ) -> None:
        files = deployment_artifact_with_methodology.file_map()
        suffixes = {".SOUL.md", ".STYLE.md", ".personality.json", ".openclaw.json"}
        missing = {s for s in suffixes if not any(k.endswith(s) for k in files)}
        assert not missing, f"Missing after methodology enrichment: {missing}"

    def test_soul_md_contains_decision_frameworks(
        self, deployment_artifact_with_methodology: OpenClawOutput
    ) -> None:
        assert "## Decision Frameworks" in deployment_artifact_with_methodology.soul_md, \
            "SOUL.md should contain ## Decision Frameworks when methodology is provided"

    def test_soul_md_contains_routing_section(
        self, deployment_artifact_with_methodology: OpenClawOutput
    ) -> None:
        assert "## Routing" in deployment_artifact_with_methodology.soul_md

    def test_soul_md_contains_heuristic_trigger(
        self, deployment_artifact_with_methodology: OpenClawOutput
    ) -> None:
        assert "evaluating data pipeline performance" in \
            deployment_artifact_with_methodology.soul_md

    def test_methodology_openclaw_json_still_valid(
        self, deployment_artifact_with_methodology: OpenClawOutput
    ) -> None:
        config = json.loads(deployment_artifact_with_methodology.openclaw_json)
        assert "name" in config
        assert "files" in config

    def test_methodology_identity_yaml_still_validates(
        self, compiled_identity  # type: ignore[override]
    ) -> None:
        """Methodology doesn't touch the identity YAML — it should still validate."""
        _, yaml_str = compiled_identity
        data = yaml.safe_load(yaml_str)
        validator = IdentityValidator()
        result = validator.validate_dict(data)
        assert result.valid


# ---------------------------------------------------------------------------
# 8. Reference fixture round-trip
# ---------------------------------------------------------------------------

class TestReferenceFixtureRoundTrip:
    """The reference YAML fixture in tests/fixtures/ should be PersonaNexus-valid.

    This guards against bit-rot: if the PersonaNexus schema evolves and the
    fixture becomes invalid, this test catches it before any agent is deployed.
    """

    def test_reference_identity_yaml_validates(self, fixtures_dir) -> None:
        fixture_path = fixtures_dir / "senior_data_engineer_identity.yaml"
        assert fixture_path.exists(), \
            f"Reference fixture not found at {fixture_path}"
        validator = IdentityValidator()
        result = validator.validate_file(fixture_path)
        assert result.valid, \
            (f"Reference fixture failed PersonaNexus validation:\n"
             + "\n".join(result.errors))

    def test_reference_fixture_schema_version(self, fixtures_dir) -> None:
        fixture_path = fixtures_dir / "senior_data_engineer_identity.yaml"
        data = yaml.safe_load(fixture_path.read_text())
        assert data["schema_version"] == "1.0"

    def test_reference_fixture_has_agentforge_tags(self, fixtures_dir) -> None:
        fixture_path = fixtures_dir / "senior_data_engineer_identity.yaml"
        data = yaml.safe_load(fixture_path.read_text())
        tags = data.get("metadata", {}).get("tags", [])
        assert "agentforge" in tags, \
            "Reference fixture should carry 'agentforge' provenance tag"
        assert "generated" in tags, \
            "Reference fixture should carry 'generated' provenance tag"

    def test_reference_fixture_has_hard_guardrails(self, fixtures_dir) -> None:
        fixture_path = fixtures_dir / "senior_data_engineer_identity.yaml"
        data = yaml.safe_load(fixture_path.read_text())
        hard = data.get("guardrails", {}).get("hard", [])
        assert len(hard) >= 1

    def test_reference_fixture_principles_unique_priorities(self, fixtures_dir) -> None:
        fixture_path = fixtures_dir / "senior_data_engineer_identity.yaml"
        data = yaml.safe_load(fixture_path.read_text())
        priorities = [p["priority"] for p in data.get("principles", [])]
        assert len(priorities) == len(set(priorities)), \
            "Principle priorities must be unique in reference fixture"
