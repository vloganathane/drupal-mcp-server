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

# Install pre-commit hooks
pre-commit install

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

# Run specific test file
pytest tests/unit/test_content_tools.py

# Run with verbose output
pytest -v
```

## Linting & Type Checking

```bash
# Lint with ruff
ruff check src/ tests/

# Auto-fix lint issues
ruff check --fix src/ tests/

# Type check
mypy src/drupal_mcp_server/

# Run all checks at once
ruff check src/ tests/ && mypy src/drupal_mcp_server/
```

## Project Structure

```
src/drupal_mcp_server/
├── auth/           # Authentication strategies (Basic, Token, OAuth)
├── clients/        # HTTP and subprocess clients (JSON:API, GraphQL, Drush)
├── services/       # Business logic layer (AI, Migration, SiteManager)
├── tools/          # MCP tool modules
│   ├── _utils.py   # Shared utilities (ensure_dict, validate_pagination)
│   ├── content.py  # Content management tools
│   ├── users.py    # User management tools
│   └── ...         # 30+ more tool modules
├── config.py       # Pydantic settings
├── errors.py       # Standardized error responses
├── exceptions.py   # Exception hierarchy
├── schemas.py      # Pydantic schemas for tool I/O
├── validation.py   # Reusable input validators
├── logging_config.py # Structured logging setup
└── server.py       # FastMCP entry point
```

## Adding a New Tool Module

1. Create `src/drupal_mcp_server/tools/my_module.py`:

```python
"""Description of my module."""

from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict, validate_pagination


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def my_tool(param: str) -> dict[str, Any]:
        """Short description of what this tool does.

        Args:
            param: Description of the parameter

        Returns:
            Description of the return value
        """
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_resource(param)
            return ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}
```

2. Import the module in `server.py` and add it to the registration loop
3. Add tests in `tests/unit/test_my_module.py`
4. Update the tool list in `README.md`

## Code Standards

### Required for All Code

- Type hints on all public functions
- Docstrings on all public functions (Google style)
- Input validation for all user-provided parameters
- Use `ensure_dict()` from `tools/_utils.py` for JSON:API responses
- Use `validate_pagination()` for paginated endpoints
- Use `error_response()` from `errors.py` for consistent error format

### Security Requirements

- **Never** use f-strings for SQL queries — use parameterized queries
- **Never** use f-strings for shell commands — use argument arrays
- **Never** use f-strings for file paths — use `os.path.realpath()`
- Always validate user input before use in any external call

### Testing Requirements

- New features must have tests
- Bug fixes must have a test that reproduces the bug
- Tests should cover both success and error paths
- Mock external services (httpx, subprocess) in unit tests

## Commit Message Format

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]
[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `build`, `ci`

Examples:

```
feat(tools): add bulk user import tool

fix(security): prevent SQL injection in db_query

docs(readme): add installation instructions for Windows
```

## Pull Request Process

1. Fork the repository and create a feature branch
2. Make your changes with clear commit messages
3. Ensure all checks pass: `ruff check src/ tests/ && mypy src/drupal_mcp_server/ && pytest`
4. Open a PR with a clear description of what and why
5. Address review feedback
6. A maintainer will merge once approved

## Review Process

### What Reviewers Look For

- Does it solve a real problem?
- Are there tests?
- Does it follow the code standards?
- Are there security implications?
- Is the documentation updated?

### Expected Turnaround

- Initial review: within 3 business days
- Follow-up reviews: within 2 business days
- Security fixes: expedited review

## Reporting Issues

- Check existing issues first
- Include Python version, OS, and steps to reproduce
- For security issues, see SECURITY.md instead of opening a public issue

## Questions?

- Open a [GitHub Discussion](https://github.com/your-org/drupal-mcp-server/discussions) for questions
- Use [GitHub Issues](https://github.com/your-org/drupal-mcp-server/issues) for bug reports and feature requests
