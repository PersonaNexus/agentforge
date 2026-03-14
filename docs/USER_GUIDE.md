# AgentSkillFactory — User Guide

> Transform job descriptions into production-ready AI agent skills, tool configs, and team blueprints.

---

## Quick Start

### Install & Run

```bash
# Install
pip install agentforge

# Interactive setup (sets API key, default model)
agentforge init

# Launch web UI
agentforge serve --open
```

### Fastest Path to a Skill

```bash
# CLI: one command, one file
agentforge forge job_description.txt --skill-folder

# Output: .claude/skills/<role>/SKILL.md — drop it into your project
```

---

## Core Concepts

**AgentSkillFactory** takes a job description and produces:

| Output | What it is | Where it goes |
|--------|-----------|---------------|
| **SKILL.md** | Claude Code skill with persona + methodology | `.claude/skills/<name>/SKILL.md` |
| **Identity YAML** | PersonaNexus agent identity (traits, competencies, workflows) | Importable back into pipeline |
| **Tool Profile** | Tool inventory + MCP config + usage workflows | `.mcp.json` |
| **ClawHub Skill** | Compact, action-oriented skill for OpenClaw registry | ClawHub-compatible format |

### The Two-Layer Model

1. **Thin Persona Layer** — *Who* the agent is (identity, traits, tone)
2. **Thick Methodology Layer** — *How* the agent works (heuristics, decision rules, output templates, quality criteria)

The methodology layer is what makes skills actually useful. Without it, you get generic instructions. With it, you get expert decision-making encoded into the skill.

---

## Web UI

Launch with `agentforge serve` — six tabs:

### Extract

Upload a JD file → get structured analysis without generating a skill.

- **Skills table**: sortable by name, category, proficiency, importance
- **Trait bars**: suggested PersonaNexus personality traits (0–1 scale)
- **Automation assessment**: what % of the role an AI can handle
- **Human elements**: skills and responsibilities that need a human
- **Agent value estimate**: ROI calculation if salary range is provided

Good for: exploring a JD before committing to a full forge.

### Forge

The main workflow — a 4-step wizard:

**Step 1: Upload** — drag-and-drop a `.txt`, `.md`, `.pdf`, or `.docx` file. Or import an existing identity YAML to refine it.

**Step 2: Configure**
- **Pipeline mode**: Default (full analysis), Quick (skip culture + gap analysis), Deep (per-skill scoring)
- **Model**: Claude Sonnet 4 (best quality), Claude Haiku 4.5 (fastest), GPT-4o
- **Output format**: Claude Code, ClawHub, or both
- **Personality sliders**: override auto-detected traits (leave untouched to use LLM suggestions)
- **Anonymize**: replace company names with generic equivalents
- **Enhance quality**: paste real-world examples and frameworks you use — this is the single biggest quality lever

**Step 3: Forge** — watch real-time progress as each pipeline stage completes

**Step 4: Download** — get SKILL.md, ClawHub skill, ZIP folder, or view inline previews. Also shows tool profile summary, skill gap analysis, and agent team composition.

### Batch

Process multiple JDs at once:
- Upload several files → set parallel workers (1–8)
- Same config options as forge
- Downloads a ZIP with all outputs

### Culture

Shape agent personality through organizational culture profiles:

- **Built-in templates**: Innovative Startup, Enterprise Collaborative, Customer Centric
- **Parse custom**: upload a YAML or markdown culture doc → get a structured CultureProfile
- **Export mixin**: convert a CultureProfile into a PersonaNexus mixin YAML

Culture profiles apply **trait deltas** — e.g., a startup culture might add `+0.15 assertiveness`, `+0.2 creativity`, `-0.1 rigor`.

**Example culture YAML**:
```yaml
name: "Fast-Moving Startup"
description: "Ship fast, learn fast, iterate"
values:
  - name: "Bias for Action"
    description: "Default to doing, not planning"
    behavioral_indicators:
      - "Proposes solutions, not just problems"
      - "Ships MVPs within days"
    trait_deltas:
      assertiveness: 0.15
      creativity: 0.2
      rigor: -0.1
communication_tone: "direct, informal, energetic"
decision_style: "fast with strong ownership"
```

### Agent Tools

View and configure which tools your agent needs:

- **Tool inventory**: cards showing each tool with category, transport type, MCP server, and priority
- **Usage patterns**: step-by-step workflow visualizations showing how tools chain together
- **MCP config**: auto-generated `.mcp.json` ready to copy or download
- **Filter by category**: file I/O, code execution, data query, web search, etc.

