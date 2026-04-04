# AgentForge

> **Note:** The published package and CLI are called **AgentForge** (`agentforge`). The GitHub repository is named **AgentSkillFactory** for historical reasons — they are the same project.

Transform job descriptions into deployable AI agent blueprints via [PersonaNexus](https://github.com/PersonaNexus/personanexus).

AgentForge reads a job description (txt, md, pdf, docx), extracts skills and role metadata with an LLM, maps them to [PersonaNexus](https://github.com/PersonaNexus/personanexus) personality traits, and outputs a ready-to-use agent identity — including Claude Code skill folders you can drop straight into `.claude/skills/`.

### PersonaNexus Ecosystem

| Project | Role |
|---------|------|
| [**PersonaNexus**](https://github.com/PersonaNexus/personanexus) | Declarative identity spec — defines *who* an agent is (traits, guardrails, communication style) |
| **AgentForge** (this repo) | The factory — *generates* PersonaNexus identities from job descriptions and team requirements |
| [**Voice Packs**](https://github.com/PersonaNexus/voice-packs) | Weight-level personality — LoRA adapters that encode authorial voice into model weights ([adapters on HuggingFace](https://huggingface.co/jcrowan3/voice-pack-adapters)) |

Think of PersonaNexus as the schema, AgentForge as the factory, and Voice Packs as the voice.

## Install

```bash
pip install agentforge            # core CLI
pip install "agentforge[web]"     # adds REST API + web UI
```

Or from source:

```bash
git clone https://github.com/PersonaNexus/AgentSkillFactory.git
cd AgentSkillFactory
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
├── cli.py                  # Typer CLI
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
├── web/                    # FastAPI app, routes, templates
└── templates/              # Culture templates, prompts
```

## License

MIT — see [LICENSE](LICENSE).
