# ADR 0002: Use Pydantic Settings for Configuration

## Status
Accepted

## Date
2026-10-13

## Context

The server needs configuration from multiple sources:
- Environment variables (12-factor app)
- `.env` files for local development
- Sensible defaults for optional settings
- Type validation and IDE support

## Decision

Use `pydantic-settings` with `BaseSettings` for all configuration.

## Consequences

### Positive
- Type-safe configuration with validation
- Automatic `.env` file loading
- IDE autocomplete via Pydantic models
- `lru_cache` for singleton settings instance
- `extra="ignore"` prevents crashes from unknown env vars

### Negative
- Pydantic dependency (already required for tool schemas)
- Settings are global singleton (harder to test with different configs)

## Alternatives Considered

- **python-dotenv + os.environ** — No type safety, manual validation
- **dynaconf** — More features but heavier, less Pythonic
- **Custom config class** — Reinventing the wheel