Select any completed forge job → view or (re)generate its tool profile.

### Settings

- API key (Anthropic or OpenAI — auto-detected)
- Default model
- Output directory
- Batch parallelism

---

## CLI Reference

```bash
# Extract skills only (no skill file generation)
agentforge extract job.txt --format yaml --output skills.yaml

# Full forge with culture
agentforge forge job.txt --culture startup.yaml --skill-folder

# Quick forge (faster, less analysis)
agentforge forge job.txt --quick

# Deep forge (per-skill scoring)
agentforge forge job.txt --deep

# Batch process a directory
agentforge batch ./jds/ --parallel 4 --culture enterprise.yaml

# Import existing identity and re-export
agentforge identity import agent.yaml --format both --refine

# Culture tools
agentforge culture parse culture.md --output profile.yaml
agentforge culture to-mixin profile.yaml
agentforge culture list
```

---

## Pipeline Modes

| Mode | Stages | Best for |
|------|--------|----------|
| **Default** | Ingest → Anonymize → Extract → Methodology → Map → Culture → Generate → ToolMap → Analyze → Team | Production use — full analysis |
| **Quick** | Ingest → Anonymize → Extract → Methodology → Generate → Team | Rapid prototyping — ~50% faster |
| **Deep** | Ingest → Anonymize → Extract → Methodology → Map → Culture → Generate → ToolMap → DeepAnalyze → Team | Per-skill coverage scores and priority ranking |

---

## Enhancing Quality

The single biggest improvement to output quality comes from the **Enhance Skill Quality** section in the forge wizard:

### Real-World Examples

Describe how you *actually* do the work:

> "When I evaluate a new codebase, I start by checking open issues sorted by reactions, then cross-reference with release notes to see what's already addressed. I categorize remaining gaps by severity and effort before recommending changes."

### Frameworks & Methodologies

List the specific tools, templates, and processes:

> "We use Architecture Decision Records (ADRs) for design choices, RICE scoring for prioritization, and a custom code review checklist that checks for security, performance, maintainability, and test coverage."

**Without these**: the pipeline infers methodology from the JD alone — producing generic workflows.
**With these**: you get expert decision-making rules, concrete output templates, and domain-specific heuristics.

---

## MCP Server

AgentSkillFactory itself can run as an MCP server, letting other Claude Code agents forge skills programmatically:

```json
// .mcp.json or ~/.claude/mcp.json
{
  "mcpServers": {
    "agentforge": {
      "command": "python",
      "args": ["-m", "agentforge.mcp_server"]
    }
  }
}
```

Exposes three tools:
- `agentforge_extract` — extract skills from JD text
- `agentforge_forge` — full pipeline from JD text
- `agentforge_forge_file` — forge from a file path

---

## Python API

```python
from agentforge.pipeline.forge_pipeline import ForgePipeline

# Build and run the pipeline
pipeline = ForgePipeline.default()
context = pipeline.run({
    "jd_path": "job_description.txt",
    "model": "claude-sonnet-4-20250514",
})

# Get the blueprint
blueprint = pipeline.to_blueprint(context)

# Access results
print(blueprint.extraction.role.title)
print(blueprint.extraction.skills)
print(blueprint.skill_folder.skill_md)

# Access tool profile
tool_profile = context["tool_profile"]
print(tool_profile.tools)
print(tool_profile.generate_mcp_json())
```

---

## Output Structure

After forging, your `.claude/skills/` directory looks like:

```
.claude/skills/
  senior-data-engineer/
    SKILL.md          # Main skill file (YAML frontmatter + methodology)
    identity.yaml     # PersonaNexus identity (importable)
```

The **SKILL.md** contains:
- YAML frontmatter: name, description, allowed-tools
- Identity section: role, purpose, traits
- Methodology section: heuristics, trigger→technique mappings, output templates, quality criteria

---

## Tips

- **Start with Extract** to preview what the LLM will pull from a JD before running a full forge
- **Use culture profiles** when building multiple agents for the same org — ensures consistent tone
- **Anonymize** before sharing skills externally to strip company names
- **Import → Refine** to iterate on an existing identity without re-extracting
- **Deep mode** is worth the extra time when you need to know exactly which skills have gaps
- **Provide examples** in the enhance section — even 2-3 sentences dramatically improve methodology quality
- **Check the Agent Tools tab** after forging to get a ready-to-use `.mcp.json` for your agent's tool setup
