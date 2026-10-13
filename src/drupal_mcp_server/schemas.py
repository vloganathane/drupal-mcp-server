"""Pydantic schemas for MCP tool inputs and outputs.

These schemas provide structured validation for complex tool parameters
that currently use dict[str, Any]. Adopt these in new and refactored tools.
"""

from typing import Any

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """Standard pagination parameters."""

    page_limit: int = Field(default=50, ge=1, le=500, description="Items per page")
    page_offset: int = Field(default=0, ge=0, description="Offset from start")


class NodeIdentifier(BaseModel):
    """Reference to a Drupal node."""

    nid: str = Field(description="Node ID or UUID")
    bundle: str | None = Field(default=None, description="Content type bundle")


class FieldMapping(BaseModel):
    """Mapping between source and target fields."""

    source: str = Field(description="Source field name")
    target: str = Field(description="Target Drupal field name")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    notes: str | None = Field(default=None, description="Conversion notes")


class MigrationConfig(BaseModel):
    """Migration configuration parameters."""

    source_plugin: str = Field(default="d7_node", description="Source plugin ID")
    destination_bundle: str = Field(description="Target bundle")
    dependencies: dict[str, list[str]] = Field(default_factory=dict)


class AIAnalysisResult(BaseModel):
    """Standard AI analysis result format."""

    duplicates: list[str] = Field(default_factory=list)
    malformed: list[dict[str, Any]] = Field(default_factory=list)


class ToolErrorResponse(BaseModel):
    """Standard error response from MCP tools."""

    error: str = Field(description="Error message")
    code: str = Field(default="ERROR", description="Error code")
    details: dict[str, Any] | None = Field(default=None)
