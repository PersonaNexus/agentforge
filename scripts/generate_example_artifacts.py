"""Generate reproducible example artifacts for docs/examples.

This script uses the same deterministic sample extraction fixtures as the test
suite. It does not call any live LLM/API providers.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml

from agentforge.generation.identity_generator import IdentityGenerator
from agentforge.generation.personanexus_deployment import PersonaNexusDeploymentCompiler
from agentforge.generation.skill_folder import SkillFolderGenerator
from agentforge.models.extracted_skills import (
    ExtractedRole,
    ExtractedSkill,
    ExtractionResult,
    Heuristic,
    MethodologyExtraction,
    OutputTemplate,
    QualityCriterion,
    SeniorityLevel,
    SkillCategory,
    SkillImportance,
    SkillProficiency,
    SuggestedTraits,
    TriggerTechniqueMapping,
)

FIXED_DATE = "2026-05-18"
FIXED_TIMESTAMP = "2026-05-18T00:00:00Z"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_sample_extraction() -> ExtractionResult:
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


def _make_sample_methodology() -> MethodologyExtraction:
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


def _normalize_skill_md(skill_md: str) -> str:
    """Normalize date footer so generated docs are reproducible."""
    return re.sub(
        r"(\*Generated by AgentForge \| Source: [^|]+ \| )\d{4}-\d{2}-\d{2}\*",
        rf"\g<1>{FIXED_DATE}*",
        skill_md,
    )


def _normalize_deployment_yaml(deployment_yaml: str) -> str:
    """Normalize generated_at timestamp so artifacts remain stable."""
    data = yaml.safe_load(deployment_yaml)
    data["generated_at"] = FIXED_TIMESTAMP
    return yaml.safe_dump(data, sort_keys=False)


def main() -> None:
    repo_root = REPO_ROOT
    fixture_jd = repo_root / "tests" / "fixtures" / "senior_data_engineer.txt"

    example_root = repo_root / "examples" / "senior-data-engineer"
    output_root = example_root / "output"

    if example_root.exists():
        shutil.rmtree(example_root)

    (example_root / "input").mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    extraction = _make_sample_extraction()
    methodology = _make_sample_methodology()

    identity, identity_yaml = IdentityGenerator().generate(extraction)
    skill = SkillFolderGenerator().generate(
        extraction=extraction,
        identity=identity,
        methodology=methodology,
    )
    deployment = PersonaNexusDeploymentCompiler().compile(
        extraction=extraction,
        identity_yaml=identity_yaml,
        identity=identity,
        methodology=methodology,
        skill_folder=skill,
    )

    # Input sample JD
    (example_root / "input" / "job_description.txt").write_text(fixture_jd.read_text())

    # Primary forge output artifacts
    (output_root / "identity.yaml").write_text(identity_yaml)

    skill_dir = output_root / "skill-folder"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(_normalize_skill_md(skill.skill_md_with_references()))
    for rel_path, content in skill.supplementary_files.items():
        path = skill_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    # Deployment package output
    package_root = output_root / "personanexus-deployment"
    package_root.mkdir(parents=True, exist_ok=True)
    for rel_path, content in deployment.file_map().items():
        path = package_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if rel_path == "deployment.yaml":
            path.write_text(_normalize_deployment_yaml(content))
        elif rel_path.endswith("/SKILL.md"):
            path.write_text(_normalize_skill_md(content))
        else:
            path.write_text(content)

    (example_root / "README.md").write_text(
        "\n".join(
            [
                "# Senior Data Engineer Example",
                "",
                "Sanitized example input/output package generated from AgentForge fixture data.",
                "",
                "## Reproduce",
                "",
                "```bash",
                "uv sync --dev",
                "uv run python scripts/generate_example_artifacts.py",
                "```",
                "",
                "This flow is deterministic and does not call external LLM providers.",
                "",
            ]
        )
    )

    print(f"Wrote example artifacts to: {example_root}")


if __name__ == "__main__":
    main()
