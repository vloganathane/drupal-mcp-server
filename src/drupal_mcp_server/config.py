"""Configuration settings for Drupal MCP Server."""

from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Drupal Connection
    DRUPAL_BASE_URL: str = Field(default="http://localhost", description="Base URL of Drupal site")
    DRUPAL_JSONAPI_PATH: str = Field(default="/jsonapi", description="JSON:API endpoint path")
    DRUPAL_GRAPHQL_PATH: str = Field(default="/graphql", description="GraphQL endpoint path")
    DRUPAL_USERNAME: Optional[str] = Field(default=None, description="Basic auth username")
    DRUPAL_PASSWORD: Optional[str] = Field(default=None, description="Basic auth password")
    DRUPAL_OAUTH_CLIENT_ID: Optional[str] = Field(default=None, description="OAuth client ID")
    DRUPAL_OAUTH_CLIENT_SECRET: Optional[str] = Field(default=None, description="OAuth client secret")
    DRUPAL_OAUTH_TOKEN_URL: Optional[str] = Field(default=None, description="OAuth token endpoint URL")

    # Drush
    DRUSH_PATH: str = Field(default="drush", description="Path to drush executable")
    DRUSH_ALIAS: str = Field(default="@self", description="Drush site alias")

    # DDEV
    DDEV_BINARY: str = Field(default="ddev", description="Path to ddev executable")

    # AI Providers
    DEFAULT_AI_PROVIDER: str = Field(default="ollama", description="Default AI provider")
    AI_ENABLED: bool = Field(default=True, description="Enable AI-enhanced tools")
    AI_FALLBACK_TO_CORE: bool = Field(default=True, description="Fallback to core tools if AI fails")
    AI_TIMEOUT: int = Field(default=60, description="AI request timeout in seconds")

    # Ollama
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434", description="Ollama API base URL")
    OLLAMA_MODEL: str = Field(default="llama3.2:3b", description="Ollama model name")

    # OpenAI
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key")
    OPENAI_MODEL: str = Field(default="gpt-4o-mini", description="OpenAI model name")

    # Anthropic
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, description="Anthropic API key")
    ANTHROPIC_MODEL: str = Field(default="claude-3-5-haiku-20241022", description="Anthropic model name")

    # NVIDIA NIM
    NVIDIA_NIM_API_KEY: Optional[str] = Field(default=None, description="NVIDIA NIM API key")
    NVIDIA_NIM_BASE_URL: str = Field(default="https://integrate.api.nvidia.com/v1", description="NVIDIA NIM base URL")
    NVIDIA_NIM_MODEL: str = Field(default="nvidia/nemotron-3-ultra", description="NVIDIA NIM model name")

    # MCP Server
    MCP_SERVER_NAME: str = Field(default="drupal-mcp-server", description="MCP server name")
    MCP_TRANSPORT: str = Field(default="stdio", description="MCP transport type")
    MCP_HOST: str = Field(default="0.0.0.0", description="MCP HTTP host")
    MCP_PORT: int = Field(default=8000, description="MCP HTTP port")
    MCP_LOG_LEVEL: str = Field(default="INFO", description="Logging level")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()