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


class AnonymizeStage(PipelineStage):
    """Anonymize company names and identifying info in the JD."""

    name = "anonymize"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        if not context.get("anonymize"):
            return context

        from agentforge.ingestion.anonymizer import anonymize_text

        jd = context["jd"]
        llm_client = context.get("llm_client")
        if not llm_client:
            return context

        result = anonymize_text(jd.raw_text, llm_client)
        jd.raw_text = result.anonymized_text

        # Re-anonymize section content too
        for section in jd.sections:
            for repl in result.replacements:
                orig = repl.get("original", "")
                replacement = repl.get("replacement", "")
                if orig and replacement:
                    section.content = section.content.replace(orig, replacement)

        # Anonymize company field
        if jd.company:
            for repl in result.replacements:
                orig = repl.get("original", "")
                replacement = repl.get("replacement", "")
                if orig and replacement and orig.lower() in (jd.company or "").lower():
                    jd.company = replacement
                    break

        context["jd"] = jd
        context["anonymization"] = {
            "replacements": [r for r in result.replacements],
            "was_anonymized": True,
        }
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


class MethodologyStage(PipelineStage):
    """Extract actionable methodology (heuristics, templates, trigger mappings, rubrics)."""

    name = "methodology"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from agentforge.extraction.methodology_extractor import MethodologyExtractor

        extractor = context.get("methodology_extractor") or MethodologyExtractor(
            client=context.get("llm_client")
        )
        context["methodology"] = extractor.extract(
            extraction=context["extraction"],
            user_examples=context.get("user_examples", ""),
            user_frameworks=context.get("user_frameworks", ""),
        )
        return context


