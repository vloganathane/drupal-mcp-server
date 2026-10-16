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


def test_all_twelve_drupal_org_tools_are_registered():
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
        "module_issues_search",
        "module_popular",
        "module_recommendation",
    ])


def test_no_drupal_org_tool_returns_raw_html():
    """The old failure mode dumped 400 lines of a 404 page into the response."""
    import inspect

    source = inspect.getsource(drupal_org)
    assert "e.response.text" not in source


# --- Composer metadata ---------------------------------------------------
#
# updates.drupal.org stopped answering for Drupal 9+ ("No release history
# available"), so releases, dependencies and core compatibility now come from
# packages.drupal.org, whose metadata is delta-encoded.

RAW_PACKAGES = [
    {   # Newest: the complete document.
        "name": "drupal/pathauto",
        "version": "1.15.0",
        "type": "drupal-module",
        "conflict": {"drush/drush": "<12.5.1"},
        "require": {"drupal/core": "^10.2 || ^11", "drupal/token": "*", "drupal/ctools": "*"},
        "dist": {"url": "https://ftp.drupal.org/files/projects/pathauto-8.x-1.15.zip",
                 "reference": "8.x-1.15"},
        "extra": {"drupal": {"version": "8.x-1.15", "datestamp": "1778049296",
                             "security-coverage": {"status": "covered"}}},
    },
    {   # Delta only: name/type inherited, `conflict` removed.
        "version": "1.14.0",
        "require": {"drupal/core": "^10 || ^11", "drupal/token": "^1.0"},
        "dist": {"url": "https://ftp.drupal.org/files/projects/pathauto-8.x-1.14.zip",
                 "reference": "8.x-1.14"},
        "extra": {"drupal": {"version": "8.x-1.14", "datestamp": "1759838097"}},
        "conflict": "__unset",
    },
    {   # `require` omitted: unchanged, so it must come from the previous entry.
        "version": "1.13.0",
        "dist": {"url": "https://ftp.drupal.org/files/projects/pathauto-8.x-1.13.zip",
                 "reference": "8.x-1.13"},
        "extra": {"drupal": {"version": "8.x-1.13"}},
    },
    {   # A release line that predates Drupal 10.
        "version": "1.0.0",
        "require": {"drupal/core": "^7 || ^8"},
        "dist": {"url": "https://ftp.drupal.org/files/projects/pathauto-7.x-1.0.zip",
                 "reference": "7.x-1.0"},
        "extra": {"drupal": {"version": "7.x-1.0"}},
    },
]


def test_minified_entries_inherit_omitted_keys():
    """15 of pathauto's 24 releases omit `require`; reading them raw would
    silently report most releases as having no dependencies."""
    assert "require" not in RAW_PACKAGES[2]

    expanded = drupal_org._expand_minified(RAW_PACKAGES)

    assert expanded[2]["require"] == {"drupal/core": "^10 || ^11", "drupal/token": "^1.0"}
    assert expanded[2]["name"] == "drupal/pathauto"
    assert expanded[2]["type"] == "drupal-module"
    assert "conflict" in expanded[0]
    assert "conflict" not in expanded[1]


def test_minified_expansion_does_not_mutate_the_source():
    drupal_org._expand_minified(RAW_PACKAGES)

    assert "require" not in RAW_PACKAGES[2]
    assert RAW_PACKAGES[0]["conflict"] == {"drush/drush": "<12.5.1"}


@pytest.mark.parametrize(
    ("constraint", "expected"),
    [
        ("^10.2 || ^11", [10, 11]),
        (">=8.3 <11", [8, 11]),
        ("*", []),
        (None, []),
        ("", []),
        ("10.x", [10]),
    ],
)
def test_core_majors_reads_the_drupal_version(constraint, expected):
    assert drupal_org._core_majors(constraint) == expected


def test_composer_releases_are_filtered_by_core():
    entries = drupal_org._expand_minified(RAW_PACKAGES)

    history = drupal_org._parse_composer_packages(entries, "pathauto", "10.x")

    assert history["source"] == "packages.drupal.org"
    assert len(history["releases"]) == 3
    assert all(r["version"] != "7.x-1.0" for r in history["releases"])
    assert history["compatible_release_count"] == 3


