"""Built-in pipeline stages for the AgentForge pipeline."""

from __future__ import annotations

from typing import Any


class PipelineStage:
    """Base class for pipeline stages."""

    name: str = "base"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class IngestStage(PipelineStage):
    """Ingest a JD file into a JobDescription model."""

    name = "ingest"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from pathlib import Path

        path = Path(context["input_path"])
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            from agentforge.ingestion.pdf import ingest_pdf
            jd = ingest_pdf(path, company=context.get("company"))
        elif suffix == ".docx":
            from agentforge.ingestion.docx import ingest_docx
            jd = ingest_docx(path, company=context.get("company"))
        else:
            from agentforge.ingestion.text import ingest_file
            jd = ingest_file(path, company=context.get("company"))

        context["jd"] = jd
        return context


class ExtractStage(PipelineStage):
    """Extract skills and role information via LLM."""

    name = "extract"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from agentforge.extraction.skill_extractor import SkillExtractor

        extractor = context.get("extractor") or SkillExtractor(client=context.get("llm_client"))
        context["extraction"] = extractor.extract(context["jd"])
        return context


class MapStage(PipelineStage):
    """Map extraction results to PersonaNexus traits and role structures."""

    name = "map"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from agentforge.mapping.trait_mapper import TraitMapper

        mapper = context.get("trait_mapper") or TraitMapper()
        context["traits"] = mapper.map_traits(context["extraction"])
        return context


class GenerateStage(PipelineStage):
    """Generate PersonaNexus AgentIdentity, SKILL.md, and skill folder."""

    name = "generate"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from agentforge.generation.identity_generator import IdentityGenerator
        from agentforge.generation.skill_file import SkillFileGenerator
        from agentforge.generation.skill_folder import SkillFolderGenerator

        # Apply user trait overrides to extraction before generating
        trait_overrides = context.get("trait_overrides")
        if trait_overrides:
            extraction = context["extraction"]
            for trait_name, value in trait_overrides.items():
                if hasattr(extraction.suggested_traits, trait_name):
                    setattr(extraction.suggested_traits, trait_name, value)

        generator = context.get("identity_generator") or IdentityGenerator()
        identity, yaml_str = generator.generate(context["extraction"])
        context["identity"] = identity
        context["identity_yaml"] = yaml_str

        skill_gen = SkillFileGenerator()
        context["skill_file"] = skill_gen.generate(
            context["extraction"], jd=context.get("jd")
        )

        skill_folder_gen = SkillFolderGenerator()
        context["skill_folder"] = skill_folder_gen.generate(
            context["extraction"], identity, jd=context.get("jd")
        )

        return context


class CultureStage(PipelineStage):
    """Apply culture profile to the generation context."""

    name = "culture"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from agentforge.mapping.culture_mapper import CultureMixinConverter, CultureParser

        culture_path = context.get("culture_path")
        culture_profile = context.get("culture_profile")

        if culture_path and not culture_profile:
            parser = CultureParser(llm_client=context.get("llm_client"))
            culture_profile = parser.parse_file(culture_path)

        if culture_profile:
            context["culture_profile"] = culture_profile

            # Generate mixin YAML
            converter = CultureMixinConverter()
            context["culture_mixin_yaml"] = converter.convert(culture_profile)

            # Apply trait deltas to the mapped traits
            traits = context.get("traits", {})
            for value in culture_profile.values:
                for trait, delta in value.trait_deltas.items():
                    current = traits.get(trait, 0.5)
                    traits[trait] = round(max(0.0, min(1.0, current + delta)), 2)
            context["traits"] = traits

        return context


class AnalyzeStage(PipelineStage):
    """Run gap analysis on the generated agent."""

    name = "analyze"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from agentforge.analysis.gap_analyzer import GapAnalyzer

        analyzer = GapAnalyzer()
        coverage, gaps = analyzer.analyze(context["extraction"])
        context["coverage_score"] = coverage
        context["coverage_gaps"] = gaps
        return context


class DeepAnalyzeStage(PipelineStage):
    """Run detailed gap analysis with per-skill scoring."""

    name = "deep_analyze"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from agentforge.analysis.gap_analyzer import GapAnalyzer

        analyzer = GapAnalyzer()
        coverage, gaps, skill_scores = analyzer.detailed_analyze(context["extraction"])
        context["coverage_score"] = coverage
        context["coverage_gaps"] = gaps
        context["skill_scores"] = skill_scores
        return context


class TeamComposeStage(PipelineStage):
    """Compose an AI agent team from extraction results."""

    name = "team_compose"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from agentforge.analysis.team_composer import TeamComposer

        composer = TeamComposer()
        context["agent_team"] = composer.compose(context["extraction"])
        return context
