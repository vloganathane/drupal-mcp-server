"""Automated Testing tools for Drupal.

PHPUnit, Behat, and Nightwatch run from the site's own binaries. Drush
ships no ``php:unit``/``behat:run``/``nightwatch:run`` command (verified
against drush-ops/drush 13.x: core defines none of the three), so the
previous runners answered the live sweep with a wrapped failure --
``{"result": {"returncode": 1, "stderr": "Command \\"php:unit\\" is not
defined"}}`` has no top-level ``error`` and reads as success -- while every
real call died on the same missing command.
"""

import asyncio
import os
import shutil
from typing import Any

from fastmcp import FastMCP

from ..config import get_settings
from ._utils import ensure_dict as _ensure_dict


def _site_root() -> str:
    """The configured Drupal root, falling back to the working directory."""
    try:
        root = get_settings().DRUPAL_ROOT
    except Exception:
        root = None
    return str(root or os.getcwd())


def _site_tool(name: str) -> str | None:
    """Locate ``name`` inside the site, then on PATH.

    Site-local binaries come first: a global phpunit or behat on PATH may
    not match the site's own PHPUnit/Drupal versions.
    """
    roots: list[str] = []
    for root in (_site_root(), "/var/www/html", "/app"):
        if root and root not in roots:
            roots.append(root)
    for root in roots:
        for sub in ("vendor/bin", "node_modules/.bin"):
            candidate = os.path.join(root, sub, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return shutil.which(name)


def _missing_tool(name: str) -> dict[str, Any]:
    return {
        "error": (
            f"{name} was not found: looked in vendor/bin and node_modules/.bin "
            "under DRUPAL_ROOT and the working directory, then on PATH. "
            "Install the site's dev dependencies (composer install), or set "
            "DRUPAL_ROOT to the site root."
        )
    }


async def _run_tool(cmd: list[str]) -> dict[str, Any]:
    """Run a test binary; a failing exit becomes a top-level ``error``.

    The previous shape, ``{"result": {"returncode": 1, ...}}``, carried no
    error key, so MCP callers and the live sweep both read a failed run as
    an ordinary answer.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    payload: dict[str, Any] = {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "output": stdout.decode(errors="replace")[-4000:],
        "stderr": stderr.decode(errors="replace")[-2000:],
    }
    if proc.returncode:
        reason = payload["stderr"].strip() or payload["output"].strip() or "no output"
        payload["error"] = f"{cmd[0]} failed (exit {proc.returncode}): {reason[:800]}"
    return payload


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    # The test runners execute the site's own binaries and never shell out
    # through drush; the scaffolding tools below still take drush_client.
    drush = deps.get("drush_client")

    @mcp.tool()
    async def test_run_phpunit(
        test_path: str | None = None,
        group: str | None = None,
        filter: str | None = None,
        coverage: bool = False,
    ) -> dict[str, Any]:
        """Run the site's PHPUnit tests (vendor/bin/phpunit)."""
        binary = _site_tool("phpunit")
        if not binary:
            return _missing_tool("phpunit")
        cmd = [binary]
        if test_path:
            cmd.append(test_path)
        if group:
            cmd.extend(["--group", group])
        if filter:
            cmd.extend(["--filter", filter])
        if coverage:
            cmd.extend(["--coverage-html", "coverage"])
        return await _run_tool(cmd)

    @mcp.tool()
    async def test_run_kernel(
        test_path: str | None = None,
        filter: str | None = None,
    ) -> dict[str, Any]:
        """Run the site's Kernel-test suite (vendor/bin/phpunit)."""
        binary = _site_tool("phpunit")
        if not binary:
            return _missing_tool("phpunit")
        # Suite names are exact: Drupal's phpunit.xml.dist defines "Kernel".
        cmd = [binary, "--testsuite=Kernel"]
        if test_path:
            cmd.append(test_path)
        if filter:
            cmd.extend(["--filter", filter])
        return await _run_tool(cmd)

    @mcp.tool()
    async def test_run_behat(
        profile: str = "default",
        tags: str | None = None,
        format: str = "pretty",
    ) -> dict[str, Any]:
        """Run the site's Behat features (vendor/bin/behat)."""
        binary = _site_tool("behat")
        if not binary:
            return _missing_tool("behat")
        cmd = [binary, "--profile", profile, "--format", format]
        if tags:
            cmd.extend(["--tags", tags])
        return await _run_tool(cmd)

    @mcp.tool()
    async def test_run_nightwatch(
        test_path: str | None = None,
        env: str = "default",
    ) -> dict[str, Any]:
        """Run Nightwatch tests (node_modules/.bin/nightwatch)."""
        binary = _site_tool("nightwatch")
        if not binary:
            return _missing_tool("nightwatch")
        cmd = [binary, "--env", env]
        if test_path:
            cmd.append(test_path)
        return await _run_tool(cmd)

    @mcp.tool()
    async def test_scaffold_phpunit(
        module: str,
        test_type: str = "unit",
        class_name: str | None = None,
        test_methods: list[str] | None = None,
    ) -> dict[str, Any]:
        """Scaffold a PHPUnit test class."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            if class_name is None:
                class_name = f"{module.capitalize()}Test"
            
            base_class = "Drupal\\Tests\\UnitTestCase" if test_type == "unit" else "Drupal\\KernelTests\\KernelTestBase"
            
            test_code = f"""<?php

namespace Drupal\\Tests\\{module}\\{test_type.capitalize()};

use {base_class};

/**
 * Tests for {module}.
 */
class {class_name} extends {base_class} {{
"""
            if test_methods:
                for method in test_methods:
                    test_code += f"""
  /**
   * Test {method}.
   */
  public function test{method.capitalize()}() {{
    // TODO: Implement test
    $this->assertTrue(TRUE);
  }}
"""
            test_code += "}\n"
            
            # Save to file
            import os
            test_dir = f"{module}/tests/src/{test_type.capitalize()}"
            os.makedirs(test_dir, exist_ok=True)
            test_file = os.path.join(test_dir, f"{class_name}.php")
            
            with open(test_file, "w") as f:
                f.write(test_code)
            
            return _ensure_dict({"created": test_file, "class": class_name})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def test_scaffold_behat(
        module: str,
        feature_name: str,
        scenarios: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Scaffold a Behat feature file."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            feature_content = f"""Feature: {feature_name}
  In order to test {module}
  As a developer
  I need to verify functionality

"""
            if scenarios:
                for scenario in scenarios:
                    feature_content += f"""  Scenario: {scenario.get('name', 'Test scenario')}
"""
                    for step in scenario.get('steps', []):
                        feature_content += f"    {step}\n"
                    feature_content += "\n"
            else:
                feature_content += """  Scenario: Basic test
    Given I am on the homepage
    Then I should see "Drupal"
"""
            
            import os
            feature_dir = f"{module}/tests/behat"
            os.makedirs(feature_dir, exist_ok=True)
            feature_file = os.path.join(feature_dir, f"{feature_name.lower().replace(' ', '_')}.feature")
            
            with open(feature_file, "w") as f:
                f.write(feature_content)
            
            return _ensure_dict({"created": feature_file})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def test_scaffold_nightwatch(
        module: str,
        test_name: str,
        test_steps: list[str] | None = None,
    ) -> dict[str, Any]:
        """Scaffold a Nightwatch test."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            test_content = f"""module.exports = {{
  '{test_name}': function (browser) {{
"""
            if test_steps:
                for step in test_steps:
                    test_content += f"    {step}\n"
            else:
                test_content += """    browser
      .url(browser.launchUrl)
      .waitForElementVisible('body')
      .assert.titleContains('Drupal')
      .end()
"""
            test_content += "  }\n};\n"
            
            import os
            test_dir = f"{module}/tests/nightwatch"
            os.makedirs(test_dir, exist_ok=True)
            test_file = os.path.join(test_dir, f"{test_name.lower().replace(' ', '-')}.js")
            
            with open(test_file, "w") as f:
                f.write(test_content)
            
            return _ensure_dict({"created": test_file})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def test_coverage_report(
        format: str = "html",
        output_dir: str = "coverage",
    ) -> dict[str, Any]:
        """Generate a test coverage report (vendor/bin/phpunit)."""
        allowed = ("html", "clover", "crap4j", "php", "text", "xml")
        if format not in allowed:
            # The format became the flag verbatim: `--coverage-` + anything
            # was passed straight to phpunit.
            return {
                "error": (
                    f"unsupported coverage format {format!r}; phpunit accepts "
                    f"one of {', '.join(allowed)}. Nothing was run."
                )
            }
        binary = _site_tool("phpunit")
        if not binary:
            return _missing_tool("phpunit")
        payload = await _run_tool([binary, f"--coverage-{format}", output_dir])
        payload["output_dir"] = output_dir
        return payload

    @mcp.tool()
    async def test_list_suites(
    ) -> dict[str, Any]:
        """List the site's PHPUnit test suites."""
        binary = _site_tool("phpunit")
        if not binary:
            return _missing_tool("phpunit")
        return await _run_tool([binary, "--list-suites"])
