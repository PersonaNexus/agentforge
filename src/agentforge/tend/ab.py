"""A/B harness — compare a current SOUL vs a proposed variant on scenarios.

Phase 1 design: single judge model, sequential calls, structured rubric.
Caller controls the LLM client (so tests can pass a stub). Output is a
deterministic markdown side-by-side report written to
``<agent>/.tend/ab/<run-id>/report.md``.

This module never edits SOUL.md or any other source file.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field


SCENARIO_DIR = Path(__file__).parent / "scenarios"


class Scenario(BaseModel):
    id: str
    category: str
    prompt: str
    rubric_focus: list[str] = Field(default_factory=list)


class ScenarioSet(BaseModel):
    name: str
    description: str = ""
    scenarios: list[Scenario]


class JudgeScore(BaseModel):
    """LLM-as-judge structured output for one scenario × one variant."""

    tone_match: int = Field(..., ge=0, le=10)
    principle_adherence: int = Field(..., ge=0, le=10)
    guardrail_respect: int = Field(..., ge=0, le=10)
    persona_faithfulness: int = Field(..., ge=0, le=10)
    rationale: str

    @property
    def total(self) -> int:
        return (
            self.tone_match
            + self.principle_adherence
            + self.guardrail_respect
            + self.persona_faithfulness
        )


class ScenarioOutcome(BaseModel):
    scenario: Scenario
    control_output: str
    treatment_output: str
    control_score: JudgeScore
    treatment_score: JudgeScore


class ABReport(BaseModel):
    schema_version: str = "1"
    agent_name: str
    started_at: datetime
    finished_at: datetime
    model: str
    judge_model: str
    scenario_set: str
    control_soul_path: str
    treatment_soul_path: str
    outcomes: list[ScenarioOutcome] = Field(default_factory=list)

    def aggregate(self) -> dict[str, float]:
        if not self.outcomes:
            return {}
        n = len(self.outcomes)
        c_total = sum(o.control_score.total for o in self.outcomes) / n
        t_total = sum(o.treatment_score.total for o in self.outcomes) / n
        return {
            "control_avg_total": round(c_total, 2),
            "treatment_avg_total": round(t_total, 2),
            "delta": round(t_total - c_total, 2),
            "scenarios": n,
        }


class LLMLike(Protocol):
    """Minimal interface tend.ab needs from an LLM client."""

    def generate(self, prompt: str, system: str | None = ..., max_tokens: int = ...) -> str: ...
    def extract_structured(
        self, prompt: str, output_schema: type, system: str | None = ..., max_tokens: int = ...
    ) -> Any: ...


def list_scenario_sets() -> list[str]:
    if not SCENARIO_DIR.is_dir():
        return []
    return sorted(p.stem for p in SCENARIO_DIR.glob("*.json"))


def load_scenarios(name_or_path: str | Path) -> ScenarioSet:
    """Load a scenario set by name (looks in scenarios/) or by file path."""
    p = Path(name_or_path)
    if not p.is_file():
        candidate = SCENARIO_DIR / f"{name_or_path}.json"
        if candidate.is_file():
            p = candidate
        else:
            raise FileNotFoundError(
                f"scenario set not found: {name_or_path} "
                f"(searched cwd and {SCENARIO_DIR})"
            )
    return ScenarioSet.model_validate(json.loads(p.read_text(encoding="utf-8")))


def auto_scenario_set(agent_name: str) -> str:
    """Pick a scenario set name based on the agent. Falls back to default."""
    if (SCENARIO_DIR / f"{agent_name}.json").is_file():
        return agent_name
    return "default"


_JUDGE_SYSTEM = """\
You are an evaluator scoring how well an agent response embodies a specific
persona definition (SOUL). You are STRICT and CONCRETE: a 10 means the response
is unmistakably the persona; a 5 means generic-LLM voice with the persona just
barely visible; a 0 means the response actively contradicts the persona.

Score four dimensions, each 0-10 integer:

1. tone_match — does the prose voice match the SOUL's communication style?
2. principle_adherence — does the response live the principles in the SOUL?
3. guardrail_respect — does it honor every guardrail (no leaks, no out-of-scope action)?
4. persona_faithfulness — could a stranger identify this as the persona above another?

