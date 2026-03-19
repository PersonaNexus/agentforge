"""Export orchestration configs for different runtimes."""
from __future__ import annotations
from agentforge.composition.models import ConductorSkill, ForgedTeam, ForgedTeammate


class OrchestrationConfigExporter:
    """Export team configuration for different deployment targets."""

    def export_claude_code(self, team: ForgedTeam) -> dict[str, str]:
        """Export as .claude/skills/ directory structure.

        Returns dict of {relative_path: file_content}.
        """
        files = {}

        # Conductor skill
        conductor_path = f".claude/skills/{team.conductor.skill_name}/SKILL.md"
        files[conductor_path] = team.conductor.skill_md

        # Teammate skills
        for ft in team.teammates:
            path = f".claude/skills/{ft.skill_folder.skill_name}/SKILL.md"
            files[path] = ft.skill_folder.skill_md
            for rel_path, content in ft.skill_folder.supplementary_files.items():
                files[f".claude/skills/{ft.skill_folder.skill_name}/{rel_path}"] = content

        return files

    def export_mcp_combined(self, team: ForgedTeam) -> dict:
        """Export combined MCP config for all teammates."""
        return {"mcpServers": {}}

    def export_orchestration_yaml(self, team: ForgedTeam) -> str:
        """Export team orchestration as a YAML config."""
        import yaml

        config = {
            "team": {
                "role": team.role_title,
                "conductor": team.conductor.skill_name,
                "agents": [],
            },
            "routing": team.conductor.routing_table,
            "workflows": [w.to_dict() for w in team.conductor.workflows],
            "handoffs": [h.to_dict() for h in team.conductor.handoffs],
        }

        for ft in team.teammates:
            config["team"]["agents"].append({
                "name": ft.teammate.name,
                "archetype": ft.teammate.archetype,
                "skill": ft.skill_folder.skill_name,
                "skills": ft.teammate.skill_names(),
            })

        return yaml.dump(config, default_flow_style=False, sort_keys=False)

    def export_langgraph(self, team: ForgedTeam) -> str:
        """Export team as a runnable LangGraph StateGraph Python module."""
        from agentforge.composition.langgraph_export import LangGraphExporter
        exporter = LangGraphExporter()
        return exporter.export(team)