def test_composer_releases_finds_the_old_line_for_7x():
    entries = drupal_org._expand_minified(RAW_PACKAGES)

    history = drupal_org._parse_composer_packages(entries, "pathauto", "7.x")

    assert [r["version"] for r in history["releases"]] == ["7.x-1.0"]
    assert history["releases"][0]["core"] == "^7 || ^8"


def test_composer_releases_carry_dependencies_and_security():
    entries = drupal_org._expand_minified(RAW_PACKAGES)

    history = drupal_org._parse_composer_packages(entries, "pathauto", "10.x")
    newest = history["releases"][0]

    assert newest["version"] == "8.x-1.15"
    assert newest["composer_version"] == "1.15.0"
    assert newest["created"] == "1778049296"
    assert newest["core"] == "^10.2 || ^11"
    assert newest["dependencies"] == {"drupal/token": "*", "drupal/ctools": "*"}
    assert newest["security"] == "covered"
    assert "drupal/core" not in newest["dependencies"]


def test_composer_releases_reports_no_match_instead_of_nothing():
    entries = drupal_org._expand_minified(RAW_PACKAGES)

    with pytest.raises(drupal_org.NoCompatibleReleases, match="4 releases"):
        drupal_org._parse_composer_packages(entries, "pathauto", "12.x")


def _tool_functions(**deps: Any) -> dict[str, Any]:
    class FakeMCP:
        def __init__(self) -> None:
            self.fns: dict[str, Any] = {}

        def tool(self, *args: Any, **kwargs: Any):
            def decorate(fn):
                self.fns[fn.__name__] = fn
                return fn

            return decorate

    mcp = FakeMCP()
    drupal_org.register_tools(mcp, **deps)  # type: ignore[arg-type]
    return mcp.fns


@pytest.mark.asyncio
async def test_module_dependencies_returns_the_require_map(monkeypatch):
    async def fake_entries(name: str):
        assert name == "pathauto"
        return drupal_org._expand_minified(RAW_PACKAGES)

    monkeypatch.setattr(drupal_org, "_composer_entries", fake_entries)
    fns = _tool_functions()

    result = await fns["module_dependencies"]("pathauto")

    assert result["version"] == "8.x-1.15"
    assert result["drupal_core"] == "^10.2 || ^11"
    assert result["dependencies"] == {"drupal/token": "*", "drupal/ctools": "*"}
    assert "error" not in result


@pytest.mark.asyncio
async def test_module_dependencies_accepts_a_drupal_version_string(monkeypatch):
    async def fake_entries(name: str):
        return drupal_org._expand_minified(RAW_PACKAGES)

    monkeypatch.setattr(drupal_org, "_composer_entries", fake_entries)
    fns = _tool_functions()

    result = await fns["module_dependencies"]("pathauto", "8.x-1.14")

    assert result["composer_version"] == "1.14.0"
    assert result["dependencies"] == {"drupal/token": "^1.0"}


@pytest.mark.asyncio
async def test_module_dependencies_names_the_known_releases_when_one_is_wrong(monkeypatch):
    async def fake_entries(name: str):
        return drupal_org._expand_minified(RAW_PACKAGES)

    monkeypatch.setattr(drupal_org, "_composer_entries", fake_entries)
    fns = _tool_functions()

    result = await fns["module_dependencies"]("pathauto", "8.x-9.9")

    assert "No release" in result["error"]
    assert "8.x-1.15" in result["error"]


@pytest.mark.asyncio
async def test_release_history_falls_back_to_composer_when_xml_is_dead(monkeypatch):
    """updates.drupal.org answers <error> for every 9.x+ project."""
    called: list[str] = []

    async def dead_xml(name: str, core: str):
        raise RuntimeError(
            f"drupal.org has no release history for {name!r} against core {core!r}: "
            "No release history available"
        )

    async def fake_entries(name: str):
        called.append(name)
        return drupal_org._expand_minified(RAW_PACKAGES)

    monkeypatch.setattr(drupal_org, "_release_history", dead_xml)
    monkeypatch.setattr(drupal_org, "_composer_entries", fake_entries)
    fns = _tool_functions()

    result = await fns["release_history"]("pathauto", "10.x")

    assert result["source"] == "packages.drupal.org"
    assert called == ["pathauto"]
    assert len(result["releases"]) == 3


