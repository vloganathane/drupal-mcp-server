"""Unit tests for the Drupal.org tools.

drupal.org retired the ``/api-d7/project/...`` endpoints these tools used to
call, so every one of them returned an HTML 404 page. The parsers here are
exercised against captured markup rather than the network.
"""

from typing import Any

import pytest

from drupal_mcp_server.tools import drupal_org

SEARCH_HTML = """
<html><body>
<ul class="main-nav">
  <li><a href="https://www.drupal.org/project/modules">Modules</a></li>
  <li><a href="https://www.drupal.org/project/themes">Themes</a></li>
</ul>
<ol class="search-results apachesolr_search-results">
  <li class="search-result">
    <h3 class="title">
      <a href="https://www.drupal.org/project/webform">Webform</a>
    </h3>
    <div class="search-info"><p class="project-type">Module project</p></div>
  </li>
  <li class="search-result">
    <h3 class="title">
      <a href="https://www.drupal.org/project/gin">Gin</a>
    </h3>
    <div class="search-info"><p class="project-type">Theme project</p></div>
  </li>
</ol>
</body></html>
"""

USAGE_HTML = """
<table class="full-width">
  <thead>
    <tr><th>Week starting</th><th>7.x-1.x</th><th>10.x-1.x</th><th>Total</th></tr>
  </thead>
  <tbody>
    <tr><td>October 4th, 2026</td><td>121885</td><td>4584</td><td>126469</td></tr>
    <tr><td>September 27th, 2026</td><td>120000</td><td>4400</td><td>124400</td></tr>
  </tbody>
</table>
"""


def test_search_parser_separates_modules_from_themes():
    results = drupal_org._parse_search_results(SEARCH_HTML)

    assert {r["machine_name"] for r in results} == {"webform", "gin"}
    by_name = {r["machine_name"]: r["type"] for r in results}
    assert by_name == {"webform": "module", "gin": "theme"}
    assert all(r["url"].startswith("https://www.drupal.org/project/") for r in results)


def test_search_parser_drops_navigation_links():
    """The nav also links to /project/modules and /project/themes."""
    results = drupal_org._parse_search_results(SEARCH_HTML)
    names = [r["machine_name"] for r in results]

    assert "modules" not in names
    assert "themes" not in names


def test_search_parser_reports_markup_change_instead_of_empty_list():
    """Silently returning [] would look like 'no results' forever."""
    with pytest.raises(RuntimeError, match="markup may have changed"):
        drupal_org._parse_search_results("<html><body>no results here</body></html>")


def test_usage_parser_reads_the_latest_week():
    usage = drupal_org._parse_usage(USAGE_HTML, "pathauto", "month")

    assert usage["week_starting"] == "October 4th, 2026"
    assert usage["total"] == "126469"
    assert usage["by_branch"] == {"7.x-1.x": "121885", "10.x-1.x": "4584"}


def test_usage_parser_errors_when_there_is_no_table():
    with pytest.raises(RuntimeError, match="no usage statistics"):
        drupal_org._parse_usage("<html></html>", "nope", "month")


def test_release_history_surfaces_the_upstream_error():
    """updates.drupal.org answers 200 with an <error> document."""
    with pytest.raises(RuntimeError, match="no release history"):
        drupal_org._parse_release_history(
            '<?xml version="1.0"?><error>No release history available.</error>',
            "pathauto",
            "10.x",
        )


def test_release_history_parses_success_document():
    xml = """<?xml version="1.0"?>
    <project>
      <release><name>pathauto</name><version>10.x-1.15</version>
        <created>1770000000</created><core>10.x</core><status>published</status>
      </release>
    </project>"""

    history = drupal_org._parse_release_history(xml, "pathauto", "10.x")

    assert history["project"] == "pathauto"
    assert len(history["releases"]) == 1
    assert history["releases"][0]["version"] == "10.x-1.15"
    assert history["releases"][0]["core"] == "10.x"


def test_release_history_rejects_malformed_xml():
    with pytest.raises(RuntimeError, match="not valid XML"):
        drupal_org._parse_release_history("<project><oops", "pathauto", "10.x")


def test_project_summary_strips_markup_from_the_body():
    node: dict[str, Any] = {
        "nid": "17345",
        "title": "Pathauto",
        "type": "project_module",
        "field_project_machine_name": "pathauto",
        "body": {"value": "<p>Pathauto automatically generates URL aliases.</p>"},
    }

    summary = drupal_org._project_summary(node)

    assert summary["field_project_machine_name"] == "pathauto"
    assert summary["summary"] == "Pathauto automatically generates URL aliases."
    assert "<p>" not in summary["summary"]


def test_all_nine_drupal_org_tools_are_registered():
    """The tools must keep their names; an MCP client may hold references."""

    class _FakeMCP:
        def __init__(self) -> None:
            self.names: list[str] = []

        def tool(self, *args: Any, **kwargs: Any):
            def decorate(fn):
                self.names.append(fn.__name__)
                return fn
            return decorate

    mcp = _FakeMCP()
    drupal_org.register_tools(mcp)  # type: ignore[arg-type]

    assert sorted(mcp.names) == sorted([
        "module_search",
        "module_get",
        "module_versions",
        "module_dependencies",
        "theme_search",
        "theme_get",
        "release_history",
        "project_usage",
        "module_compatibility",
    ])


def test_no_drupal_org_tool_returns_raw_html():
    """The old failure mode dumped 400 lines of a 404 page into the response."""
    import inspect

    source = inspect.getsource(drupal_org)
    assert "e.response.text" not in source
