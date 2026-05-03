---
name: run-tests
description: Run the test suite for the current project and report failures.
allowed-tools:
  - Bash
  - Read
---

# Run tests

Run the project test suite, surface failures, and (when asked) drill
into the first failure.

## When to use

Use this when the user says "run the tests" or after meaningful code
changes.

## Procedure

1. `Bash` `pytest -x` (or the project's documented test command).
2. If a test fails, `Read` the failing file and the source under test.
3. Report the failure with a 1-line root cause.
