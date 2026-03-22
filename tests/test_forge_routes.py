"""Comprehensive tests for forge web routes: zip download, refine, attachments."""

from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agentforge.web.app import create_app
from agentforge.web.jobs import Job, JobStore


# ---------------------------------------------------------------------------
# Helpers — build a minimal completed job result matching the real shape
# ---------------------------------------------------------------------------

def _make_skill_folder_result(
    skill_name: str = "senior-data-engineer",
    skill_md: str = "---\nname: senior-data-engineer\n---\n# Senior Data Engineer",
    supplementary_files: dict[str, str] | None = None,
) -> dict:
    return {
        "skill_md": skill_md,
        "skill_name": skill_name,
        "supplementary_files": supplementary_files or {},
    }


def _make_clawhub_result(
    skill_name: str = "senior-data-engineer",
    skill_md: str = "# Senior Data Engineer (ClawHub)",
) -> dict:
    return {"skill_md": skill_md, "skill_name": skill_name}


def _make_extraction_dict() -> dict:
    """Minimal extraction result as JSON-serialisable dict."""
    return {
        "role": {
            "title": "Senior Data Engineer",
            "purpose": "Design and build data infrastructure",
            "scope_primary": ["ETL pipelines"],
            "scope_secondary": [],
            "audience": ["Data scientists"],
            "seniority": "senior",
            "domain": "Data Engineering",
        },
        "skills": [
            {
                "name": "Python",
                "category": "hard",
                "proficiency": "advanced",
                "importance": "required",
                "context": "Primary language",
                "examples": [],
                "genai_application": None,
            },
        ],
        "responsibilities": ["Design ETL pipelines"],
        "qualifications": ["5+ years experience"],
        "suggested_traits": {"rigor": 0.85, "directness": 0.7},
        "automation_potential": 0.35,
        "automation_rationale": "Requires architectural judgment",
    }


def _make_methodology_dict() -> dict:
    return {
        "heuristics": [],
        "output_templates": [],
        "trigger_mappings": [],
        "quality_criteria": [],
    }


