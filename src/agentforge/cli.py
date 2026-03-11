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
        False, "--no-skill-file", help="Skip SKILL.md generation"
    ),
    skill_folder: bool = typer.Option(
        False, "--skill-folder", help="Output Claude-compatible skill folder (instructions.md + manifest.json)"
    ),
    culture: Path | None = typer.Option(
        None, "--culture", "-c", help="Culture file (YAML or markdown) to infuse"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Forge a complete AI agent blueprint from a job description.

    Runs the full pipeline: ingest -> extract -> map -> culture -> generate -> analyze.
    Outputs a PersonaNexus identity YAML and optional SKILL.md.

    Examples:
        agentforge forge job_posting.txt
        agentforge forge resume.pdf --culture startup.yaml -d ./agents
        agentforge forge posting.md --quick --no-skill-file
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

    # Save identity YAML with safe filename
    agent_id = context["identity"].metadata.id
    yaml_path = safe_output_path(output_dir, f"{agent_id}.yaml")
    yaml_path.write_text(identity_yaml)
    console.print(f"[green]Identity saved:[/green] {yaml_path}")

    # Save SKILL.md
    if not no_skill_file and "skill_file" in context:
        skill_path = safe_output_path(output_dir, f"{agent_id}_SKILL.md")
        skill_path.write_text(context["skill_file"])
        console.print(f"[green]Skill file saved:[/green] {skill_path}")

    # Save skill folder
    if skill_folder and "skill_folder" in context:
        sf = context["skill_folder"]
        folder_path = safe_output_path(output_dir, sf.agent_id)
        folder_path.mkdir(exist_ok=True)
        (folder_path / "instructions.md").write_text(sf.instructions_md)
        (folder_path / "manifest.json").write_text(sf.manifest_json)
        console.print(f"[green]Skill folder saved:[/green] {folder_path}/")

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
