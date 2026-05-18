# AgentForge Telemetry & Observability Design (Opt-In)

Status: design-only. No telemetry collection is enabled by default.

## Goals

- Provide operational visibility into local AgentForge usage.
- Help users understand pipeline reliability, latency, and token cost.
- Preserve privacy by default and avoid silent data export.

## No-Default-Exfiltration Guarantee

- Default mode is `off`.
- AgentForge sends no telemetry to any remote endpoint unless the user explicitly opts in.
- Local logs/metrics can be enabled without any network transmission.

## Proposed Metric Set

- Command-level:
  - command name (`extract`, `forge`, `test`, etc.)
  - success/failure
  - wall-clock duration
- Pipeline-level:
  - stage timing breakdown
  - stage failure point
  - output target (`openclaw`, `personanexus`, `both`)
- LLM usage (when available from provider responses):
  - model name
  - prompt tokens
  - completion tokens
  - estimated cost

## Explicitly Excluded By Default

- Raw JD text
- Generated identity/skill content
- Prompt bodies
- User-supplied supplemental documents

## Privacy Boundaries

- Hash-only identifiers for runs/sessions (no direct personal identifiers).
- Optional project label allowed, but no file path collection by default.
- Redaction step before any optional remote export.

## Configuration Shape (Proposed)

Environment variables:

- `AGENTFORGE_TELEMETRY_MODE=off|local|remote`
- `AGENTFORGE_TELEMETRY_ENDPOINT=https://...` (required only for `remote`)
- `AGENTFORGE_TELEMETRY_SAMPLE_RATE=0.0-1.0`

CLI flags (override env):

- `--telemetry off|local|remote`
- `--telemetry-endpoint URL`

## Modes

- `off` (default): no telemetry collection.
- `local`: write metrics to local JSONL file only.
- `remote`: same local write plus batched export to configured endpoint.

## Rollout Plan

1. Implement `local` mode only with unit tests and docs.
2. Add schema versioning for telemetry events.
3. Add `remote` mode behind explicit endpoint configuration.
4. Add integration test to verify no network calls in `off` mode.
