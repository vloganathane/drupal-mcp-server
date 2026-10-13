# ADR 0003: Execute Drush via Subprocess

## Status
Accepted

## Date
2026-10-13

## Context

Drush is a PHP CLI tool. We need to execute Drush commands from Python and capture their output. Options include:
- Shell execution via `os.system()` or `subprocess.run(shell=True)`
- PHP-FPM HTTP calls
- Direct database queries

## Decision

Use `asyncio.create_subprocess_exec()` with argument arrays (no shell).

## Consequences

### Positive
- No shell injection risk — arguments passed as array
- Async-native — doesn't block the event loop
- Timeout support via `asyncio.wait_for()`
- Cross-platform (works on Linux, macOS, Windows)
- Captures stdout/stderr separately

### Negative
- Drush must be installed on the host system
- No structured error codes from Drush itself
- JSON parsing depends on `--format=json` flag

## Alternatives Considered

- **subprocess.run(shell=True)** — Shell injection risk
- **php:command via HTTP** — Requires PHP-FPM, more complex
- **Direct DB queries** — Bypasses Drush's business logic
