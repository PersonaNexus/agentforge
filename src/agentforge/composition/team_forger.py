"""Forge individual skills for each team member from a single extraction."""
from __future__ import annotations
from agentforge.analysis.team_composer import AgentTeamComposition, AgentTeammate
from agentforge.composition.models import ForgedTeammate
from agentforge.generation.identity_generator import IdentityGenerator
from agentforge.generation.skill_folder import SkillFolderGenerator
from agentforge.models.extracted_skills import (
    ExtractionResult,
    MethodologyExtraction,
    SkillCategory,
)


class TeamForger:
    """Forge individual agent skills for each teammate in a team composition."""

    def forge_team(
        self,
        team: AgentTeamComposition,
        extraction: ExtractionResult,
        methodology: MethodologyExtraction | None = None,
    ) -> list[ForgedTeammate]:
        forged = []
        for teammate in team.teammates:
            scoped_extraction = self._scope_extraction(extraction, teammate)
            scoped_methodology = self._scope_methodology(methodology, teammate)

            generator = IdentityGenerator()
            identity, identity_yaml = generator.generate(scoped_extraction)

            folder_gen = SkillFolderGenerator()
            skill_folder = folder_gen.generate(
                scoped_extraction,
                identity,
                methodology=scoped_methodology,
            )

            forged.append(ForgedTeammate(
                teammate=teammate,
                identity_yaml=identity_yaml,
                skill_folder=skill_folder,
            ))
        return forged

    def _scope_extraction(
        self, extraction: ExtractionResult, teammate: AgentTeammate
    ) -> ExtractionResult:
        """Create a focused extraction with only this teammate's skills."""
        scoped = extraction.model_copy(deep=True)
        # Use the teammate's assigned skills
        teammate_skill_names = {s.name for s in teammate.skills}
        scoped.skills = [s for s in scoped.skills if s.name in teammate_skill_names]

        # Adjust role for this teammate
        scoped.role = scoped.role.model_copy(update={
            "title": teammate.name,
            "purpose": teammate.description,
        })

        # Filter responsibilities to matching ones
        scoped.responsibilities = self._filter_responsibilities(
            extraction.responsibilities, teammate.skills
        )

        # Apply teammate personality
        for trait_name, value in teammate.personality.items():
            if hasattr(scoped.suggested_traits, trait_name):
                setattr(scoped.suggested_traits, trait_name, value)

        return scoped

    def _scope_methodology(
        self,
        methodology: MethodologyExtraction | None,
        teammate: AgentTeammate,
    ) -> MethodologyExtraction | None:
        """Filter methodology to relevant items for this teammate."""
        if not methodology:
            return None

        skill_keywords = set()
        for s in teammate.skills:
            skill_keywords.update(s.name.lower().split())
            if s.context:
                for word in s.context.lower().split()[:10]:
                    if len(word) > 3:
                        skill_keywords.add(word)

        filtered_heuristics = [
            h for h in methodology.heuristics
            if self._text_matches(f"{h.trigger} {h.procedure}", skill_keywords)
        ]
        filtered_triggers = [
            t for t in methodology.trigger_mappings
            if self._text_matches(f"{t.trigger_pattern} {t.technique}", skill_keywords)
        ]
        filtered_templates = [
            t for t in methodology.output_templates
            if self._text_matches(f"{t.name} {t.when_to_use}", skill_keywords)
        ]

        return MethodologyExtraction(
            heuristics=filtered_heuristics or methodology.heuristics[:1],
            trigger_mappings=filtered_triggers or methodology.trigger_mappings[:1],
            output_templates=filtered_templates or methodology.output_templates[:1],
            quality_criteria=methodology.quality_criteria,  # Shared across team
        )

    def _filter_responsibilities(
        self, responsibilities: list[str], skills: list
    ) -> list[str]:
        """Keep responsibilities that match this teammate's skill set."""
        keywords = set()
        for s in skills:
            keywords.update(s.name.lower().split())

        filtered = []
        for resp in responsibilities:
            resp_lower = resp.lower()
            if any(kw in resp_lower for kw in keywords if len(kw) > 3):
                filtered.append(resp)

        return filtered or responsibilities[:2]

    def _text_matches(self, text: str, keywords: set[str]) -> bool:
        """Check if text contains any of the keywords."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords if len(kw) > 3)
