"""Generate conductor skill that orchestrates a team of agents."""
from __future__ import annotations
from datetime import datetime, timezone
from agentforge.analysis.team_composer import AgentTeamComposition
from agentforge.composition.models import (
    ConductorSkill,
    ForgedTeammate,
    HandoffProtocol,
    OrchestratedWorkflow,
    WorkflowStep,
)
from agentforge.models.extracted_skills import ExtractionResult
from agentforge.utils import make_skill_slug


class ConductorGenerator:
    """Generate a conductor skill that routes and orchestrates teammate agents."""

    def generate(
        self,
        team: AgentTeamComposition,
        forged_teammates: list[ForgedTeammate],
        extraction: ExtractionResult,
    ) -> ConductorSkill:
        routing_table = self._build_routing_table(forged_teammates)
        workflows = self._build_workflows(forged_teammates, extraction)
        handoffs = self._build_handoffs(forged_teammates)
        skill_name = make_skill_slug(f"{extraction.role.title} conductor")
        skill_md = self._render_skill_md(
            skill_name=skill_name,
            role_title=extraction.role.title,
            routing_table=routing_table,
            workflows=workflows,
            teammates=forged_teammates,
            handoffs=handoffs,
            extraction=extraction,
        )

        return ConductorSkill(
            skill_name=skill_name,
            skill_md=skill_md,
            routing_table=routing_table,
            workflows=workflows,
            handoffs=handoffs,
        )

    def _build_routing_table(
        self, teammates: list[ForgedTeammate]
    ) -> dict[str, list[str]]:
        """Build keyword routing: agent_name -> keywords."""
        table = {}
        for ft in teammates:
            keywords = set()
            for skill in ft.teammate.skills:
                keywords.update(w.lower() for w in skill.name.split() if len(w) > 2)
                if skill.context:
                    keywords.update(
                        w.lower() for w in skill.context.split()[:5] if len(w) > 3
                    )
            table[ft.teammate.name] = sorted(keywords)[:10]
        return table

    def _build_workflows(
        self,
        teammates: list[ForgedTeammate],
        extraction: ExtractionResult,
    ) -> list[OrchestratedWorkflow]:
        """Build multi-agent workflows from responsibilities."""
        workflows = []
        if len(teammates) < 2:
            return workflows

        # Create a workflow for complex responsibilities that span multiple agents
        for resp in extraction.responsibilities[:3]:
            involved = []
            for ft in teammates:
                skill_text = " ".join(s.name.lower() for s in ft.teammate.skills)
                resp_lower = resp.lower()
                if any(w in resp_lower for w in skill_text.split() if len(w) > 3):
                    involved.append(ft)

            if len(involved) >= 2:
                steps = []
                for i, ft in enumerate(involved):
                    step_inputs = ["initial context"] if i == 0 else [f"output from {involved[i-1].teammate.name}"]
                    steps.append(WorkflowStep(
                        agent=ft.teammate.name,
                        task=f"Handle {ft.teammate.archetype.lower()} aspects of: {resp[:80]}",
                        inputs=step_inputs,
                        outputs=[f"{ft.teammate.name} deliverable"],
                    ))

                workflows.append(OrchestratedWorkflow(
                    name=f"Workflow: {resp[:60]}",
                    trigger=resp,
                    steps=steps,
                ))

        return workflows[:5]

    def _build_handoffs(
        self, teammates: list[ForgedTeammate]
    ) -> list[HandoffProtocol]:
        """Build handoff protocols between teammates."""
        handoffs = []
        for i, ft_from in enumerate(teammates):
            for ft_to in teammates[i+1:]:
                # Create handoff if archetypes commonly interact
                handoffs.append(HandoffProtocol(
                    from_agent=ft_from.teammate.name,
                    to_agent=ft_to.teammate.name,
                    trigger=f"When {ft_from.teammate.name} produces output needing {ft_to.teammate.archetype.lower()} review",
                    context_passed=["task description", "work product", "quality criteria"],
                    expected_output=f"Reviewed/enhanced deliverable from {ft_to.teammate.name}",
                ))
        return handoffs

    def _render_skill_md(
        self,
        skill_name: str,
        role_title: str,
        routing_table: dict[str, list[str]],
        workflows: list[OrchestratedWorkflow],
        teammates: list[ForgedTeammate],
        handoffs: list[HandoffProtocol],
        extraction: ExtractionResult,
    ) -> str:
        lines = []

        # Frontmatter
        lines.append("---")
        lines.append(f"name: {skill_name}")
        lines.append(f'description: "Orchestrate the {role_title} agent team"')
        lines.append("allowed-tools: Read, Grep, Glob, Bash, Write, Edit")
        lines.append("---")
        lines.append("")

        # Title
        lines.append(f"# {role_title} — Team Conductor")
        lines.append("")
        lines.append(
            f"You coordinate a team of {len(teammates)} specialized agents. "
            "Route requests to the right agent, orchestrate multi-step workflows, "
            "and synthesize results."
        )
        lines.append("")

        # Team roster
        lines.append("## Team Roster")
        lines.append("")
        lines.append("| Agent | Specialization | Skills |")
        lines.append("|-------|---------------|--------|")
        for ft in teammates:
            skills_str = ", ".join(ft.teammate.skill_names()[:3])
            if len(ft.teammate.skill_names()) > 3:
                skills_str += f" +{len(ft.teammate.skill_names()) - 3}"
            lines.append(f"| {ft.teammate.name} | {ft.teammate.archetype} | {skills_str} |")
        lines.append("")

        # Routing rules
        lines.append("## Routing Rules")
        lines.append("")
        lines.append("When a request arrives, match keywords to route to the right agent:")
        lines.append("")
        for agent_name, keywords in routing_table.items():
            kw_str = ", ".join(keywords[:8])
            lines.append(f"- **{agent_name}**: [{kw_str}]")
        lines.append("")
        lines.append("For ambiguous requests, ask the user to clarify scope before routing.")
        lines.append("")

        # Workflows
        if workflows:
            lines.append("## Multi-Agent Workflows")
            lines.append("")
            for wf in workflows:
                lines.append(f"### {wf.name}")
                lines.append(f"**Trigger:** {wf.trigger}")
                lines.append("")
                for i, step in enumerate(wf.steps, 1):
                    inputs = ", ".join(step.inputs)
                    lines.append(f"{i}. **{step.agent}**: {step.task}")
                    lines.append(f"   - Input: {inputs}")
                    lines.append(f"   - Output: {', '.join(step.outputs)}")
                lines.append("")

        # Handoff protocol
        lines.append("## Handoff Protocol")
        lines.append("")
        lines.append("When delegating to an agent:")
        lines.append("- Provide: task description, relevant context, expected output format")
        lines.append("- Receive: completed work product, confidence level, blockers (if any)")
        lines.append("- If blocked: escalate to user or try alternative agent")
        lines.append("")

        # Scope
        lines.append("## Scope")
        lines.append("")
        lines.append("The conductor should:")
        lines.append("- Route single-domain requests to the appropriate specialist")
        lines.append("- Orchestrate multi-step workflows spanning multiple agents")
        lines.append("- Synthesize outputs from multiple agents into coherent deliverables")
        lines.append("- Escalate to the user when no agent can handle a request")
        lines.append("")
        lines.append("The conductor should NOT:")
        lines.append("- Attempt specialist work directly — always delegate")
        lines.append("- Make decisions that require domain expertise — consult the specialist")
        lines.append("- Skip the handoff protocol — always provide context when delegating")
        lines.append("")

        # Footer
        lines.append("---")
        lines.append(
            f"*Generated by AgentForge Team Mode | "
            f"Source: {role_title} | "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}*"
        )
        lines.append("")

        return "\n".join(lines)
