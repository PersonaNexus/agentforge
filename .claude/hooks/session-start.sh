#!/bin/bash
set -euo pipefail

# Only run in remote (web) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

VENV_DIR="${CLAUDE_PROJECT_DIR}/.venv"

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
  python3.12 -m venv "$VENV_DIR"
fi

# Use venv pip/python explicitly
PIP="${VENV_DIR}/bin/pip"

# Persist venv for the session
echo "export PATH=\"${VENV_DIR}/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
echo "export VIRTUAL_ENV=\"${VENV_DIR}\"" >> "$CLAUDE_ENV_FILE"

# Install personanexus from PyPI first (pyproject.toml has a broken local path)
$PIP install personanexus

# Install the project in editable mode with --no-deps
# to avoid the broken file:// reference for personanexus
$PIP install --no-deps -e "${CLAUDE_PROJECT_DIR}"

# Install runtime dependencies
$PIP install \
  "pydantic>=2.0,<3.0" \
  "pyyaml>=6.0.1,<7.0" \
  "typer>=0.9,<1.0" \
  "rich>=13.0,<14.0" \
  "anthropic>=0.40,<1.0" \
  "openai>=2.0,<3.0" \
  "pymupdf>=1.24,<2.0" \
  "python-docx>=1.0,<2.0"

# Install web optional dependencies
$PIP install \
  "fastapi>=0.115,<1.0" \
  "uvicorn[standard]>=0.30,<1.0" \
  "python-multipart>=0.0.9"

# Install dev dependencies (linter, tests, type checker)
$PIP install \
  "pytest>=8.0" \
  "pytest-cov>=4.0" \
  "ruff>=0.4" \
  "mypy>=1.8"
