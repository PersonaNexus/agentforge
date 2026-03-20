# AgentForge Enhancement Specification

**v2.0 — Build Roadmap for Claude Code**
*March 2026 · PersonaNexus Project*

-----

## Context & Purpose

AgentForge transforms job descriptions into deployable AI agent blueprints via PersonaNexus. This document specifies 8 prioritized enhancements to be implemented in Claude Code, organized by tier and build sequence.

### The Three-Layer Stack

```
AgentForge          →    PersonaNexus     →    OpenClaw
(Build pipeline)         (Identity layer)      (Runtime — Mac native)

JD/role → extract        YAML → compile        Agents run,
  → identity YAML          → SOUL.md             chat, cron,
  → skill folders          → openclaw.json       channels
  → gap analysis           → system prompt
```

These enhancements deepen the integration between all three layers and fix the core weakness in the current pipeline.

-----

## TIER 1 — Fix the Core Weakness

These two enhancements address the fundamental gap in AgentForge: it currently extracts what a role *does*, not how a skilled practitioner actually thinks and decides. Fixing this is the highest-leverage investment.

-----

### E1 — Methodology Extraction

> *Extract how practitioners think — not just what they're responsible for*

**Problem**
AgentForge reads a JD and extracts role responsibilities. It doesn't extract decision logic — when a skilled practitioner encounters situation X, they do Y not Z. This means forged skills have the right labels but don't perform differently.

**Solution**
Add a `--methodology` flag that prompts the LLM to generate trigger-to-technique mappings from the role description. Adds a `decision_patterns:` section to the identity YAML and generates if/then routing in the skill output.

```bash
agentforge forge atlas-role.txt --methodology
# → adds decision_patterns: section to identity YAML
# → generates if/then routing in skill output
# → maps: 'when market signal X appears → do Y, not Z'
```

**Impact:** Transforms forged skills from labeled personas into genuine behavioral differentiation. The single biggest quality improvement possible.

-----

### E2 — Usage Feedback Refinement Loop

> *Turn real deployment experience into skill improvements*

**Problem**
AgentForge is currently one-shot: JD in → skill out → done. There's no path from real usage back to skill improvement. Skills degrade or stay static while the agent's actual behavior evolves.

