"""Tests for the pydantic schemas intended for new and refactored tools."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from drupal_mcp_server.schemas import (
    AIAnalysisResult,
    FieldMapping,
    MigrationConfig,
    NodeIdentifier,
    PaginationParams,
    ToolErrorResponse,
)


class TestPaginationParams:
    def test_defaults(self) -> None:
        p = PaginationParams()
        assert p.page_limit == 50
        assert p.page_offset == 0

    @pytest.mark.parametrize("limit", [0, -1, 501])
    def test_page_limit_bounds(self, limit: int) -> None:
        with pytest.raises(PydanticValidationError):
            PaginationParams(page_limit=limit)

    @pytest.mark.parametrize("offset", [-1, -100])
    def test_page_offset_must_not_be_negative(self, offset: int) -> None:
        with pytest.raises(PydanticValidationError):
            PaginationParams(page_offset=offset)

    @pytest.mark.parametrize("limit", [1, 500])
    def test_page_limit_accepts_the_inclusive_ends(self, limit: int) -> None:
        assert PaginationParams(page_limit=limit).page_limit == limit


class TestNodeIdentifier:
    def test_requires_a_nid(self) -> None:
        with pytest.raises(PydanticValidationError):
            NodeIdentifier()  # type: ignore[call-arg]

    def test_bundle_is_optional(self) -> None:
        assert NodeIdentifier(nid="1").bundle is None

    def test_bundle_is_recorded_when_given(self) -> None:
        assert NodeIdentifier(nid="1", bundle="article").bundle == "article"


class TestFieldMapping:
    def test_confidence_defaults_to_high(self) -> None:
        assert FieldMapping(source="title", target="title").confidence == 0.95

    @pytest.mark.parametrize("value", [-0.1, 1.1])
    def test_confidence_is_a_probability(self, value: float) -> None:
        with pytest.raises(PydanticValidationError):
            FieldMapping(source="a", target="b", confidence=value)

    @pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
    def test_confidence_accepts_its_full_range(self, value: float) -> None:
        assert FieldMapping(source="a", target="b", confidence=value).confidence == value

    def test_notes_is_optional(self) -> None:
        assert FieldMapping(source="a", target="b").notes is None


class TestMigrationConfig:
    def test_source_plugin_defaults(self) -> None:
        assert MigrationConfig(destination_bundle="article").source_plugin == "d7_node"

    def test_requires_a_destination_bundle(self) -> None:
        with pytest.raises(PydanticValidationError):
            MigrationConfig()  # type: ignore[call-arg]

    def test_dependencies_default_to_empty(self) -> None:
        assert MigrationConfig(destination_bundle="article").dependencies == {}


class TestAIAnalysisResult:
    def test_empty_by_default(self) -> None:
        r = AIAnalysisResult()
        assert r.duplicates == []
        assert r.malformed == []


class TestToolErrorResponse:
    def test_defaults(self) -> None:
        r = ToolErrorResponse(error="boom")
        assert r.code == "ERROR"
        assert r.details is None

    def test_records_details(self) -> None:
        r = ToolErrorResponse(error="boom", code="NOT_FOUND", details={"id": 1})
        assert r.code == "NOT_FOUND"
        assert r.details == {"id": 1}
