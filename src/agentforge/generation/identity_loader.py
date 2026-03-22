"""Load a PersonaNexus identity YAML and reverse-map it to AgentForge models.

This enables round-tripping: load an existing identity, enrich it through
AgentForge's refine pipeline, and export it back as a valid PersonaNexus YAML.
"""

from __future__ import annotations

from typing import Any

import yaml
from personanexus.types import AgentIdentity

from agentforge.models.extracted_skills import (
    ExtractionResult,
    ExtractedRole,
    ExtractedSkill,
    MethodologyExtraction,
    SeniorityLevel,
    SkillCategory,
    SkillImportance,
    SkillProficiency,
    SuggestedTraits,
)


# Reverse mappings (inverse of what RoleMapper/TraitMapper use)
_REGISTER_TO_SENIORITY: dict[str, SeniorityLevel] = {
    "intimate": SeniorityLevel.JUNIOR,
    "casual": SeniorityLevel.JUNIOR,
    "consultative": SeniorityLevel.SENIOR,
    "formal": SeniorityLevel.EXECUTIVE,
    "frozen": SeniorityLevel.EXECUTIVE,
}

_LEVEL_TO_PROFICIENCY: list[tuple[float, SkillProficiency]] = [
    (0.8, SkillProficiency.EXPERT),
    (0.6, SkillProficiency.ADVANCED),
    (0.4, SkillProficiency.INTERMEDIATE),
    (0.0, SkillProficiency.BEGINNER),
]

_CATEGORY_TO_IMPORTANCE: dict[str, SkillImportance] = {
    "primary": SkillImportance.REQUIRED,
    "secondary": SkillImportance.PREFERRED,
    "tertiary": SkillImportance.NICE_TO_HAVE,
}


