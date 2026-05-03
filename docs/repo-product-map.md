# PersonaNexus ecosystem repo/product map

This document keeps the public project names, GitHub repositories, Python package names, and responsibilities aligned across the PersonaNexus ecosystem.

## Canonical products

| Product | Public repository | Python package / CLI | Responsibility |
|---|---|---|---|
| **PersonaNexus** | `PersonaNexus/personanexus` | `personanexus` / `personanexus` | Declarative agent identity: YAML schema, persona compilation, validation, evaluation, Studio, and team definitions. |
| **AgentForge** | `PersonaNexus/agentforge` | `agentforge` / `agentforge` | Skill and agent factory + day-2+ lifecycle tooling: converts job descriptions, role descriptions, and operating context into PersonaNexus identities, OpenClaw/Claude skills, teams, QA reports, and handoff artifacts; keeps live agents healthy via Tend (persona), Drill (skills), Department (team synthesis), and Market (corpus observability). |
| **Voice Packs** | `PersonaNexus/voice-packs` | adapter artifacts | Weight-level voice/personality adapters that complement PersonaNexus identities and AgentForge-generated agents. |

## Naming policy

AgentForge is the product, package, and CLI name for this repository.

The GitHub repository was formerly named `AgentSkillFactory`; the canonical public repository is now `PersonaNexus/agentforge`. Public docs should therefore use this wording consistently:

> AgentForge (`agentforge`) is published from the `PersonaNexus/agentforge` repository, formerly `PersonaNexus/AgentSkillFactory`.

Avoid introducing additional names such as “Agent Skill Builder” as top-level product names. Use those as features or initiatives inside AgentForge.

## Product boundaries

### PersonaNexus owns

- Agent identity schema and validation.
- Persona inheritance, mixins, trait mapping, and guardrails.
- Compilation to prompts, SOUL.md-style files, OpenClaw personality configs, and other identity targets.
- Identity and team evaluation harnesses.
- PersonaNexus Studio and visual/personality editing surfaces.

### AgentForge owns

**Bootstrap factory:**

- Ingesting job descriptions, role descriptions, runbooks, meeting notes, and other operating context.
- Extracting skills, responsibilities, triggers, and operating heuristics.
- Generating PersonaNexus-compatible identities.
- Generating OpenClaw/Claude skill folders and `SKILL.md` files.
- Team/conductor generation and orchestration exports.
- Skill quality tooling: lint, audit, prompt-size, prompt-diff, cost, and scenario testing.

**Day-2+ lifecycle tooling** (see [`day2-products.md`](day2-products.md) for the full design):

- **Tend** — persona maintenance: snapshot SOUL.md, watch for drift, A/B test variants, version log.
- **Drill** — skill-folder maintenance: snapshot inventory, deterministic diagnostics (bloat, overlap, missing files, tool sprawl), watch for evolution, version log.
- **Department** — multi-agent team synthesis from a JD corpus: per-role identities, shared skill library, conductor agent, orchestration graph, README.
- **Market** — JD-corpus observability: top-skill trends, recency split, agent ↔ market gap analysis with coverage scoring.
- Future Skill Builder workflows: idea intake, spec packets, validation, and implementation handoff.

### Voice Packs owns

- Voice adapter packaging and distribution.
- Model-weight or adapter-level personality assets.
- Examples that show how adapter voice can complement PersonaNexus identity and AgentForge-generated skills.

## Integration flow

```text
PersonaNexus schema + examples
        ↓
AgentForge ingestion/extraction/generation
        ↓
PersonaNexus identity YAML + OpenClaw/Claude skill folders
        ↓
OpenClaw / Claude / LangGraph / other runtime targets
        ↓
Optional voice-pack adapters for model-level style
```

## Cross-linking requirements

Every public README should keep these links visible near the top:

- PersonaNexus: <https://github.com/PersonaNexus/personanexus>
- AgentForge: <https://github.com/PersonaNexus/agentforge>
- Voice Packs: <https://github.com/PersonaNexus/voice-packs>

AgentForge docs should describe PersonaNexus as the identity substrate. PersonaNexus docs should describe AgentForge as the factory that can generate PersonaNexus identities and operational skills from real-world role/context inputs.

## Repository rename option

Repository naming has been cleaned up: AgentForge now lives at `PersonaNexus/agentforge`. GitHub should redirect old `PersonaNexus/AgentSkillFactory` links, but new docs and tooling should use the canonical lowercase repo URL.
