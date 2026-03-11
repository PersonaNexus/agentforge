"""Agent team composer: cluster skills into logical AI agent teammates for a role.

Instead of framing automation as "what the agent replaces," this module proposes
a team of specialized AI agents that *pair with* the human in the role — each
with a distinct archetype, personality, and benefit statement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agentforge.models.extracted_skills import (
    ExtractionResult,
    ExtractedSkill,
    SkillCategory,
    SkillProficiency,
)


@dataclass
class AgentTeammate:
    """A single AI agent teammate proposed for the role."""

    name: str
    archetype: str
    arch_key: str
    description: str
    skills: list[ExtractedSkill]
    personality: dict[str, float]
    benefit: str

    def skill_names(self) -> list[str]:
        return [s.name for s in self.skills]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "archetype": self.archetype,
            "description": self.description,
            "skills": self.skill_names(),
            "personality": {k: round(v, 2) for k, v in self.personality.items()},
            "benefit": self.benefit,
        }


@dataclass
class AgentTeamComposition:
    """A complete team of AI agent teammates for a role."""

    role_title: str
    teammates: list[AgentTeammate] = field(default_factory=list)
    team_benefit: str = ""

    def to_dict(self) -> dict:
        return {
            "role_title": self.role_title,
            "teammates": [t.to_dict() for t in self.teammates],
            "team_benefit": self.team_benefit,
        }


# ── Archetype definitions ──
# Each archetype maps to a set of skill affinities and a personality profile.

_ARCHETYPES: dict[str, dict] = {
    "research_analyst": {
        "label": "Research Analyst",
        "affinity_categories": [SkillCategory.DOMAIN],
        "affinity_keywords": [
            "research", "analysis", "data", "insight", "market", "competitive",
            "trend", "report", "survey", "benchmark", "literature",
        ],
        "personality": {
            "rigor": 0.85,
            "creativity": 0.60,
            "patience": 0.75,
            "directness": 0.70,
            "warmth": 0.35,
            "verbosity": 0.65,
        },
        "benefit_template": (
            "Continuously surfaces insights and intelligence so {role} "
            "can make faster, data-informed decisions"
        ),
    },
    "technical_builder": {
        "label": "Technical Builder",
        "affinity_categories": [SkillCategory.HARD],
        "affinity_keywords": [
            "develop", "build", "code", "engineer", "implement", "architect",
            "design", "test", "debug", "deploy", "infrastructure", "system",
            "software", "programming", "algorithm",
        ],
        "personality": {
            "rigor": 0.90,
            "directness": 0.80,
            "patience": 0.60,
            "creativity": 0.55,
            "warmth": 0.30,
            "verbosity": 0.40,
        },
        "benefit_template": (
            "Handles technical implementation and prototyping so {role} "
            "can focus on architecture decisions and strategy"
        ),
    },
    "ops_automator": {
        "label": "Ops Automator",
        "affinity_categories": [SkillCategory.TOOL],
        "affinity_keywords": [
            "automate", "pipeline", "workflow", "process", "monitor",
            "ci/cd", "devops", "infrastructure", "cloud", "deploy",
            "integration", "platform", "tool", "dashboard",
        ],
        "personality": {
            "rigor": 0.85,
            "directness": 0.85,
            "patience": 0.50,
            "creativity": 0.40,
            "warmth": 0.25,
            "verbosity": 0.30,
        },
        "benefit_template": (
            "Manages tooling, automation, and operational workflows so {role} "
            "spends less time on repetitive tasks"
        ),
    },
    "content_crafter": {
        "label": "Content Crafter",
        "affinity_categories": [],
        "affinity_keywords": [
            "write", "draft", "document", "content", "copy", "edit",
            "report", "proposal", "presentation", "communication",
            "blog", "article", "spec", "prd", "brief",
        ],
        "personality": {
            "creativity": 0.80,
            "verbosity": 0.75,
            "warmth": 0.60,
            "rigor": 0.65,
            "directness": 0.55,
            "patience": 0.70,
        },
        "benefit_template": (
            "Drafts and polishes documents, specs, and communications so {role} "
            "can iterate quickly on ideas"
        ),
    },
    "data_navigator": {
        "label": "Data Navigator",
        "affinity_categories": [],
        "affinity_keywords": [
            "data", "analytics", "metrics", "dashboard", "sql", "database",
            "visualization", "reporting", "statistics", "bi", "etl",
            "warehouse", "query", "spreadsheet",
        ],
        "personality": {
            "rigor": 0.90,
            "directness": 0.75,
            "patience": 0.65,
            "creativity": 0.45,
            "warmth": 0.30,
            "verbosity": 0.50,
        },
        "benefit_template": (
            "Wrangles data and surfaces key metrics so {role} "
            "always has the numbers to back decisions"
        ),
    },
    "stakeholder_liaison": {
        "label": "Stakeholder Liaison",
        "affinity_categories": [SkillCategory.SOFT],
        "affinity_keywords": [
            "stakeholder", "client", "customer", "communicate", "present",
            "negotiate", "relationship", "collaborate", "meeting", "align",
            "manage", "coordinate", "facilitat",
        ],
        "personality": {
            "warmth": 0.85,
            "empathy": 0.80,
            "patience": 0.80,
            "directness": 0.55,
            "verbosity": 0.65,
            "humor": 0.40,
        },
        "benefit_template": (
            "Prepares meeting briefs, drafts updates, and tracks action items so {role} "
            "can focus on the human side of stakeholder relationships"
        ),
    },
    "quality_guardian": {
        "label": "Quality Guardian",
        "affinity_categories": [],
        "affinity_keywords": [
            "quality", "test", "review", "audit", "compliance", "security",
            "standard", "validation", "verification", "inspect", "check",
            "assurance", "risk", "governance",
        ],
        "personality": {
            "rigor": 0.95,
            "directness": 0.80,
            "epistemic_humility": 0.75,
            "patience": 0.70,
            "creativity": 0.30,
            "warmth": 0.35,
        },
        "benefit_template": (
            "Continuously reviews and validates work against standards so {role} "
            "can ship with confidence"
        ),
    },
    "learning_coach": {
        "label": "Learning Coach",
        "affinity_categories": [],
        "affinity_keywords": [
            "mentor", "train", "teach", "onboard", "guide", "coach",
            "develop", "skill", "growth", "learn", "knowledge",
        ],
        "personality": {
            "patience": 0.90,
            "warmth": 0.85,
            "empathy": 0.80,
            "verbosity": 0.70,
            "creativity": 0.60,
            "directness": 0.50,
        },
        "benefit_template": (
            "Creates training materials and knowledge resources so {role} "
            "can scale their expertise across the team"
        ),
    },
}


_DOMAIN_NAMES: dict[str, dict[str, str]] = {
    "engineering": {
        "research_analyst": "Tech Scout",
        "technical_builder": "Code Architect",
        "ops_automator": "DevOps Pilot",
        "content_crafter": "Spec Drafter",
        "data_navigator": "Data Wrangler",
        "quality_guardian": "Code Reviewer",
    },
    "data": {
        "research_analyst": "Insight Miner",
        "data_navigator": "Data Whisperer",
        "technical_builder": "Pipeline Builder",
    },
    "marketing": {
        "content_crafter": "Campaign Crafter",
        "research_analyst": "Market Scout",
        "data_navigator": "Metrics Maven",
    },
    "sales": {
        "stakeholder_liaison": "Deal Prep",
        "content_crafter": "Pitch Crafter",
        "research_analyst": "Market Scout",
    },
    "product": {
        "research_analyst": "Market Scout",
        "content_crafter": "Spec Drafter",
        "data_navigator": "Metrics Maven",
        "stakeholder_liaison": "Stakeholder Prep",
    },
    "finance": {
        "data_navigator": "Numbers Analyst",
        "quality_guardian": "Compliance Checker",
        "research_analyst": "Market Watcher",
    },
}


class TeamComposer:
    """Compose a team of AI agent teammates from extraction results.

    Uses heuristic skill clustering to group skills into logical agent
    archetypes. Each archetype is scored by affinity (category match +
    keyword overlap), and only archetypes with meaningful skill coverage
    are included.
    """

    def __init__(self, min_skills_per_teammate: int = 1, max_teammates: int = 5):
        self.min_skills = min_skills_per_teammate
        self.max_teammates = max_teammates

    def compose(self, extraction: ExtractionResult) -> AgentTeamComposition:
        """Compose an agent team from extraction results."""
        if not extraction.skills:
            return AgentTeamComposition(
                role_title=extraction.role.title,
                team_benefit=f"No skills extracted for {extraction.role.title}.",
            )

        # Score each archetype against available skills
        archetype_scores: list[tuple[str, float, list[ExtractedSkill]]] = []

        for arch_key, arch_def in _ARCHETYPES.items():
            matched_skills, score = self._score_archetype(
                extraction.skills, arch_def
            )
            if matched_skills and score > 0:
                archetype_scores.append((arch_key, score, matched_skills))

        # Sort by score descending
        archetype_scores.sort(key=lambda x: x[1], reverse=True)

        # Assign skills greedily (each skill goes to its best-fit archetype)
        assigned: set[str] = set()
        teammates: list[AgentTeammate] = []

        for arch_key, _, candidate_skills in archetype_scores:
            if len(teammates) >= self.max_teammates:
                break

            unassigned = [s for s in candidate_skills if s.name not in assigned]
            if len(unassigned) < self.min_skills:
                continue

            arch_def = _ARCHETYPES[arch_key]
            role_short = extraction.role.title.split(",")[0].strip()

            teammate = AgentTeammate(
                name=self._generate_name(arch_key, extraction),
                archetype=arch_def["label"],
                arch_key=arch_key,
                description=self._generate_description(unassigned, arch_def),
                skills=unassigned,
                personality=dict(arch_def["personality"]),
                benefit=arch_def["benefit_template"].replace("{role}", role_short),
            )
            teammates.append(teammate)
            assigned.update(s.name for s in unassigned)

        # Sweep remaining unassigned skills into the closest existing teammate
        remaining = [s for s in extraction.skills if s.name not in assigned]
        if remaining and teammates:
            for skill in remaining:
                best_teammate = self._find_closest_teammate(skill, teammates)
                best_teammate.skills.append(skill)

        team_benefit = self._generate_team_benefit(
            extraction.role.title, teammates
        )

        return AgentTeamComposition(
            role_title=extraction.role.title,
            teammates=teammates,
            team_benefit=team_benefit,
        )

    def _score_archetype(
        self,
        skills: list[ExtractedSkill],
        arch_def: dict,
    ) -> tuple[list[ExtractedSkill], float]:
        """Score how well skills match an archetype. Returns matched skills and score."""
        matched: list[ExtractedSkill] = []
        total_score = 0.0

        affinity_cats: list[SkillCategory] = arch_def.get("affinity_categories", [])
        keywords: list[str] = arch_def.get("affinity_keywords", [])

        for skill in skills:
            score = 0.0

            # Category match
            if skill.category in affinity_cats:
                score += 2.0

            # Keyword match against skill name, context, and genai_application
            text = f"{skill.name} {skill.context} {skill.genai_application}".lower()
            keyword_hits = sum(1 for kw in keywords if kw in text)
            score += keyword_hits * 0.5

            if score > 0:
                matched.append(skill)
                total_score += score

        return matched, total_score

    def _generate_name(self, arch_key: str, extraction: ExtractionResult) -> str:
        """Generate a contextual name for the teammate."""
        domain_lower = (extraction.role.domain or "").lower()
        for domain_key, names in _DOMAIN_NAMES.items():
            if domain_key in domain_lower and arch_key in names:
                return names[arch_key]
        return _ARCHETYPES[arch_key]["label"]

    def _generate_description(
        self, skills: list[ExtractedSkill], arch_def: dict
    ) -> str:
        """Generate a brief description of what this teammate handles."""
        skill_names = [s.name for s in skills[:4]]
        if len(skills) > 4:
            skill_names.append(f"+{len(skills) - 4} more")
        skills_str = ", ".join(skill_names)
        return f"Handles {skills_str}"

    def _find_closest_teammate(
        self, skill: ExtractedSkill, teammates: list[AgentTeammate]
    ) -> AgentTeammate:
        """Find the teammate whose archetype best matches a skill."""
        best = teammates[0]
        best_score = 0.0

        for teammate in teammates:
            arch_def = _ARCHETYPES.get(teammate.arch_key)
            if not arch_def:
                continue
            _, score = self._score_archetype([skill], arch_def)
            if score > best_score:
                best_score = score
                best = teammate

        return best

    def _generate_team_benefit(
        self, role_title: str, teammates: list[AgentTeammate]
    ) -> str:
        """Generate an overall team benefit statement."""
        if not teammates:
            return ""

        count = len(teammates)
        total_skills = sum(len(t.skills) for t in teammates)
        archetypes = [t.archetype for t in teammates]

        return (
            f"A team of {count} specialized AI agents covering {total_skills} skills "
            f"({', '.join(archetypes)}) — designed to amplify the {role_title}'s "
            f"impact by handling the heavy lifting while keeping humans in the "
            f"driver's seat for judgment calls and relationships."
        )
