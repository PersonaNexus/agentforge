"""Tests for PersonaNexus deployment package generation."""

from __future__ import annotations

import yaml

from agentforge.generation.identity_generator import IdentityGenerator
from agentforge.generation.personanexus_deployment import PersonaNexusDeploymentCompiler
from agentforge.generation.skill_folder import SkillFolderGenerator


def test_personanexus_deployment_package_contains_expected_files(sample_extraction):
    identity, identity_yaml = IdentityGenerator().generate(sample_extraction)
    skill_folder = SkillFolderGenerator().generate(sample_extraction, identity)

    output = PersonaNexusDeploymentCompiler().compile(
        extraction=sample_extraction,
        identity_yaml=identity_yaml,
        identity=identity,
        skill_folder=skill_folder,
    )

    files = output.file_map()

    assert files["agent_identity.yaml"] == identity_yaml
    assert "compiled_prompt.md" in files
    assert "deployment.yaml" in files
    assert "README.md" in files
    assert f"{output.agent_name}-skills/SKILL.md" in files


def test_personanexus_deployment_manifest_has_validate_commands(sample_extraction):
    identity, identity_yaml = IdentityGenerator().generate(sample_extraction)

    output = PersonaNexusDeploymentCompiler().compile(
        extraction=sample_extraction,
        identity_yaml=identity_yaml,
        identity=identity,
    )

    manifest = yaml.safe_load(output.deployment_yaml)

    assert manifest["runtime"] == "personanexus"
    assert manifest["files"]["identity"] == "agent_identity.yaml"
    assert manifest["commands"]["validate"] == "personanexus validate agent_identity.yaml"
    assert (
        manifest["commands"]["compile"] == "personanexus compile agent_identity.yaml --target text"
    )


def test_personanexus_deployment_compiled_prompt_mentions_role(sample_extraction):
    identity, identity_yaml = IdentityGenerator().generate(sample_extraction)

    output = PersonaNexusDeploymentCompiler().compile(
        extraction=sample_extraction,
        identity_yaml=identity_yaml,
        identity=identity,
    )

    assert sample_extraction.role.title in output.compiled_prompt_md
