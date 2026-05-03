"""``agentforge department ...`` sub-CLI (Phase 1.0)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agentforge.corpus import load_corpus
from agentforge.department.synthesize import (
    analyze_directory,
    extract_corpus,
    write_report,
)
from agentforge.department.synthesize_team import synthesize_team

app = typer.Typer(
    name="department",
    help="Synthesize a multi-agent team from a JD corpus directory.",
    no_args_is_help=True,
)
console = Console()


@app.command("scan")
def cmd_scan(
    jd_folder: Path = typer.Argument(
        ...,
        help="Directory of JD markdown files (one per role, with YAML frontmatter).",
    ),
) -> None:
    """List the corpus without extracting anything (cheap, no LLM)."""
    jd_folder = jd_folder.expanduser().resolve()
    corpus = load_corpus(jd_folder)
    table = Table(title=f"corpus: {corpus.root}", show_lines=False)
    table.add_column("Role ID", style="cyan")
    table.add_column("Title")
    table.add_column("Seniority", style="dim")
    table.add_column("Body lines", justify="right")
    for e in corpus:
        body_lines = e.body.count("\n")
        table.add_row(
            e.role_id,
            e.title,
            e.frontmatter.seniority or "—",
            str(body_lines),
        )
    console.print(table)
    console.print(f"[green]✓[/green] {len(corpus)} JD(s) loaded")


@app.command("analyze")
def cmd_analyze(
    jd_folder: Path = typer.Argument(
        ...,
        help="Directory of JD markdown files.",
    ),
    output_dir: Path | None = typer.Option(
        None, "--output-dir", "-d",
        help="Where to write skill-landscape.{md,json}. Default: <jd-folder>/.agentforge/",
    ),
    model: str | None = typer.Option(
        None, "--model", "-m",
        help="LLM model for skill extraction.",
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache",
        help="Force re-extraction (ignore cached results in <corpus>/.agentforge/extractions/).",
    ),
) -> None:
    """Phase 1.0: extract skills per role, cluster across roles, write report."""
    jd_folder = jd_folder.expanduser().resolve()
    out_dir = (output_dir or (jd_folder / ".agentforge")).expanduser().resolve()

    from agentforge.llm.client import LLMClient
    client = LLMClient(model=model) if model else LLMClient()
    model_label = client.model

    console.print(Panel(
        f"[cyan]analyzing[/cyan] {jd_folder}\n"
        f"model: [bold]{model_label}[/bold] · "
        f"cache: {'off' if no_cache else 'on'}",
        title="department analyze",
    ))

    corpus, extractions, landscape = analyze_directory(
        jd_folder,
        client=client,
        use_cache=not no_cache,
    )
    md_path, json_path = write_report(corpus, extractions, landscape, out_dir)

    shared = landscape.shared_clusters
    role_spec = landscape.role_specific_clusters
    console.print(
        f"\n[green]✓[/green] {landscape.role_count} role(s), "
        f"[bold]{len(shared)}[/bold] shared skills, "
        f"[bold]{len(role_spec)}[/bold] role-specific."
    )
    console.print(f"  report: [bold]{md_path}[/bold]")
    console.print(f"  json:   [bold]{json_path}[/bold]")


@app.command("synthesize")
def cmd_synthesize(
    jd_folder: Path = typer.Argument(
        ...,
        help="Directory of JD markdown files (one per role).",
    ),
    output_dir: Path = typer.Option(
        ...,
        "--output-dir", "-o",
        help="Where to write the synthesized department.",
    ),
    department_name: str | None = typer.Option(
        None, "--name", "-n",
        help="Display name for the department (default: corpus directory name).",
    ),
    target: str = typer.Option(
        "claude-code", "--target",
        help="Output target. 'plain' / 'openclaw' suppress identity.yaml.",
    ),
    keep_identity_yaml: bool = typer.Option(
        False, "--keep-identity-yaml",
        help="Override --target suppression and always write identity.yaml.",
    ),
    use_llm: bool = typer.Option(
        False, "--use-llm",
        help="Use the LLM for handoff detection and the README team brief.",
    ),
    model: str | None = typer.Option(
        None, "--model", "-m",
        help="LLM model for extraction + (with --use-llm) handoffs/brief.",
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache",
        help="Force re-extraction (ignore cached results).",
    ),
) -> None:
    """Phase 1.1: synthesize a coordinated multi-agent team from a JD corpus."""
    jd_folder = jd_folder.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if target not in {"claude-code", "plain", "openclaw"}:
        raise typer.BadParameter(
            f"--target must be one of claude-code, plain, openclaw (got {target!r})"
        )

    from agentforge.department.synthesize import _default_extractor
    from agentforge.llm.client import LLMClient

    client = LLMClient(model=model) if model else LLMClient()
    corpus = load_corpus(jd_folder)
    console.print(Panel(
        f"[cyan]synthesizing[/cyan] {jd_folder} → {output_dir}\n"
        f"model: [bold]{client.model}[/bold] · target: [bold]{target}[/bold] · "
        f"llm-augment: {'on' if use_llm else 'off'} · "
        f"cache: {'off' if no_cache else 'on'}",
        title="department synthesize",
    ))

    extract = _default_extractor(client)
    extractions = extract_corpus(corpus, extract, use_cache=not no_cache)

    artifacts = synthesize_team(
        corpus,
        output_dir,
        department_name=department_name,
        extractions=extractions,
        client=client if use_llm else None,
        use_llm_handoffs=use_llm,
        use_llm_brief=use_llm,
        target=target,
        keep_identity_yaml=keep_identity_yaml,
    )

    table = Table(title="Synthesized roles")
    table.add_column("Role", style="cyan")
    table.add_column("identity.yaml", style="dim")
    table.add_column("SKILL.md", style="dim")
    table.add_column("Refs", justify="right")
    for r in artifacts.role_artifacts:
        table.add_row(
            r.role_id,
            "✓" if r.identity_yaml_path else "—",
            "✓",
            str(len(r.supplementary_paths)),
        )
    console.print(table)

    console.print(
        f"\n[green]✓[/green] {len(artifacts.role_artifacts)} role(s), "
        f"[bold]{artifacts.shared_cluster_count}[/bold] shared skill(s), "
        f"[bold]{artifacts.handoff_count}[/bold] handoff(s)."
    )
    console.print(f"  README:        [bold]{artifacts.readme_path}[/bold]")
    console.print(f"  orchestration: [bold]{artifacts.orchestration_path}[/bold]")
    console.print(f"  conductor:     [bold]{artifacts.conductor_skill_path}[/bold]")


def register(parent: typer.Typer) -> None:
    parent.add_typer(app, name="department")
