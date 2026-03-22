"""AgentForge Factory — Transform job descriptions into deployable AI agent blueprints."""

__version__ = "0.1.0"

# Public API — importable as `from agentforge import ...`
from agentforge.extraction.skill_extractor import SkillExtractor
from agentforge.llm.client import LLMClient
from agentforge.models.blueprint import AgentBlueprint
from agentforge.models.extracted_skills import ExtractionResult
from agentforge.models.job_description import JobDescription
from agentforge.pipeline.forge_pipeline import ForgePipeline

__all__ = [
    "__version__",
    "ExtractionResult",
    "ForgePipeline",
    "JobDescription",
    "LLMClient",
    "AgentBlueprint",
    "SkillExtractor",
]
