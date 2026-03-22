"""Shared test fixtures for AgentForge."""

from __future__ import annotations

from pathlib import Path

import pytest

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