**Solution**
Add a `refine` command that takes a forged skill plus structured feedback (what worked, what didn't) and produces an improved version. Shows a diff of what changed. Outputs a versioned v2 skill.

```bash
agentforge refine agents/atlas/ \
  --feedback "too verbose in briefings, misses market signals"
# → diffs the skill, shows what changed
# → outputs atlas-v2/ with targeted improvements
# → preserves version history
```

**Impact:** Turns AgentForge from a build tool into a continuous improvement loop. Pairs with E1 — methodology extractions become refinable through real feedback.

-----

## TIER 2 — Strengthen OpenClaw Integration

These enhancements eliminate manual handoffs, add cron agent support, and wire in PersonaNexus team validation — making the full stack deployable in a single command.

-----

### E3 — Native OpenClaw Compiler

> *End-to-end pipeline: role description → OpenClaw-ready files in one command*

**Problem**
The current flow requires two manual steps: AgentForge → PersonaNexus → compile → OpenClaw. Each handoff is a friction point and an opportunity for config drift between the spec and the deployed agent.

**Solution**
Add `--target openclaw` to the forge command. Runs the full AgentForge + PersonaNexus pipeline internally and outputs all OpenClaw-ready files in a single directory, ready to drop into the workspace.

```bash
agentforge forge atlas-role.txt --target openclaw -d ./openclaw-agents/
# → atlas.SOUL.md
# → atlas.STYLE.md
# → atlas.personality.json
# → atlas-skills/   (Claude Code skill folder)
# All ready to drop into OpenClaw workspace
```

**Impact:** Eliminates the manual PersonaNexus handoff. Makes the build loop fast enough to iterate same-day. Critical for the 5-agent rebuild.

-----

### E4 — Cron Agent Template

> *First-class support for scheduled/autonomous agents*

**Problem**
Cron agents have fundamentally different requirements than interactive ones — fresh context per run, delivery-formatted output, no session state bleed, failure handling. AgentForge has no concept of this distinction and generates the same scaffolding for both.

**Solution**
Add `--mode cron` flag that generates cron-appropriate scaffolding: context isolation guardrails, delivery-formatted output templates, schedule config block, and failure handling patterns.

```bash
agentforge forge atlas-role.txt --mode cron --schedule "0 8 * * *"
# → adds cron_config: block to identity YAML
# → generates delivery-formatted output templates
# → adds context isolation guardrails
# → generates failure/retry handling scaffold
```

**Impact:** Required before deploying Atlas as a daily intelligence brief. Cron agents without this scaffolding accumulate context and degrade over time.

-----

### E5 — Team Relationship Validation

> *Catch overlaps and routing conflicts at build time, not runtime*

**Problem**
`agentforge team` generates `orchestration.yaml` but doesn't validate it against PersonaNexus's relationship schema. Trait overlaps, missing conductor deference, and conflicting guardrails aren't caught until agents are live — exactly the Atlas/Annie/Bob duplication problem.

**Solution**
Wire `agentforge team --validate` to run `personanexus validate-team` internally. Surface trait overlap percentages, missing relationship declarations, and routing gaps before deployment.

```bash
agentforge team team-roles.txt --validate
# → runs personanexus validate-team internally
# ⚠ Atlas + Annie: 73% trait overlap — consider merging
# ⚠ No agent has defers_to Orchestrator — conductor may be ignored
# ✓ Guardrail coverage: all agents have no_fabrication hard guardrail
# → outputs validated orchestration.yaml on pass
```

**Impact:** Directly solves the duplication problem that caused the original messy deployment. Validates the 5-agent team before going live.

-----

## TIER 3 — Quality-of-Life Improvements

These enhancements compound over time. Not blockers for the initial rebuild, but each adds meaningful leverage as the agent team matures.

-----

### E6 — Supplement Quality Scoring

> *Know what you're feeding in before it contaminates the skill*

**Problem**
The `--supplement` flag accepts any input and treats all sources equally. Raw conversation history, mixed-quality notes, or off-topic content gets ingested with the same weight as clean runbooks. There's no way to know if you're encoding signal or noise.

**Solution**
Add preprocessing that scores each supplement source on signal density, role relevance, and recency before ingestion. Surfaces a quality report and asks for confirmation when score is below threshold.

```bash
agentforge forge atlas-role.txt \
  --supplement convos.md \
  --supplement runbook.md
# Supplement quality: convos.md    34% signal (low — consider filtering)
# Supplement quality: runbook.md   87% signal (high)
# Proceed with low-quality source? [y/n]
```

**Impact:** Solves the hesitation about feeding 2 months of mixed conversation history. Safe selective ingestion of real usage patterns.

-----

### E7 — Skill Drift Detection

> *Know when an agent has diverged from its spec*

**Problem**
After deployment, agents evolve through manual SOUL.md edits, channel configs, and OpenClaw updates. The forged spec and the running agent slowly diverge with no visibility into what's changed or whether it matters.

**Solution**
Add a `diff` command that compares a running agent's current files against its original forged spec. Surfaces trait drift, manual guardrail additions, and spec/runtime mismatches. Recommends re-forge or spec sync.

```bash
agentforge diff agents/atlas/ --current ~/.openclaw/agents/atlas/
# Trait drift:    rigor 0.85 → 0.72  (significant)
# New guardrail:  no_stock_picks (added manually, not in spec)
# Missing tool:   web_search (in spec, not in runtime)
# Recommend: re-forge from updated spec or sync spec to runtime
```

**Impact:** Long-term spec integrity. Especially valuable as the agent team grows and manual edits accumulate across 5+ agents.

-----

### E8 — Interview Mode

> *Better input = better output — especially for agents without a real JD*

**Problem**
The quality of the forge output is entirely dependent on the quality of the role description input. For personal agents like Scout or Quill there's no JD to pull from — the user has to write the role description cold, with no guidance on what makes a good one.

**Solution**
Add an `agentforge interview` command that asks structured questions to build a precise role description interactively before forging. Captures purpose, common tasks, output format preferences, and hard boundaries.

```bash
agentforge interview
# What is this agent's primary job in one sentence?
# > Scout is my test agent for experimenting with new tools
# What are the 3 most common tasks it will handle?
# > Testing new prompts, validating skill configs, capability experiments
# What should it never do?
# > Never touch production agent configs
# → Generates role description → forks into forge pipeline
```

**Impact:** Natural input method for personal agents without a JD. Especially useful for Quill (creative writing) and Scout (test sandbox).

-----

## Build Priority Matrix

Recommended sequence for Claude Code implementation. E3 and E4 are blockers for the 5-agent rebuild. E1 is the highest-leverage enhancement but also the most complex — build it once E2 is in place so methodology extractions can be refinable through feedback.

|Enhancement                |Tier|Effort|Build Order|Unlocks                               |
|---------------------------|----|------|-----------|--------------------------------------|
|E3 Native OpenClaw Compiler|2   |Medium|1st        |Eliminates manual PersonaNexus handoff|
|E4 Cron Agent Template     |2   |Low   |2nd        |Atlas daily brief deployment          |
|E5 Team Validation         |2   |Medium|3rd        |Catches overlap before go-live        |
|E2 Refinement Loop         |1   |Medium|4th        |Continuous improvement post-deploy    |
|E1 Methodology Extraction  |1   |High  |5th        |Core weakness fix — biggest leverage  |
|E6 Supplement Scoring      |3   |Low   |6th        |Safe history ingestion                |
|E7 Skill Drift Detection   |3   |Medium|7th        |Long-term spec integrity              |
|E8 Interview Mode          |3   |Low   |8th        |Better input = better output          |

-----

## MCP Integration Note

AgentForge already ships an MCP server. Once E3 is built, wire the `agentforge_forge` tool into Forge and Scout agent configs in OpenClaw. This enables agents to call AgentForge as a tool — Scout can test new role definitions, Forge can spin up agent blueprints on demand.

```json
// .mcp.json — add to Forge and Scout agent configs
{
  "mcpServers": {
    "agentforge": {
      "command": "python",
      "args": ["-m", "agentforge.mcp_server"]
    }
  }
}
```

This makes the system self-improving: agents that help build better agents. Scout tests new role definitions before they go into production. Forge generates agent blueprints on demand without leaving the OpenClaw interface.

-----

*AgentForge Enhancement Spec · PersonaNexus Project · March 2026*