@pytest.mark.asyncio
async def test_release_history_prefers_updates_drupal_org_when_it_answers(monkeypatch):
    async def live_xml(name: str, core: str):
        return {"project": name, "core": core, "releases": [{"version": "7.x-1.15"}]}

    async def should_not_be_called(name: str):
        raise AssertionError("composer fallback must not be consulted")

    monkeypatch.setattr(drupal_org, "_release_history", live_xml)
    monkeypatch.setattr(drupal_org, "_composer_entries", should_not_be_called)
    fns = _tool_functions()

    result = await fns["release_history"]("pathauto", "7.x")

    assert result["source"] == "updates.drupal.org"
    assert result["releases"] == [{"version": "7.x-1.15"}]


@pytest.mark.asyncio
async def test_module_compatibility_distinguishes_no_match_from_failure(monkeypatch):
    async def dead_xml(name: str, core: str):
        raise RuntimeError("No release history available")

    async def fake_entries(name: str):
        return drupal_org._expand_minified(RAW_PACKAGES)

    monkeypatch.setattr(drupal_org, "_release_history", dead_xml)
    monkeypatch.setattr(drupal_org, "_composer_entries", fake_entries)
    fns = _tool_functions()

    yes = await fns["module_compatibility"]("pathauto", "10.x")
    no = await fns["module_compatibility"]("pathauto", "12.x")

    assert yes["compatible"] is True
    assert yes["release_count"] == 3
    assert yes["core_constraints"] == ["^10.2 || ^11", "^10 || ^11", "^10 || ^11"]

    assert no["compatible"] is False
    assert no["release_count"] == 0
    assert "error" not in no


# --- module_issues_search / module_popular / module_recommendation ----------


def test_issue_keywords_drop_stopwords_and_short_words():
    keywords = drupal_org._issue_keywords("The token is failing for my users!")

    assert keywords == ["token", "failing", "users"]


def test_score_issue_prefers_title_then_body_with_phrase_bonus():
    keywords = ["token", "authentication"]

    title_hit = drupal_org._score_issue(
        "Token authentication fails on login", "", keywords, "token authentication fails on login"
    )
    body_hit = drupal_org._score_issue(
        "Unrelated title", "the token breaks during authentication", keywords, "something else"
    )
    miss = drupal_org._score_issue("Totally unrelated", "", keywords, "something else")

    assert title_hit >= 14  # two title keywords (2+2) + exact phrase bonus (10)
    assert body_hit == 2  # both keywords, body weight only
    assert miss == 0


def test_version_compatible_matrix():
    # Drupal-major-encoded versions are compared strictly.
    assert drupal_org._version_compatible("10.3.x", "10") is True
    assert drupal_org._version_compatible("10.3.x", "11") is False
    assert drupal_org._version_compatible("11.x-1.x-dev", "10") is False
    # Project-era branches ("6.3.x-dev") are not Drupal 6 claims: keep them.
    assert drupal_org._version_compatible("6.3.x-dev", "10") is True
    assert drupal_org._version_compatible("7.x-1.x", "10") is False
    assert drupal_org._version_compatible("7.x-1.x", "7") is True
    # Unknowns never filter.
    assert drupal_org._version_compatible("", "10") is True
    assert drupal_org._version_compatible("dev", "10") is True
    assert drupal_org._version_compatible("10.3.x", None) is True


def test_local_drupal_major_reads_core_version(tmp_path):
    core = tmp_path / "core" / "lib"
    core.mkdir(parents=True)
    (core / "Drupal.php").write_text("<?php const VERSION = '10.2.3';")

    assert drupal_org._local_drupal_major(str(tmp_path)) == "10"
    assert drupal_org._local_drupal_major(str(tmp_path / "missing")) is None
    assert drupal_org._local_drupal_major(None) is None


def test_total_usage_sums_only_digit_release_lines():
    node = {
        "project_usage": {"5.x-1.x": 8, "8.x-5.x": "13161", "total": 999, "odd": "n/a"},
    }

    assert drupal_org._total_usage(node) == 13169
    assert drupal_org._total_usage({}) == 0
    assert drupal_org._total_usage({"project_usage": None}) == 0


