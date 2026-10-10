#!/usr/bin/env bash
# Setup and configuration script for drupal-mcp-server
set -e
cd "$(dirname "$0")/.."

echo "==> Setting up Drupal MCP Server..."

# Create virtual environment if needed
if [ ! -d ".venv" ]; then
    echo "==> Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "==> Upgrading pip..."
pip install --upgrade pip

echo "==> Installing package with dev dependencies..."
pip install -e ".[dev]" 2>/dev/null || pip install -e .

# Copy environment example if .env doesn't exist
if [ ! -f .env ] && [ -f .env.example ]; then
    echo "==> Creating .env from template..."
    cp .env.example .env
    echo "==> Please edit .env with your Drupal site credentials"
fi

echo ""
echo "==> Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your Drupal site URL and credentials"
echo "  2. Run: source .venv/bin/activate"
echo "  3. Run: python -m drupal_mcp_server"
echo ""
echo "Or use the helper scripts:"
echo "  ./scripts/run.sh    # Start the MCP server"
echo "  ./scripts/test.sh   # Run tests"
echo "  ./scripts/lint.sh   # Run linters"
