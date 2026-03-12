# Skill Review & Refinement Feature

## Problem
After generating a SKILL.md, users have no way to identify what's weak/generic in the output or to iteratively improve it without re-running the full pipeline. The current quality notice tells users what was *missing from input* but not what's *weak in the output*.

## Feature: Two-Part Skill Review & Refine

### Part 1: Skill Quality Reviewer (`SkillReviewer`)

A new analyzer that examines the generated skill content + extraction data and produces specific, actionable gap items. Each gap has a category, description, and an edit prompt the user can fill in.

**Gap categories detected:**

| Gap Type | Detection Logic | User Edit Prompt |
|----------|----------------|------------------|
| **Generic workflows** | Methodology missing or heuristics < 2 | "Describe how you actually approach [responsibility]. What's your decision process?" |
| **Weak triggers** | trigger_mappings < 2 or triggers are vague | "What specific requests or situations should activate this skill?" |
| **Missing templates** | output_templates empty | "Paste a real output example or describe the format you typically produce" |
| **Vague quality criteria** | quality_criteria < 2 | "What does 'done well' look like? List your review checklist items" |
| **Missing domain context** | Domain skills lack genai_application | "How should AI apply [skill] specifically? What pitfalls to avoid?" |
| **Thin persona** | suggested_traits are all near 0.5 (defaults) | "Describe the communication style: formal/casual, verbose/concise, etc." |
| **Scope too broad** | No scope_secondary or guardrails | "What should this agent explicitly NOT do?" |

**New file:** `src/agentforge/analysis/skill_reviewer.py`

```python
class SkillGap:
    category: str        # e.g. "methodology", "triggers", "templates"
    title: str           # e.g. "Generic Decision Frameworks"
    description: str     # What's weak and why it matters
    edit_prompt: str      # What the user should provide
    section: str         # Which SKILL.md section this affects
    priority: str        # "high", "medium", "low"

class SkillReviewer:
    def review(extraction, methodology, identity, has_examples, has_frameworks) -> list[SkillGap]
```

This is pure analysis — no LLM call, just heuristic checks on the extraction + methodology data.

### Part 2: Skill Refinement (Patch & Regenerate)

**Backend:** New endpoint `POST /api/forge/{job_id}/refine` that accepts user edits (a dict of gap_category → user text) and re-generates just the SKILL.md sections that were weak, without re-running extraction or methodology stages.

The pipeline context is already stored in `job.result` — we have `extraction`, `methodology`, `identity`, etc. The refinement:
1. Merges user edits into the methodology (e.g., user-provided heuristics become new `Heuristic` entries, user templates become `OutputTemplate` entries)
2. Re-runs only `SkillFolderGenerator.generate()` and/or `ClawHubSkillGenerator.generate()` with the enriched data
3. Returns the updated SKILL.md

**New endpoint flow:**
```
POST /api/forge/{job_id}/refine
Body: { "edits": { "methodology": "...", "triggers": "...", "templates": "..." } }
→ Merge edits into stored context
→ Re-generate skill files only
→ Return updated skill_md + new gap review
```

### Part 3: UI — Review Step Between Generate & Download

Current flow: Generate → Download
New flow: Generate → **Review** → Refine (optional) → Download

In the forge results (step 4), add a **"Review & Refine"** collapsible section between the download buttons and the detailed analysis:

```
[Download SKILL.md]
[Download ClawHub SKILL.md]

▼ Review & Refine Skill
  ┌─────────────────────────────────────┐
  │ ⚠ 3 opportunities to strengthen     │
  │                                     │
  │ HIGH: Generic Decision Frameworks   │
  │ The skill has only 1 heuristic...   │
  │ [textarea: describe your process]   │
  │                                     │
  │ MED: Missing Output Templates       │
  │ No concrete output formats...       │
  │ [textarea: paste an example]        │
  │                                     │
  │ LOW: Broad Scope                    │
  │ No explicit guardrails defined...   │
  │ [textarea: what should it NOT do?]  │
  │                                     │
  │        [Refine Skill →]             │
  └─────────────────────────────────────┘

▼ Preview SKILL.md
▼ Detailed Analysis
```

After clicking "Refine Skill", the UI:
1. POSTs user edits to `/api/forge/{job_id}/refine`
2. Shows a brief spinner
3. Updates the skill preview and download links with the refined version
4. Re-runs the review to show remaining gaps (ideally fewer)

## Implementation Order

1. `SkillReviewer` class (pure analysis, no LLM)
2. Tests for SkillReviewer
3. `/api/forge/{job_id}/refine` endpoint + store pipeline context in job
4. UI: review panel with gap cards and edit textareas
5. UI: refine button wiring + skill preview update