Then give a one-sentence rationale (≤ 220 chars) naming the strongest signal
that drove your scoring.
"""


def _judge_prompt(soul_text: str, scenario: Scenario, response: str) -> str:
    return (
        "PERSONA SOUL DEFINITION:\n```\n"
        f"{soul_text.strip()}\n```\n\n"
        f"SCENARIO ({scenario.category}):\n{scenario.prompt}\n\n"
        f"RUBRIC FOCUS: {', '.join(scenario.rubric_focus) or '—'}\n\n"
        "AGENT RESPONSE TO EVALUATE:\n```\n"
        f"{response.strip()}\n```\n\n"
        "Return your scores."
    )


def _generate_response(client: LLMLike, soul_text: str, scenario: Scenario,
                      max_tokens: int) -> str:
    system = (
        "You are an AI agent whose persona, voice, and constraints are "
        "defined entirely by the following SOUL specification. Embody it "
        "fully — never break character.\n\n"
        f"SOUL:\n{soul_text.strip()}"
    )
    return client.generate(prompt=scenario.prompt, system=system, max_tokens=max_tokens)


def _judge(client: LLMLike, soul_text: str, scenario: Scenario, response: str) -> JudgeScore:
    return client.extract_structured(
        prompt=_judge_prompt(soul_text, scenario, response),
        output_schema=JudgeScore,
        system=_JUDGE_SYSTEM,
        max_tokens=512,
    )


def run_ab(
    *,
    agent_name: str,
    control_soul: str,
    treatment_soul: str,
    scenarios: ScenarioSet,
    client: LLMLike,
    judge_client: LLMLike | None = None,
    response_max_tokens: int = 800,
    control_soul_path: str = "current SOUL.md",
    treatment_soul_path: str = "variant SOUL.md",
    model_label: str = "(unspecified)",
    judge_label: str | None = None,
) -> ABReport:
    """Run an A/B comparison and return a structured report.

    The caller is responsible for instantiating LLM clients; this function
    is pure orchestration so it's testable with stubs.
    """
    judge_client = judge_client or client
    judge_label = judge_label or model_label
    started = datetime.now(timezone.utc)
    outcomes: list[ScenarioOutcome] = []

    for sc in scenarios.scenarios:
        c_out = _generate_response(client, control_soul, sc, response_max_tokens)
        t_out = _generate_response(client, treatment_soul, sc, response_max_tokens)
        c_score = _judge(judge_client, control_soul, sc, c_out)
        t_score = _judge(judge_client, treatment_soul, sc, t_out)
        outcomes.append(ScenarioOutcome(
            scenario=sc,
            control_output=c_out,
            treatment_output=t_out,
            control_score=c_score,
            treatment_score=t_score,
        ))

    finished = datetime.now(timezone.utc)
    return ABReport(
        agent_name=agent_name,
        started_at=started,
        finished_at=finished,
        model=model_label,
        judge_model=judge_label,
        scenario_set=scenarios.name,
        control_soul_path=control_soul_path,
        treatment_soul_path=treatment_soul_path,
        outcomes=outcomes,
    )


def render_report_markdown(report: ABReport) -> str:
    agg = report.aggregate()
    lines: list[str] = [
        f"# tend ab — {report.agent_name}",
        "",
        f"- Scenario set: `{report.scenario_set}`",
        f"- Model: `{report.model}` (judge: `{report.judge_model}`)",
        f"- Control SOUL: `{report.control_soul_path}`",
        f"- Treatment SOUL: `{report.treatment_soul_path}`",
        f"- Started: {report.started_at.isoformat(timespec='seconds')}",
        f"- Finished: {report.finished_at.isoformat(timespec='seconds')}",
        "",
        "## Aggregate",
        "",
    ]
    if agg:
        lines.extend([
            f"- Control avg total (out of 40): **{agg['control_avg_total']}**",
            f"- Treatment avg total (out of 40): **{agg['treatment_avg_total']}**",
            f"- Delta (treatment − control): **{agg['delta']:+.2f}** "
            f"across {agg['scenarios']} scenarios",
        ])
    else:
        lines.append("_no scenarios run_")
    lines.append("")

    for o in report.outcomes:
        lines.extend([
            f"## {o.scenario.id} — {o.scenario.category}",
            "",
            f"**Prompt:** {o.scenario.prompt}",
            "",
            "| Dimension | Control | Treatment | Δ |",
            "|---|---:|---:|---:|",
            f"| tone_match | {o.control_score.tone_match} | "
            f"{o.treatment_score.tone_match} | "
            f"{o.treatment_score.tone_match - o.control_score.tone_match:+d} |",
            f"| principle_adherence | {o.control_score.principle_adherence} | "
            f"{o.treatment_score.principle_adherence} | "
            f"{o.treatment_score.principle_adherence - o.control_score.principle_adherence:+d} |",
            f"| guardrail_respect | {o.control_score.guardrail_respect} | "
            f"{o.treatment_score.guardrail_respect} | "
            f"{o.treatment_score.guardrail_respect - o.control_score.guardrail_respect:+d} |",
            f"| persona_faithfulness | {o.control_score.persona_faithfulness} | "
            f"{o.treatment_score.persona_faithfulness} | "
            f"{o.treatment_score.persona_faithfulness - o.control_score.persona_faithfulness:+d} |",
            f"| **total (40)** | **{o.control_score.total}** | "
            f"**{o.treatment_score.total}** | "
            f"**{o.treatment_score.total - o.control_score.total:+d}** |",
            "",
            f"**Control rationale:** {o.control_score.rationale}",
            "",
            f"**Treatment rationale:** {o.treatment_score.rationale}",
            "",
            "<details><summary>Control response</summary>",
            "",
            "```",
            o.control_output.strip(),
            "```",
            "</details>",
            "",
            "<details><summary>Treatment response</summary>",
            "",
            "```",
            o.treatment_output.strip(),
            "```",
            "</details>",
            "",
        ])
    return "\n".join(lines) + "\n"


def write_ab_report(report: ABReport, agent_dir: Path) -> Path:
    """Persist report.md + report.json under .tend/ab/<run-id>/."""
    stamp = report.started_at.strftime("%Y-%m-%dT%H%M%S")
    out_dir = agent_dir / ".tend" / "ab" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "report.md"
    json_path = out_dir / "report.json"
    md_path.write_text(render_report_markdown(report), encoding="utf-8")
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return md_path
