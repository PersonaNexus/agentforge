"""Interactive wizard for AgentForge CLI.

Provides a guided experience that walks users through command selection,
file picking, option configuration, pipeline execution, and post-run
actions (refine, team generation, re-run, export).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

_JD_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".docx"}
_IDENTITY_EXTENSIONS = {".yaml", ".yml"}
_CULTURE_EXTENSIONS = {".yaml", ".yml", ".md", ".markdown"}
_TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _numbered_prompt(header: str, choices: list[str], allow_skip: bool = False) -> int | None:
    """Show a numbered menu and return the selected index (0-based), or None if skipped."""
    console.print(f"\n[bold]{header}[/bold]")
    for i, choice in enumerate(choices, 1):
        console.print(f"  [cyan]{i}[/cyan]. {choice}")
    if allow_skip:
        console.print(f"  [dim]{len(choices) + 1}. Skip[/dim]")

    while True:
        raw = typer.prompt("Selection", default="1")
        try:
            idx = int(raw)
        except ValueError:
            console.print("[red]Please enter a number.[/red]")
            continue
        max_val = len(choices) + (1 if allow_skip else 0)
        if 1 <= idx <= max_val:
            if allow_skip and idx == len(choices) + 1:
                return None
            return idx - 1
        console.print(f"[red]Enter a number between 1 and {max_val}.[/red]")


def _find_files(directory: Path, extensions: set[str], limit: int = 10) -> list[Path]:
    """Find files with given extensions in directory, sorted by name."""
    try:
        matches = sorted(
            f for f in directory.iterdir()
            if f.is_file() and f.suffix.lower() in extensions
        )
        return matches[:limit]
    except OSError:
        return []


def _pick_file(
    prompt_text: str,
    extensions: set[str],
    required: bool = True,
    search_dir: Path | None = None,
) -> Path | None:
    """Interactively pick a file. Auto-discovers candidates in search_dir."""
    candidates = _find_files(search_dir or Path.cwd(), extensions)

    if candidates:
        console.print(f"\n[bold]{prompt_text}[/bold]")
        console.print("[dim]Files found in current directory:[/dim]")
        for i, f in enumerate(candidates, 1):
            console.print(f"  [cyan]{i}[/cyan]. {f.name}")
        console.print(f"  [cyan]{len(candidates) + 1}[/cyan]. Enter a custom path")
        if not required:
            console.print(f"  [dim]{len(candidates) + 2}. Skip[/dim]")

        while True:
            default = "1" if candidates else str(len(candidates) + 1)
            raw = typer.prompt("Selection", default=default)
            try:
                idx = int(raw)
            except ValueError:
                console.print("[red]Please enter a number.[/red]")
                continue

            max_val = len(candidates) + 1 + (1 if not required else 0)
            if idx < 1 or idx > max_val:
                console.print(f"[red]Enter a number between 1 and {max_val}.[/red]")
                continue

            if not required and idx == len(candidates) + 2:
                return None
            if idx == len(candidates) + 1:
                break  # fall through to manual path entry
            return candidates[idx - 1]

    # Manual path entry
    while True:
        path_str = typer.prompt(prompt_text if not candidates else "File path")
        path = Path(path_str).expanduser()
        if not path.exists():
            console.print(f"[red]File not found:[/red] {path}")
            if not required and typer.confirm("Skip this file?", default=True):
                return None
            continue
        if path.suffix.lower() not in extensions:
            ext_list = ", ".join(sorted(extensions))
            console.print(f"[yellow]Expected extensions: {ext_list}[/yellow]")
            if not typer.confirm("Use this file anyway?", default=False):
                continue
        return path


def _pick_directory(prompt_text: str, required: bool = True) -> Path | None:
    """Prompt for a directory path."""
    while True:
        raw = typer.prompt(prompt_text, default="." if not required else "")
        if not raw and not required:
            return None
        path = Path(raw).expanduser()
        if path.is_dir():
            return path
        console.print(f"[red]Not a directory:[/red] {path}")
        if not required and typer.confirm("Skip?", default=True):
            return None


# ---------------------------------------------------------------------------
# Command-specific option pickers
# ---------------------------------------------------------------------------


def _pick_optional_context_files(opts: dict, include_culture: bool = True) -> None:
    """Prompt for optional culture, examples, and frameworks files."""
    if include_culture and typer.confirm("Apply a culture profile?", default=False):
        templates_dir = Path(__file__).parent / "templates" / "cultures"
        builtins = [f.stem for f in sorted(templates_dir.glob("*.yaml"))] if templates_dir.exists() else []
        if builtins:
            console.print(f"[dim]Built-in templates: {', '.join(builtins)}[/dim]")
        opts["culture"] = _pick_file("Culture file", _CULTURE_EXTENSIONS, required=False)

    if typer.confirm("Provide work examples?", default=False):
        opts["examples"] = _pick_file("Examples file", _TEXT_EXTENSIONS, required=False)

    if typer.confirm("Provide frameworks/methodologies?", default=False):
        opts["frameworks"] = _pick_file("Frameworks file", _TEXT_EXTENSIONS, required=False)


def _load_optional_files_to_context(opts: dict, context: dict) -> None:
    """Load optional culture, examples, and frameworks files into pipeline context."""
    if opts.get("culture"):
        context["culture_path"] = str(opts["culture"])
        console.print(f"[blue]Culture:[/blue] {opts['culture']}")
    if opts.get("examples"):
        context["user_examples"] = opts["examples"].read_text()
        console.print(f"[blue]Examples:[/blue] {opts['examples']}")
    if opts.get("frameworks"):
        context["user_frameworks"] = opts["frameworks"].read_text()
        console.print(f"[blue]Frameworks:[/blue] {opts['frameworks']}")


def _pick_forge_options() -> dict:
    """Gather forge-specific options interactively."""
    opts: dict = {}

    # Mode
    mode_idx = _numbered_prompt(
        "Pipeline mode:",
        ["Default (full pipeline)", "Quick (skip culture, mapping, gap analysis)", "Deep (detailed skill scoring)"],
    )
    opts["mode"] = ["default", "quick", "deep"][mode_idx or 0]

    # Model
    opts["model"] = typer.prompt("LLM model", default="claude-sonnet-4-20250514")

    # Culture, examples, frameworks
    _pick_optional_context_files(opts)

    # Output
    opts["output_dir"] = typer.prompt("Output directory", default=".")

    # Extras
    opts["skill_folder"] = typer.confirm("Generate Claude Code skill folder?", default=True)
    opts["no_skill_file"] = not typer.confirm("Generate full agent profile (SKILL.md)?", default=True)

    return opts


def _pick_batch_options() -> dict:
    """Gather batch-specific options interactively."""
    opts: dict = {}
    opts["model"] = typer.prompt("LLM model", default="claude-sonnet-4-20250514")
    _pick_optional_context_files(opts)
    opts["output_dir"] = typer.prompt("Output directory", default="./batch_output")
    opts["parallel"] = int(typer.prompt("Parallel workers", default="1"))
    return opts


def _pick_team_options() -> dict:
    """Gather team-specific options interactively."""
    opts: dict = {}
    opts["model"] = typer.prompt("LLM model", default="claude-sonnet-4-20250514")
    _pick_optional_context_files(opts)

    fmt_idx = _numbered_prompt(
        "Output format:",
        ["Claude Code (default)", "LangGraph", "Both"],
    )
    opts["format"] = ["claude", "langgraph", "both"][fmt_idx or 0]

    opts["output_dir"] = typer.prompt("Output directory", default="./team_output")
    return opts


def _pick_identity_import_options() -> dict:
    """Gather identity import options interactively."""
    opts: dict = {}

    fmt_idx = _numbered_prompt(
        "Output format:",
        ["Claude Code", "ClawHub", "Both"],
    )
    opts["format"] = ["claude_code", "clawhub", "both"][fmt_idx or 0]

    opts["model"] = typer.prompt("LLM model", default="claude-sonnet-4-20250514")
    opts["refine"] = typer.confirm("Run LLM-based refinement after import?", default=False)
    _pick_optional_context_files(opts, include_culture=False)
    opts["output_dir"] = typer.prompt("Output directory", default=".")
    return opts


# ---------------------------------------------------------------------------
# Pipeline runners (delegate to existing pipeline code)
# ---------------------------------------------------------------------------


def _run_forge(jd_file: Path, opts: dict) -> dict:
    """Run the forge pipeline and return context."""
    from agentforge.cli import _display_extraction, _make_client
    from agentforge.pipeline.forge_pipeline import ForgePipeline
    from agentforge.utils import safe_output_path, safe_rel_path

    mode = opts.get("mode", "default")
    if mode == "quick":
        pipeline = ForgePipeline.quick()
    elif mode == "deep":
        pipeline = ForgePipeline.deep_analysis()
    else:
        pipeline = ForgePipeline.default()

    client = _make_client(opts.get("model", "claude-sonnet-4-20250514"))
    context: dict = {
        "input_path": str(jd_file),
        "llm_client": client,
    }
    _load_optional_files_to_context(opts, context)

    console.print(f"[blue]Forging agent from:[/blue] {jd_file}")
    context = pipeline.run(context)

    extraction = context["extraction"]
    _display_extraction(extraction)

    # Save outputs
    output_dir = Path(opts.get("output_dir", "."))
    output_dir.mkdir(parents=True, exist_ok=True)

    identity_yaml = context["identity_yaml"]
    agent_id = context["identity"].metadata.id
    yaml_path = safe_output_path(output_dir, f"{agent_id}.yaml")
    yaml_path.write_text(identity_yaml)
    console.print(f"[green]Identity saved:[/green] {yaml_path}")

    if not opts.get("no_skill_file") and "skill_file" in context:
        skill_path = safe_output_path(output_dir, f"{agent_id}_SKILL.md")
        skill_path.write_text(context["skill_file"])
        console.print(f"[green]Full agent profile saved:[/green] {skill_path}")

    if opts.get("skill_folder") and "skill_folder" in context:
        sf = context["skill_folder"]
        folder_path = safe_output_path(output_dir, sf.skill_name)
        folder_path.mkdir(exist_ok=True)
        (folder_path / "SKILL.md").write_text(sf.skill_md_with_references())
        for rel_path, content in sf.supplementary_files.items():
            ref_path = safe_rel_path(folder_path, rel_path)
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(content)
        ref_count = len(sf.supplementary_files)
        ref_msg = f" + {ref_count} reference file{'s' if ref_count != 1 else ''}" if ref_count else ""
        console.print(
            f"[green]Claude Code skill saved:[/green] {folder_path}/\n"
            f"  [dim]SKILL.md{ref_msg}[/dim]"
        )

    coverage = context.get("coverage_score", 0.0)
    automation = extraction.automation_potential
    console.print(
        f"\n[bold green]Agent '{extraction.role.title}' forged![/bold green]\n"
        f"  Skills: {len(extraction.skills)} | "
        f"Coverage: {int(coverage * 100)}% | "
        f"Automation: {int(automation * 100)}%"
    )

    context["_output_dir"] = str(output_dir)
    return context


def _run_batch(jd_dir: Path, opts: dict) -> dict:
    """Run the batch pipeline."""
    from agentforge.cli import _make_client
    from agentforge.pipeline.batch import BatchProcessor
    from agentforge.pipeline.forge_pipeline import ForgePipeline

    jd_files = sorted(
        str(f) for f in jd_dir.iterdir()
        if f.is_file() and f.suffix.lower() in _JD_EXTENSIONS
    )
    if not jd_files:
        console.print(f"[yellow]No JD files found in {jd_dir}[/yellow]")
        return {}

    console.print(f"[blue]Found {len(jd_files)} JD files in {jd_dir}[/blue]")

    client = _make_client(opts.get("model", "claude-sonnet-4-20250514"))
    shared_context: dict = {"llm_client": client}
    _load_optional_files_to_context(opts, shared_context)

    output_dir = Path(opts.get("output_dir", "./batch_output"))
    pipeline = ForgePipeline.default()
    processor = BatchProcessor(
        pipeline=pipeline,
        parallel=opts.get("parallel", 1),
        output_dir=output_dir,
    )

    results = processor.process(jd_files, shared_context=shared_context)
    processor.display_summary(results)
    return {"_batch_results": results, "_output_dir": str(output_dir)}


def _run_team(jd_file: Path, opts: dict) -> dict:
    """Run the team pipeline."""
    from agentforge.cli import _make_client
    from agentforge.composition.orchestration_config import OrchestrationConfigExporter
    from agentforge.pipeline.forge_pipeline import ForgePipeline

    pipeline = ForgePipeline.team()
    client = _make_client(opts.get("model", "claude-sonnet-4-20250514"))
    context: dict = {
        "input_path": str(jd_file),
        "llm_client": client,
    }
    _load_optional_files_to_context(opts, context)

    console.print(f"[blue]Forging team from:[/blue] {jd_file}")
    context = pipeline.run(context)

    forged_team_result = context.get("forged_team_result")
    if not forged_team_result:
        console.print("[yellow]No team was composed — the role may be too narrow.[/yellow]")
        return context

    output_dir = Path(opts.get("output_dir", "./team_output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save conductor
    conductor = forged_team_result.conductor
    conductor_dir = output_dir / conductor.skill_name
    conductor_dir.mkdir(exist_ok=True)
    (conductor_dir / "SKILL.md").write_text(conductor.skill_md)
    console.print(f"[green]Conductor saved:[/green] {conductor_dir}/SKILL.md")

    # Save teammates
    for ft in forged_team_result.teammates:
        tm_dir = output_dir / ft.skill_folder.skill_name
        tm_dir.mkdir(exist_ok=True)
        (tm_dir / "SKILL.md").write_text(ft.skill_folder.skill_md)
        for rel_path, content in ft.skill_folder.supplementary_files.items():
            ref_path = safe_rel_path(tm_dir, rel_path)
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(content)
        console.print(f"[green]Agent saved:[/green] {tm_dir}/SKILL.md ({ft.teammate.archetype})")

    # Orchestration config
    exporter = OrchestrationConfigExporter()
    orch_yaml = exporter.export_orchestration_yaml(forged_team_result)
    (output_dir / "orchestration.yaml").write_text(orch_yaml)
    console.print(f"[green]Orchestration config:[/green] {output_dir}/orchestration.yaml")

    fmt = opts.get("format", "claude")
    if fmt in ("langgraph", "both"):
        langgraph_py = exporter.export_langgraph(forged_team_result)
        graph_path = output_dir / "agent_graph.py"
        graph_path.write_text(langgraph_py)
        console.print(f"[green]LangGraph module:[/green] {graph_path}")

    # Display team table
    team_table = Table(title="Forged Agent Team", show_lines=True, title_style="bold cyan")
    team_table.add_column("Agent", style="cyan")
    team_table.add_column("Archetype", style="green")
    team_table.add_column("Skills", style="dim", max_width=35)
    for ft in forged_team_result.teammates:
        skills_str = ", ".join(ft.teammate.skill_names()[:3])
        if len(ft.teammate.skill_names()) > 3:
            skills_str += f" +{len(ft.teammate.skill_names()) - 3}"
        team_table.add_row(ft.teammate.name, ft.teammate.archetype, skills_str)
    console.print(team_table)

    console.print(
        f"\n[bold green]Team of {len(forged_team_result.teammates)} agents + conductor forged![/bold green]"
    )

    context["_output_dir"] = str(output_dir)
    return context


def _run_identity_import(identity_file: Path, opts: dict) -> dict:
    """Run identity import."""
    from agentforge.cli import _display_extraction, _make_client
    from agentforge.generation.identity_generator import IdentityGenerator
    from agentforge.generation.identity_loader import IdentityLoader
    from agentforge.utils import safe_output_path, safe_rel_path

    console.print(f"[blue]Loading identity:[/blue] {identity_file}")
    loader = IdentityLoader()
    extraction, methodology, original_yaml = loader.load_file(str(identity_file))

    console.print(f"[green]Loaded:[/green] {extraction.role.title}")
    _display_extraction(extraction)

    output_dir = Path(opts.get("output_dir", "."))
    output_dir.mkdir(parents=True, exist_ok=True)

    generator = IdentityGenerator()
    identity, identity_yaml = generator.generate(extraction)

    agent_id = identity.metadata.id
    yaml_path = safe_output_path(output_dir, f"{agent_id}.yaml")
    yaml_path.write_text(identity_yaml)
    console.print(f"[green]Identity saved:[/green] {yaml_path}")

    output_format = opts.get("format", "claude_code")
    user_examples = opts["examples"].read_text() if opts.get("examples") else ""
    user_frameworks = opts["frameworks"].read_text() if opts.get("frameworks") else ""

    if output_format in ("claude_code", "both"):
        from agentforge.generation.skill_folder import SkillFolderGenerator

        sf_gen = SkillFolderGenerator()
        sf = sf_gen.generate(
            extraction, identity, jd=None, methodology=methodology,
            user_examples=user_examples, user_frameworks=user_frameworks,
        )
        folder_path = safe_output_path(output_dir, sf.skill_name)
        folder_path.mkdir(exist_ok=True)
        (folder_path / "SKILL.md").write_text(sf.skill_md_with_references())
        for rel_path, content in sf.supplementary_files.items():
            ref_path = safe_rel_path(folder_path, rel_path)
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(content)
        console.print(f"[green]Claude Code skill saved:[/green] {folder_path}/")

    if output_format in ("clawhub", "both"):
        from agentforge.generation.clawhub_skill import ClawHubSkillGenerator

        ch_gen = ClawHubSkillGenerator()
        ch = ch_gen.generate(extraction, jd=None, methodology=methodology)
        ch_path = safe_output_path(output_dir, f"{ch.skill_name}_clawhub_SKILL.md")
        ch_path.write_text(ch.skill_md)
        console.print(f"[green]ClawHub skill saved:[/green] {ch_path}")

    console.print(f"\n[bold green]Identity '{extraction.role.title}' imported![/bold green]")
    return {
        "extraction": extraction,
        "methodology": methodology,
        "identity": identity,
        "_output_dir": str(output_dir),
    }


# ---------------------------------------------------------------------------
# Post-run actions
# ---------------------------------------------------------------------------


def _refine_loop(context: dict) -> dict:
    """Interactive refinement loop using SkillRefiner."""
    from agentforge.analysis.skill_refiner import SkillRefiner
    from agentforge.generation.skill_folder import SkillFolderGenerator
    from agentforge.utils import safe_output_path, safe_rel_path

    refiner = SkillRefiner()
    sf_gen = SkillFolderGenerator()
    extraction = context.get("extraction")
    methodology = context.get("methodology")
    identity = context.get("identity")

    if not extraction or not identity:
        console.print("[yellow]Refinement requires a completed forge — skipping.[/yellow]")
        return context

    output_dir = Path(context.get("_output_dir", "."))

    console.print(Panel(
        "[bold]Refinement Mode[/bold]\n"
        "Available categories: methodology, triggers, templates, quality,\n"
        "domain, persona, scope, examples, frameworks\n\n"
        "Type your refinement instructions, or 'done' to finish.",
        border_style="yellow",
    ))

    while True:
        category_idx = _numbered_prompt(
            "What would you like to refine?",
            [
                "Methodology (heuristics, procedures)",
                "Triggers (trigger-to-technique mappings)",
                "Templates (output templates)",
                "Quality (quality criteria)",
                "Domain (domain context)",
                "Persona (personality traits)",
                "Scope (scope and guardrails)",
                "Examples (work examples)",
                "Frameworks (frameworks/methodologies)",
                "Done refining",
            ],
        )

        categories = [
            "methodology", "triggers", "templates", "quality",
            "domain", "persona", "scope", "examples", "frameworks",
        ]

        if category_idx is None or category_idx == 9:
            break

        category = categories[category_idx]
        console.print(f"\n[cyan]Enter your {category} refinement (end with an empty line):[/cyan]")

        lines: list[str] = []
        while True:
            line = typer.prompt("", default="", show_default=False)
            if not line and lines:
                break
            if line:
                lines.append(line)

        if not lines:
            console.print("[dim]No input — skipping.[/dim]")
            continue

        text = "\n".join(lines)
        edits = {category: text}

        extraction, methodology, supplementary = refiner.merge(
            extraction, methodology, edits,
        )

        # Regenerate skill folder with refined data
        sf = sf_gen.generate(
            extraction, identity, jd=None, methodology=methodology,
        )

        # Add any supplementary files from refinement
        for k, v in supplementary.items():
            sf.supplementary_files[k] = v

        # Save updated skill folder
        folder_path = safe_output_path(output_dir, sf.skill_name)
        folder_path.mkdir(exist_ok=True)
        (folder_path / "SKILL.md").write_text(sf.skill_md_with_references())
        for rel_path, content in sf.supplementary_files.items():
            ref_path = safe_rel_path(folder_path, rel_path)
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(content)

        console.print(f"[green]Skill updated:[/green] {folder_path}/SKILL.md")
        console.print("[dim]You can continue refining or select 'Done'.[/dim]")

    # Update context with refined data
    context["extraction"] = extraction
    context["methodology"] = methodology
    return context


def _export_outputs(context: dict) -> None:
    """Copy outputs to a different directory."""
    source_dir = Path(context.get("_output_dir", "."))
    dest_str = typer.prompt("Export to directory")
    dest = Path(dest_str).expanduser()
    dest.mkdir(parents=True, exist_ok=True)

    count = 0
    for item in source_dir.iterdir():
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
        count += 1

    console.print(f"[green]Exported {count} items to:[/green] {dest}")


def _post_run_menu(command: str, context: dict, jd_file: Path | None) -> None:
    """Post-run action menu loop."""
    while True:
        choices = ["Refine the generated agent"]

        # Offer team generation after single forge
        can_team = command == "forge" and jd_file is not None
        if can_team:
            choices.append("Generate a team from this JD")

        choices.extend([
            "Re-run with different options",
            "Export outputs to another directory",
            "Done",
        ])

        idx = _numbered_prompt("What would you like to do next?", choices)
        if idx is None:
            break

        selected = choices[idx]

        if selected == "Refine the generated agent":
            context = _refine_loop(context)

        elif selected == "Generate a team from this JD":
            console.print("\n[blue]Setting up team generation...[/blue]")
            team_opts = _pick_team_options()
            try:
                _run_team(jd_file, team_opts)
            except Exception as e:
                console.print(Panel(f"[red]{e}[/red]", title="Team Failed", border_style="red"))

        elif selected == "Re-run with different options":
            # Signal to the caller to restart the options/run cycle
            context["_rerun"] = True
            return

        elif selected == "Export outputs to another directory":
            _export_outputs(context)

        elif selected == "Done":
            break


# ---------------------------------------------------------------------------
# Main wizard entry point
# ---------------------------------------------------------------------------


def run_wizard() -> None:
    """Main wizard flow: command → file → options → run → post-run menu."""
    console.print(Panel(
        "[bold]Welcome to the AgentForge Wizard[/bold]\n\n"
        "This guided experience will walk you through:\n"
        "  1. Choosing a command (forge, batch, team, identity import)\n"
        "  2. Selecting your input files\n"
        "  3. Configuring options\n"
        "  4. Running the pipeline\n"
        "  5. Post-run actions (refine, team, export)",
        border_style="blue",
    ))

    # Step 1: Pick command
    cmd_idx = _numbered_prompt(
        "What would you like to do?",
        [
            "Forge — create an AI agent blueprint from a job description",
            "Batch — process multiple job descriptions at once",
            "Team — forge a multi-agent team from a single JD",
            "Identity Import — import an existing PersonaNexus identity",
        ],
    )
    commands = ["forge", "batch", "team", "identity_import"]
    command = commands[cmd_idx or 0]

    while True:
        # Step 2: Pick input file(s)
        jd_file: Path | None = None

        if command == "forge":
            jd_file = _pick_file("Job description file", _JD_EXTENSIONS, required=True)
            if not jd_file:
                console.print("[red]A job description file is required.[/red]")
                raise typer.Exit(code=1)
        elif command == "batch":
            jd_dir = _pick_directory("Directory containing JD files", required=True)
            if not jd_dir:
                console.print("[red]A directory is required.[/red]")
                raise typer.Exit(code=1)
        elif command == "team":
            jd_file = _pick_file("Job description file", _JD_EXTENSIONS, required=True)
            if not jd_file:
                console.print("[red]A job description file is required.[/red]")
                raise typer.Exit(code=1)
        elif command == "identity_import":
            jd_file = _pick_file("PersonaNexus identity YAML", _IDENTITY_EXTENSIONS, required=True)
            if not jd_file:
                console.print("[red]An identity file is required.[/red]")
                raise typer.Exit(code=1)

        # Step 3: Pick options
        console.print(Panel("[bold]Configuration[/bold]", border_style="cyan"))

        if command == "forge":
            opts = _pick_forge_options()
        elif command == "batch":
            opts = _pick_batch_options()
        elif command == "team":
            opts = _pick_team_options()
        else:
            opts = _pick_identity_import_options()

        # Confirm
        console.print()
        console.print(Panel(
            f"[bold]Ready to run:[/bold] agentforge {command.replace('_', ' ')}\n"
            f"[dim]Input:[/dim] {jd_file or jd_dir}\n"  # type: ignore[possibly-undefined]
            f"[dim]Options:[/dim] {', '.join(f'{k}={v}' for k, v in opts.items() if v is not None and k != 'model')}",
            border_style="green",
        ))
        if not typer.confirm("Proceed?", default=True):
            if typer.confirm("Change options?", default=True):
                continue
            console.print("[dim]Wizard cancelled.[/dim]")
            return

        # Step 4: Run
        try:
            if command == "forge":
                context = _run_forge(jd_file, opts)
            elif command == "batch":
                context = _run_batch(jd_dir, opts)  # type: ignore[possibly-undefined]
            elif command == "team":
                context = _run_team(jd_file, opts)
            else:
                context = _run_identity_import(jd_file, opts)
        except typer.Exit:
            raise
        except Exception as e:
            console.print(Panel(f"[red]{e}[/red]", title="Pipeline Failed", border_style="red"))
            if typer.confirm("Try again with different options?", default=True):
                continue
            raise typer.Exit(code=1)

        # Step 5: Post-run menu
        _post_run_menu(command, context, jd_file)

        if context.get("_rerun"):
            del context["_rerun"]
            continue
        break

    console.print(Panel(
        "[bold green]Wizard complete![/bold green]\n"
        "[dim]Run 'agentforge wizard' again anytime, or use commands directly.[/dim]",
        border_style="green",
    ))