def _make_job_result(
    include_clawhub: bool = False,
    supplementary_files: dict[str, str] | None = None,
) -> dict:
    """Build a complete job result dict like the pipeline produces."""
    result: dict = {
        "blueprint": {
            "extraction": _make_extraction_dict(),
            "automation_estimate": 0.35,
        },
        "identity_yaml": "name: senior-data-engineer\ntraits:\n  rigor: 0.85\n",
        "source_filename": "senior_data_engineer",
        "traits": {"rigor": 0.85},
        "coverage_score": 0.72,
        "coverage_gaps": ["Missing domain context"],
        "skill_scores": None,
        "skill_folder": _make_skill_folder_result(
            supplementary_files=supplementary_files,
        ),
        "skill_gaps": [],
        "_refine_context": {
            "extraction": _make_extraction_dict(),
            "methodology": _make_methodology_dict(),
            "identity_yaml": "name: senior-data-engineer\n",
            "output_format": "claude_code",
            "user_examples": "",
            "user_frameworks": "",
        },
    }
    if include_clawhub:
        result["clawhub_skill"] = _make_clawhub_result()
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a fresh FastAPI app for testing."""
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def store(app) -> JobStore:
    return app.state.jobs


@pytest.fixture
def completed_job(store) -> Job:
    """A job that has finished with a typical result set."""
    job = store.create()
    job.status = "done"
    job.result = _make_job_result()
    return job


@pytest.fixture
def completed_job_with_clawhub(store) -> Job:
    job = store.create()
    job.status = "done"
    job.result = _make_job_result(include_clawhub=True)
    return job


@pytest.fixture
def completed_job_with_refs(store) -> Job:
    job = store.create()
    job.status = "done"
    job.result = _make_job_result(supplementary_files={
        "references/work-examples.md": "# Examples\nSome work samples",
        "references/frameworks.md": "# Frameworks\nRICE scoring",
    })
    return job


# ===================================================================
# ZIP DOWNLOAD TESTS
# ===================================================================

class TestZipDownload:
    """Tests for the /forge/{job_id}/download/zip endpoint."""

    def test_zip_download_returns_200(self, client, completed_job):
        resp = client.get(f"/api/forge/{completed_job.id}/download/zip")
        assert resp.status_code == 200

    def test_zip_has_correct_content_type(self, client, completed_job):
        resp = client.get(f"/api/forge/{completed_job.id}/download/zip")
        assert resp.headers["content-type"] == "application/zip"

    def test_zip_has_content_disposition(self, client, completed_job):
        resp = client.get(f"/api/forge/{completed_job.id}/download/zip")
        cd = resp.headers["content-disposition"]
        assert "attachment" in cd
        assert "senior_data_engineer_skill.zip" in cd

    def test_zip_contains_skill_md(self, client, completed_job):
        resp = client.get(f"/api/forge/{completed_job.id}/download/zip")
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert "senior-data-engineer/SKILL.md" in names

    def test_zip_contains_identity_yaml(self, client, completed_job):
        resp = client.get(f"/api/forge/{completed_job.id}/download/zip")
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert "senior-data-engineer/agent_identity.yaml" in names

    def test_zip_contains_clawhub_when_present(self, client, completed_job_with_clawhub):
        resp = client.get(f"/api/forge/{completed_job_with_clawhub.id}/download/zip")
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert "senior-data-engineer/CLAWHUB_SKILL.md" in names

    def test_zip_omits_clawhub_when_absent(self, client, completed_job):
        resp = client.get(f"/api/forge/{completed_job.id}/download/zip")
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert all("CLAWHUB" not in n for n in names)

    def test_zip_contains_supplementary_files(self, client, completed_job_with_refs):
        resp = client.get(f"/api/forge/{completed_job_with_refs.id}/download/zip")
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert "senior-data-engineer/references/work-examples.md" in names
            assert "senior-data-engineer/references/frameworks.md" in names

    def test_zip_file_contents_match(self, client, completed_job):
        resp = client.get(f"/api/forge/{completed_job.id}/download/zip")
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            skill_md = zf.read("senior-data-engineer/SKILL.md").decode()
            assert "Senior Data Engineer" in skill_md

    def test_zip_is_valid_archive(self, client, completed_job):
        resp = client.get(f"/api/forge/{completed_job.id}/download/zip")
        buf = io.BytesIO(resp.content)
        assert zipfile.is_zipfile(buf)

    def test_zip_404_for_unknown_job(self, client):
        resp = client.get("/api/forge/nonexistent/download/zip")
        assert resp.status_code == 404

    def test_zip_404_for_incomplete_job(self, client, store):
        job = store.create()
        job.status = "running"
        resp = client.get(f"/api/forge/{job.id}/download/zip")
        assert resp.status_code == 404

    def test_zip_404_when_no_skill_folder(self, client, store):
        job = store.create()
        job.status = "done"
        job.result = {"identity_yaml": "name: test\n"}
        resp = client.get(f"/api/forge/{job.id}/download/zip")
        assert resp.status_code == 404


# ===================================================================
# ROUTE ORDERING — zip must not be shadowed by {file_type}
# ===================================================================

class TestRouteOrdering:
    """Verify that /download/zip is not shadowed by /download/{file_type}."""

    def test_zip_route_not_intercepted_by_file_type(self, client, completed_job):
        """The zip route must return a zip, not a 400 'Invalid file type'."""
        resp = client.get(f"/api/forge/{completed_job.id}/download/zip")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

    def test_individual_file_routes_still_work(self, client, completed_job):
        """yaml/skill downloads should still work after reorder."""
        resp_yaml = client.get(f"/api/forge/{completed_job.id}/download/yaml")
        assert resp_yaml.status_code == 200
        assert "text/yaml" in resp_yaml.headers["content-type"]

        resp_skill = client.get(f"/api/forge/{completed_job.id}/download/skill")
        assert resp_skill.status_code == 200
        assert "SKILL.md" in resp_skill.headers.get("content-disposition", "")

    def test_invalid_file_type_returns_400(self, client, completed_job):
        resp = client.get(f"/api/forge/{completed_job.id}/download/nonsense")
        assert resp.status_code == 400


# ===================================================================
# INDIVIDUAL FILE DOWNLOAD TESTS
# ===================================================================

class TestFileDownloads:
    """Tests for /forge/{job_id}/download/{file_type} variants."""

    def test_download_yaml(self, client, completed_job):
        resp = client.get(f"/api/forge/{completed_job.id}/download/yaml")
        assert resp.status_code == 200
        assert "rigor" in resp.text

    def test_download_skill_md(self, client, completed_job):
        resp = client.get(f"/api/forge/{completed_job.id}/download/skill")
        assert resp.status_code == 200
        assert "Senior Data Engineer" in resp.text

    def test_download_clawhub(self, client, completed_job_with_clawhub):
        resp = client.get(f"/api/forge/{completed_job_with_clawhub.id}/download/clawhub")
        assert resp.status_code == 200
        assert "ClawHub" in resp.text

    def test_download_clawhub_404_when_absent(self, client, completed_job):
        resp = client.get(f"/api/forge/{completed_job.id}/download/clawhub")
        assert resp.status_code == 404


# ===================================================================
# REFINE ENDPOINT TESTS
# ===================================================================

class TestRefineEndpoint:
    """Tests for POST /forge/{job_id}/refine."""

    def _refine_json(self, client, job_id, edits):
        return client.post(
            f"/api/forge/{job_id}/refine",
            json={"edits": edits},
        )

    def _refine_multipart(self, client, job_id, edits, files=None, file_categories=None):
        data = {"edits": json.dumps(edits)}
        if file_categories is not None:
            data["file_categories"] = json.dumps(file_categories)
        upload_files = []
        if files:
            for fname, content in files.items():
                upload_files.append(("files", (fname, content.encode(), "text/plain")))
        return client.post(
            f"/api/forge/{job_id}/refine",
            data=data,
            files=upload_files or None,
        )

    def test_refine_with_text_returns_200(self, client, completed_job):
        resp = self._refine_json(client, completed_job.id, {"methodology": "When evaluating data, check schema first"})
        assert resp.status_code == 200

    def test_refine_returns_updated_skill_folder(self, client, completed_job):
        resp = self._refine_json(client, completed_job.id, {"methodology": "Check schema first"})
        data = resp.json()
        assert "skill_folder" in data
        assert data["skill_folder"]["skill_md"]

    def test_refine_returns_updated_gaps(self, client, completed_job):
        resp = self._refine_json(client, completed_job.id, {"methodology": "Check schema first"})
        data = resp.json()
        assert "skill_gaps" in data
        assert isinstance(data["skill_gaps"], list)

    def test_refine_returns_identity_yaml(self, client, completed_job):
        resp = self._refine_json(client, completed_job.id, {"scope": "Data governance"})
        data = resp.json()
        assert "identity_yaml" in data
        assert data["identity_yaml"]

    def test_refine_404_for_unknown_job(self, client):
        resp = client.post(
            "/api/forge/nonexistent/refine",
            json={"edits": {"methodology": "test"}},
        )
        assert resp.status_code == 404

    def test_refine_400_with_empty_edits(self, client, completed_job):
        resp = self._refine_json(client, completed_job.id, {})
        assert resp.status_code == 400

    def test_refine_methodology_adds_heuristics(self, client, completed_job):
        resp = self._refine_json(client, completed_job.id, {
            "methodology": "1. Check for schema drift\n2. Validate data freshness",
        })
        data = resp.json()
        # The skill should now reference the methodology
        assert data["skill_folder"]["skill_md"]
        assert resp.status_code == 200

    def test_refine_scope_extends_secondary(self, client, completed_job):
        resp = self._refine_json(client, completed_job.id, {
            "scope": "Data governance, Privacy compliance",
        })
        assert resp.status_code == 200

    def test_refine_persona_adjusts_traits(self, client, completed_job):
        resp = self._refine_json(client, completed_job.id, {
            "persona": "warm and friendly, very patient with junior devs",
        })
        data = resp.json()
        assert resp.status_code == 200
        assert data["identity_yaml"]

    def test_refine_preserves_context_across_cycles(self, client, completed_job):
        """Multiple refine calls should accumulate changes."""
        self._refine_json(client, completed_job.id, {"methodology": "Check schema first"})
        resp2 = self._refine_json(client, completed_job.id, {"scope": "Data governance"})
        assert resp2.status_code == 200

    def test_refine_updates_stored_job_result(self, client, completed_job):
        self._refine_json(client, completed_job.id, {"methodology": "Check schema first"})
        # The stored job result should be updated
        assert "skill_folder" in completed_job.result


# ===================================================================
# REFINE WITH FILE ATTACHMENTS
# ===================================================================

class TestRefineWithAttachments:
    """Tests for refine endpoint with file uploads and category tracking."""

    def test_refine_with_files_returns_200(self, client, completed_job):
        resp = client.post(
            f"/api/forge/{completed_job.id}/refine",
            data={
                "edits": json.dumps({}),
                "file_categories": json.dumps(["examples"]),
            },
            files=[("files", ("sample.md", b"# My Work Sample\nHere is how I do ETL...", "text/plain"))],
        )
        assert resp.status_code == 200

    def test_file_categories_suppress_example_gap(self, client, completed_job):
        """Attaching files with examples category should suppress the examples gap."""
        resp = client.post(
            f"/api/forge/{completed_job.id}/refine",
            data={
                "edits": json.dumps({"methodology": "Check schema first"}),
                "file_categories": json.dumps(["examples"]),
            },
            files=[("files", ("sample.md", b"# Sample ETL work", "text/plain"))],
        )
        data = resp.json()
        # The examples gap should not appear after providing example files
        example_gaps = [g for g in data["skill_gaps"] if g["category"] == "examples"]
        assert len(example_gaps) == 0

    def test_file_categories_suppress_frameworks_gap(self, client, completed_job):
        resp = client.post(
            f"/api/forge/{completed_job.id}/refine",
            data={
                "edits": json.dumps({"methodology": "Use schema-first approach"}),
                "file_categories": json.dumps(["frameworks"]),
            },
            files=[("files", ("framework.md", b"# RICE Scoring Framework\n...", "text/plain"))],
        )
        data = resp.json()
        framework_gaps = [g for g in data["skill_gaps"] if g["category"] == "frameworks"]
        assert len(framework_gaps) == 0

    def test_has_references_flag_set_with_files(self, client, completed_job):
        resp = client.post(
            f"/api/forge/{completed_job.id}/refine",
            data={
                "edits": json.dumps({}),
                "file_categories": json.dumps(["examples"]),
            },
            files=[("files", ("sample.md", b"Work sample content", "text/plain"))],
        )
        data = resp.json()
        assert data["has_references"] is True

    def test_uploaded_files_persist_in_refine_context(self, client, completed_job):
        """Uploaded files should be stored in the refine context for future cycles."""
        client.post(
            f"/api/forge/{completed_job.id}/refine",
            data={
                "edits": json.dumps({}),
                "file_categories": json.dumps(["examples"]),
            },
            files=[("files", ("sample.md", b"Work sample content", "text/plain"))],
        )
        # Check that supplementary files are in the stored context
        supp = completed_job.result.get("_refine_context", {}).get("supplementary_files", {})
        assert any("sample" in k for k in supp)

    def test_uploaded_files_included_in_zip(self, client, completed_job):
        """After refine with files, the zip should include them."""
        client.post(
            f"/api/forge/{completed_job.id}/refine",
            data={
                "edits": json.dumps({}),
                "file_categories": json.dumps(["examples"]),
            },
            files=[("files", ("my-report.md", b"# Report\nContent here", "text/plain"))],
        )
        resp = client.get(f"/api/forge/{completed_job.id}/download/zip")
        assert resp.status_code == 200
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            # Should have a reference file in the zip
            ref_files = [n for n in names if "references/" in n]
            assert len(ref_files) > 0

    def test_text_and_files_together(self, client, completed_job):
        """Both text edits and file attachments should work in the same request."""
        resp = client.post(
            f"/api/forge/{completed_job.id}/refine",
            data={
                "edits": json.dumps({
                    "methodology": "Always validate schema before processing",
                    "quality": "Data must be < 24h old",
                }),
                "file_categories": json.dumps(["examples"]),
            },
            files=[("files", ("sample.md", b"ETL work sample", "text/plain"))],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["skill_folder"]["skill_md"]

    def test_multiple_files_uploaded(self, client, completed_job):
        """Multiple files should all be processed."""
        resp = client.post(
            f"/api/forge/{completed_job.id}/refine",
            data={
                "edits": json.dumps({}),
                "file_categories": json.dumps(["examples", "frameworks"]),
            },
            files=[
                ("files", ("example1.md", b"First example", "text/plain")),
                ("files", ("example2.md", b"Second example", "text/plain")),
                ("files", ("framework.md", b"RICE framework", "text/plain")),
            ],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_references"] is True

    def test_file_without_categories_still_works(self, client, completed_job):
        """Files uploaded without file_categories should still be accepted."""
        resp = client.post(
            f"/api/forge/{completed_job.id}/refine",
            data={
                "edits": json.dumps({"methodology": "Check schema first"}),
            },
            files=[("files", ("sample.md", b"Content", "text/plain"))],
        )
        assert resp.status_code == 200


# ===================================================================
# SUPPLEMENTARY FILES ACROSS REFINE CYCLES
# ===================================================================

class TestSupplementaryFilePersistence:
    """Supplementary files should accumulate across multiple refine cycles."""

    def test_files_accumulate_across_cycles(self, client, completed_job):
        # First refine: add examples
        client.post(
            f"/api/forge/{completed_job.id}/refine",
            json={"edits": {"examples": "Here is how I do ETL review"}},
        )

        # Second refine: add frameworks
        client.post(
            f"/api/forge/{completed_job.id}/refine",
            json={"edits": {"frameworks": "RICE scoring, ADR templates"}},
        )

        # Both should be in the zip
        resp = client.get(f"/api/forge/{completed_job.id}/download/zip")
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            # Examples go to examples/good/, frameworks go to references/
            example_files = [n for n in names if "examples/good/" in n]
            ref_files = [n for n in names if "references/" in n]
            assert len(example_files) + len(ref_files) >= 2

    def test_existing_refs_not_lost_on_refine(self, client, completed_job_with_refs):
        """Pre-existing reference files should survive a refine cycle."""
        resp = client.post(
            f"/api/forge/{completed_job_with_refs.id}/refine",
            json={"edits": {"methodology": "New heuristic"}},
        )
        assert resp.status_code == 200

        # Original refs should still be in zip
        resp = client.get(f"/api/forge/{completed_job_with_refs.id}/download/zip")
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert any("work-examples.md" in n for n in names)
            assert any("frameworks.md" in n for n in names)


# ===================================================================
# SKILL REFINER UNIT TESTS
# ===================================================================

class TestSkillRefiner:
    """Unit tests for the SkillRefiner merge strategies."""

    def _make_extraction(self):
        from agentforge.models.extracted_skills import (
            ExtractionResult, ExtractedRole, ExtractedSkill,
            SuggestedTraits,
        )
        return ExtractionResult(
            role=ExtractedRole(
                title="Engineer",
                purpose="Build things",
                scope_primary=["Development"],
                scope_secondary=[],
                audience=["Team"],
                seniority="senior",
                domain="Engineering",
            ),
            skills=[
                ExtractedSkill(
                    name="Python",
                    category="hard",
                    proficiency="advanced",
                    importance="required",
                    context="Primary language",
                ),
                ExtractedSkill(
                    name="System Design",
                    category="domain",
                    proficiency="advanced",
                    importance="required",
                    context="Architecture",
                ),
            ],
            responsibilities=["Write code"],
            qualifications=["5+ years"],
            suggested_traits=SuggestedTraits(rigor=0.8),
            automation_potential=0.5,
            automation_rationale="Mixed",
        )

    def test_merge_methodology_adds_heuristics(self):
        from agentforge.analysis.skill_refiner import SkillRefiner
        from agentforge.models.extracted_skills import MethodologyExtraction

        refiner = SkillRefiner()
        ext = self._make_extraction()
        meth = MethodologyExtraction()

        ext, meth, files = refiner.merge(ext, meth, {"methodology": "1. Check types\n2. Validate inputs"})
        assert len(meth.heuristics) >= 2

    def test_merge_triggers_adds_mappings(self):
        from agentforge.analysis.skill_refiner import SkillRefiner
        from agentforge.models.extracted_skills import MethodologyExtraction

        refiner = SkillRefiner()
        ext = self._make_extraction()
        meth = MethodologyExtraction()

        ext, meth, files = refiner.merge(ext, meth, {"triggers": "Code review -> Check for security issues"})
        assert len(meth.trigger_mappings) >= 1
        assert "security" in meth.trigger_mappings[0].technique.lower()

    def test_merge_examples_creates_reference_file(self):
        from agentforge.analysis.skill_refiner import SkillRefiner
        from agentforge.models.extracted_skills import MethodologyExtraction

        refiner = SkillRefiner()
        ext = self._make_extraction()
        meth = MethodologyExtraction()

        ext, meth, files = refiner.merge(ext, meth, {"examples": "When reviewing code, I always check for N+1 queries first..."})
        assert "examples/good/work-examples.md" in files

    def test_merge_frameworks_creates_reference_file(self):
        from agentforge.analysis.skill_refiner import SkillRefiner
        from agentforge.models.extracted_skills import MethodologyExtraction

        refiner = SkillRefiner()
        ext = self._make_extraction()
        meth = MethodologyExtraction()

        ext, meth, files = refiner.merge(ext, meth, {"frameworks": "RICE scoring, ADR templates"})
        assert "references/frameworks.md" in files

    def test_merge_scope_extends_secondary(self):
        from agentforge.analysis.skill_refiner import SkillRefiner
        from agentforge.models.extracted_skills import MethodologyExtraction

        refiner = SkillRefiner()
        ext = self._make_extraction()
        meth = MethodologyExtraction()

        ext, meth, files = refiner.merge(ext, meth, {"scope": "Data governance, Privacy compliance"})
        assert len(ext.role.scope_secondary) >= 2

    def test_merge_domain_sets_genai_application(self):
        from agentforge.analysis.skill_refiner import SkillRefiner
        from agentforge.models.extracted_skills import MethodologyExtraction

        refiner = SkillRefiner()
        ext = self._make_extraction()
        meth = MethodologyExtraction()

        ext, meth, files = refiner.merge(ext, meth, {"domain": "AI-assisted architecture review"})
        domain_skills = [s for s in ext.skills if s.category == "domain"]
        assert all(s.genai_application for s in domain_skills)

    def test_merge_uploaded_files_as_references(self):
        from agentforge.analysis.skill_refiner import SkillRefiner
        from agentforge.models.extracted_skills import MethodologyExtraction

        refiner = SkillRefiner()
        ext = self._make_extraction()
        meth = MethodologyExtraction()

        ext, meth, files = refiner.merge(
            ext, meth, {},
            uploaded_files={"report.md": "# Monthly Report\nContent here"},
        )
        assert any("report" in k for k in files)

    def test_merge_empty_text_is_skipped(self):
        from agentforge.analysis.skill_refiner import SkillRefiner
        from agentforge.models.extracted_skills import MethodologyExtraction

        refiner = SkillRefiner()
        ext = self._make_extraction()
        meth = MethodologyExtraction()

        ext, meth, files = refiner.merge(ext, meth, {"methodology": "  "})
        assert len(meth.heuristics) == 0

    def test_merge_persona_sets_traits(self):
        from agentforge.analysis.skill_refiner import SkillRefiner
        from agentforge.models.extracted_skills import MethodologyExtraction

        refiner = SkillRefiner()
        ext = self._make_extraction()
        meth = MethodologyExtraction()

        ext, meth, files = refiner.merge(ext, meth, {"persona": "warm and creative, very patient"})
        assert ext.suggested_traits.warmth is not None
        assert ext.suggested_traits.creativity is not None
        assert ext.suggested_traits.patience is not None


# ===================================================================
# EDGE CASES & ERROR HANDLING
# ===================================================================

class TestEdgeCases:
    """Edge cases and error handling for forge routes."""

    def test_refine_with_no_refine_context(self, client, store):
        """Job without _refine_context should return 400."""
        job = store.create()
        job.status = "done"
        job.result = {"skill_folder": _make_skill_folder_result()}
        resp = client.post(
            f"/api/forge/{job.id}/refine",
            json={"edits": {"methodology": "test"}},
        )
        assert resp.status_code == 400

    def test_refine_with_malformed_edits_json(self, client, completed_job):
        """Malformed edits JSON in multipart form should not crash."""
        resp = client.post(
            f"/api/forge/{completed_job.id}/refine",
            data={"edits": "not valid json"},
            files=[("files", ("sample.md", b"Content", "text/plain"))],
        )
        # Should either handle gracefully or use empty edits
        assert resp.status_code in (200, 400)

    def test_refine_with_malformed_file_categories(self, client, completed_job):
        """Malformed file_categories should not crash."""
        resp = client.post(
            f"/api/forge/{completed_job.id}/refine",
            data={
                "edits": json.dumps({"methodology": "test"}),
                "file_categories": "not json",
            },
            files=[("files", ("sample.md", b"Content", "text/plain"))],
        )
        assert resp.status_code == 200

    def test_zip_with_empty_skill_md(self, client, store):
        """ZIP should work even if SKILL.md is empty."""
        job = store.create()
        job.status = "done"
        job.result = {
            "skill_folder": _make_skill_folder_result(skill_md=""),
            "identity_yaml": "",
        }
        resp = client.get(f"/api/forge/{job.id}/download/zip")
        assert resp.status_code == 200
        buf = io.BytesIO(resp.content)
        assert zipfile.is_zipfile(buf)

    def test_download_skill_404_when_no_skill_folder(self, client, store):
        job = store.create()
        job.status = "done"
        job.result = {"identity_yaml": "test"}
        resp = client.get(f"/api/forge/{job.id}/download/skill")
        assert resp.status_code == 404
