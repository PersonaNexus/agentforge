"""Batch processing for multiple job descriptions."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from agentforge.models.blueprint import AgentBlueprint
from agentforge.pipeline.forge_pipeline import ForgePipeline

console = Console()


class BatchResult:
    """Result of processing a single JD in a batch."""

    def __init__(
        self,
        input_path: str,
        blueprint: AgentBlueprint | None = None,
        error: str | None = None,
        duration: float = 0.0,
    ):
        self.input_path = input_path
        self.blueprint = blueprint
        self.error = error
        self.duration = duration

    @property
    def success(self) -> bool:
        return self.blueprint is not None


class BatchProcessor:
    """Process multiple job descriptions through the forge pipeline."""

    def __init__(
        self,
        pipeline: ForgePipeline | None = None,
        parallel: int = 1,
        output_dir: Path | None = None,
    ):
        self.pipeline = pipeline or ForgePipeline.default()
        self.parallel = max(1, parallel)
        self.output_dir = output_dir or Path(".")

    def _process_single(
        self,
        input_path: str,
        shared_context: dict[str, Any],
    ) -> BatchResult:
        """Process a single JD file."""
        start = time.time()
        try:
            context = {
                **shared_context,
                "input_path": input_path,
            }
            context = self.pipeline.run(context)
            blueprint = self.pipeline.to_blueprint(context)

            # Save output files with safe filenames
            from agentforge.utils import safe_output_path

            agent_id = context["identity"].metadata.id
            yaml_path = safe_output_path(self.output_dir, f"{agent_id}.yaml")
            yaml_path.write_text(context["identity_yaml"])

            if "skill_file" in context:
                skill_path = safe_output_path(self.output_dir, f"{agent_id}_SKILL.md")
                skill_path.write_text(context["skill_file"])

            if "skill_folder" in context:
                sf = context["skill_folder"]
                sf_dir = safe_output_path(self.output_dir, sf.skill_name)
                sf_dir.mkdir(exist_ok=True)
                (sf_dir / "SKILL.md").write_text(sf.skill_md)

            duration = time.time() - start
            return BatchResult(
                input_path=input_path,
                blueprint=blueprint,
                duration=duration,
            )
        except Exception as e:
            duration = time.time() - start
            return BatchResult(
                input_path=input_path,
                error=str(e),
                duration=duration,
            )

    def process(
        self,
        input_paths: list[str],
        shared_context: dict[str, Any] | None = None,
        show_progress: bool = True,
    ) -> list[BatchResult]:
        """Process multiple JD files with progress tracking."""
        ctx = shared_context or {}
        self.output_dir.mkdir(parents=True, exist_ok=True)
        results: list[BatchResult] = []

        if show_progress:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"Processing {len(input_paths)} JDs...",
                    total=len(input_paths),
                )

                if self.parallel > 1:
                    results = self._process_parallel(input_paths, ctx, progress, task)
                else:
                    for path in input_paths:
                        result = self._process_single(path, ctx)
                        results.append(result)
                        progress.advance(task)
        else:
            for path in input_paths:
                result = self._process_single(path, ctx)
                results.append(result)

        return results

    def _process_parallel(
        self,
        input_paths: list[str],
        shared_context: dict[str, Any],
        progress: Any,
        task: Any,
    ) -> list[BatchResult]:
        """Process JDs in parallel using ThreadPoolExecutor."""
        results: list[BatchResult] = []

        with ThreadPoolExecutor(max_workers=self.parallel) as executor:
            futures = {
                executor.submit(self._process_single, path, shared_context): path
                for path in input_paths
            }
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                progress.advance(task)

        # Sort by input order
        path_order = {p: i for i, p in enumerate(input_paths)}
        results.sort(key=lambda r: path_order.get(r.input_path, 0))
        return results

    @staticmethod
    def display_summary(results: list[BatchResult]) -> None:
        """Display a summary table of batch results."""
        table = Table(title="Batch Processing Results", show_lines=True)
        table.add_column("File", style="cyan", max_width=40)
        table.add_column("Status", style="bold")
        table.add_column("Agent", style="green")
        table.add_column("Skills", justify="right")
        table.add_column("Coverage", justify="right")
        table.add_column("Time", justify="right", style="dim")

        succeeded = 0
        failed = 0

        for result in results:
            filename = Path(result.input_path).name
            time_str = f"{result.duration:.1f}s"

            if result.success:
                succeeded += 1
                bp = result.blueprint
                table.add_row(
                    filename,
                    "[green]OK[/green]",
                    bp.extraction.role.title,
                    str(len(bp.extraction.skills)),
                    f"{int(bp.coverage_score * 100)}%",
                    time_str,
                )
            else:
                failed += 1
                table.add_row(
                    filename,
                    "[red]FAIL[/red]",
                    result.error[:30] if result.error else "Unknown",
                    "-",
                    "-",
                    time_str,
                )

        console.print(table)
        console.print(
            f"\n[bold]Summary:[/bold] {succeeded} succeeded, {failed} failed, "
            f"{len(results)} total"
        )
