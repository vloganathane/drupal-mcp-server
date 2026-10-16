"""Console entry point.

``drupal-mcp`` with no arguments (or any unrecognized argument) still starts
the MCP server exactly as before, so every existing client config keeps
working. Recognized verbs are intercepted:

* ``drupal-mcp install`` - register the server with local MCP clients
* ``drupal-mcp --version`` / ``-V`` - print the package version
* ``drupal-mcp --help`` / ``-h`` / ``help`` - print usage
"""

from __future__ import annotations

import sys

from drupal_mcp_server import __version__

_USAGE = """\
drupal-mcp - MCP server for Drupal (JSON:API, GraphQL, Drush, migration)

Usage:
  drupal-mcp                     Start the MCP server over stdio
  drupal-mcp install [OPTIONS]   Register the server with local MCP clients
  drupal-mcp --version           Print the version
  drupal-mcp --help              Show this help

`install` detects the MCP clients on this machine (Claude Code, Claude
Desktop, Cursor, Codex, OpenCode, Windsurf, Pi, Hermes, OpenClaw) and writes
the server into their configuration. Run `drupal-mcp install --help` for its
options.
"""

_INSTALL_VERBS = {"install"}
_VERSION_FLAGS = {"--version", "-V"}
_HELP_FLAGS = {"--help", "-h", "help"}


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else list(argv)

    if args and args[0] in _VERSION_FLAGS:
        print(__version__)
        return

    if args and args[0] in _HELP_FLAGS:
        print(_USAGE, end="")
        return

    if args and args[0] in _INSTALL_VERBS:
        from drupal_mcp_server.installer import install_main

        install_main(args[1:])
        return

    # Anything else runs the server, as it always has.
    from drupal_mcp_server.server import run_server

    run_server()
