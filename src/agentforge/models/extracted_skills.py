"""Data models for LLM-extracted skills and role information."""

from __future__ import annotations

import enum

import logging

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class SkillCategory(enum.StrEnum):
    HARD = "hard"
    SOFT = "soft"
    DOMAIN = "domain"
    TOOL = "tool"


class SkillProficiency(enum.StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class SkillImportance(enum.StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    NICE_TO_HAVE = "nice_to_have"


class SeniorityLevel(enum.StrEnum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    EXECUTIVE = "executive"


def _coerce_enum(value: str, enum_cls: type[enum.StrEnum], default: enum.StrEnum) -> enum.StrEnum:
    """Try to match a value to an enum, falling back to default for LLM hallucinations."""
    if isinstance(value, enum_cls):
        return value
    normalized = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return enum_cls(normalized)
    except ValueError:
        logger.warning("Coercing invalid %s value %r → %s", enum_cls.__name__, value, default)
        return default


class ExtractedSkill(BaseModel):
    """A single skill extracted from a job description."""

    name: str = Field(..., min_length=1)
    category: SkillCategory
    proficiency: SkillProficiency = SkillProficiency.INTERMEDIATE
    importance: SkillImportance = SkillImportance.REQUIRED
    context: str = Field(default="", description="How this skill is used in the role")
    examples: list[str] = Field(
        default_factory=list,
        description="Specific tools, libraries, or applications (e.g., 'Salesforce for CRM', 'Hugging Face for NLP')",
    )
    genai_application: str = Field(
        default="",
        description="How GenAI/ML can augment or automate this skill area",
    )

    @field_validator("proficiency", mode="before")
    @classmethod
    def coerce_proficiency(cls, v: object) -> SkillProficiency:
        return _coerce_enum(v, SkillProficiency, SkillProficiency.INTERMEDIATE)

    @field_validator("importance", mode="before")
    @classmethod
    def coerce_importance(cls, v: object) -> SkillImportance:
        return _coerce_enum(v, SkillImportance, SkillImportance.REQUIRED)

    @field_validator("category", mode="before")
    @classmethod
    def coerce_category(cls, v: object) -> SkillCategory:
        return _coerce_enum(v, SkillCategory, SkillCategory.HARD)


class ExtractedRole(BaseModel):
    """Role information extracted from a job description."""

    title: str
    purpose: str = Field(..., min_length=1)
    scope_primary: list[str] = Field(default_factory=list)
    scope_secondary: list[str] = Field(default_factory=list)
    audience: list[str] = Field(default_factory=list)
    seniority: SeniorityLevel = SeniorityLevel.MID
    domain: str = Field(default="general")

    @field_validator("scope_primary", "scope_secondary", "audience", mode="before")
    @classmethod
    def coerce_none_to_list(cls, v: object) -> list:
        """LLM may return None for optional list fields; coerce to empty list."""
        if v is None:
            return []
        return v


class SuggestedTraits(BaseModel):
    """LLM-suggested personality traits for the agent (0-1 scale)."""

    warmth: float | None = Field(None, ge=0.0, le=1.0)
    verbosity: float | None = Field(None, ge=0.0, le=1.0)
    assertiveness: float | None = Field(None, ge=0.0, le=1.0)
    humor: float | None = Field(None, ge=0.0, le=1.0)
    empathy: float | None = Field(None, ge=0.0, le=1.0)
    directness: float | None = Field(None, ge=0.0, le=1.0)
    rigor: float | None = Field(None, ge=0.0, le=1.0)
    creativity: float | None = Field(None, ge=0.0, le=1.0)
    epistemic_humility: float | None = Field(None, ge=0.0, le=1.0)
    patience: float | None = Field(None, ge=0.0, le=1.0)

    def defined_traits(self) -> dict[str, float]:
        """Return only traits that have been explicitly set."""
        return {
            k: v
            for k, v in self.model_dump(exclude_none=True).items()
            if isinstance(v, (int, float))
        }


class ExtractionResult(BaseModel):
    """Complete extraction output from analyzing a job description."""

    role: ExtractedRole
    skills: list[ExtractedSkill] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)
    suggested_traits: SuggestedTraits = Field(default_factory=SuggestedTraits)
    automation_potential: float = Field(0.0, ge=0.0, le=1.0)
    automation_rationale: str = ""

    @field_validator("skills", "responsibilities", "qualifications", mode="before")
    @classmethod
    def coerce_none_to_list(cls, v: object) -> list:
        """LLM may return None for optional list fields; coerce to empty list."""
        if v is None:
            return []
        return v
    salary_min: float | None = Field(
        None, ge=0, description="Minimum annual salary if stated in the JD"
    )
    salary_max: float | None = Field(
        None, ge=0, description="Maximum annual salary if stated in the JD"
    )
