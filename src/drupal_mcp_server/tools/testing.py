"""Automated Testing tools for Drupal."""

import os
import yaml
import json
from typing import Any

from fastmcp import FastMCP


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    jsonapi = deps.get("jsonapi_client")

    def _ensure_dict(result: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
        """Ensure result is a dict, not a list."""
        if result is None:
            return {"error": "No response"}
        if isinstance(result, list):
            return {"error": f"Unexpected list response: {result}"}
        return result

    @mcp.tool()
    async def test_run_phpunit(
        test_path: str | None = None,
        group: str | None = None,
        filter: str | None = None,
        coverage: bool = False,
    ) -> dict[str, Any]:
        """Run PHPUnit tests."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["php:unit"]
            if test_path:
                cmd.append(test_path)
            if group:
                cmd.extend(["--group", group])
            if filter:
                cmd.extend(["--filter", filter])
            if coverage:
                cmd.extend(["--coverage-html", "coverage"])
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def test_run_kernel(
        test_path: str | None = None,
        filter: str | None = None,
    ) -> dict[str, Any]:
        """Run Kernel tests."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["php:unit", "--testsuite=kernel"]
            if test_path:
                cmd.append(test_path)
            if filter:
                cmd.extend(["--filter", filter])
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def test_run_behat(
        profile: str = "default",
        tags: str | None = None,
        format: str = "pretty",
    ) -> dict[str, Any]:
        """Run Behat tests."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["behat:run", "--profile", profile, "--format", format]
            if tags:
                cmd.extend(["--tags", tags])
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def test_run_nightwatch(
        test_path: str | None = None,
        env: str = "default",
    ) -> dict[str, Any]:
        """Run Nightwatch tests."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["nightwatch:run", "--env", env]
            if test_path:
                cmd.append(test_path)
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

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
    \$this->assertTrue(TRUE);
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
        """Generate test coverage report."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["php:unit", "--coverage-" + format, output_dir]
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result, "output_dir": output_dir})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def test_list_suites(
    ) -> dict[str, Any]:
        """List available test suites."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("php:unit", ["--list-suites"])
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}
