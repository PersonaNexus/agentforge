# Layered Prompt Architecture

**Status:** MVP in progress (branch `forge/layered-prompt-composer`)

## Problem

Today, PersonaNexus `SystemPromptCompiler` renders an `AgentIdentity` into a system prompt as one merged blob. It has section priorities and token budgets, but treats all content as coming from a single source (the identity YAML). In practice, a running agent's prompt is composed from many sources:

1. **Persona** — who the agent is (PersonaNexus identity YAML → SOUL.md)
2. **Operating rules** — how the agent should behave (guardrails, CLAUDE.md instructions)
3. **Memory** — episodic preferences, feedback, user profile (MEMORY.md)
4. **Wiki knowledge** — structured facts about entities/concepts (wiki-memory pages)
5. **Skills** — capability declarations and workflows (SKILL.md files)
6. **Task context** — current project state, task board, delegation instructions

These sources have different lifetimes, update frequencies, and precedence rules. Treating them as one blob leads to:
- No clear precedence when sources conflict (does a skill override a guardrail?)
- No per-layer token budgeting (memory bloats and personality gets truncated)
- No clean retrieval boundaries (everything is loaded upfront vs on-demand)

## Design

### Layer types

Each prompt source becomes a typed **PromptLayer** with metadata:

| Layer type | Priority | Budget | Lifetime | Source |
|---|---|---|---|---|
| `persona` | 1 (highest) | 30% | static | PersonaNexus identity YAML |
| `rules` | 2 | 15% | static | guardrails, CLAUDE.md |
| `memory` | 3 | 15% | session | MEMORY.md, feedback files |
| `wiki` | 4 | 15% | on-demand | wiki-memory pages matched by context |
| `skills` | 5 | 15% | per-task | SKILL.md for active skills |
| `task_context` | 6 | 10% | ephemeral | task board, delegation, project state |

Priority determines conflict resolution: persona > rules > memory > wiki > skills > task_context.

Budget is a percentage of the total token budget. Layers that underuse their allocation donate tokens downward.

### Assembly pipeline

```
PersonaResolver → RulesResolver → MemoryResolver → WikiResolver → SkillsResolver → TaskResolver
       ↓               ↓               ↓               ↓              ↓               ↓
   PromptLayer     PromptLayer     PromptLayer     PromptLayer    PromptLayer     PromptLayer
       ↓               ↓               ↓               ↓              ↓               ↓
                              PromptComposer.assemble()
                                       ↓
                              assembled system prompt
                              (with token budget enforcement)
```

Each **Resolver** is responsible for:
1. Fetching content from its source (file, API, search)
2. Formatting it as a `PromptLayer`
3. Estimating token cost

The **PromptComposer** receives all layers and:
1. Sorts by priority
2. Allocates token budgets (proportional, with overflow donation)
3. Truncates layers that exceed their allocation (lowest-priority content first)
4. Renders the final prompt with clear section markers

### Precedence rules

When content conflicts across layers:
- **Explicit contradiction:** higher-priority layer wins
- **Additive content:** both layers included (e.g., memory adds context to persona)
- **Budget overflow:** lower-priority layers get truncated first

### Token budgeting

```python
total_budget = 8000  # configurable
layer_budgets = {
    "persona": total_budget * 0.30,    # 2400
    "rules": total_budget * 0.15,      # 1200
    "memory": total_budget * 0.15,     # 1200
    "wiki": total_budget * 0.15,       # 1200
    "skills": total_budget * 0.15,     # 1200
    "task_context": total_budget * 0.10,  # 800
}
# Unused budget rolls down to next layer
```

## Module boundaries

```
src/agentforge/prompt_composer/
├── __init__.py          — public API: PromptComposer, PromptLayer
├── types.py             — PromptLayer, LayerType, LayerConfig dataclasses
├── composer.py           — PromptComposer: assemble, budget, render
├── resolvers/
│   ├── __init__.py
│   ├── persona.py       — loads PersonaNexus identity → PromptLayer
│   ├── rules.py         — loads guardrails/CLAUDE.md → PromptLayer
│   ├── memory.py        — loads MEMORY.md + feedback → PromptLayer
│   ├── wiki.py          — searches wiki-memory for context → PromptLayer
│   ├── skills.py        — loads active SKILL.md files → PromptLayer
│   └── task_context.py  — loads task board/delegation → PromptLayer
└── budget.py            — token estimation + budget allocation
```

## MVP scope (this PR)

- [x] `types.py` — `PromptLayer`, `LayerType`, `LayerConfig`, `AssembledPrompt`
- [x] `composer.py` — `PromptComposer.assemble()` with priority ordering, budget allocation, overflow donation, section markers
- [x] `budget.py` — character-based token estimation (word/4 heuristic), budget enforcement
- [x] `resolvers/persona.py` — loads SOUL.md or PersonaNexus YAML
- [x] `resolvers/memory.py` — loads MEMORY.md
- [x] `resolvers/rules.py` — loads CLAUDE.md / guardrails
- [x] Tests for composer, budgeting, layer ordering

**Deferred:**
- WikiResolver (depends on wiki-memory module — separate PR)
- SkillsResolver (loads from disk, straightforward follow-up)
- TaskResolver (reads task board, ephemeral)
- PersonaNexus compiler integration (refactor existing `SystemPromptCompiler` to emit layers)
- LLM-based conflict detection across layers

## Risks

| Risk | Mitigation |
|---|---|
| Token estimation drift (chars vs real tokens) | Ship with char/4 heuristic; swap to tiktoken later |
| Over-engineering prompt assembly | MVP is <400 LOC; resolvers are optional/pluggable |
| Breaking PersonaNexus compiler | Composer is additive — existing compiler untouched |