class GenerateStage(PipelineStage):
    """Generate PersonaNexus AgentIdentity, SKILL.md, and skill folder."""

    name = "generate"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from agentforge.generation.identity_generator import IdentityGenerator
        from agentforge.generation.skill_file import SkillFileGenerator
        from agentforge.generation.skill_folder import SkillFolderGenerator

        output_format = context.get("output_format", "claude_code")

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

        # Reference skill file (used by all output formats)
        if output_format != "clawhub":
            skill_gen = SkillFileGenerator()
            context["skill_file"] = skill_gen.generate(
                context["extraction"], jd=context.get("jd")
            )

        # Claude Code skill folder
        if output_format in ("claude_code", "both"):
            skill_folder_gen = SkillFolderGenerator()
            context["skill_folder"] = skill_folder_gen.generate(
                context["extraction"],
                identity,
                jd=context.get("jd"),
                methodology=context.get("methodology"),
                user_examples=context.get("user_examples", ""),
                user_frameworks=context.get("user_frameworks", ""),
            )

        # ClawHub skill
        if output_format in ("clawhub", "both"):
            from agentforge.generation.clawhub_skill import ClawHubSkillGenerator

            clawhub_gen = ClawHubSkillGenerator()
            context["clawhub_skill"] = clawhub_gen.generate(
                context["extraction"],
                jd=context.get("jd"),
                methodology=context.get("methodology"),
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


class ToolMapStage(PipelineStage):
    """Map extracted skills to concrete tool recommendations."""

    name = "tool_map"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from agentforge.mapping.tool_mapper import ToolMapper

        mapper = context.get("tool_mapper") or ToolMapper(client=context.get("llm_client"))
        context["tool_profile"] = mapper.map_tools(context["extraction"])
        return context


class TeamComposeStage(PipelineStage):
    """Compose an AI agent team from extraction results."""

    name = "team_compose"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from agentforge.analysis.team_composer import TeamComposer

        composer = TeamComposer()
        context["agent_team"] = composer.compose(context["extraction"])
        return context


class MultiIngestStage(PipelineStage):
    """Ingest JD plus supplementary sources for methodology enrichment."""

    name = "multi_ingest"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from pathlib import Path

        # Standard JD ingestion
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

        # Parse supplementary sources
        sources = context.get("supplementary_sources", [])
        if sources:
            from agentforge.ingestion.multi_source import (
                compile_enrichment,
                parse_supplementary_source,
            )

            corpora = []
            for source in sources:
                try:
                    corpus = parse_supplementary_source(source)
                    corpora.append(corpus)
                except Exception:
                    continue

            if corpora:
                enrichment = compile_enrichment(corpora)
                # Merge enrichment into context for MethodologyStage
                existing_examples = context.get("user_examples", "")
                existing_frameworks = context.get("user_frameworks", "")

                if enrichment.examples:
                    context["user_examples"] = (
                        f"{existing_examples}\n\n{enrichment.examples}".strip()
                    )
                if enrichment.frameworks:
                    context["user_frameworks"] = (
                        f"{existing_frameworks}\n\n{enrichment.frameworks}".strip()
                    )
                if enrichment.operational_context:
                    context["operational_context"] = enrichment.operational_context

                context["supplementary_enrichment"] = enrichment

        return context


class TestStage(PipelineStage):
    """Run test scenarios against the generated skill."""

    name = "test"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from agentforge.testing.scenario_generator import ScenarioGenerator
        from agentforge.testing.skill_runner import SkillRunner
        from agentforge.testing.evaluator import Evaluator

        skill_folder = context.get("skill_folder")
        if not skill_folder:
            return context

        scenarios = ScenarioGenerator().generate(
            extraction=context["extraction"],
            methodology=context.get("methodology"),
        )

        if not scenarios:
            return context

        llm_client = context.get("llm_client")
        if not llm_client:
            return context

        executions = SkillRunner().run_scenarios(
            skill_md=skill_folder.skill_md,
            scenarios=scenarios,
            llm_client=llm_client,
        )

        # Get quality criteria from methodology
        meth = context.get("methodology")
        default_criteria = None
        if meth and meth.quality_criteria:
            default_criteria = [c.criterion for c in meth.quality_criteria]

        report = Evaluator().evaluate(
            executions=executions,
            default_criteria=default_criteria,
            llm_client=llm_client,
        )

        context["test_report"] = report
        return context


class TeamForgeStage(PipelineStage):
    """Forge individual skills for each team member."""

    name = "team_forge"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from agentforge.composition.team_forger import TeamForger

        agent_team = context.get("agent_team")
        if not agent_team or not agent_team.teammates:
            return context

        forger = TeamForger()
        context["forged_team"] = forger.forge_team(
            team=agent_team,
            extraction=context["extraction"],
            methodology=context.get("methodology"),
        )
        return context


class ConductorGenerateStage(PipelineStage):
    """Generate conductor skill for team orchestration."""

    name = "conductor_generate"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from agentforge.composition.conductor_generator import ConductorGenerator
        from agentforge.composition.models import ForgedTeam

        forged_teammates = context.get("forged_team")
        agent_team = context.get("agent_team")
        if not forged_teammates or not agent_team:
            return context

        generator = ConductorGenerator()
        conductor = generator.generate(
            team=agent_team,
            forged_teammates=forged_teammates,
            extraction=context["extraction"],
        )

        context["conductor"] = conductor
        context["forged_team_result"] = ForgedTeam(
            role_title=context["extraction"].role.title,
            conductor=conductor,
            teammates=forged_teammates,
        )
        return context


class OpenClawCompileStage(PipelineStage):
    """Compile pipeline output into OpenClaw-ready deployment files."""

    name = "openclaw_compile"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        from agentforge.generation.openclaw_compiler import OpenClawCompiler

        compiler = OpenClawCompiler()
        context["openclaw_output"] = compiler.compile(
            extraction=context["extraction"],
            identity_yaml=context["identity_yaml"],
            identity=context["identity"],
            methodology=context.get("methodology"),
            skill_folder=context.get("skill_folder"),
            schedule=context.get("cron_schedule"),
            cron_config=context.get("cron_config_dict"),
        )
        return context


class CronEnrichStage(PipelineStage):
    """Enrich identity YAML and skill output with cron-specific scaffolding."""

    name = "cron_enrich"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        cron_schedule = context.get("cron_schedule")
        if not cron_schedule:
            return context

        from agentforge.generation.cron_template import CronConfig, CronTemplateGenerator

        config = CronConfig(
            schedule=cron_schedule,
            timezone=context.get("cron_timezone", "UTC"),
        )
        generator = CronTemplateGenerator()

        # Enrich identity YAML
        if "identity_yaml" in context:
            context["identity_yaml"] = generator.enrich_identity_yaml(
                context["identity_yaml"], config,
            )

        # Enrich skill folder SKILL.md
        sf = context.get("skill_folder")
        if sf:
            enriched_md = generator.enrich_skill_md(
                sf.skill_md, context["extraction"], config,
            )
            sf.skill_md = enriched_md

        # Store cron config dict for downstream stages
        context["cron_config_dict"] = config.to_dict()
        return context


class SupplementScoreStage(PipelineStage):
    """Score supplementary sources before ingestion."""

    name = "supplement_score"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        sources = context.get("supplementary_sources", [])
        if not sources:
            return context

        from agentforge.analysis.supplement_scorer import SupplementScorer

        scorer = SupplementScorer()
        extraction = context.get("extraction")
        role_keywords: list[str] = []
        if extraction:
            role_keywords = [extraction.role.title, extraction.role.domain]
            role_keywords.extend(s.name for s in extraction.skills[:10])

        source_pairs: list[tuple[str, str]] = []
        for source in sources:
            from pathlib import Path
            p = Path(source)
            if p.exists():
                source_pairs.append((p.name, p.read_text()))

        if source_pairs:
            report = scorer.score_sources(source_pairs, role_keywords)
            context["supplement_report"] = report

        return context
