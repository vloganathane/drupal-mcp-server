# Contributing to Drupal MCP Server

Thank you for your interest in contributing!

## Development Setup

```bash
# Clone the repository
git clone https://github.com/your-org/drupal-mcp-server.git
cd drupal-mcp-server

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Copy environment template
cp examples/.env.example .env
# Edit .env with your Drupal credentials
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/drupal_mcp_server --cov-report=term-missing

# Run linting
ruff check src/ tests/

# Run type checking
mypy src/drupal_mcp_server/
```

## Project Structure

```
src/drupal_mcp_server/
├── auth/           # Authentication strategies
├── clients/        # HTTP and subprocess clients
├── services/       # Business logic layer
├── tools/          # MCP tool modules
│   └── _utils.py   # Shared utilities
├── config.py       # Pydantic settings
├── exceptions.py   # Exception hierarchy
└── server.py       # FastMCP entry point
```

## Adding a New Tool Module

1. Create `src/drupal_mcp_server/tools/my_module.py` with a `register_tools(mcp, **deps)` function.
2. Import the module in `server.py` and add it to the registration loop.
3. Add tests in `tests/unit/test_my_module.py`.
4. Import `ensure_dict` from `._utils` for consistent response handling.

## Code Standards

- All user input must be validated before use in SQL, shell commands, or file paths.
- Use `ensure_dict()` from `tools/_utils.py` for JSON:API response handling.
- Add type hints on all public functions.
- Write tests for new features and bug fixes.

## Pull Request Process

1. Fork the repository and create a feature branch.
2. Make your changes with clear commit messages (Conventional Commits).
3. Ensure all tests pass: `pytest && ruff check && mypy`
4. Open a PR with a clear description of what and why.
5. Address review feedback.

## Reporting Issues

- Check existing issues first.
- Include Python version, OS, and steps to reproduce.
- For security issues, see SECURITY.md instead of opening a public issue.
