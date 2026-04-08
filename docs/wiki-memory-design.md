# Wiki-Memory Layer — Design & MVP Plan

**Status:** MVP in progress (first slice shipping on branch `forge/wiki-memory-mvp`)

## Why

Today, agents built with AgentForge + PersonaNexus rely on a single flat memory surface (`MEMORY.md` + a `memory/` directory of episodic notes). That works for preferences and short-lived task state, but it collapses under two pressures:

1. **Entity knowledge is fragmented.** Facts about the same person, project, or system accumulate across many session notes with no canonical home.
2. **Cross-agent knowledge doesn't compound.** When Nova, Forge, and Atlas each learn something about the same project, the lesson stays siloed in whichever agent was in the room.

A wiki-memory layer gives agents a *structured, linked, durable* knowledge store — complementary to the existing episodic memory, not a replacement.

## Three-layer memory model

| Layer | Purpose | Format | Retrieval priority |
|---|---|---|---|
| **1. MEMORY (episodic/preference)** | user feedback, prefs, in-flight task state, corrections | flat `.md` files w/ frontmatter | first — always loaded |
| **2. Wiki (durable structured)** | canonical facts about entities + concepts, with links | `.md` pages w/ YAML frontmatter, `[[wikilinks]]` | second — searched on demand / by entity match |
| **3. Broad docs / RAG** | code, long docs, historical transcripts | embeddings or grep | third — fallback |

Layer 1 tells you **how to work with Jim**. Layer 2 tells you **what Project X is and how it connects to Person Y**. Layer 3 is the long tail.

## Page schema

Two top-level page types:

- **entity** — a real-world thing with identity: person, project, system, organization, place, paper, experiment, lab
- **concept** — a topic, idea, pattern, or domain: "agent orchestration", "Catholic education", "prompt caching"

Entities have a `kind` sub-type (`person | project | system | org | place | other | paper | experiment | lab`). Concepts don't.

### Research knowledge space

Research findings map naturally to these page types:

| Research type | Wiki mapping | Example |
|---|---|---|
| **Papers** | entity/paper | "Attention Is All You Need" |
| **Themes** | concept (tag: research) | "prompt-caching", "agent-orchestration" |
| **People** | entity/person | researcher profiles |
| **Labs** | entity/lab | "Anthropic", "DeepMind" |
| **Projects** | entity/project | open-source tools, frameworks |
| **Experiments** | entity/experiment | internal benchmarks, A/B tests |
| **Internal Implications** | concept (tag: implications) | "what X means for our stack" |