class IdentityLoader:
    """Reverse-maps a PersonaNexus AgentIdentity to AgentForge models.

    This enables loading an existing identity YAML, feeding it through
    AgentForge's refine pipeline, and exporting an enriched version.
    """

    def load_yaml(self, yaml_str: str) -> tuple[ExtractionResult, MethodologyExtraction, str]:
        """Parse an identity YAML string and reverse-map to AgentForge models.

        Args:
            yaml_str: A valid PersonaNexus identity YAML string.

        Returns:
            Tuple of (ExtractionResult, MethodologyExtraction, identity_yaml).
            The identity_yaml is the original string passed through for
            re-serialization after refinement.

        Raises:
            ValueError: If the YAML is not valid or not a PersonaNexus identity.
        """
        data = yaml.safe_load(yaml_str)
        if not isinstance(data, dict):
            raise ValueError("Invalid YAML: expected a mapping at top level")

        # Validate through PersonaNexus to ensure it's a real identity
        identity = AgentIdentity.model_validate(data)

        extraction = self._build_extraction(identity, data)
        methodology = self._build_methodology(data)

        return extraction, methodology, yaml_str

    def load_file(self, path: str) -> tuple[ExtractionResult, MethodologyExtraction, str]:
        """Load an identity YAML file and reverse-map to AgentForge models."""
        from pathlib import Path

        yaml_str = Path(path).read_text(encoding="utf-8")
        return self.load_yaml(yaml_str)

    # ------------------------------------------------------------------
    # Reverse mapping
    # ------------------------------------------------------------------

    def _build_extraction(self, identity: AgentIdentity, data: dict) -> ExtractionResult:
        """Reverse-map an AgentIdentity to an ExtractionResult."""
        role = self._extract_role(identity, data)
        skills = self._extract_skills(data)
        traits = self._extract_traits(identity, data)

        return ExtractionResult(
            role=role,
            skills=skills,
            responsibilities=self._extract_responsibilities(data),
            qualifications=[],
            suggested_traits=traits,
            automation_potential=0.5,
            automation_rationale="Imported from existing identity — automation potential not assessed",
        )

    def _extract_role(self, identity: AgentIdentity, data: dict) -> ExtractedRole:
        """Reverse-map role fields."""
        role_data = data.get("role", {})
        scope_data = role_data.get("scope", {})
        audience_data = role_data.get("audience", {})

        # Reverse-map seniority from communication register
        seniority = SeniorityLevel.MID
        comm = data.get("communication", {})
        tone = comm.get("tone", {})
        register = tone.get("register")
        if register:
            seniority = _REGISTER_TO_SENIORITY.get(register, SeniorityLevel.MID)

        # Build audience list
        audience: list[str] = []
        if audience_data:
            primary_aud = audience_data.get("primary")
            if primary_aud:
                audience.append(primary_aud)
            secondary_aud = audience_data.get("secondary")
            if secondary_aud:
                audience.append(secondary_aud)

        # Infer domain from tags or expertise
        domain = "general"
        metadata = data.get("metadata", {})
        tags = metadata.get("tags", [])
        # Filter out meta-tags
        domain_tags = [t for t in tags if t not in ("agentforge", "generated", "imported")]
        if domain_tags:
            domain = domain_tags[0].replace("_", " ").title()

        return ExtractedRole(
            title=identity.role.title,
            purpose=identity.role.purpose,
            scope_primary=scope_data.get("primary", []),
            scope_secondary=scope_data.get("secondary", []),
            audience=audience,
            seniority=seniority,
            domain=domain,
        )

    def _extract_skills(self, data: dict) -> list[ExtractedSkill]:
        """Reverse-map expertise domains to ExtractedSkills."""
        expertise = data.get("expertise", {})
        domains = expertise.get("domains", [])

        skills: list[ExtractedSkill] = []
        for domain in domains:
            name = domain.get("name", "")
            if not name:
                continue

            level = domain.get("level", 0.5)
            proficiency = self._level_to_proficiency(level)
            importance = _CATEGORY_TO_IMPORTANCE.get(
                domain.get("category", "secondary"),
                SkillImportance.PREFERRED,
            )

            # Expertise domains are hard/domain/tool — infer category from context
            category = self._infer_skill_category(name, domain)

            skills.append(ExtractedSkill(
                name=name,
                category=category,
                proficiency=proficiency,
                importance=importance,
                context=domain.get("description", ""),
            ))

        return skills

    def _extract_traits(self, identity: AgentIdentity, data: dict) -> SuggestedTraits:
        """Reverse-map personality traits."""
        personality = data.get("personality", {})
        traits_data = personality.get("traits", {})

        trait_fields = SuggestedTraits.model_fields.keys()
        trait_dict = {}
        for field in trait_fields:
            value = traits_data.get(field)
            if value is not None:
                trait_dict[field] = float(value)

        return SuggestedTraits(**trait_dict)

    def _extract_responsibilities(self, data: dict) -> list[str]:
        """Extract responsibilities from principles and scope."""
        responsibilities: list[str] = []

        # Principles imply responsibilities
        principles = data.get("principles", [])
        for p in principles:
            statement = p.get("statement", "")
            if statement:
                responsibilities.append(statement)

        # Scope primary items are de-facto responsibilities
        scope = data.get("role", {}).get("scope", {})
        for item in scope.get("primary", []):
            if item not in responsibilities:
                responsibilities.append(item)

        return responsibilities

    def _build_methodology(self, data: dict) -> MethodologyExtraction:
        """Extract any methodology-like content from the identity.

        PersonaNexus identities don't have explicit methodology sections,
        but behavior strategies, decision heuristics, and tone overrides
        can be reverse-mapped into methodology.
        """
        from agentforge.models.extracted_skills import (
            Heuristic,
            QualityCriterion,
            TriggerTechniqueMapping,
        )

        methodology = MethodologyExtraction()

        # Behavior strategies → heuristics
        behavior = data.get("behavior", {})
        strategies = behavior.get("strategies", {})
        for name, strategy in strategies.items():
            approach = strategy.get("approach", "")
            if approach:
                methodology.heuristics.append(Heuristic(
                    trigger=f"When handling {name.replace('_', ' ')}",
                    procedure=approach,
                    source_responsibility=f"Imported from identity behavior strategy: {name}",
                ))
            for rule in strategy.get("rules", []):
                condition = rule.get("condition", "")
                action = rule.get("action", "")
                if condition and action:
                    methodology.trigger_mappings.append(TriggerTechniqueMapping(
                        trigger_pattern=condition,
                        technique=action,
                    ))

        # Decision heuristics → heuristics
        decision = behavior.get("decision_making", {})
        for heuristic in decision.get("heuristics", []):
            name = heuristic.get("name", "")
            rule = heuristic.get("rule", "")
            if name and rule:
                methodology.heuristics.append(Heuristic(
                    trigger=f"When making a decision about {name}",
                    procedure=rule,
                    source_responsibility="Imported from identity decision heuristics",
                ))

        # Guardrail rules → quality criteria
        guardrails = data.get("guardrails", {})
        for hard in guardrails.get("hard", []):
            rule = hard.get("rule", "")
            if rule:
                methodology.quality_criteria.append(QualityCriterion(
                    criterion=rule,
                    description=f"Hard guardrail (severity: {hard.get('severity', 'unknown')})",
                ))

        return methodology

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _level_to_proficiency(level: float) -> SkillProficiency:
        """Convert a 0-1 expertise level back to a proficiency enum."""
        for threshold, prof in _LEVEL_TO_PROFICIENCY:
            if level >= threshold:
                return prof
        return SkillProficiency.BEGINNER

    @staticmethod
    def _infer_skill_category(name: str, domain: dict) -> SkillCategory:
        """Infer whether an expertise domain maps to hard, domain, or tool."""
        name_lower = name.lower()

        # Tool indicators
        tool_keywords = [
            "git", "docker", "kubernetes", "aws", "gcp", "azure",
            "jenkins", "terraform", "ansible", "jira", "confluence",
            "slack", "figma", "photoshop", "vscode", "vim",
            "postgres", "mysql", "redis", "mongodb", "elasticsearch",
            "kafka", "rabbitmq", "nginx", "grafana", "prometheus",
            "salesforce", "hubspot", "tableau", "powerbi", "excel",
        ]
        if any(kw in name_lower for kw in tool_keywords):
            return SkillCategory.TOOL

        # Domain indicators (specialized knowledge areas)
        domain_keywords = [
            "machine learning", "data science", "cybersecurity",
            "compliance", "regulatory", "financial", "healthcare",
            "legal", "accounting", "marketing", "analytics",
            "ux research", "market research", "competitive analysis",
        ]
        if any(kw in name_lower for kw in domain_keywords):
            return SkillCategory.DOMAIN

        # Default to hard skill
        return SkillCategory.HARD
