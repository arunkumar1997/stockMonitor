#!/usr/bin/env bash
# Format staged Python files with Ruff, using the backend venv's copy.
# Called by lint-staged (see .lintstagedrc.json). File paths are passed
# as arguments.
#
# Fails loudly with a helpful hint if the venv or Ruff isn't set up yet
# — this matches the existing "./start_backend.sh bootstraps everything"
# convention.

set -euo pipefail

RUFF="${RUFF:-backend/venv/bin/ruff}"

if [ ! -x "$RUFF" ]; then
  cat >&2 <<EOF
error: Ruff not found at $RUFF

The pre-commit hook needs Ruff to format staged Python files. Bootstrap
the backend venv first, which installs Ruff along with the other deps:

    ./start_backend.sh    # or: backend/venv/bin/pip install -r backend/requirements.txt

Then re-run your commit.
EOF
  exit 1
fi

exec "$RUFF" format "$@"
