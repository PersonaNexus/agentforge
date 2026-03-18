"""Data models for multi-agent team composition and orchestration."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from agentforge.analysis.team_composer import AgentTeammate
from agentforge.generation.skill_folder import SkillFolderResult


@dataclass
class ForgedTeammate:
    """A fully forged teammate with identity and skill files."""
    teammate: AgentTeammate
    identity_yaml: str
    skill_folder: SkillFolderResult

    def to_dict(self) -> dict:
        return {
            "teammate": self.teammate.to_dict(),
            "identity_yaml": self.identity_yaml,
            "skill_folder": {
                "skill_name": self.skill_folder.skill_name,
                "skill_md": self.skill_folder.skill_md,
                "supplementary_files": self.skill_folder.supplementary_files,
            },
        }


@dataclass
class HandoffProtocol:
    """Defines how one agent passes work to another."""
    from_agent: str
    to_agent: str
    trigger: str
    context_passed: list[str] = field(default_factory=list)
    expected_output: str = ""
    fallback: str = "Escalate to user"

    def to_dict(self) -> dict:
        return {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "trigger": self.trigger,
            "context_passed": self.context_passed,
            "expected_output": self.expected_output,
            "fallback": self.fallback,
        }


@dataclass
class WorkflowStep:
    """A single step in an orchestrated workflow."""
    agent: str
    task: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "task": self.task,
            "inputs": self.inputs,
            "outputs": self.outputs,
        }


@dataclass
class OrchestratedWorkflow:
    """A multi-step workflow involving multiple agents."""
    name: str
    trigger: str
    steps: list[WorkflowStep] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "trigger": self.trigger,
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass
class ConductorSkill:
    """The conductor agent's skill that orchestrates the team."""
    skill_name: str
    skill_md: str
    routing_table: dict[str, list[str]] = field(default_factory=dict)  # agent_name -> keywords
    workflows: list[OrchestratedWorkflow] = field(default_factory=list)
    handoffs: list[HandoffProtocol] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "skill_name": self.skill_name,
            "skill_md": self.skill_md,
            "routing_table": self.routing_table,
            "workflows": [w.to_dict() for w in self.workflows],
            "handoffs": [h.to_dict() for h in self.handoffs],
        }


@dataclass
class ForgedTeam:
    """Complete forged team with conductor and all teammates."""
    role_title: str
    conductor: ConductorSkill
    teammates: list[ForgedTeammate] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "role_title": self.role_title,
            "conductor": self.conductor.to_dict(),
            "teammates": [t.to_dict() for t in self.teammates],
        }
