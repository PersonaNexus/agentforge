"""AgentForge CLI — forge AI agents from job descriptions."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agentforge.config import DEFAULT_MODEL
from agentforge.models.extracted_skills import ExtractionResult
from agentforge.utils import safe_output_path, safe_rel_path

app = typer.Typer(
    name="agentforge",
    help="Transform job descriptions into deployable AI agent blueprints.",
    no_args_is_help=True,
)
console = Console()


def _ingest_file(path: Path) -> "JobDescription":
    """Ingest a file based on its extension."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from agentforge.ingestion.pdf import ingest_pdf
        return ingest_pdf(path)
    elif suffix == ".docx":
        from agentforge.ingestion.docx import ingest_docx
        return ingest_docx(path)
    else:
        from agentforge.ingestion.text import ingest_file
        return ingest_file(path)


def _make_client(model: str) -> "LLMClient":
    """Create an LLM client, showing a helpful error if API key is missing."""
    try:
        from agentforge.llm.client import LLMClient
        return LLMClient(model=model)
    except ValueError as e:
        console.print(Panel(
            f"[red]{e}[/red]\n\n"
            "[dim]Hint: export ANTHROPIC_API_KEY or OPENAI_API_KEY, or run agentforge init[/dim]",
            title="Configuration Error",
            border_style="red",
        ))
        raise typer.Exit(code=1)


def _display_extraction(result: ExtractionResult) -> None:
    """Display extraction results in a rich table."""
    role = result.role
    role_text = (
        f"[bold]{role.title}[/bold] ({role.seniority})\n"
        f"[dim]Domain:[/dim] {role.domain}\n"
        f"[dim]Purpose:[/dim] {role.purpose}"
    )
    console.print(Panel(role_text, title="Role", border_style="blue"))

    table = Table(title="Extracted Skills", show_lines=True)
    table.add_column("Skill", style="cyan", min_width=20)
    table.add_column("Category", style="green")
    table.add_column("Proficiency", style="yellow")
    table.add_column("Importance", style="magenta")
    table.add_column("Context", style="dim", max_width=40)

    for skill in result.skills:
        table.add_row(
            skill.name,
            skill.category.value,
            skill.proficiency.value,
            skill.importance.value,
            skill.context[:40] + "..." if len(skill.context) > 40 else skill.context,
        )
    console.print(table)

    traits = result.suggested_traits.defined_traits()
    if traits:
        trait_table = Table(title="Suggested Personality Traits", show_lines=True)
        trait_table.add_column("Trait", style="cyan")
        trait_table.add_column("Value", style="yellow")
        trait_table.add_column("Bar", min_width=20)
        for name, value in sorted(traits.items()):
            bar_len = int(value * 20)
            bar = "[green]" + "█" * bar_len + "[/green]" + "░" * (20 - bar_len)
            trait_table.add_row(name, f"{value:.2f}", bar)
        console.print(trait_table)

    pct = int(result.automation_potential * 100)
    console.print(
        Panel(
            f"[bold]{pct}%[/bold] automation potential\n{result.automation_rationale}",
            title="Automation Assessment",
            border_style="red" if pct < 30 else "yellow" if pct < 60 else "green",
        )
    )