def test_match_category_exact_then_substring_then_none():
    terms = [
        {"tid": "104", "name": "E-commerce"},
        {"tid": "20", "name": "Search engine optimization (SEO)"},
    ]

    assert drupal_org._match_category(terms, "e-commerce")["tid"] == "104"
    assert drupal_org._match_category(terms, "SEO")["tid"] == "20"
    assert drupal_org._match_category(terms, "blockchain") is None
    assert drupal_org._match_category(terms, "   ") is None


def _issue_node(**overrides: Any) -> dict[str, Any]:
    node: dict[str, Any] = {
        "title": "Default issue title",
        "url": "https://www.drupal.org/node/1",
        "field_issue_status": "1",
        "field_issue_version": "10.x-1.x-dev",
        "comment_count": 3,
        "changed": 1700000000,
        "body": {"value": "<p>Some body text</p>"},
    }
    node.update(overrides)
    return node


@pytest.mark.asyncio
async def test_module_issues_search_scores_filters_and_links(monkeypatch):
    async def fake_nid(name: str):
        assert name == "webform"
        return "7404"

    async def fake_nodes(params, *, max_pages=1):
        assert params["type"] == "project_issue"
        assert params["field_project"] == "7404"
        return [
            _issue_node(
                title="Token authentication fails during login",
                url="https://www.drupal.org/node/111",
                field_issue_status="3",
            ),
            _issue_node(
                title="Token authentication broken",
                field_issue_version="11.x-1.x-dev",
            ),
            _issue_node(title="Cosmetic tweak for icons"),
        ]

    monkeypatch.setattr(drupal_org, "_project_nid", fake_nid)
    monkeypatch.setattr(drupal_org, "_node_list", fake_nodes)
    fns = _tool_functions()

    result = await fns["module_issues_search"](
        "webform", "token authentication fails", 5, drupal_version="10"
    )

    assert result["keywords"] == ["token", "authentication", "fails"]
    assert result["drupal_version"] == "10"
    # The matching 10.x issue ranks first; the 11.x one is filtered out.
    assert result["results"][0]["url"] == "https://www.drupal.org/node/111"
    assert result["results"][0]["status"] == "Reviewed & tested by community"
    assert len(result["results"]) == 1


@pytest.mark.asyncio
async def test_module_issues_search_falls_back_to_recent_when_no_keyword_matches(monkeypatch):
    async def fake_nid(name: str):
        return "7404"

    async def fake_nodes(params, *, max_pages=1):
        return [_issue_node(title="Cosmetic tweak for icons")]

    monkeypatch.setattr(drupal_org, "_project_nid", fake_nid)
    monkeypatch.setattr(drupal_org, "_node_list", fake_nodes)
    fns = _tool_functions()

    result = await fns["module_issues_search"]("webform", "quantum blockchain sync", 5)

    assert result["count"] == 1
    assert "recently updated" in result["note"]
    assert result["results"][0]["title"] == "Cosmetic tweak for icons"


@pytest.mark.asyncio
async def test_module_issues_search_unknown_project_errors(monkeypatch):
    async def fake_nid(name: str):
        return None

    monkeypatch.setattr(drupal_org, "_project_nid", fake_nid)
    fns = _tool_functions()

    result = await fns["module_issues_search"]("no_such_project_xyz", "anything")

    assert "error" in result


@pytest.mark.asyncio
async def test_module_issues_search_ignores_a_filter_that_hides_everything(monkeypatch):
    async def fake_nid(name: str):
        return "7404"

    async def fake_nodes(params, *, max_pages=1):
        return [
            _issue_node(title="Cosmetic tweak for icons", field_issue_version="11.x-1.x-dev"),
            _issue_node(title="Another minor tweak", field_issue_version="12.x-dev"),
        ]

    monkeypatch.setattr(drupal_org, "_project_nid", fake_nid)
    monkeypatch.setattr(drupal_org, "_node_list", fake_nodes)
    fns = _tool_functions()

    result = await fns["module_issues_search"]("webform", "quantum blockchain sync", 5, drupal_version="10")

    assert result["count"] == 2
    assert "the filter was ignored" in result["note"]


