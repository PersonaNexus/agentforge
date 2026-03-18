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

from agentforge.models.extracted_skills import ExtractionResult
from agentforge.utils import safe_output_path

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
        "claude-sonnet-4-20250514", "--model", "-m", help="Claude model to use"
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
        "claude-sonnet-4-20250514", "--model", "-m", help="Claude model to use"
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
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Forge a complete AI agent blueprint from a job description.

    Runs the full pipeline: ingest -> extract -> map -> culture -> generate -> analyze.

    Outputs:
      - PersonaNexus identity YAML (always)
      - Claude Code skill folder (always) — drop into .claude/skills/ to use
      - Full agent profile SKILL.md (unless --no-skill-file) — detailed analysis

    Examples:
        agentforge forge job_posting.txt
        agentforge forge resume.pdf --culture startup.yaml -d ./agents
        agentforge forge posting.md --quick --no-skill-file
        agentforge forge job.txt --skill-folder  # also save skill folder to disk
        agentforge forge job.txt --deep  # enhanced gap analysis
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

    output_dir.mkdir(parents=True, exist_ok=True)

    # Build pipeline
    if quick_mode:
        pipeline = ForgePipeline.quick()
    elif deep:
        pipeline = ForgePipeline.deep_analysis()
    else:
        pipeline = ForgePipeline.default()

    # Set up context
    client = _make_client(model)
    context: dict = {
        "input_path": str(jd_file),
        "llm_client": client,
    }
    if culture:
        context["culture_path"] = str(culture)
        console.print(f"[blue]Culture:[/blue] {culture}")

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
            ref_path = folder_path / rel_path
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(content)

        ref_count = len(sf.supplementary_files)
        ref_msg = f" + {ref_count} reference file{'s' if ref_count != 1 else ''}" if ref_count else ""
        console.print(
            f"[green]Claude Code skill saved:[/green] {folder_path}/\n"
            f"  [dim]SKILL.md{ref_msg} — copy to .claude/skills/ or ~/.claude/skills/ to use[/dim]"
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
        sf = sf_gen.generate(extraction, identity, jd=None, methodology=methodology)

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
        "claude-sonnet-4-20250514", "--model", "-m", help="Claude model (for markdown parsing)"
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
    parallel: int = typer.Option(1, "--parallel", "-p", help="Number of parallel workers"),
    model: str = typer.Option(
        "claude-sonnet-4-20250514", "--model", "-m", help="Claude model to use"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Process multiple job descriptions in batch.

    Examples:
        agentforge batch ./job_descriptions/ -d ./agents
        agentforge batch ./jds/ --culture startup.yaml --parallel 4
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
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Forge a complete multi-agent team from a single job description.

    Creates specialized agent skills plus a conductor that orchestrates them.

    Examples:
        agentforge team job.txt -d ./agents
        agentforge team posting.pdf --culture startup.yaml
    """
    from agentforge.pipeline.forge_pipeline import ForgePipeline

    if verbose:
        logging.basicConfig(level=logging.DEBUG)

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

    # Save orchestration config
    from agentforge.composition.orchestration_config import OrchestrationConfigExporter
    exporter = OrchestrationConfigExporter()
    orch_yaml = exporter.export_orchestration_yaml(forged_team_result)
    (output_dir / "orchestration.yaml").write_text(orch_yaml)
    console.print(f"[green]Orchestration config:[/green] {output_dir}/orchestration.yaml")

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
