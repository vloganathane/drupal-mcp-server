#!/usr/bin/env bash
# Importer/Caller: User management of project skeleton
# Affected API: None (Shell script)
# Data Schemas: None
# User Instruction: "scripts folder is empty"
set -e
cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Run scripts/setup.sh first."
    exit 1
fi

source .venv/bin/activate
python -m drupal_mcp_server
