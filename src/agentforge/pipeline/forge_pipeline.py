"""Composable forge pipeline engine."""

from __future__ import annotations

from typing import Any

from agentforge.models.blueprint import AgentBlueprint
from agentforge.pipeline.stages import (
    AnalyzeStage,
    AnonymizeStage,
    ConductorGenerateStage,
    CultureStage,
    DeepAnalyzeStage,
    ExtractStage,
    GenerateStage,
    IngestStage,
    MapStage,
    MethodologyStage,
    MultiIngestStage,
    PipelineStage,
    TeamComposeStage,
    TeamForgeStage,
    TestStage,
    ToolMapStage,
)


class ForgePipeline:
    """Composable pipeline for transforming JDs into agent blueprints.

    Supports adding, removing, and skipping stages. The pipeline passes
    a context dict through each stage sequentially.
    """

    def __init__(self) -> None:
        self.stages: list[PipelineStage] = []
        self._skipped: set[str] = set()

    def add_stage(self, stage: PipelineStage) -> "ForgePipeline":
        """Add a stage to the pipeline."""
        self.stages.append(stage)
        return self

    def skip_stage(self, name: str) -> "ForgePipeline":
        """Skip a named stage during execution."""
        self._skipped.add(name)
        return self

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute all non-skipped stages sequentially."""
        for stage in self.stages:
            if stage.name not in self._skipped:
                context = stage.run(context)
        return context

    def to_blueprint(self, context: dict[str, Any]) -> AgentBlueprint:
        """Convert pipeline context into an AgentBlueprint."""
        agent_team = context.get("agent_team")
        return AgentBlueprint(
            source_jd=context["jd"],
            extraction=context["extraction"],
            culture=context.get("culture_profile"),
            identity_yaml=context["identity_yaml"],
            skill_file=context.get("skill_file"),
            skill_folder=context.get("skill_folder"),
            coverage_score=context.get("coverage_score", 0.0),
            coverage_gaps=context.get("coverage_gaps", []),
            automation_estimate=context["extraction"].automation_potential,
            agent_team=agent_team.to_dict() if agent_team else None,
        )

    @classmethod
    def default(cls) -> "ForgePipeline":
        """Standard pipeline: ingest -> [anonymize] -> extract -> methodology -> map -> culture -> generate -> tool_map -> analyze -> team."""
        pipeline = cls()
        pipeline.add_stage(IngestStage())
        pipeline.add_stage(AnonymizeStage())
        pipeline.add_stage(ExtractStage())
        pipeline.add_stage(MethodologyStage())
        pipeline.add_stage(MapStage())
        pipeline.add_stage(CultureStage())
        pipeline.add_stage(GenerateStage())
        pipeline.add_stage(ToolMapStage())
        pipeline.add_stage(AnalyzeStage())
        pipeline.add_stage(TeamComposeStage())
        return pipeline

    @classmethod
    def quick(cls) -> "ForgePipeline":
        """Minimal pipeline: ingest -> [anonymize] -> extract -> methodology -> generate -> team."""
        pipeline = cls()
        pipeline.add_stage(IngestStage())
        pipeline.add_stage(AnonymizeStage())
        pipeline.add_stage(ExtractStage())
        pipeline.add_stage(MethodologyStage())
        pipeline.add_stage(GenerateStage())
        pipeline.add_stage(TeamComposeStage())
        return pipeline

    @classmethod
    def deep_analysis(cls) -> "ForgePipeline":
        """Deep analysis pipeline with per-skill scoring and priority ranking."""
        pipeline = cls()
        pipeline.add_stage(IngestStage())
        pipeline.add_stage(AnonymizeStage())
        pipeline.add_stage(ExtractStage())
        pipeline.add_stage(MethodologyStage())
        pipeline.add_stage(MapStage())
        pipeline.add_stage(CultureStage())
        pipeline.add_stage(GenerateStage())
        pipeline.add_stage(ToolMapStage())
        pipeline.add_stage(DeepAnalyzeStage())
        pipeline.add_stage(TeamComposeStage())
        return pipeline

    @classmethod
    def team(cls) -> "ForgePipeline":
        """Team forge: extract once, compose team, forge each member + conductor."""
        pipeline = cls()
        pipeline.add_stage(IngestStage())
        pipeline.add_stage(AnonymizeStage())
        pipeline.add_stage(ExtractStage())
        pipeline.add_stage(MethodologyStage())
        pipeline.add_stage(MapStage())
        pipeline.add_stage(CultureStage())
        pipeline.add_stage(GenerateStage())
        pipeline.add_stage(TeamComposeStage())
        pipeline.add_stage(TeamForgeStage())
        pipeline.add_stage(ConductorGenerateStage())
        pipeline.add_stage(AnalyzeStage())
        return pipeline
