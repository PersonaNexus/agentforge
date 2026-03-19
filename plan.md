# CLI Interactive Wizard — Implementation Plan

## Overview

Add an `agentforge wizard` command that provides a full guided experience for
forging agents, with a post-run action menu. Uses `typer.prompt()` + `rich`
(already in deps) — no new dependencies needed.

## Architecture

One new file: `src/agentforge/cli_wizard.py` containing the wizard logic,
registered as a command in `cli.py`. Keeps the existing CLI commands unchanged
(wizard is additive, not a replacement).

---

## Step 1 — Create `src/agentforge/cli_wizard.py`

The wizard module with these functions:

### `_pick_command()` → str
Prompt user to pick: **forge** | **batch** | **team** | **identity import**
Uses numbered menu via `typer.prompt()`.

### `_pick_file(prompt_text, extensions, allow_dir=False)` → Path
File/directory picker — prompts for a path, validates it exists and has an
allowed extension. Shows auto-detected candidates from cwd if any match.

### `_pick_options(command)` → dict
Command-specific option gathering:

- **forge**: mode (default/quick/deep), culture file?, examples file?,
  frameworks file?, skill-folder output?, no-skill-file?
- **batch**: culture?, examples?, frameworks?, parallel workers count
- **team**: culture?, examples?, frameworks?, output format (claude/langgraph/both)
- **identity import**: output format, refine?, examples?, frameworks?

Each prompt uses sensible defaults (just press Enter to skip).

### `_run_command(command, file_path, options)` → context dict
Delegates to the existing pipeline functions (same code paths as the
non-wizard CLI commands). Returns the pipeline context for post-run actions.

### `_post_run_menu(command, context, output_dir)` → None
After forge/team/batch completes, shows an action menu:

1. **Refine** — enter refinement instructions (text prompt), re-run generate
   stage with `SkillRefiner`
2. **Generate team** — if single forge, offer to run team pipeline on same JD
3. **Re-run with different options** — loop back to `_pick_options()`
4. **Export** — save outputs to a different directory
5. **Done** — exit

The refine loop can repeat (refine → show results → refine again or done).

### `wizard()` — the Typer command
Orchestrates: welcome banner → pick command → pick file → pick options →
run → post-run menu → exit.

---

## Step 2 — Register in `cli.py`

Add to `cli.py`:

```python
@app.command()
def wizard(...):
    from agentforge.cli_wizard import run_wizard
    run_wizard()
```

Minimal footprint in cli.py — all logic lives in the new module.

---

## Step 3 — Post-run refinement integration

The post-run "Refine" action will:

1. Prompt for free-text refinement instructions
2. Use `SkillRefiner.refine()` (already exists in
   `agentforge/analysis/skill_refiner.py`) to merge changes
3. Re-run `SkillFolderGenerator.generate()` with updated extraction/methodology
4. Display updated results and loop back to the post-run menu

This mirrors the web UI's refine loop but in the terminal.

---

## Step 4 — File auto-detection

When prompting for a JD file, scan cwd for files matching allowed extensions
(`.txt`, `.md`, `.pdf`, `.docx`) and show them as numbered choices if ≤10 found.
If >10, just show the prompt. Same for culture/examples/frameworks files.

---

## Files changed

| File | Change |
|------|--------|
| `src/agentforge/cli_wizard.py` | **New** — all wizard logic |
| `src/agentforge/cli.py` | Add `wizard` command (3-4 lines) |

## No new dependencies

Uses only `typer.prompt()`, `typer.confirm()`, `rich.console.Console`,
`rich.panel.Panel`, `rich.table.Table` — all already available.
