# AgentForge

> **Repo/Product map:** AgentForge is the product, Python package, and CLI (`agentforge`). The public GitHub repository is [`PersonaNexus/agentforge`](https://github.com/PersonaNexus/agentforge). It was formerly named `AgentSkillFactory`; GitHub redirects old links. See [docs/repo-product-map.md](docs/repo-product-map.md) for the ecosystem map and naming policy.

Transform job descriptions, role descriptions, and operating context into deployable AI agent blueprints via [PersonaNexus](https://github.com/PersonaNexus/personanexus) — and keep them healthy after they ship.

AgentForge reads a job description (txt, md, pdf, docx), extracts skills and role metadata with an LLM, maps them to [PersonaNexus](https://github.com/PersonaNexus/personanexus) personality traits, and outputs a ready-to-use agent identity — including Claude Code skill folders you can drop straight into `.claude/skills/`.

Beyond the one-shot factory, AgentForge ships a **day-2+ tooling line** for the lifecycle that starts after the agent is live: persona drift detection, skill-folder maintenance, multi-agent team synthesis, and JD-corpus observability. See [Day-2+ tooling](#day-2-tooling) below or the [full design doc](docs/day2-products.md).

### PersonaNexus Ecosystem

| Project | Role |
|---------|------|
| [**PersonaNexus**](https://github.com/PersonaNexus/personanexus) | Declarative identity spec — defines *who* an agent is: schema, traits, guardrails, communication style, teams, and evaluation |
| **AgentForge** (this repo) | The factory — *builds operational agents and skills* from job descriptions, role requirements, and team context |
| [**Voice Packs**](https://github.com/PersonaNexus/voice-packs) | Weight-level personality — LoRA adapters that encode authorial voice into model weights ([adapters on HuggingFace](https://huggingface.co/jcrowan3/voice-pack-adapters)) |

Think of PersonaNexus as the schema, AgentForge as the factory, and Voice Packs as the voice.

## Install

```bash
pip install agentforge            # core CLI
pip install "agentforge[web]"     # adds REST API + web UI
```

Or from source:

```bash
git clone https://github.com/PersonaNexus/agentforge.git
cd agentforge
pip install -e ".[web]"
```

Set an API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# or
export OPENAI_API_KEY=sk-...
```

## Quick start

```bash
# Interactive wizard — guided experience for all commands
agentforge wizard

# Extract skills from a job description
agentforge extract job_posting.txt

# Full pipeline — identity YAML + skill folder + gap analysis
agentforge forge job_posting.txt

# Quick mode (skip culture/mapping/gap analysis)
agentforge forge job_posting.txt --quick

# Deep analysis with per-skill scoring
agentforge forge job_posting.txt --deep

# Batch-process a directory of JDs
agentforge batch ./job_descriptions/ -d ./agents --parallel 4

# Forge a multi-agent team with conductor
agentforge team job_posting.txt -d ./team-output

# Test a forged skill against generated scenarios
agentforge test job_posting.txt
```

## Python API

```python
from agentforge import LLMClient, SkillExtractor, ForgePipeline, JobDescription

# Extract skills
client = LLMClient(model="claude-sonnet-4-20250514")
extractor = SkillExtractor(client=client)
jd = JobDescription.from_file("job_posting.txt")
result = extractor.extract(jd)

print(result.role.title)
for skill in result.skills:
    print(f"  {skill.name} ({skill.category.value})")

# Full pipeline
pipeline = ForgePipeline.default()
context = pipeline.run({"input_path": "job_posting.txt", "llm_client": client})
print(context["identity_yaml"])
```

## REST API

```bash
agentforge serve                     # http://localhost:8000
agentforge serve --host 0.0.0.0      # expose to network
```

Key endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/extract` | Synchronous skill extraction |
| `POST` | `/api/forge` | Async forge job (returns `job_id`) |
| `GET` | `/api/forge/{job_id}/stream` | SSE progress stream |
| `GET` | `/api/forge/{job_id}/result` | Final result |
| `POST` | `/api/batch` | Batch processing |
| `GET` | `/health` | Health check |
| `GET` | `/api/docs` | OpenAPI / Swagger UI |

## Docker

```bash
docker compose up                    # builds and starts on :8000
```

Or build manually:

```bash
docker build -t agentforge .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY agentforge
```

## MCP Server (agent-to-agent)

AgentForge ships an [MCP](https://modelcontextprotocol.io/) server so other agents (Claude Code, etc.) can call it as a tool.

### Add to Claude Code

In your project's `.mcp.json` or `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "agentforge": {
      "command": "python",
      "args": ["-m", "agentforge.mcp_server"]
    }
  }
}
```

### Available tools

| Tool | Description |
|------|-------------|
| `agentforge_extract` | Extract skills/role/traits from job description text |
| `agentforge_forge` | Full pipeline — returns identity YAML, skill folder, gap analysis |
| `agentforge_forge_file` | Same as forge but reads from a file path on disk |

### Run standalone

```bash
python -m agentforge.mcp_server      # stdio transport
```

## Multi-agent teams

Forge a complete agent team from a single JD — each teammate gets a scoped skill, and a conductor agent handles routing and handoffs:

```bash
agentforge team job_posting.txt -d ./team-output
```

Outputs: conductor skill, per-teammate skills, identity YAMLs, and `orchestration.yaml`.

### LangGraph export

Export the team as a runnable LangGraph `StateGraph`:

```bash
agentforge team job_posting.txt -d ./team-output --format langgraph

# Or get both Claude Code skills and LangGraph module
agentforge team job_posting.txt --format both
```

Produces `agent_graph.py` — a self-contained Python module with typed state, agent nodes, conductor routing, and a compiled graph. Requires `pip install "agentforge[langgraph]"`.

## Skill testing

Validate a forged skill by running it against auto-generated test scenarios:

```bash
agentforge test job_posting.txt
```

Generates scenarios from trigger mappings, responsibilities, and edge cases. Evaluates responses with LLM-as-judge scoring and produces a pass/fail report.

## Day-2+ tooling

The one-shot `forge` flow stops after the agent ships. Day-2+ commands keep agents and skill folders healthy over time, on a single operating model: **observe → diagnose → propose → test → version**. All four products are deterministic by default; LLM is reserved for experimentation and proposal surfaces.

### `tend` — persona maintenance

Read-only on `SOUL.md`. Snapshots persona artifacts, diffs them, and runs A/B tests against scenario sets with LLM-as-judge.

```bash
agentforge tend ingest <agent-dir>             # snapshot persona artifacts
agentforge tend watch <agent-dir>              # diff snapshots, surface drift + promotion candidates
agentforge tend ab <agent-dir> -v variant.md   # A/B test a SOUL variant on scenarios
agentforge tend version <agent-dir>            # SOUL evolution log (versions.jsonl)
```

All output goes to `<agent>/.tend/`. Snapshots are deterministic — re-ingesting an unchanged agent produces an identical-modulo-timestamp snapshot.

### `drill` — skill-folder maintenance

Counterpart to Tend on the *capability* surface. Auto-detects single-skill folders vs `.claude/skills/`-shaped parents.

```bash
agentforge drill ingest <skill-dir>     # snapshot a skill directory
agentforge drill scan <skill-dir>       # deterministic diagnostics
agentforge drill watch <skill-dir>      # diff snapshots
agentforge drill version <skill-dir>    # inventory evolution log
```

`drill scan` flags four classes of issue: **missing_file** (folder lacks SKILL.md), **broken_reference** (body cites a path that's not on disk), **bloat** (body word count above threshold), **overlap** (Jaccard similarity between two skill descriptions above threshold), **tool_sprawl** (`allowed-tools` count above threshold or stale entries not mentioned in body). Thresholds are configurable per-run.

### `department` — multi-agent team synthesis

Synthesize a coordinated team from a folder of JDs (one per role, with YAML frontmatter).

```bash
agentforge department scan <jd-folder>          # list the corpus, no LLM
agentforge department analyze <jd-folder>       # extract + cluster skills, write report
agentforge department synthesize <jd-folder> -o <out>            # full team
agentforge department synthesize <jd-folder> -o <out> --use-llm  # + LLM handoff judge + team brief
```

`synthesize` produces per-role identity + decomposed SKILL.md, an `_shared/skills/` library for clusters spanning ≥2 roles, an `_conductor/` agent with a baked-in routing table, an `orchestration.yaml` handoff graph, and a README. With `--use-llm` the handoff edges are LLM-judged and the README gains a written team brief.

### `market` — JD-corpus observability

Aggregate statistics over a JD corpus + agent ↔ market gap analysis.

```bash
agentforge market trends <jd-folder>                                   # top skills, breakdowns, recency split
agentforge market gap <jd-folder> --skill-dir <agent-skills>           # coverage score + market_only / agent_only / shared
```

`trends` surfaces top skills by frequency and role-share, breakdowns by category / domain / seniority, and a rising-vs-falling skills split when JDs carry `date:` frontmatter. `gap` compares an agent's drill SkillInventory to the corpus's clustered SkillLandscape and emits a coverage score over load-bearing market skills.

### Shared substrate

All four products ride on `agentforge.day2/` — a thin shared package for git-state probes, JSONL evolution logs, frontmatter parsing, finding-list markdown, CLI directory validation, and size-capped + symlink-safe file IO. Designed so future day-2+ products reuse it instead of mirroring helpers.

## Quality & safety tools

Analyze, lint, and validate generated skills:

```bash
# Check prompt size and detect bloat
agentforge prompt-size output/SKILL.md

# Lint for structural/semantic issues (missing sections, trait contradictions)
agentforge lint output/SKILL.md

# Audit safety guardrails (with auto-fix for missing ones)
agentforge audit output/SKILL.md --domain "data engineering"
agentforge audit output/SKILL.md --fix --output fixed_SKILL.md

# Estimate monthly token costs
agentforge cost output/SKILL.md --daily-calls 100

# Compare two versions of a skill
agentforge prompt-diff v1/SKILL.md v2/SKILL.md
```

All quality commands support `--format json` for CI integration and return exit code 1 on failure.

## Wiki-memory (structured knowledge layer)

Adds a durable, cross-linked knowledge layer alongside each agent's flat episodic MEMORY. Two-tier memory: episodic (MEMORY.md) + structured wiki pages.

```bash
# Initialize a wiki at a directory
python -m agentforge.wiki_memory.cli init --root ~/wiki

# Add a page directly
python -m agentforge.wiki_memory.cli add \
  --title "AI Gateway" --type entity --kind project \
  --alias gateway --fact "Runs on port 8900" --source session:2026-04-04

# Capture a candidate fact (goes to review queue)
python -m agentforge.wiki_memory.cli candidate \
  --subject "AI Gateway" --claim "Uses Gemma 4 E4B" \
  --type entity --kind project --source session:2026-04-04

# Review pending candidates
python -m agentforge.wiki_memory.cli pending
python -m agentforge.wiki_memory.cli promote --accept-all
```

**Key features:**
- **Capture → candidate → review → promote** funnel (no silent writes)
- **3-tier entity resolver** (slug → alias → title substring)
- **Provenance on every fact** (source, confidence, date)
- **Exact-dedupe** on claim text, confidence roll-up
- Filesystem-backed markdown with YAML frontmatter
- Audit trail of all review decisions

See `docs/wiki-memory-design.md` for the full design.

## Non-JD input sources

Enrich skills with context beyond the job description:

```bash
# Supplement a forge with Slack history, git logs, runbooks, or meeting notes
agentforge forge job.txt --supplement slack_export.zip --supplement runbook.md
```

Supported sources: Slack JSON exports, git log output, runbook/SOP markdown, meeting notes. Each parser extracts decision patterns, recurring workflows, and domain context that gets merged into the methodology layer.

## Project structure

```
src/agentforge/
├── cli.py                  # Typer CLI (forge + day-2+ sub-apps)
├── cli_wizard.py           # Interactive wizard
├── mcp_server.py           # MCP tool server
├── extraction/             # LLM-powered skill extraction
├── generation/             # Identity & skill file generation
├── ingestion/              # PDF, DOCX, text + Slack, git, runbook, meeting notes
├── llm/                    # LLM client (Anthropic + OpenAI)
├── mapping/                # Skill-to-trait mapping, culture
├── models/                 # Pydantic data models
├── pipeline/               # Composable forge pipeline
├── analysis/               # Gap analysis, skill review, guardrails, linting, cost, prompt size
├── composition/            # Multi-agent team forging, conductor generation
├── testing/                # Skill validation, scenario generation, evaluation
├── corpus/                 # JD-corpus loader (shared by department + market)
├── tend/                   # Day-2+ persona maintenance
├── drill/                  # Day-2+ skill-folder maintenance
├── department/             # Day-2+ multi-agent team synthesis from JD corpus
├── market/                 # Day-2+ JD-corpus observability + agent gap
├── day2/                   # Shared substrate for tend/drill/department/market
├── web/                    # FastAPI app, routes, templates
└── templates/              # Culture templates, prompts
```

## License

MIT — see [LICENSE](LICENSE).
