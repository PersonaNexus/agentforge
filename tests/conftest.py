"""Shared test fixtures for AgentForge."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

collect_ignore: list[str] = []
if importlib.util.find_spec("sqlalchemy") is None:
    collect_ignore.append("test_db.py")
if importlib.util.find_spec("fastapi") is None:
    collect_ignore.append("test_forge_routes.py")

from agentforge.models.extracted_skills import (
    ExtractionResult,
    ExtractedRole,
    ExtractedSkill,
    SeniorityLevel,
    SkillCategory,
    SkillImportance,
    SkillProficiency,
    SuggestedTraits,
)
from agentforge.models.job_description import JDSection, JDSource, JobDescription

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Re-usable factory for MethodologyExtraction (mirrors test_enhancements.py)
# ---------------------------------------------------------------------------

from agentforge.models.extracted_skills import (
    Heuristic,
    MethodologyExtraction,
    OutputTemplate,
    QualityCriterion,
    TriggerTechniqueMapping,
)


def _make_sample_methodology() -> MethodologyExtraction:
    """Factory for a canonical sample methodology extraction.

    Mirrors ``_make_sample_extraction`` in its scope so that deployment-
    artifact tests can compose a fully-enriched compile context without
    duplicating data.
    """
    return MethodologyExtraction(
        heuristics=[
            Heuristic(
                trigger="When evaluating data pipeline performance",
                procedure="1. Check throughput 2. Check latency 3. Compare baselines",
                source_responsibility="Monitor pipeline performance",
            ),
        ],
        trigger_mappings=[
            TriggerTechniqueMapping(
                trigger_pattern="Evaluate pipeline",
                technique="Use throughput and latency metrics",
                output_format="Markdown table",
            ),
        ],
        output_templates=[
            OutputTemplate(
                name="Pipeline Report",
                when_to_use="After pipeline evaluation",
                template="# Pipeline Report\n## Throughput\n## Latency",
            ),
        ],
        quality_criteria=[
            QualityCriterion(
                criterion="Includes quantified metrics",
                description="All findings should include measurable data",
            ),
        ],
    )


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_jd_text() -> str:
    return (FIXTURES_DIR / "senior_data_engineer.txt").read_text()


@pytest.fixture
def sample_jd(sample_jd_text: str) -> JobDescription:
    return JobDescription(
        source=JDSource.TEXT,
        title="Senior Data Engineer",
        company="Acme Technologies",
        raw_text=sample_jd_text,
        sections=[
            JDSection(heading="About the Role", content="Design and build data infrastructure."),
            JDSection(heading="Responsibilities", content="Design ETL pipelines. Build data warehouse."),
            JDSection(heading="Requirements", content="5+ years experience. Python and SQL."),
        ],
    )


def _make_sample_extraction() -> ExtractionResult:
    """Factory function for creating a sample ExtractionResult.

    Can be called directly from tests or via the sample_extraction fixture.
    """
    return ExtractionResult(
        role=ExtractedRole(
            title="Senior Data Engineer",
            purpose="Design, build, and maintain scalable data infrastructure",
            scope_primary=["ETL pipeline design", "Data warehouse architecture", "Data quality"],
            scope_secondary=["ML model operationalization", "Mentoring"],
            audience=["Data scientists", "Analysts", "Product teams"],
            seniority=SeniorityLevel.SENIOR,
            domain="Data Engineering",
        ),
        skills=[
            ExtractedSkill(
                name="Python",
                category=SkillCategory.HARD,
                proficiency=SkillProficiency.ADVANCED,
                importance=SkillImportance.REQUIRED,
                context="Primary programming language for data pipelines",
                examples=["pandas for data manipulation", "PySpark for distributed processing"],
                genai_application="ML-powered code generation and automated testing",
            ),
            ExtractedSkill(
                name="SQL",
                category=SkillCategory.HARD,
                proficiency=SkillProficiency.ADVANCED,
                importance=SkillImportance.REQUIRED,
                context="Data warehouse querying and modeling",
                examples=["PostgreSQL", "BigQuery", "dbt for transformations"],
            ),
            ExtractedSkill(
                name="Apache Spark",
                category=SkillCategory.TOOL,
                proficiency=SkillProficiency.ADVANCED,
                importance=SkillImportance.REQUIRED,
                context="Large-scale data processing",
                examples=["Spark SQL", "Spark Streaming", "Delta Lake"],
                genai_application="Auto-tuning Spark jobs via ML optimization",
            ),
            ExtractedSkill(
                name="Data Architecture",
                category=SkillCategory.DOMAIN,
                proficiency=SkillProficiency.ADVANCED,
                importance=SkillImportance.REQUIRED,
                context="End-to-end data platform design and governance",
                genai_application="AI-assisted schema evolution and data lineage tracking",
            ),
            ExtractedSkill(
                name="Team Collaboration",
                category=SkillCategory.SOFT,
                proficiency=SkillProficiency.ADVANCED,
                importance=SkillImportance.REQUIRED,
                context="Cross-functional work with data scientists and analysts",
            ),
        ],
        responsibilities=[
            "Design and implement scalable ETL/ELT pipelines",
            "Build and maintain data warehouse architecture",
            "Develop real-time streaming solutions",
            "Establish data quality frameworks",
        ],
        qualifications=[
            "5+ years of experience in data engineering",
            "Bachelor's degree in Computer Science",
        ],
        suggested_traits=SuggestedTraits(
            rigor=0.85,
            directness=0.7,
            patience=0.6,
            creativity=0.5,
        ),
        automation_potential=0.35,
        automation_rationale="Data pipeline design requires significant architectural judgment",
    )


@pytest.fixture
def sample_extraction() -> ExtractionResult:
    return _make_sample_extraction()


@pytest.fixture
def sample_methodology() -> MethodologyExtraction:
    return _make_sample_methodology()


# ---------------------------------------------------------------------------
# Deployment-artifact fixtures
# ---------------------------------------------------------------------------

from agentforge.generation.identity_generator import IdentityGenerator
from agentforge.generation.openclaw_compiler import OpenClawCompiler, OpenClawOutput
from personanexus.types import AgentIdentity


@pytest.fixture(scope="session")
def _session_extraction() -> ExtractionResult:
    """Session-scoped extraction — avoids rebuilding for every test."""
    return _make_sample_extraction()


@pytest.fixture(scope="session")
def compiled_identity(_session_extraction: ExtractionResult) -> tuple[AgentIdentity, str]:
    """Session-scoped (identity, yaml_str) from the standard sample extraction.

    Use this when you need the PersonaNexus AgentIdentity object or its YAML
    without the full OpenClaw compile step.
    """
    generator = IdentityGenerator()
    return generator.generate(_session_extraction)


@pytest.fixture(scope="session")
def deployment_artifact(
    _session_extraction: ExtractionResult,
    compiled_identity: tuple[AgentIdentity, str],
) -> OpenClawOutput:
    """Session-scoped fully-compiled OpenClaw deployment artifact.

    Provides the canonical ``OpenClawOutput`` produced from the standard
    ``sample_extraction`` so deployment-artifact tests share a single compiled
    instance across the session.  Tests that mutate state should work from a
    fresh compile instead.

    Covers the minimal (no methodology, no skill folder) path — the most
    common public-deployment scenario.  For enriched-path coverage use
    ``deployment_artifact_with_methodology`` or build inline.
    """
    identity, yaml_str = compiled_identity
    compiler = OpenClawCompiler()
    return compiler.compile(
        extraction=_session_extraction,
        identity_yaml=yaml_str,
        identity=identity,
    )


@pytest.fixture(scope="session")
def deployment_artifact_with_methodology(
    _session_extraction: ExtractionResult,
    compiled_identity: tuple[AgentIdentity, str],
) -> OpenClawOutput:
    """Session-scoped deployment artifact compiled with full methodology enrichment."""
    identity, yaml_str = compiled_identity
    compiler = OpenClawCompiler()
    return compiler.compile(
        extraction=_session_extraction,
        identity_yaml=yaml_str,
        identity=identity,
        methodology=_make_sample_methodology(),
    )
