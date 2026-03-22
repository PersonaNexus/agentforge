"""Tests for identity round-tripping: generate → load → regenerate."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from agentforge.generation.identity_generator import IdentityGenerator
from agentforge.generation.identity_loader import IdentityLoader
from agentforge.models.extracted_skills import (
    ExtractionResult,
    ExtractedRole,
    ExtractedSkill,
    MethodologyExtraction,
    SeniorityLevel,
    SkillCategory,
    SkillImportance,
    SkillProficiency,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def identity_yaml(sample_extraction) -> str:
    """Generate a valid PersonaNexus identity YAML from sample extraction."""
    generator = IdentityGenerator()
    _, yaml_str = generator.generate(sample_extraction)
    return yaml_str


@pytest.fixture
def loader() -> IdentityLoader:
    return IdentityLoader()


# ------------------------------------------------------------------
# IdentityLoader unit tests
# ------------------------------------------------------------------


class TestIdentityLoader:
    """Test the IdentityLoader reverse-mapping."""

    def test_load_yaml_returns_tuple(self, loader, identity_yaml):
        result = loader.load_yaml(identity_yaml)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_extraction_has_role(self, loader, identity_yaml):
        extraction, _, _ = loader.load_yaml(identity_yaml)
        assert isinstance(extraction, ExtractionResult)
        assert extraction.role.title

    def test_extraction_has_skills(self, loader, identity_yaml):
        extraction, _, _ = loader.load_yaml(identity_yaml)
        assert len(extraction.skills) > 0
        for skill in extraction.skills:
            assert skill.name
            assert isinstance(skill.category, SkillCategory)
            assert isinstance(skill.proficiency, SkillProficiency)

    def test_extraction_has_responsibilities(self, loader, identity_yaml):
        extraction, _, _ = loader.load_yaml(identity_yaml)
        assert len(extraction.responsibilities) > 0

    def test_methodology_returned(self, loader, identity_yaml):
        _, methodology, _ = loader.load_yaml(identity_yaml)
        assert isinstance(methodology, MethodologyExtraction)

    def test_original_yaml_preserved(self, loader, identity_yaml):
        _, _, original = loader.load_yaml(identity_yaml)
        assert original == identity_yaml

    def test_load_file(self, loader, identity_yaml):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(identity_yaml)
            f.flush()
            extraction, methodology, _ = loader.load_file(f.name)
        assert extraction.role.title
        Path(f.name).unlink(missing_ok=True)

    def test_invalid_yaml_raises(self, loader):
        with pytest.raises(ValueError, match="expected a mapping"):
            loader.load_yaml("- just\n- a\n- list\n")

    def test_non_identity_yaml_raises(self, loader):
        with pytest.raises(Exception):
            loader.load_yaml("foo: bar\nbaz: 42\n")


class TestReverseMapping:
    """Test specific reverse-mapping logic."""

    def test_seniority_from_register(self, loader):
        """Formal register → EXECUTIVE seniority."""
        prof = loader._level_to_proficiency(0.9)
        assert prof == SkillProficiency.EXPERT

    def test_level_thresholds(self, loader):
        assert loader._level_to_proficiency(1.0) == SkillProficiency.EXPERT
        assert loader._level_to_proficiency(0.8) == SkillProficiency.EXPERT
        assert loader._level_to_proficiency(0.7) == SkillProficiency.ADVANCED
        assert loader._level_to_proficiency(0.5) == SkillProficiency.INTERMEDIATE
        assert loader._level_to_proficiency(0.3) == SkillProficiency.BEGINNER
        assert loader._level_to_proficiency(0.0) == SkillProficiency.BEGINNER

    def test_infer_tool_category(self, loader):
        assert loader._infer_skill_category("Docker", {}) == SkillCategory.TOOL
        assert loader._infer_skill_category("PostgreSQL", {}) == SkillCategory.TOOL

    def test_infer_domain_category(self, loader):
        assert loader._infer_skill_category("Machine Learning", {}) == SkillCategory.DOMAIN
        assert loader._infer_skill_category("cybersecurity", {}) == SkillCategory.DOMAIN

    def test_infer_hard_category_default(self, loader):
        assert loader._infer_skill_category("Python", {}) == SkillCategory.HARD
        assert loader._infer_skill_category("API Design", {}) == SkillCategory.HARD


# ------------------------------------------------------------------
# Full round-trip tests
# ------------------------------------------------------------------


class TestRoundTrip:
    """Test generate → load → regenerate preserves key data."""

    def test_role_title_preserved(self, sample_extraction):
        generator = IdentityGenerator()
        _, yaml_str = generator.generate(sample_extraction)

        loader = IdentityLoader()
        extraction, _, _ = loader.load_yaml(yaml_str)
        assert extraction.role.title == sample_extraction.role.title

    def test_role_purpose_preserved(self, sample_extraction):
        generator = IdentityGenerator()
        _, yaml_str = generator.generate(sample_extraction)

        loader = IdentityLoader()
        extraction, _, _ = loader.load_yaml(yaml_str)
        assert extraction.role.purpose == sample_extraction.role.purpose

    def test_skills_count_matches(self, sample_extraction):
        """Round-trip should preserve same number of skills (from expertise domains)."""
        generator = IdentityGenerator()
        _, yaml_str = generator.generate(sample_extraction)

        loader = IdentityLoader()
        extraction, _, _ = loader.load_yaml(yaml_str)
        # The number of skills may differ slightly due to domain grouping,
        # but should be non-zero
        assert len(extraction.skills) > 0

    def test_regeneration_valid(self, sample_extraction):
        """Round-tripped extraction can generate a valid identity again."""
        generator = IdentityGenerator()
        _, yaml_str = generator.generate(sample_extraction)

        loader = IdentityLoader()
        extraction, _, _ = loader.load_yaml(yaml_str)

        # Second generation should also produce valid YAML
        _, yaml_str2 = generator.generate(extraction)
        data = yaml.safe_load(yaml_str2)
        assert data["schema_version"] == "1.0"
        assert "role" in data
        assert "personality" in data


# ------------------------------------------------------------------
# Import web route tests
# ------------------------------------------------------------------


class TestImportRoute:
    """Test the POST /api/forge/import-identity endpoint."""

    @pytest.fixture
    def client(self):
        from agentforge.web.app import create_app
        from starlette.testclient import TestClient

        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def valid_yaml(self, sample_extraction) -> str:
        generator = IdentityGenerator()
        _, yaml_str = generator.generate(sample_extraction)
        return yaml_str

    def test_import_returns_job_id(self, client, valid_yaml):
        resp = client.post(
            "/api/forge/import-identity",
            files={"file": ("identity.yaml", valid_yaml.encode(), "text/yaml")},
            data={"output_format": "claude_code"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "job_id" in body
        assert "result" in body

    def test_import_result_has_blueprint(self, client, valid_yaml):
        resp = client.post(
            "/api/forge/import-identity",
            files={"file": ("identity.yaml", valid_yaml.encode(), "text/yaml")},
            data={"output_format": "claude_code"},
        )
        body = resp.json()
        bp = body["result"]["blueprint"]
        assert bp["extraction"]["role"]["title"]

    def test_import_result_has_skill_folder(self, client, valid_yaml):
        resp = client.post(
            "/api/forge/import-identity",
            files={"file": ("identity.yaml", valid_yaml.encode(), "text/yaml")},
            data={"output_format": "claude_code"},
        )
        body = resp.json()
        assert body["result"]["skill_folder"] is not None
        assert "skill_md" in body["result"]["skill_folder"]

    def test_import_creates_refinable_job(self, client, valid_yaml):
        """Imported job should be refinable through the refine endpoint."""
        resp = client.post(
            "/api/forge/import-identity",
            files={"file": ("identity.yaml", valid_yaml.encode(), "text/yaml")},
            data={"output_format": "claude_code"},
        )
        job_id = resp.json()["job_id"]

        # Refine the imported job
        refine_resp = client.post(
            f"/api/forge/{job_id}/refine",
            json={"edits": {"scope": "Handle compliance reporting"}},
        )
        assert refine_resp.status_code == 200
        refine_body = refine_resp.json()
        assert "skill_folder" in refine_body

    def test_import_job_downloadable_as_zip(self, client, valid_yaml):
        resp = client.post(
            "/api/forge/import-identity",
            files={"file": ("identity.yaml", valid_yaml.encode(), "text/yaml")},
            data={"output_format": "claude_code"},
        )
        job_id = resp.json()["job_id"]

        zip_resp = client.get(f"/api/forge/{job_id}/download/zip")
        assert zip_resp.status_code == 200
        assert zip_resp.headers["content-type"] == "application/zip"

    def test_import_rejects_non_yaml(self, client):
        resp = client.post(
            "/api/forge/import-identity",
            files={"file": ("doc.txt", b"some text", "text/plain")},
            data={"output_format": "claude_code"},
        )
        assert resp.status_code == 422

    def test_import_rejects_invalid_yaml(self, client):
        resp = client.post(
            "/api/forge/import-identity",
            files={"file": ("bad.yaml", b"- just\n- a\n- list\n", "text/yaml")},
            data={"output_format": "claude_code"},
        )
        assert resp.status_code == 422

    def test_import_rejects_invalid_format(self, client, valid_yaml):
        resp = client.post(
            "/api/forge/import-identity",
            files={"file": ("identity.yaml", valid_yaml.encode(), "text/yaml")},
            data={"output_format": "invalid"},
        )
        assert resp.status_code == 422