@app.command()
def extract(
    jd_file: Path = typer.Argument(..., help="Path to job description file (txt, md, pdf, docx)"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path"),
    format: str = typer.Option("yaml", "--format", "-f", help="Output format: yaml or json"),
    model: str = typer.Option(
        DEFAULT_MODEL, "--model", "-m", help="LLM model to use (supports Claude and OpenAI models)"
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress display output"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Extract skills and role info from a job description.

    Examples:
        agentforge extract resume.pdf
        agentforge extract job.txt --format json --output skills.json
        agentforge extract posting.md --quiet -o result.yaml
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    if not jd_file.exists():
        console.print(f"[red]Error:[/red] File not found: {jd_file}")
        raise typer.Exit(code=1)

    try:
        from agentforge.extraction.skill_extractor import SkillExtractor

        console.print(f"[blue]Ingesting:[/blue] {jd_file}")
        jd = _ingest_file(jd_file)
        console.print(f"[blue]Title:[/blue] {jd.title}")
        console.print(f"[blue]Sections found:[/blue] {len(jd.sections)}")

        console.print("[yellow]Extracting skills via LLM...[/yellow]")
        client = _make_client(model)
        extractor = SkillExtractor(client=client)
        result = extractor.extract(jd)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(Panel(
            f"[red]{e}[/red]",
            title="Extraction Failed",
            border_style="red",
        ))
        raise typer.Exit(code=1)

    if not quiet:
        _display_extraction(result)

    data = json.loads(result.model_dump_json())
    if format == "json":
        serialized = json.dumps(data, indent=2)
    else:
        serialized = yaml.dump(data, default_flow_style=False, sort_keys=False)

    if output:
        output.write_text(serialized)
        console.print(f"[green]Saved to:[/green] {output}")
    else:
        console.print(Panel(serialized, title=f"Extraction ({format})", border_style="green"))

    console.print(f"[green]Extracted {len(result.skills)} skills from '{jd.title}'[/green]")


@app.command()
def forge(
    jd_file: Path = typer.Argument(..., help="Path to job description file (txt, md, pdf, docx)"),
    output_dir: Path = typer.Option(
        Path("."), "--output-dir", "-d", help="Directory for output files"
    ),
    model: str = typer.Option(
        DEFAULT_MODEL, "--model", "-m", help="LLM model to use (supports Claude and OpenAI models)"
    ),
    quick_mode: bool = typer.Option(
        False, "--quick", help="Quick mode: skip culture, mapping, and gap analysis"
    ),
    deep: bool = typer.Option(
        False, "--deep", help="Deep analysis: detailed skill scoring and priority ranking"
    ),
    no_skill_file: bool = typer.Option(
        False, "--no-skill-file",
        help="Skip full agent profile (detailed SKILL.md with analysis & embedded data)",
    ),
    skill_folder: bool = typer.Option(
        False, "--skill-folder",
        help="Output Claude Code-ready skill folder (drop into .claude/skills/)",
    ),
    culture: Path | None = typer.Option(
        None, "--culture", "-c", help="Culture file (YAML or markdown) to infuse"
    ),
    examples: Path | None = typer.Option(
        None, "--examples", "-e",
        help="File containing work samples/examples (txt or md)",
    ),
    frameworks: Path | None = typer.Option(
        None, "--frameworks",
        help="File containing frameworks/methodologies (txt or md)",
    ),
    target: str = typer.Option(
        "", "--target", "-t",
        help="Deployment target: 'openclaw' for OpenClaw-ready output",
    ),
    mode: str = typer.Option(
        "", "--mode",
        help="Agent mode: 'cron' for scheduled/autonomous agents",
    ),
    schedule: str = typer.Option(
        "", "--schedule",
        help="Cron schedule expression (e.g. '0 8 * * *') — used with --mode cron",
    ),
    methodology: bool = typer.Option(
        True, "--methodology/--no-methodology",
        help="Extract decision patterns and trigger-technique mappings (default: on)",
    ),
    supplement: list[Path] | None = typer.Option(
        None, "--supplement", "-s",
        help="Supplementary source files to enrich methodology (repeatable)",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Forge a complete AI agent blueprint from a job description.

    Runs the full pipeline: ingest -> extract -> map -> culture -> generate -> analyze.

    Outputs:
      - PersonaNexus identity YAML (always)
      - Claude Code skill folder (always) — drop into .claude/skills/ to use
      - Full agent profile SKILL.md (unless --no-skill-file) — detailed analysis
      - OpenClaw files (with --target openclaw): SOUL.md, STYLE.md, personality.json

    Examples:
        agentforge forge job_posting.txt
        agentforge forge resume.pdf --culture startup.yaml -d ./agents
        agentforge forge posting.md --quick --no-skill-file
        agentforge forge job.txt --target openclaw -d ./openclaw-agents/
        agentforge forge job.txt --mode cron --schedule "0 8 * * *"
        agentforge forge job.txt --supplement convos.md --supplement runbook.md
        agentforge forge job.txt --no-methodology  # skip decision pattern extraction
    """
    from agentforge.pipeline.forge_pipeline import ForgePipeline

    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    if not jd_file.exists():
        console.print(f"[red]Error:[/red] File not found: {jd_file}")
        raise typer.Exit(code=1)

    if culture and not culture.exists():
        console.print(f"[red]Error:[/red] Culture file not found: {culture}")
        raise typer.Exit(code=1)

    if quick_mode and deep:
        console.print("[red]Error:[/red] --quick and --deep cannot be used together.")
        raise typer.Exit(code=1)

    if examples and not examples.exists():
        console.print(f"[red]Error:[/red] Examples file not found: {examples}")
        raise typer.Exit(code=1)

    if frameworks and not frameworks.exists():
        console.print(f"[red]Error:[/red] Frameworks file not found: {frameworks}")
        raise typer.Exit(code=1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Score supplements if provided (E6)
    if supplement:
        from agentforge.analysis.supplement_scorer import SupplementScorer
        scorer = SupplementScorer()
        source_pairs = []
        for s in supplement:
            if not s.exists():
                console.print(f"[red]Error:[/red] Supplement file not found: {s}")
                raise typer.Exit(code=1)
            source_pairs.append((s.name, s.read_text()))
        if source_pairs:
            report = scorer.score_sources(source_pairs)
            for score in report.scores:
                quality = score.assessment
                color = "green" if quality == "high" else "yellow" if quality == "medium" else "red"
                hint = "" if quality != "low" else " — consider filtering"
                console.print(
                    f"[blue]Supplement quality:[/blue] {score.source}    "
                    f"[{color}]{score.pct}% signal ({quality}{hint})[/{color}]"
                )
            if report.has_low_quality:
                if not typer.confirm("Proceed with low-quality source(s)?", default=True):
                    console.print("[yellow]Aborted.[/yellow]")
                    raise typer.Exit(code=0)

    # Build pipeline
    if target == "openclaw":
        pipeline = ForgePipeline.openclaw()
    elif mode == "cron":
        pipeline = ForgePipeline.cron()
    elif quick_mode:
        pipeline = ForgePipeline.quick()
    elif deep:
        pipeline = ForgePipeline.deep_analysis()
    else:
        pipeline = ForgePipeline.default()

    # Skip methodology if explicitly disabled (E1)
    if not methodology:
        pipeline.skip_stage("methodology")

    # Set up context
    client = _make_client(model)
    context: dict = {
        "input_path": str(jd_file),
        "llm_client": client,
    }
    if culture:
        context["culture_path"] = str(culture)
        console.print(f"[blue]Culture:[/blue] {culture}")
    if examples:
        context["user_examples"] = examples.read_text()
        console.print(f"[blue]Examples:[/blue] {examples}")
    if frameworks:
        context["user_frameworks"] = frameworks.read_text()
        console.print(f"[blue]Frameworks:[/blue] {frameworks}")
    if mode == "cron":
        context["cron_schedule"] = schedule or "0 8 * * *"
        console.print(f"[blue]Mode:[/blue] cron (schedule: {context['cron_schedule']})")
    if target == "openclaw":
        console.print(f"[blue]Target:[/blue] OpenClaw")
    if supplement:
        context["supplementary_sources"] = [str(s) for s in supplement]

    # Warn if using a non-Claude model — skill folder output is Claude Code-specific
    if not model.startswith("claude"):
        console.print(
            "[yellow]Note:[/yellow] Skill folder output uses Claude Code format "
            "(.claude/skills/). It may not be directly usable with non-Claude models."
        )

    console.print(f"[blue]Forging agent from:[/blue] {jd_file}")

    try:
        context = pipeline.run(context)
    except Exception as e:
        console.print(Panel(
            f"[red]{e}[/red]",
            title="Pipeline Failed",
            border_style="red",
        ))
        # Show partial results if available
        if "extraction" in context:
            console.print("[yellow]Partial results (extraction completed):[/yellow]")
            _display_extraction(context["extraction"])
        raise typer.Exit(code=1)

    extraction = context["extraction"]
    identity_yaml = context["identity_yaml"]

    _display_extraction(extraction)

    # Show mapped traits
    if "traits" in context:
        trait_table = Table(title="Mapped PersonaNexus Traits", show_lines=True)
        trait_table.add_column("Trait", style="cyan")
        trait_table.add_column("Value", style="yellow")
        trait_table.add_column("Bar", min_width=20)
        for name, value in sorted(context["traits"].items()):
            bar_len = int(value * 20)
            bar = "[green]" + "█" * bar_len + "[/green]" + "░" * (20 - bar_len)
            trait_table.add_row(name, f"{value:.2f}", bar)
        console.print(trait_table)

    # Coverage results
    if "coverage_score" in context:
        score = context["coverage_score"]
        gaps = context.get("coverage_gaps", [])
        color = "green" if score > 0.7 else "yellow" if score > 0.5 else "red"
        gap_text = "\n".join(f"  - {g}" for g in gaps[:5])
        if len(gaps) > 5:
            gap_text += f"\n  ... and {len(gaps) - 5} more"
        console.print(Panel(
            f"[bold]{int(score * 100)}%[/bold] coverage\n{gap_text}",
            title="Gap Analysis",
            border_style=color,
        ))

    # Deep analysis detail table
    if "skill_scores" in context:
        detail_table = Table(title="Skill-by-Skill Coverage", show_lines=True)
        detail_table.add_column("Skill", style="cyan")
        detail_table.add_column("Score", justify="right", style="yellow")
        detail_table.add_column("Priority", style="magenta")
        for entry in context["skill_scores"]:
            detail_table.add_row(
                entry["skill"],
                f"{int(entry['score'] * 100)}%",
                entry["priority"],
            )
        console.print(detail_table)

    # Agent team composition
    agent_team = context.get("agent_team")
    if agent_team and agent_team.teammates:
        team_table = Table(
            title="Your Agent Team",
            show_lines=True,
            title_style="bold cyan",
        )
        team_table.add_column("Agent", style="cyan", min_width=18)
        team_table.add_column("Archetype", style="green")
        team_table.add_column("Skills", style="dim", max_width=35)
        team_table.add_column("Benefit", style="white", max_width=50)

        for teammate in agent_team.teammates:
            skills_str = ", ".join(teammate.skill_names()[:4])
            if len(teammate.skill_names()) > 4:
                skills_str += f" +{len(teammate.skill_names()) - 4}"
            team_table.add_row(
                teammate.name,
                teammate.archetype,
                skills_str,
                teammate.benefit,
            )
        console.print(team_table)
        console.print(Panel(
            agent_team.team_benefit,
            border_style="cyan",
        ))

    # Save identity YAML with safe filename
    agent_id = context["identity"].metadata.id
    yaml_path = safe_output_path(output_dir, f"{agent_id}.yaml")
    yaml_path.write_text(identity_yaml)
    console.print(f"[green]Identity saved:[/green] {yaml_path}")

    # Save full agent profile SKILL.md (detailed analysis + embedded data)
    if not no_skill_file and "skill_file" in context:
        skill_path = safe_output_path(output_dir, f"{agent_id}_SKILL.md")
        skill_path.write_text(context["skill_file"])
        console.print(f"[green]Full agent profile saved:[/green] {skill_path}")

    # Save Claude Code skill folder (drop into .claude/skills/ to use)
    if skill_folder and "skill_folder" in context:
        sf = context["skill_folder"]
        folder_path = safe_output_path(output_dir, sf.skill_name)
        folder_path.mkdir(exist_ok=True)
        (folder_path / "SKILL.md").write_text(sf.skill_md_with_references())

        # Write supplementary reference files
        for rel_path, content in sf.supplementary_files.items():
            ref_path = safe_rel_path(folder_path, rel_path)
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(content)

        ref_count = len(sf.supplementary_files)
        ref_msg = f" + {ref_count} reference file{'s' if ref_count != 1 else ''}" if ref_count else ""
        console.print(
            f"[green]Claude Code skill saved:[/green] {folder_path}/\n"
            f"  [dim]SKILL.md{ref_msg} — copy to .claude/skills/ or ~/.claude/skills/ to use[/dim]"
        )

    # Save OpenClaw files (E3)
    if "openclaw_output" in context:
        oc = context["openclaw_output"]
        for rel_path, content in oc.file_map().items():
            out_path = safe_rel_path(output_dir, rel_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content)
        console.print(
            f"[green]OpenClaw files saved:[/green] {output_dir}/\n"
            f"  [dim]{oc.agent_name}.SOUL.md, {oc.agent_name}.STYLE.md, "
            f"{oc.agent_name}.personality.json, {oc.agent_name}-skills/[/dim]\n"
            f"  [dim]Ready to drop into OpenClaw workspace[/dim]"
        )

    # Build blueprint
    blueprint = pipeline.to_blueprint(context)
    console.print(
        f"\n[bold green]Agent '{extraction.role.title}' forged successfully![/bold green]"
    )
    console.print(
        f"  Skills: {len(extraction.skills)} | "
        f"Coverage: {int(blueprint.coverage_score * 100)}% | "
        f"Automation: {int(blueprint.automation_estimate * 100)}%"
    )


# --- Identity subcommands ---

identity_app = typer.Typer(help="PersonaNexus identity management.")
app.add_typer(identity_app, name="identity")


@identity_app.command("import")
def identity_import(
    identity_file: Path = typer.Argument(..., help="Path to PersonaNexus identity YAML"),
    output_dir: Path = typer.Option(
        Path("."), "--output-dir", "-d", help="Directory for output files"
    ),
    output_format: str = typer.Option(
        "claude_code", "--format", "-f", help="Output format: claude_code, clawhub, or both"
    ),
    model: str = typer.Option(
        "claude-sonnet-4-20250514", "--model", "-m", help="Claude model to use for refinement"
    ),
    examples: Path | None = typer.Option(
        None, "--examples", "-e",
        help="File containing work samples/examples (txt or md)",
    ),
    frameworks: Path | None = typer.Option(
        None, "--frameworks",
        help="File containing frameworks/methodologies (txt or md)",
    ),
    refine: bool = typer.Option(
        False, "--refine", help="Run LLM-based refinement after import"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Import an existing PersonaNexus identity YAML and generate skill files.

    Round-trips the identity through AgentForge: loads the YAML, reverse-maps
    to AgentForge models, regenerates enriched skill files and identity YAML.

    Examples:
        agentforge identity import agent_identity.yaml
        agentforge identity import my-agent.yaml -d ./output --format both
        agentforge identity import agent.yaml --refine  # LLM-enhanced round-trip
        agentforge identity import agent.yaml --examples samples.md
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    if not identity_file.exists():
        console.print(f"[red]Error:[/red] File not found: {identity_file}")
        raise typer.Exit(code=1)

    suffix = identity_file.suffix.lower()
    if suffix not in (".yaml", ".yml"):
        console.print(f"[red]Error:[/red] Expected a YAML file, got: {suffix}")
        raise typer.Exit(code=1)

    if output_format not in ("claude_code", "clawhub", "both"):
        console.print(f"[red]Error:[/red] Invalid format: {output_format}")
        raise typer.Exit(code=1)

    output_dir.mkdir(parents=True, exist_ok=True)

    from agentforge.generation.identity_loader import IdentityLoader
    from agentforge.generation.identity_generator import IdentityGenerator

    console.print(f"[blue]Loading identity:[/blue] {identity_file}")
    loader = IdentityLoader()
    try:
        extraction, methodology, original_yaml = loader.load_file(str(identity_file))
    except ValueError as e:
        console.print(Panel(f"[red]{e}[/red]", title="Invalid Identity", border_style="red"))
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Load Failed", border_style="red"))
        raise typer.Exit(code=1)

    console.print(f"[green]Loaded:[/green] {extraction.role.title}")
    console.print(f"  Skills: {len(extraction.skills)} | Responsibilities: {len(extraction.responsibilities)}")
    if methodology:
        console.print(
            f"  Heuristics: {len(methodology.heuristics)} | "
            f"Quality criteria: {len(methodology.quality_criteria)}"
        )

    # Read user-provided examples/frameworks
    user_examples = ""
    user_frameworks = ""
    if examples:
        if not examples.exists():
            console.print(f"[red]Error:[/red] Examples file not found: {examples}")
            raise typer.Exit(code=1)
        user_examples = examples.read_text()
        console.print(f"[blue]Examples:[/blue] {examples}")
    if frameworks:
        if not frameworks.exists():
            console.print(f"[red]Error:[/red] Frameworks file not found: {frameworks}")
            raise typer.Exit(code=1)
        user_frameworks = frameworks.read_text()
        console.print(f"[blue]Frameworks:[/blue] {frameworks}")

    _display_extraction(extraction)

    # Regenerate identity (round-trip)
    generator = IdentityGenerator()
    identity, identity_yaml = generator.generate(extraction)

    agent_id = identity.metadata.id
    yaml_path = safe_output_path(output_dir, f"{agent_id}.yaml")
    yaml_path.write_text(identity_yaml)
    console.print(f"[green]Identity saved:[/green] {yaml_path}")

    # Generate skill files
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
            ref_path = folder_path / rel_path
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(content)

        ref_count = len(sf.supplementary_files)
        ref_msg = f" + {ref_count} reference file{'s' if ref_count != 1 else ''}" if ref_count else ""
        console.print(
            f"[green]Claude Code skill saved:[/green] {folder_path}/\n"
            f"  [dim]SKILL.md{ref_msg}[/dim]"
        )

    if output_format in ("clawhub", "both"):
        from agentforge.generation.clawhub_skill import ClawHubSkillGenerator

        ch_gen = ClawHubSkillGenerator()
        ch = ch_gen.generate(extraction, jd=None, methodology=methodology)
        ch_path = safe_output_path(output_dir, f"{ch.skill_name}_clawhub_SKILL.md")
        ch_path.write_text(ch.skill_md)
        console.print(f"[green]ClawHub skill saved:[/green] {ch_path}")

    # Run gap analysis
    from agentforge.analysis.skill_reviewer import SkillReviewer

    reviewer = SkillReviewer()
    gaps = reviewer.review(extraction, methodology=methodology)
    if gaps:
        console.print(f"\n[yellow]{len(gaps)} improvement suggestions:[/yellow]")
        for gap in gaps:
            console.print(f"  [{gap.priority}] {gap.title}: {gap.description}")
    else:
        console.print("\n[green]No gaps detected — identity is comprehensive.[/green]")

    console.print(
        f"\n[bold green]Identity '{extraction.role.title}' imported successfully![/bold green]"
    )


# --- Culture subcommands ---

culture_app = typer.Typer(help="Culture profile management.")
app.add_typer(culture_app, name="culture")


@culture_app.command("parse")
def culture_parse(
    culture_file: Path = typer.Argument(..., help="Culture file (YAML or markdown)"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output YAML file"),
    model: str = typer.Option(
        DEFAULT_MODEL, "--model", "-m", help="LLM model for markdown parsing"
    ),
) -> None:
    """Parse a culture document into a structured CultureProfile.

    Examples:
        agentforge culture parse company_culture.yaml
        agentforge culture parse values.md --output profile.yaml
    """
    from agentforge.mapping.culture_mapper import CultureParser

    if not culture_file.exists():
        console.print(f"[red]Error:[/red] File not found: {culture_file}")
        raise typer.Exit(code=1)

    client = _make_client(model)
    parser = CultureParser(llm_client=client)
    profile = parser.parse_file(culture_file)

    console.print(Panel(
        f"[bold]{profile.name}[/bold]\n{profile.description}\n"
        f"[dim]Values:[/dim] {len(profile.values)} | "
        f"[dim]Tone:[/dim] {profile.communication_tone or 'N/A'}",
        title="Culture Profile",
        border_style="magenta",
    ))

    for value in profile.values:
        deltas = ", ".join(f"{k}: {v:+.2f}" for k, v in value.trait_deltas.items())
        console.print(f"  [cyan]{value.name}[/cyan]: {value.description}")
        if deltas:
            console.print(f"    [dim]Trait deltas: {deltas}[/dim]")

    data = json.loads(profile.model_dump_json())
    serialized = yaml.dump(data, default_flow_style=False, sort_keys=False)

    if output:
        output.write_text(serialized)
        console.print(f"\n[green]Saved to:[/green] {output}")
    else:
        console.print(Panel(serialized, title="CultureProfile (YAML)", border_style="green"))


@culture_app.command("to-mixin")
def culture_to_mixin(
    culture_file: Path = typer.Argument(..., help="CultureProfile YAML file"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output mixin YAML file"),
) -> None:
    """Convert a CultureProfile YAML into a PersonaNexus mixin.

    Examples:
        agentforge culture to-mixin profile.yaml
        agentforge culture to-mixin profile.yaml -o mixin.yaml
    """
    from agentforge.mapping.culture_mapper import CultureMixinConverter, CultureParser

    if not culture_file.exists():
        console.print(f"[red]Error:[/red] File not found: {culture_file}")
        raise typer.Exit(code=1)

    parser = CultureParser()
    profile = parser.parse_yaml(culture_file)

    converter = CultureMixinConverter()
    mixin_yaml = converter.convert(profile)

    if output:
        output.write_text(mixin_yaml)
        console.print(f"[green]Mixin saved to:[/green] {output}")
    else:
        console.print(Panel(mixin_yaml, title="PersonaNexus Mixin", border_style="green"))


@culture_app.command("list")
def culture_list() -> None:
    """List built-in culture templates.

    Examples:
        agentforge culture list
    """
    templates_dir = Path(__file__).parent / "templates" / "cultures"
    if not templates_dir.exists():
        console.print("[yellow]No culture templates found.[/yellow]")
        return

    table = Table(title="Built-in Culture Templates", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="dim")
    table.add_column("Values", justify="right")

    for f in sorted(templates_dir.glob("*.yaml")):
        data = yaml.safe_load(f.read_text())
        table.add_row(
            f.stem,
            data.get("description", "")[:60],
            str(len(data.get("values", []))),
        )
    console.print(table)


# --- Batch command ---

@app.command()
def batch(
    jd_directory: Path = typer.Argument(..., help="Directory containing JD files"),
    output_dir: Path = typer.Option(
        Path("./batch_output"), "--output-dir", "-d", help="Output directory"
    ),
    culture: Path | None = typer.Option(
        None, "--culture", "-c", help="Culture file to apply to all agents"
    ),
    examples: Path | None = typer.Option(
        None, "--examples", "-e",
        help="File containing work samples/examples to apply to all agents",
    ),
    frameworks: Path | None = typer.Option(
        None, "--frameworks",
        help="File containing frameworks/methodologies to apply to all agents",
    ),
    parallel: int = typer.Option(1, "--parallel", "-p", help="Number of parallel workers"),
    model: str = typer.Option(
        DEFAULT_MODEL, "--model", "-m", help="LLM model to use (supports Claude and OpenAI models)"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Process multiple job descriptions in batch.

    Examples:
        agentforge batch ./job_descriptions/ -d ./agents
        agentforge batch ./jds/ --culture startup.yaml --parallel 4
        agentforge batch ./jds/ --examples samples.md --frameworks methods.md
    """
    from agentforge.pipeline.batch import BatchProcessor
    from agentforge.pipeline.forge_pipeline import ForgePipeline

    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    if not jd_directory.exists() or not jd_directory.is_dir():
        console.print(f"[red]Error:[/red] Directory not found: {jd_directory}")
        raise typer.Exit(code=1)

    # Collect JD files
    extensions = {".txt", ".md", ".pdf", ".markdown", ".docx"}
    jd_files = sorted(
        str(f) for f in jd_directory.iterdir()
        if f.suffix.lower() in extensions and f.is_file()
    )

    if not jd_files:
        console.print(f"[yellow]No JD files found in {jd_directory}[/yellow]")
        raise typer.Exit(code=1)

    console.print(f"[blue]Found {len(jd_files)} JD files in {jd_directory}[/blue]")

    client = _make_client(model)
    shared_context: dict = {"llm_client": client}

    if culture:
        if not culture.exists():
            console.print(f"[red]Error:[/red] Culture file not found: {culture}")
            raise typer.Exit(code=1)
        shared_context["culture_path"] = str(culture)
        console.print(f"[blue]Culture:[/blue] {culture}")
    if examples:
        if not examples.exists():
            console.print(f"[red]Error:[/red] Examples file not found: {examples}")
            raise typer.Exit(code=1)
        shared_context["user_examples"] = examples.read_text()
        console.print(f"[blue]Examples:[/blue] {examples}")
    if frameworks:
        if not frameworks.exists():
            console.print(f"[red]Error:[/red] Frameworks file not found: {frameworks}")
            raise typer.Exit(code=1)
        shared_context["user_frameworks"] = frameworks.read_text()
        console.print(f"[blue]Frameworks:[/blue] {frameworks}")

    pipeline = ForgePipeline.default()
    processor = BatchProcessor(
        pipeline=pipeline,
        parallel=parallel,
        output_dir=output_dir,
    )

    results = processor.process(jd_files, shared_context=shared_context)
    processor.display_summary(results)


# --- Team command ---

@app.command()
def team(
    jd_file: Path = typer.Argument(..., help="Path to job description file"),
    output_dir: Path = typer.Option(
        Path("./team_output"), "--output-dir", "-d", help="Directory for output files"
    ),
    model: str = typer.Option(
        "claude-sonnet-4-20250514", "--model", "-m", help="Claude model to use"
    ),
    culture: Path | None = typer.Option(
        None, "--culture", "-c", help="Culture file to apply to all agents"
    ),
    validate: bool = typer.Option(
        False, "--validate",
        help="Validate team for trait overlaps, routing gaps, and guardrail coverage",
    ),
    examples: Path | None = typer.Option(
        None, "--examples", "-e",
        help="File containing work samples/examples to apply to all agents",
    ),
    frameworks: Path | None = typer.Option(
        None, "--frameworks",
        help="File containing frameworks/methodologies to apply to all agents",
    ),
    fmt: str = typer.Option(
        "claude", "--format", "-f",
        help="Output format: claude (default), langgraph, or both",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Forge a complete multi-agent team from a single job description.

    Creates specialized agent skills plus a conductor that orchestrates them.

    Examples:
        agentforge team job.txt -d ./agents
        agentforge team posting.pdf --culture startup.yaml
        agentforge team job.txt --format langgraph
        agentforge team job.txt --examples samples.md --frameworks methods.md
    """
    from agentforge.pipeline.forge_pipeline import ForgePipeline

    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    if fmt not in ("claude", "langgraph", "both"):
        console.print(f"[red]Error:[/red] Invalid format: {fmt}. Choose: claude, langgraph, both")
        raise typer.Exit(code=1)

    if not jd_file.exists():
        console.print(f"[red]Error:[/red] File not found: {jd_file}")
        raise typer.Exit(code=1)

    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline = ForgePipeline.team()
    client = _make_client(model)
    context: dict = {
        "input_path": str(jd_file),
        "llm_client": client,
    }
    if culture:
        context["culture_path"] = str(culture)
    if examples:
        if not examples.exists():
            console.print(f"[red]Error:[/red] Examples file not found: {examples}")
            raise typer.Exit(code=1)
        context["user_examples"] = examples.read_text()
        console.print(f"[blue]Examples:[/blue] {examples}")
    if frameworks:
        if not frameworks.exists():
            console.print(f"[red]Error:[/red] Frameworks file not found: {frameworks}")
            raise typer.Exit(code=1)
        context["user_frameworks"] = frameworks.read_text()
        console.print(f"[blue]Frameworks:[/blue] {frameworks}")

    console.print(f"[blue]Forging team from:[/blue] {jd_file}")

    try:
        context = pipeline.run(context)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Pipeline Failed", border_style="red"))
        raise typer.Exit(code=1)

    forged_team_result = context.get("forged_team_result")
    if not forged_team_result:
        console.print("[yellow]No team was composed — the role may be too narrow.[/yellow]")
        raise typer.Exit(code=1)

    # Save conductor
    conductor = forged_team_result.conductor
    conductor_dir = output_dir / conductor.skill_name
    conductor_dir.mkdir(exist_ok=True)
    (conductor_dir / "SKILL.md").write_text(conductor.skill_md)
    console.print(f"[green]Conductor saved:[/green] {conductor_dir}/SKILL.md")

    # Save each teammate
    for ft in forged_team_result.teammates:
        tm_dir = output_dir / ft.skill_folder.skill_name
        tm_dir.mkdir(exist_ok=True)
        (tm_dir / "SKILL.md").write_text(ft.skill_folder.skill_md)
        for rel_path, content in ft.skill_folder.supplementary_files.items():
            ref_path = tm_dir / rel_path
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(content)
        console.print(f"[green]Agent saved:[/green] {tm_dir}/SKILL.md ({ft.teammate.archetype})")

    # Team validation (E5)
    if validate:
        from agentforge.analysis.team_validator import TeamValidator
        validator = TeamValidator()
        validation = validator.validate(forged_team_result)

        for issue in validation.issues:
            color = {"error": "red", "warning": "yellow", "info": "green"}.get(issue.severity, "white")
            console.print(f"  [{color}]{issue}[/{color}]")

        if not validation.passed:
            console.print(Panel(
                f"[red]Team validation failed: {validation.summary()}[/red]",
                title="Validation Failed",
                border_style="red",
            ))
        else:
            console.print(Panel(
                f"[green]{validation.summary()}[/green]",
                title="Validation Passed",
                border_style="green",
            ))

    # Save orchestration config
    from agentforge.composition.orchestration_config import OrchestrationConfigExporter
    exporter = OrchestrationConfigExporter()
    orch_yaml = exporter.export_orchestration_yaml(forged_team_result)
    (output_dir / "orchestration.yaml").write_text(orch_yaml)
    console.print(f"[green]Orchestration config:[/green] {output_dir}/orchestration.yaml")

    # LangGraph export
    if fmt in ("langgraph", "both"):
        langgraph_py = exporter.export_langgraph(forged_team_result)
        graph_path = output_dir / "agent_graph.py"
        graph_path.write_text(langgraph_py)
        console.print(f"[green]LangGraph module:[/green] {graph_path}")
        console.print(
            '  [dim]Install deps: pip install "agentforge[langgraph]"[/dim]\n'
            f"  [dim]Run: python {graph_path} \"your task here\"[/dim]"
        )

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
        f"\n[bold green]Team of {len(forged_team_result.teammates)} agents + conductor forged![/bold green]\n"
        f"  [dim]Copy {output_dir}/*/ to .claude/skills/ to use[/dim]"
    )


# --- Test command ---

@app.command()
def test(
    jd_file: Path = typer.Argument(..., help="Path to job description file"),
    model: str = typer.Option(
        "claude-sonnet-4-20250514", "--model", "-m", help="Claude model to use"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Forge an agent and run test scenarios against the generated skill.

    Generates test cases from the extraction, runs them against the skill,
    and scores the output using LLM-as-judge.

    Examples:
        agentforge test job.txt
        agentforge test posting.pdf --model claude-haiku-4-5-20251001
    """
    from agentforge.pipeline.forge_pipeline import ForgePipeline
    from agentforge.pipeline.stages import TestStage

    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    if not jd_file.exists():
        console.print(f"[red]Error:[/red] File not found: {jd_file}")
        raise typer.Exit(code=1)

    # Build pipeline with test stage
    pipeline = ForgePipeline.default()
    pipeline.add_stage(TestStage())

    client = _make_client(model)
    context: dict = {
        "input_path": str(jd_file),
        "llm_client": client,
    }

    console.print(f"[blue]Forging and testing:[/blue] {jd_file}")

    try:
        context = pipeline.run(context)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Pipeline Failed", border_style="red"))
        raise typer.Exit(code=1)

    report = context.get("test_report")
    if not report:
        console.print("[yellow]No test report generated — skill may not have been created.[/yellow]")
        raise typer.Exit(code=1)

    # Display test results
    console.print(Panel(
        f"[bold]{report.summary()}[/bold]\n"
        f"Overall score: {report.overall_score:.0%}",
        title="Test Report",
        border_style="green" if report.overall_score >= 0.7 else "yellow" if report.overall_score >= 0.5 else "red",
    ))

    results_table = Table(title="Scenario Results", show_lines=True)
    results_table.add_column("Scenario", style="cyan", max_width=30)
    results_table.add_column("Score", justify="right", style="yellow")
    results_table.add_column("Status", style="green")

    for scored in report.scored_executions:
        status = "[green]PASS[/green]" if scored.overall_score >= 0.7 else "[red]FAIL[/red]"
        results_table.add_row(
            scored.execution.scenario.name,
            f"{scored.overall_score:.0%}",
            status,
        )
    console.print(results_table)

    if report.recommendations:
        console.print("\n[yellow]Recommendations:[/yellow]")
        for rec in report.recommendations:
            console.print(f"  - {rec}")


# --- Init command ---

@app.command()
def init() -> None:
    """Interactive setup wizard for AgentForge configuration.

    Creates ~/.agentforge/config.yaml with your API key, default model,
    output directory, and batch processing preferences.

    Examples:
        agentforge init
    """
    from agentforge.config import AgentForgeConfig, load_config, save_config

    console.print(Panel(
        "[bold]Welcome to AgentForge Setup[/bold]\n"
        "This wizard will configure your AgentForge installation.",
        border_style="blue",
    ))

    # Load existing config as defaults
    try:
        existing = load_config()
    except Exception:
        existing = AgentForgeConfig()

    # API key (supports both Anthropic and OpenAI)
    import os
    env_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    default_key = existing.api_key or env_key
    key_hint = f" (current: ...{default_key[-8:]})" if default_key else ""

    api_key = typer.prompt(
        f"API key (Anthropic sk-ant-... or OpenAI sk-...){key_hint}",
        default=default_key or "",
        hide_input=True,
    )

    # Detect provider from key
    from agentforge.llm.client import _detect_provider
    detected_provider = _detect_provider(api_key) if api_key else "anthropic"
    provider_display = detected_provider.capitalize()
    console.print(f"[dim]Detected provider: {provider_display}[/dim]")

    # Default model (suggest appropriate model for detected provider)
    from agentforge.llm.client import _DEFAULT_MODELS
    suggested_model = _DEFAULT_MODELS.get(detected_provider, existing.default_model)
    default_model = typer.prompt(
        "Default model",
        default=suggested_model if existing.default_model.startswith("claude") and detected_provider == "openai" else existing.default_model,
    )

    # Output directory
    output_dir = typer.prompt(
        "Default output directory",
        default=existing.output_dir,
    )

    # Batch parallel workers
    batch_parallel = typer.prompt(
        "Default batch parallel workers",
        default=str(existing.batch_parallel),
        type=int,
    )

    # Default culture
    templates_dir = Path(__file__).parent / "templates" / "cultures"
    available_cultures = [f.stem for f in templates_dir.glob("*.yaml")] if templates_dir.exists() else []
    culture_hint = f" (available: {', '.join(available_cultures)})" if available_cultures else ""
    default_culture = typer.prompt(
        f"Default culture template{culture_hint}",
        default=existing.default_culture or "",
    )

    config = AgentForgeConfig(
        api_key=api_key,
        provider=detected_provider,
        default_model=default_model,
        output_dir=output_dir,
        default_culture=default_culture or None,
        batch_parallel=batch_parallel,
    )

    save_config(config)

    # Validate API key
    if api_key:
        console.print(f"[yellow]Validating {provider_display} API key...[/yellow]")
        try:
            if detected_provider == "openai":
                import openai
                client = openai.OpenAI(api_key=api_key)
                client.chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Hi"}],
                )
            else:
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Hi"}],
                )
            console.print("[green]API key is valid.[/green]")
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Could not validate API key: {e}")
            console.print("[dim]The key has been saved but may not work.[/dim]")

    console.print(Panel(
        f"[green]Configuration saved to ~/.agentforge/config.yaml[/green]\n"
        f"  Provider: {provider_display}\n"
        f"  Model: {default_model}\n"
        f"  Output: {output_dir}\n"
        f"  Parallel: {batch_parallel}\n"
        f"  Culture: {default_culture or 'none'}",
        title="Setup Complete",
        border_style="green",
    ))


@app.command()
def refine(
    skill_dir: Path = typer.Argument(..., help="Path to forged skill directory (containing SKILL.md)"),
    feedback: str = typer.Option(
        ..., "--feedback", "-f", help="Feedback on what to improve"
    ),
    output_dir: Path = typer.Option(
        Path("."), "--output-dir", "-d", help="Directory for refined output"
    ),
    model: str = typer.Option(
        "claude-sonnet-4-20250514", "--model", "-m", help="Claude model to use"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Refine a forged skill based on usage feedback.

    Takes a forged skill directory and feedback, produces an improved v2 with diff.

    Examples:
        agentforge refine agents/atlas/ --feedback "too verbose in briefings"
        agentforge refine ./my-skill/ -f "misses market signals" -d ./output
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    if not skill_dir.exists():
        console.print(f"[red]Error:[/red] Directory not found: {skill_dir}")
        raise typer.Exit(code=1)

    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.exists():
        console.print(f"[red]Error:[/red] SKILL.md not found in {skill_dir}")
        raise typer.Exit(code=1)

    from agentforge.refinement.refiner import SkillRefiner

    console.print(f"[blue]Refining:[/blue] {skill_dir}")
    console.print(f"[blue]Feedback:[/blue] {feedback}")

    client = _make_client(model)
    refiner = SkillRefiner(client=client)

    try:
        result = refiner.refine_from_path(skill_dir, feedback)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Refinement Failed", border_style="red"))
        raise typer.Exit(code=1)

    # Show diff
    if result.diff_text:
        console.print(Panel(result.diff_text, title="Changes", border_style="yellow"))
    else:
        console.print("[yellow]No differences detected — skill may already address this feedback.[/yellow]")

    # Save refined output
    output_dir.mkdir(parents=True, exist_ok=True)
    skill_name = skill_dir.name
    out_path = refiner.save_refined(result, output_dir, skill_name)
    console.print(f"[green]Refined skill saved:[/green] {out_path}/SKILL.md")
    console.print(
        f"\n[bold green]Skill refined successfully![/bold green]\n"
        f"  [dim]Original: {skill_dir}[/dim]\n"
        f"  [dim]Refined:  {out_path}[/dim]"
    )


@app.command(name="diff")
def drift_diff(
    spec_dir: Path = typer.Argument(..., help="Path to original forged spec directory"),
    current: Path = typer.Option(
        ..., "--current", "-c", help="Path to current running agent directory"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Detect drift between a forged spec and running agent files.

    Compares the original forged agent against its current runtime state.
    Surfaces trait drift, guardrail changes, and file mismatches.

    Examples:
        agentforge diff agents/atlas/ --current ~/.openclaw/agents/atlas/
        agentforge diff ./spec/ -c ./runtime/
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    if not spec_dir.exists():
        console.print(f"[red]Error:[/red] Spec directory not found: {spec_dir}")
        raise typer.Exit(code=1)

    if not current.exists():
        console.print(f"[red]Error:[/red] Current directory not found: {current}")
        raise typer.Exit(code=1)

    from agentforge.analysis.drift_detector import DriftDetector

    console.print(f"[blue]Spec:[/blue] {spec_dir}")
    console.print(f"[blue]Current:[/blue] {current}")

    detector = DriftDetector()
    report = detector.detect(spec_dir, current)

    if not report.findings:
        console.print("[green]No drift detected — spec and runtime are in sync.[/green]")
        return

    # Display findings
    for finding in report.findings:
        color = {"significant": "red", "minor": "yellow", "info": "green"}.get(
            finding.severity, "white"
        )
        console.print(f"  [{color}]{finding}[/{color}]")

    console.print(Panel(
        report.recommendation,
        title=report.summary(),
        border_style="yellow" if report.has_significant_drift else "green",
    ))


@app.command()
def interview(
    output: Path = typer.Option(
        Path("interview_output.txt"), "--output", "-o",
        help="Output file for generated role description",
    ),
    forge_after: bool = typer.Option(
        False, "--forge",
        help="Immediately forge an agent from the interview output",
    ),
    model: str = typer.Option(
        "claude-sonnet-4-20250514", "--model", "-m", help="Claude model for forging"
    ),
    output_dir: Path = typer.Option(
        Path("."), "--output-dir", "-d", help="Output directory for forge results"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Interactive interview to build a role description before forging.

    Asks structured questions about purpose, tasks, boundaries, and output
    preferences, then generates a role description. Optionally forges immediately.

    Examples:
        agentforge interview
        agentforge interview --forge -d ./agents
        agentforge interview -o my_agent.txt
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    from agentforge.interview.interviewer import AgentInterviewer

    interviewer = AgentInterviewer()
    result = interviewer.interview()

    role_desc = result.to_role_description()
    output.write_text(role_desc)
    console.print(f"[green]Role description saved:[/green] {output}")

    if forge_after:
        console.print("[blue]Forging agent from interview...[/blue]")
        from agentforge.pipeline.forge_pipeline import ForgePipeline

        pipeline = ForgePipeline.default()
        client = _make_client(model)
        context: dict = {
            "input_path": str(output),
            "llm_client": client,
        }

        try:
            context = pipeline.run(context)
        except Exception as e:
            console.print(Panel(f"[red]{e}[/red]", title="Forge Failed", border_style="red"))
            raise typer.Exit(code=1)

        extraction = context["extraction"]
        identity_yaml = context["identity_yaml"]
        agent_id = context["identity"].metadata.id

        output_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = safe_output_path(output_dir, f"{agent_id}.yaml")
        yaml_path.write_text(identity_yaml)
        console.print(f"[green]Identity saved:[/green] {yaml_path}")
        console.print(
            f"\n[bold green]Agent '{extraction.role.title}' forged from interview![/bold green]"
        )


@app.command()
def wizard() -> None:
    """Interactive wizard — guided experience for forging agents.

    Walks you through command selection, file picking, option configuration,
    pipeline execution, and post-run actions (refine, team, export).

    Examples:
        agentforge wizard
    """
    from agentforge.cli_wizard import run_wizard

    run_wizard()


@app.command(name="prompt-size")
def prompt_size(
    skill_file: Path = typer.Argument(..., help="Path to a SKILL.md file to analyze"),
    identity: Path | None = typer.Option(
        None, "--identity", "-i", help="Optional identity YAML file to include in analysis"
    ),
    budget: int = typer.Option(
        8000, "--budget", "-b", help="Token budget threshold for warnings"
    ),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table or json"
    ),
) -> None:
    """Analyze prompt size and detect bloat in generated SKILL.md files.

    Measures character count, line count, and estimated tokens per section.
    Flags oversized sections, redundant content, and overall bloat.

    Examples:
        agentforge prompt-size output/SKILL.md
        agentforge prompt-size output/SKILL.md --identity output/identity.yaml
        agentforge prompt-size output/SKILL.md --budget 5000
        agentforge prompt-size output/SKILL.md --format json
    """
    if not skill_file.exists():
        console.print(f"[red]Error:[/red] File not found: {skill_file}")
        raise typer.Exit(code=1)

    skill_content = skill_file.read_text()
    identity_content = None
    if identity:
        if not identity.exists():
            console.print(f"[red]Error:[/red] File not found: {identity}")
            raise typer.Exit(code=1)
        identity_content = identity.read_text()

    from agentforge.analysis.prompt_size_analyzer import PromptSizeAnalyzer

    analyzer = PromptSizeAnalyzer(token_budget=budget)

    if identity_content:
        report = analyzer.analyze_combined(skill_content, identity_content)
    else:
        report = analyzer.analyze_skill_md(skill_content)

    if format == "json":
        console.print(Panel(
            json.dumps(report.model_dump(), indent=2),
            title="Prompt Size Report",
            border_style="blue",
        ))
    else:
        # Summary panel
        assessment_color = {
            "lean": "green",
            "moderate": "yellow",
            "bloated": "red",
        }.get(report.overall_assessment, "white")
        console.print(Panel(
            f"[bold]Total:[/bold] {report.total_chars:,} chars | "
            f"{report.total_lines:,} lines | "
            f"~{report.total_estimated_tokens:,} tokens\n"
            f"[bold]Assessment:[/bold] [{assessment_color}]{report.overall_assessment.upper()}[/{assessment_color}]",
            title="Prompt Size Summary",
            border_style=assessment_color,
        ))

        # Section breakdown table
        table = Table(title="Section Breakdown", show_lines=True)
        table.add_column("Section", style="cyan", min_width=20)
        table.add_column("Tokens", style="yellow", justify="right")
        table.add_column("Lines", justify="right")
        table.add_column("%", justify="right")
        table.add_column("Bar", min_width=20)

        for section in sorted(report.sections, key=lambda s: s.estimated_tokens, reverse=True):
            bar_len = min(int(section.percentage / 5), 20)
            bar = "[blue]" + "#" * bar_len + "[/blue]" + "." * (20 - bar_len)
            table.add_row(
                section.name,
                f"{section.estimated_tokens:,}",
                str(section.line_count),
                f"{section.percentage:.1f}%",
                bar,
            )
        console.print(table)

        # Verdicts
        if report.verdicts:
            console.print()
            for verdict in report.verdicts:
                icon = {"warning": "[yellow]!", "bloated": "[red]!!", "ok": "[green]~"}
                sev = icon.get(verdict.severity, "[white]?")
                console.print(f"  {sev}[/] [{verdict.severity}]{verdict.section}[/]: {verdict.message}")
            console.print()

    # Exit code 1 if bloated (useful for CI)
    if report.overall_assessment == "bloated":
        raise typer.Exit(code=1)


@app.command()
def lint(
    skill_file: Path = typer.Argument(..., help="Path to a SKILL.md file to lint"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table or json"
    ),
) -> None:
    """Lint a SKILL.md file for structural, semantic, and coherence issues.

    Checks for missing frontmatter, empty sections, trait contradictions,
    automation mismatches, and scope overlap.

    Examples:
        agentforge lint output/SKILL.md
        agentforge lint output/SKILL.md --format json
    """
    if not skill_file.exists():
        console.print(f"[red]Error:[/red] File not found: {skill_file}")
        raise typer.Exit(code=1)

    from agentforge.analysis.skill_linter import SkillLinter

    linter = SkillLinter()
    report = linter.lint(skill_file.read_text())

    if format == "json":
        console.print(Panel(
            json.dumps(report.model_dump(), indent=2),
            title="Lint Report",
            border_style="blue",
        ))
    else:
        status_color = "green" if report.passed else "red"
        console.print(Panel(
            f"[bold]Errors:[/bold] {report.error_count} | "
            f"[bold]Warnings:[/bold] {report.warning_count} | "
            f"[bold]Info:[/bold] {report.info_count}\n"
            f"[bold]Status:[/bold] [{status_color}]{'PASSED' if report.passed else 'FAILED'}[/{status_color}]",
            title="Lint Summary",
            border_style=status_color,
        ))

        if report.issues:
            table = Table(title="Lint Issues", show_lines=True)
            table.add_column("Rule", style="cyan", min_width=20)
            table.add_column("Severity", min_width=8)
            table.add_column("Section", style="dim")
            table.add_column("Message", max_width=60)

            severity_colors = {"error": "red", "warning": "yellow", "info": "blue"}
            for issue in report.issues:
                color = severity_colors.get(issue.severity, "white")
                table.add_row(
                    issue.rule,
                    f"[{color}]{issue.severity}[/{color}]",
                    issue.section,
                    issue.message,
                )
            console.print(table)

    if not report.passed:
        raise typer.Exit(code=1)


@app.command(name="prompt-size")
def prompt_size(
    skill_file: Path = typer.Argument(..., help="Path to a SKILL.md file to analyze"),
    identity: Path | None = typer.Option(
        None, "--identity", "-i", help="Optional identity YAML file to include in analysis"
    ),
    budget: int = typer.Option(
        8000, "--budget", "-b", help="Token budget threshold for warnings"
    ),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table or json"
    ),
) -> None:
    """Analyze prompt size and detect bloat in generated SKILL.md files.

    Measures character count, line count, and estimated tokens per section.
    Flags oversized sections, redundant content, and overall bloat.

    Examples:
        agentforge prompt-size output/SKILL.md
        agentforge prompt-size output/SKILL.md --identity output/identity.yaml
        agentforge prompt-size output/SKILL.md --budget 5000
        agentforge prompt-size output/SKILL.md --format json
    """
    if not skill_file.exists():
        console.print(f"[red]Error:[/red] File not found: {skill_file}")
        raise typer.Exit(code=1)

    skill_content = skill_file.read_text()
    identity_content = None
    if identity:
        if not identity.exists():
            console.print(f"[red]Error:[/red] File not found: {identity}")
            raise typer.Exit(code=1)
        identity_content = identity.read_text()

    from agentforge.analysis.prompt_size_analyzer import PromptSizeAnalyzer

    analyzer = PromptSizeAnalyzer(token_budget=budget)

    if identity_content:
        report = analyzer.analyze_combined(skill_content, identity_content)
    else:
        report = analyzer.analyze_skill_md(skill_content)

    if format == "json":
        console.print(Panel(
            json.dumps(report.model_dump(), indent=2),
            title="Prompt Size Report",
            border_style="blue",
        ))
    else:
        # Summary panel
        assessment_color = {
            "lean": "green",
            "moderate": "yellow",
            "bloated": "red",
        }.get(report.overall_assessment, "white")
        console.print(Panel(
            f"[bold]Total:[/bold] {report.total_chars:,} chars | "
            f"{report.total_lines:,} lines | "
            f"~{report.total_estimated_tokens:,} tokens\n"
            f"[bold]Assessment:[/bold] [{assessment_color}]{report.overall_assessment.upper()}[/{assessment_color}]",
            title="Prompt Size Summary",
            border_style=assessment_color,
        ))

        # Section breakdown table
        table = Table(title="Section Breakdown", show_lines=True)
        table.add_column("Section", style="cyan", min_width=20)
        table.add_column("Tokens", style="yellow", justify="right")
        table.add_column("Lines", justify="right")
        table.add_column("%", justify="right")
        table.add_column("Bar", min_width=20)

        for section in sorted(report.sections, key=lambda s: s.estimated_tokens, reverse=True):
            bar_len = min(int(section.percentage / 5), 20)
            bar = "[blue]" + "#" * bar_len + "[/blue]" + "." * (20 - bar_len)
            table.add_row(
                section.name,
                f"{section.estimated_tokens:,}",
                str(section.line_count),
                f"{section.percentage:.1f}%",
                bar,
            )
        console.print(table)

        # Verdicts
        if report.verdicts:
            console.print()
            for verdict in report.verdicts:
                icon = {"warning": "[yellow]!", "bloated": "[red]!!", "ok": "[green]~"}
                sev = icon.get(verdict.severity, "[white]?")
                console.print(f"  {sev}[/] [{verdict.severity}]{verdict.section}[/]: {verdict.message}")
            console.print()

    # Exit code 1 if bloated (useful for CI)
    if report.overall_assessment == "bloated":
        raise typer.Exit(code=1)


@app.command()
def cost(
    skill_file: Path = typer.Argument(..., help="Path to a SKILL.md file to estimate costs for"),
    daily_calls: int = typer.Option(
        50, "--daily-calls", "-n", help="Expected invocations per working day"
    ),
    cost_per_1k: float = typer.Option(
        0.008, "--cost-per-1k", help="Cost per 1K tokens (USD, blended input+output)"
    ),
    monthly_budget: float = typer.Option(
        500.0, "--budget", "-b", help="Monthly budget (USD) for utilization calculation"
    ),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table or json"
    ),
) -> None:
    """Estimate monthly token costs for running a generated SKILL.md.

    Projects costs based on actual prompt size and expected daily usage.

    Examples:
        agentforge cost output/SKILL.md
        agentforge cost output/SKILL.md --daily-calls 100
        agentforge cost output/SKILL.md --cost-per-1k 0.015 --budget 1000
    """
    if not skill_file.exists():
        console.print(f"[red]Error:[/red] File not found: {skill_file}")
        raise typer.Exit(code=1)

    from agentforge.analysis.cost_projector import CostProjector

    projector = CostProjector(cost_per_1k=cost_per_1k, monthly_budget=monthly_budget)
    report = projector.project(skill_file.read_text(), daily_calls=daily_calls)

    if format == "json":
        console.print(Panel(
            json.dumps(report.model_dump(), indent=2),
            title="Cost Projection",
            border_style="blue",
        ))
    else:
        util_color = "green" if report.budget_utilization < 0.5 else "yellow" if report.budget_utilization < 0.8 else "red"
        console.print(Panel(
            f"[bold]Prompt size:[/bold] ~{report.prompt_tokens:,} tokens\n"
            f"[bold]Tokens per call:[/bold] ~{report.tokens_per_call:,} "
            f"(prompt {report.prompt_tokens:,} + completion ~{report.estimated_completion_tokens:,})\n"
            f"[bold]Daily calls:[/bold] {report.estimated_daily_calls}\n"
            f"\n"
            f"[bold]Monthly tokens:[/bold] {report.monthly_token_usage:,}\n"
            f"[bold]Monthly cost:[/bold] ${report.monthly_cost_usd:,.2f}\n"
            f"[bold]Annual cost:[/bold] ${report.annual_cost_usd:,.2f}\n"
            f"[bold]Cost per call:[/bold] ${report.cost_per_call_usd:.4f}\n"
            f"[bold]Budget utilization:[/bold] [{util_color}]{report.budget_utilization:.0%}[/{util_color}]",
            title="Cost Projection",
            border_style="blue",
        ))


@app.command(name="prompt-diff")
def prompt_diff(
    old_file: Path = typer.Argument(..., help="Path to the old SKILL.md file"),
    new_file: Path = typer.Argument(..., help="Path to the new SKILL.md file"),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table or json"
    ),
) -> None:
    """Compare two SKILL.md files section-by-section.

    Shows added, removed, and changed sections, plus personality trait changes.

    Examples:
        agentforge prompt-diff old_SKILL.md new_SKILL.md
        agentforge prompt-diff v1/SKILL.md v2/SKILL.md --format json
    """
    for f in (old_file, new_file):
        if not f.exists():
            console.print(f"[red]Error:[/red] File not found: {f}")
            raise typer.Exit(code=1)

    from agentforge.analysis.prompt_differ import PromptDiffer

    differ = PromptDiffer()
    report = differ.diff(old_file.read_text(), new_file.read_text())

    if format == "json":
        console.print(Panel(
            json.dumps(report.model_dump(), indent=2),
            title="Prompt Diff",
            border_style="blue",
        ))
    else:
        delta_sign = "+" if report.total_token_delta >= 0 else ""
        console.print(Panel(
            f"[bold]Sections added:[/bold] {report.sections_added} | "
            f"[bold]Removed:[/bold] {report.sections_removed} | "
            f"[bold]Changed:[/bold] {report.sections_changed}\n"
            f"[bold]Token delta:[/bold] {delta_sign}{report.total_token_delta:,}",
            title="Prompt Diff Summary",
            border_style="blue",
        ))

        # Section table
        changed_sections = [s for s in report.sections if s.status != "unchanged"]
        if changed_sections:
            table = Table(title="Section Changes", show_lines=True)
            table.add_column("Section", style="cyan", min_width=20)
            table.add_column("Status", min_width=10)
            table.add_column("Old", justify="right")
            table.add_column("New", justify="right")
            table.add_column("Summary", max_width=50)

            status_colors = {"added": "green", "removed": "red", "changed": "yellow"}
            for s in changed_sections:
                color = status_colors.get(s.status, "white")
                table.add_row(
                    s.section,
                    f"[{color}]{s.status}[/{color}]",
                    f"{s.old_size:,}" if s.old_size else "-",
                    f"{s.new_size:,}" if s.new_size else "-",
                    s.change_summary,
                )
            console.print(table)

        # Trait changes
        if report.trait_changes:
            console.print()
            for tc in report.trait_changes:
                old_str = f"{tc.old_value:.0%}" if tc.old_value is not None else "—"
                new_str = f"{tc.new_value:.0%}" if tc.new_value is not None else "—"
                delta_sign = "+" if tc.delta > 0 else ""
                color = "green" if tc.delta > 0 else "red" if tc.delta < 0 else "dim"
                console.print(
                    f"  [{color}]{tc.trait}[/{color}]: {old_str} → {new_str} "
                    f"([{color}]{delta_sign}{tc.delta:.0%}[/{color}])"
                )
            console.print()


@app.command()
def audit(
    skill_file: Path = typer.Argument(..., help="Path to a SKILL.md file to audit"),
    domain: str = typer.Option("general", "--domain", "-d", help="Role domain for domain-specific guardrail checks"),
    fix: bool = typer.Option(False, "--fix", help="Auto-inject missing guardrails into the skill file"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output path for fixed file (defaults to stdout)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
) -> None:
    """Audit a SKILL.md file against a comprehensive guardrail safety checklist."""
    from agentforge.analysis.guardrail_auditor import GuardrailAuditor

    if not skill_file.exists():
        console.print(f"[red]Error: file not found: {skill_file}[/red]")
        raise typer.Exit(code=1)

    content = skill_file.read_text()
    auditor = GuardrailAuditor()
    report = auditor.audit(content, domain=domain)

    def _show_report(rpt: "GuardrailReport", label: str = "Guardrail Audit") -> None:
        if format == "json":
            console.print(json.dumps(rpt.model_dump(), indent=2, default=str))
            return

        table = Table(title=label)
        table.add_column("Check", style="bold")
        table.add_column("Category")
        table.add_column("Status")
        table.add_column("Evidence / Recommendation", max_width=60)

        for result in rpt.results:
            if result.passed:
                status = "[green]PASS[/green]"
                detail = result.evidence
            else:
                status = "[red]FAIL[/red]"
                detail = result.recommendation
            table.add_row(result.check.name, result.check.category, status, detail)

        console.print(table)

        overall_status = "[green]PASSED[/green]" if rpt.overall_passed else "[red]FAILED[/red]"
        summary = (
            f"Score: {rpt.score:.0%}  |  "
            f"Passed: {rpt.passed_count}  |  "
            f"Failed: {rpt.failed_count}  |  "
            f"Overall: {overall_status}"
        )
        console.print(Panel(summary, title="Summary"))

    _show_report(report)

    if fix and report.failed_count > 0:
        fixed_content = auditor.fix(content, report)
        if output:
            output.write_text(fixed_content)
            console.print(f"\n[green]Fixed file written to {output}[/green]")
        else:
            console.print("\n[bold]--- Fixed SKILL.md ---[/bold]\n")
            console.print(fixed_content)

        # Re-audit the fixed content
        re_report = auditor.audit(fixed_content, domain=domain)
        console.print()
        _show_report(re_report, label="Re-Audit After Fix")

    if not report.overall_passed:
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Show AgentForge version."""
    from agentforge import __version__
    console.print(f"AgentForge v{__version__}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to listen on"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes (dev)"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open browser on start"),
) -> None:
    """Start the AgentForge web UI server.

    Examples:
        agentforge serve
        agentforge serve --port 8080 --reload
        agentforge serve --host 0.0.0.0 --no-open
    """
    try:
        import uvicorn
    except ImportError:
        console.print(Panel(
            "[red]uvicorn not installed.[/red]\n"
            "[dim]Install web extras: uv sync --extra web[/dim]",
            title="Missing Dependency",
            border_style="red",
        ))
        raise typer.Exit(code=1)

    if open_browser:
        import threading
        import webbrowser

        def _open() -> None:
            import time
            time.sleep(1.2)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=_open, daemon=True).start()

    console.print(Panel(
        f"[green]AgentForge Web UI[/green] running at [bold]http://{host}:{port}[/bold]\n"
        "Press Ctrl+C to stop.",
        border_style="green",
    ))

    if reload:
        # uvicorn requires an import string for --reload mode
        uvicorn.run(
            "agentforge.web.app:create_app",
            factory=True,
            host=host,
            port=port,
            reload=True,
        )
    else:
        from agentforge.web.app import create_app

        uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    app()
