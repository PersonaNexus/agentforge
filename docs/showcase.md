# AgentForge Examples & Showcase

Use this path to contribute public, sanitized examples of forged outputs.

## What To Contribute

- A sanitized input under `examples/<slug>/input/` (job description text or markdown).
- Generated output under `examples/<slug>/output/` (identity, skill folder, or deployment package).
- A short `examples/<slug>/README.md` with:
  - what the example demonstrates
  - exact reproduction command
  - any assumptions

## Safety & Privacy Rules

- Remove names, email addresses, phone numbers, URLs, and company-internal identifiers.
- Remove proprietary process details and customer-specific data.
- Keep examples representative, but never include confidential source material.

## Recommended Workflow

```bash
# 1) Generate or refresh a sample output package
uv sync --dev
uv run python scripts/generate_example_artifacts.py

# 2) Inspect artifacts before commit
git diff -- examples/
```

## Review Checklist

- Input and output are both present.
- Output can be reproduced from the documented command.
- Sanitization is complete.
- README explanation is clear and brief.
