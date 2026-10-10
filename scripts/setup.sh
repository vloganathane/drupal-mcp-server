#!/usr/bin/env bash
# Importer/Caller: User management of project skeleton
# Affected API: None (Shell script)
# Data Schemas: None
# User Instruction: "scripts folder is empty"
set -e
cd "$(dirname "$0")/.."

echo "Setting up Drupal MCP Server environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
echo "Setup complete! Run 'source .venv/bin/activate' to activate."
