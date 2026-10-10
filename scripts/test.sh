#!/usr/bin/env bash
# Importer/Caller: User management of project skeleton
# Affected API: None (Shell script)
# Data Schemas: None
# User Instruction: "scripts folder is empty"
set -e
cd "$(dirname "$0")/.."

source .venv/bin/activate
pytest tests/ -v
