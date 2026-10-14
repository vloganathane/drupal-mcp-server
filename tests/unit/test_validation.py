"""Tests for input validation, including the SQL guard for `db_query`."""

import pytest

from drupal_mcp_server.validation import (
    sanitize_string,
    validate_email,
    validate_identifier,
    validate_integer,
    validate_pagination,
    validate_path_prefix,
    validate_single_select,
    validate_table_name,
    validate_url,
    validate_where_clause,
)


class TestValidateSingleSelect:
    """`db_query` guarded with startswith("SELECT") and nothing else.

    Against a real database, `SELECT 1; DROP TABLE probe` was accepted by that
    check and actually dropped the probe table. The tool therefore asked
    whether the first word was SELECT rather than what would execute.
    """

    @pytest.mark.parametrize(
        "query",
        [
            "SELECT * FROM users",
            "select nid, title from node_field_data limit 10",
            "SELECT COUNT(*) FROM node",
            "SELECT MAX(updated) FROM node_field_data WHERE status = 1",
            # A trailing semicolon is ordinary style, not a second statement.
            "SELECT * FROM node;",
            # Column names that collide with DML keywords, with and without
            # backticks: rejecting these would break legitimate queries.
            "SELECT created_at FROM node",
            "SELECT `created` FROM node",
            "SELECT name, set_count FROM node",
            # The string function, as opposed to REPLACE INTO.
            "SELECT REPLACE(title, 'a', 'b') FROM node",
        ],
    )
    def test_allows_single_read_only_select(self, query: str) -> None:
        assert validate_single_select(query) is None

    @pytest.mark.parametrize(
        "query",
        [
            "SELECT 1; DROP TABLE users",
            "SELECT 1; DELETE FROM users",
            "SELECT 1; SELECT 2",
            "DELETE FROM users",
            "DROP TABLE users",
            "UPDATE users SET name='x'",
            "INSERT INTO users VALUES (1)",
            "TRUNCATE TABLE users",
            "SHOW TABLES",
        ],
    )
    def test_rejects_writes_and_second_statements(self, query: str) -> None:
        assert validate_single_select(query) is not None

    @pytest.mark.parametrize(
        "query",
        [
            "SELECT * FROM users -- comment",
            "SELECT * FROM users # comment",
            "SELECT 1 /* hide */ ; DELETE FROM users",
        ],
    )
    def test_rejects_comments_that_could_hide_a_statement(self, query: str) -> None:
        assert validate_single_select(query) is not None

    @pytest.mark.parametrize(
        "query",
        [
            # A single SELECT can still read or write files without ever
            # needing a second statement.
            "SELECT LOAD_FILE('/etc/passwd')",
            "SELECT title INTO OUTFILE '/tmp/x' FROM node",
            "SELECT title INTO DUMPFILE '/tmp/y' FROM node",
            "LOAD DATA INFILE '/etc/passwd' INTO TABLE users",
        ],
    )
    def test_rejects_file_access_from_within_a_select(self, query: str) -> None:
        assert validate_single_select(query) is not None

    @pytest.mark.parametrize(
        "query",
        [
            "SELECT * FROM node WHERE title = 'a; DROP TABLE x'",
            "SELECT * FROM node WHERE title = 'drop table'",
            "SELECT title FROM node WHERE body LIKE '%delete%'",
        ],
    )
    def test_literal_contents_are_not_mistaken_for_sql(self, query: str) -> None:
        """Quoted text may legitimately contain the very words we reject."""
        assert validate_single_select(query) is None


class TestWhereClause:
    """The WHERE clause reaches SQL by string interpolation in `db_count`."""

    @pytest.mark.parametrize(
        "where",
        [
            "a = 1",
            "nid = 1",
            "status != 0",
            "nid >= 5",
            "nid <= 5",
            "title LIKE 'a%'",
            "name = 'admin'",
        ],
    )
    def test_accepts_simple_conditions(self, where: str) -> None:
        assert validate_where_clause(where) is None

    @pytest.mark.parametrize(
        "where",
        [
            # The regex the tool used inline required a two-character column
            # name, so a legal single-character column was rejected there.
            "id = 1; DROP TABLE users",
            "id = 'a' OR '1'='1'",
            "id = (SELECT password FROM users)",
            "1=1 OR 1=1",
            "id = 1 -- comment",
        ],
    )
    def test_rejects_injection(self, where: str) -> None:
        assert validate_where_clause(where) is not None