Each research page supports these additional sections (rendered after ## Summary, before ## Facts):

- **## Why it matters** — significance and relevance
- **## Citations** — academic/industry citations (bulleted)
- **## URLs** — source links (bulleted)
- **## Open questions** — unresolved gaps (bulleted)
- **## Downstream actions** — what to do next (bulleted)
- **## Internal commentary** — our interpretation and notes

Use `agentforge wiki research-import` to create research pages from the CLI with all fields populated in one command.

### Frontmatter (YAML)

```yaml
---
id: proj-ai-gateway         # stable slug, primary key
title: AI Gateway           # human-readable
type: entity                # entity | concept
kind: project               # only for entity
aliases: [gateway, ai-gateway]
tags: [infrastructure, routing]
created: 2026-04-04
updated: 2026-04-04
contributors: [forge, nova]
confidence: high            # high | medium | low
sources: [session:2026-04-04-nightly]
related: [proj-openclaw, concept-agent-orchestration]
---
```

### Body

Free-form markdown. Conventions:
- First `#` heading matches `title`.
- `## Summary` — one-paragraph executive description.
- `## Facts` — bulleted, each line a discrete claim.
- `## Relationships` — bullets with `[[wikilinks]]`.
- `## Open questions` / `## History` — optional.

## Repo layout

```
wiki/
├── entities/
│   ├── person/
│   │   └── jim-rowan.md
│   ├── project/
│   │   └── ai-gateway.md
│   ├── system/
│   └── org/
├── concepts/
│   └── agent-orchestration.md
├── pending/
│   ├── 2026-04-04T10-22-candidates.jsonl     # awaiting review
│   └── reviewed.jsonl                         # audit trail
└── index.json                                 # built: id → path, aliases → id
```

## Promotion pipeline

Session-derived facts become wiki updates via a four-stage funnel:

```
 capture  →  candidate  →  review  →  promote
 (inline)   (pending/)    (human)    (entities|concepts)
```

1. **Capture.** During or after a session, an agent (or a harness hook) emits structured `CandidateFact` records: `{subject_hint, claim, page_type, kind, source, confidence}`. These append to `pending/{date}-candidates.jsonl`.
2. **Candidate resolution.** Each candidate is resolved to an existing page via alias match + fuzzy title match + (optionally) LLM linking. Unresolved candidates create *draft* pages in `pending/drafts/`.
3. **Review.** A human (or, later, a reviewer agent) scans pending candidates via `agentforge wiki pending` / `wiki review`. Actions: accept / edit / reject / merge-with-existing.
4. **Promote.** Accepted candidates write to the target page's `## Facts` section, update `updated:`/`sources:`/`contributors:`, and append to `pending/reviewed.jsonl` for audit.

### Dedupe & confidence

- **Exact dedupe:** identical claim strings on the same page are merged (drop duplicate).
- **Near-dedupe:** normalized-text fuzzy match (Jaccard of tokens > 0.85) → flagged to reviewer, not auto-merged.
- **Confidence:** `high` ≥ 2 independent sources or explicit user statement; `medium` single session source; `low` inferred. Confidence on a page is `max(contributing-fact confidences)`, capped by latest contradictory fact.

## Entity linking

MVP uses a three-tier resolver:

1. **Slug/alias exact match** against `index.json`.
2. **Case-insensitive title substring match**.
3. **Fallback: create draft** (flagged for review).

Later: swap tier 2 for LLM-based resolver with candidate ranking.

## Cross-agent integration

- Wiki lives at a shared path (e.g. `~/personal-ai-org/shared/wiki`) — all agents read the same pages.
- Per-agent `MEMORY.md` stays agent-local.
- Agents reference wiki pages from `MEMORY.md` via `See: wiki:proj-ai-gateway`.
- Skills can declare `wiki_reads: [proj-*]` to hint retrieval.

## MVP scope — first slice (this PR)

Shipping now:
- [x] `schema.py` — `Page`, `CandidateFact`, serialization
- [x] `store.py` — read/write pages, build/refresh `index.json`, alias lookup
- [x] `promote.py` — candidate → page promotion, dedupe, audit trail
- [x] `review.py` — list pending, accept/reject/edit via JSONL
- [x] `cli.py` — `agentforge wiki {init,add,show,search,pending,promote,list}`
- [x] seed entity & concept templates
- [x] tests for schema, store, promotion pipeline, dedupe, CLI

**Deferred (phase 2):**
- LLM-based entity linker
- Fuzzy near-dupe detection (phase 2 uses exact-only)
- Reviewer-agent workflow (currently human only)
- Web UI for review
- Conflict resolution when two candidates contradict
- Auto-generated relationship graph

**Deferred (phase 3):**
- Embedding-based semantic search
- Per-agent read/write permissions
- Skill-level `wiki_reads` hints
- Sync with ai-gateway `/api/wiki/*` endpoints (the personal-ai-org wiki already exists — eventually this module becomes the canonical writer for both)

## Risks & tradeoffs

| Risk | Mitigation |
|---|---|
| Reviewer-bottleneck: candidates pile up unreviewed | Keep candidate schema minimal; bulk-accept via heuristic confidence threshold later |
| Stale pages drift from reality | Every fact has a source; `wiki lint` can flag pages where all sources are > N days old |
| Over-eager dedupe merges different entities with the same name | MVP: slug is canonical; no auto-merge without reviewer |
| Duplication with existing `~/personal-ai-org/shared/wiki` | Module is path-agnostic; point it at that dir to unify, or run standalone for agentforge users |
| LLM linker costs at scale | Phase 1 uses pure string matching; LLM only on explicit `wiki link --llm` |

## API surface (Python)

```python
from agentforge.wiki_memory import WikiStore, CandidateFact, promote

store = WikiStore(root="~/personal-ai-org/shared/wiki")
page = store.get_or_create("AI Gateway", type="entity", kind="project")
page.add_fact("Runs on port 8900", source="session:2026-04-04")
store.save(page)

# Capture candidates during a session
cf = CandidateFact(
    subject_hint="AI Gateway",
    claim="Uses Gemma 4 E4B for fast classification",
    page_type="entity",
    kind="project",
    source="session:2026-04-04-nightly",
    confidence="medium",
)
store.queue_candidate(cf)

# Later — review + promote
for candidate in store.pending():
    # UI layer decides; for now CLI asks y/n/e
    promote(store, candidate, decision="accept")
```
