---
name: ship-pr
description: Open a pull request from the current branch and walk it through review.
allowed-tools:
  - Bash
  - Read
  - Edit
---

# Ship a PR

Open a pull request from the current branch, walk it through review, and
land it on main.

## When to use

Use this skill when the user says "ship", "open a PR", or asks to take
working changes to review.

## Procedure

1. Run `Bash` to check `git status` and confirm the branch is clean
   relative to the staged changes.
2. Use `Read` on `CHANGELOG.md` to confirm the change is documented.
3. Open the PR via `gh pr create` with a tight title and a body that
   names the test plan.

See `templates/pr-body.md` for the body scaffold.