@pytest.mark.asyncio
async def test_module_popular_sorts_by_usage_and_drops_nameless(monkeypatch):
    seen: dict[str, Any] = {}

    async def fake_nodes(params, *, max_pages=1):
        seen.update(params)
        return [
            {"field_project_machine_name": "small", "title": "Small", "url": "u1", "project_usage": {"7.x-1.x": 12}},
            {"field_project_machine_name": "big", "title": "Big", "url": "u2", "project_usage": {"7.x-1.x": "900", "10.x-1.x": 100}},
            {"title": "Nameless"},
        ]

    monkeypatch.setattr(drupal_org, "_node_list", fake_nodes)
    fns = _tool_functions()

    result = await fns["module_popular"](10)

    assert [m["machine_name"] for m in result["results"]] == ["big", "small"]
    assert result["results"][0]["usage"] == 1000
    assert result["count"] == 2
    assert result["category"] is None
    assert "taxonomy_vocabulary_3" not in seen


@pytest.mark.asyncio
async def test_module_popular_resolves_category_to_tid(monkeypatch):
    seen: dict[str, Any] = {}

    async def fake_terms():
        return [{"tid": "20", "name": "Search engine optimization (SEO)"}]

    async def fake_nodes(params, *, max_pages=1):
        seen.update(params)
        return [{"field_project_machine_name": "xmlsitemap", "title": "XML sitemap", "url": "u", "project_usage": {"10.x-1.x": 5}}]

    monkeypatch.setattr(drupal_org, "_category_terms", fake_terms)
    monkeypatch.setattr(drupal_org, "_node_list", fake_nodes)
    fns = _tool_functions()

    result = await fns["module_popular"](5, category="seo")

    assert result["category"] == "Search engine optimization (SEO)"
    assert seen["taxonomy_vocabulary_3"] == "20"


@pytest.mark.asyncio
async def test_module_popular_unknown_category_lists_alternatives(monkeypatch):
    async def fake_terms():
        return [{"tid": "104", "name": "E-commerce"}]

    async def fake_nodes(params, *, max_pages=1):  # pragma: no cover - must not run
        raise AssertionError("node list should not be fetched for a bad category")

    monkeypatch.setattr(drupal_org, "_category_terms", fake_terms)
    monkeypatch.setattr(drupal_org, "_node_list", fake_nodes)
    fns = _tool_functions()

    result = await fns["module_popular"](5, category="blockchain")

    assert "error" in result
    assert result["available"] == ["E-commerce"]


@pytest.mark.asyncio
async def test_module_recommendation_combines_local_and_drupal_org(monkeypatch):
    class FakeIndex:
        def search_modules(self, query: str, limit: int = 5):
            assert query == "oauth login"
            return [{"machine_name": "custom_sso", "title": "Custom SSO", "source": "local"}]

    async def fake_search(query: str):
        return [
            {"machine_name": "simple_oauth", "type": "module", "url": "https://www.drupal.org/project/simple_oauth"},
            {"machine_name": "bootstrap", "type": "theme", "url": "https://www.drupal.org/project/bootstrap"},
        ]

    monkeypatch.setattr(drupal_org, "_search", fake_search)
    fns = _tool_functions(codebase_service=FakeIndex())

    result = await fns["module_recommendation"]("oauth login")

    assert result["local_indexed"] is True
    assert result["local_modules"][0]["machine_name"] == "custom_sso"
    assert [m["machine_name"] for m in result["drupal_org_modules"]] == ["simple_oauth"]
    assert "extending" in result["note"]


@pytest.mark.asyncio
async def test_module_recommendation_works_without_local_index(monkeypatch):
    async def fake_search(query: str):
        return [{"machine_name": "simple_oauth", "type": "module", "url": "u"}]

    monkeypatch.setattr(drupal_org, "_search", fake_search)
    fns = _tool_functions()

    result = await fns["module_recommendation"]("oauth")

    assert result["local_indexed"] is False
    assert result["local_modules"] == []
    assert result["drupal_org_modules"][0]["machine_name"] == "simple_oauth"