class TestTableName:
    def test_accepts_a_plain_identifier(self) -> None:
        assert validate_table_name("node_field_data") is None

    @pytest.mark.parametrize(
        "table",
        ["users; DROP TABLE x", "1users", "node--", "node field", "node.field", ""],
    )
    def test_rejects_anything_that_is_not_a_bare_identifier(self, table: str) -> None:
        assert validate_table_name(table) is not None


class TestUrl:
    @pytest.mark.parametrize("url", ["https://example.com", "http://example.com/path"])
    def test_accepts_http_and_https(self, url: str) -> None:
        assert validate_url(url) is None

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "file:///etc/passwd",
            "data:text/html,<script>",
            "example.com",
        ],
    )
    def test_rejects_other_schemes_and_missing_hosts(self, url: str) -> None:
        assert validate_url(url) is not None

    def test_allowed_schemes_can_be_narrowed(self) -> None:
        assert validate_url("https://example.com", allowed_schemes=("http",)) is not None


class TestSanitizeString:
    def test_accepts_ordinary_text(self) -> None:
        assert sanitize_string("hello world") is None

    @pytest.mark.parametrize("char", [";", "|", "&", "$", "`", "\\"])
    def test_rejects_shell_metacharacters(self, char: str) -> None:
        assert sanitize_string(f"value{char}injected") is not None

    def test_rejects_overlong_input(self) -> None:
        assert sanitize_string("x" * 256) is not None

    def test_max_length_is_configurable(self) -> None:
        assert sanitize_string("x" * 11, max_length=10) is not None
        assert sanitize_string("x" * 10, max_length=10) is None

    def test_reports_wrong_type(self) -> None:
        assert "Expected string" in str(sanitize_string(42))  # type: ignore[arg-type]


class TestMiscValidators:
    @pytest.mark.parametrize(
        "name,field,expected",
        [
            ("article", "bundle", None),
            ("my-field", "bundle", "Invalid bundle: my-field"),
            ("1article", "bundle", "Invalid bundle: 1article"),
        ],
    )
    def test_validate_identifier(self, name: str, field: str, expected: str | None) -> None:
        assert validate_identifier(name, field) == expected

    @pytest.mark.parametrize(
        "email,ok",
        [("a@b.co", True), ("first.last@example.com", True),
         ("nope", False), ("a@b", False), ("@b.co", False), ("a@@b.co", False)],
    )
    def test_validate_email(self, email: str, ok: bool) -> None:
        assert (validate_email(email) is None) is ok

    @pytest.mark.parametrize(
        "limit,offset,ok",
        [
            (1, 0, True),
            (500, 0, True),
            (501, 0, False),
            (0, 0, False),
            (-1, 0, False),
            (10, -1, False),
            (10, 10, True),
        ],
    )
    def test_validate_pagination(self, limit: int, offset: int, ok: bool) -> None:
        assert (validate_pagination(limit, offset) is None) is ok

    def test_validate_path_prefix(self) -> None:
        assert validate_path_prefix("/node/1", ("/node", "/user")) is None
        assert validate_path_prefix("/admin/config", ("/node", "/user")) is not None

    @pytest.mark.parametrize(
        "value,ok",
        [(5, True), (0, True), (4, True), (11, False), (-1, False),
         ("5", False), (5.5, False)],
    )
    def test_validate_integer(self, value: object, ok: bool) -> None:
        assert (validate_integer(value, 0, 10, "limit") is None) is ok

    def test_validate_integer_names_the_field_in_the_error(self) -> None:
        assert "limit must be an integer" in str(validate_integer("x", 0, 10, "limit"))
