#!/usr/bin/env bash
set -euo pipefail
ENVIRONMENT=development uv run uvicorn app.main:app --reload
