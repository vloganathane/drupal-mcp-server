"""Configuration settings for Drupal MCP Server."""

from functools import lru_cache

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
    DRUPAL_USERNAME: str | None = Field(default=None, description="Basic auth username")
    DRUPAL_PASSWORD: str | None = Field(default=None, description="Basic auth password")
    DRUPAL_OAUTH_CLIENT_ID: str | None = Field(default=None, description="OAuth client ID")
    DRUPAL_OAUTH_CLIENT_SECRET: str | None = Field(default=None, description="OAuth client secret")
    DRUPAL_OAUTH_TOKEN_URL: str | None = Field(default=None, description="OAuth token endpoint URL")
    DRUPAL_API_TOKEN: str | None = Field(
        default=None,
        description="Pre-obtained bearer token, sent as Authorization: Bearer",
    )
    DRUPAL_VERIFY_SSL: bool = Field(
        default=True,
        description="Verify TLS certificates. Set false for self-signed dev certs (DDEV, Lando).",
    )
    DRUPAL_HTTP_TIMEOUT: int = Field(
        default=60,
        description="Timeout in seconds for one outbound HTTP request to Drupal",
    )
    DRUPAL_HTTP_RETRIES: int = Field(
        default=2,
        description=(
            "Extra attempts for GET requests on transient failures (timeout, "
            "connection reset, 502/503/504). Mutations are never retried: a "
            "timed-out POST may already have landed."
        ),
    )

    # Drush
    DRUSH_PATH: str = Field(
        default="drush",
        description=(
            "Drush command. May include arguments, e.g. 'ddev drush' "
            "(start the MCP server from the project directory)."
        ),
    )
    DRUSH_ALIAS: str = Field(default="@self", description="Drush site alias")
    DRUSH_TIMEOUT: int = Field(
        default=120,
        description="Timeout in seconds for one drush command. Not retried: drush commands mutate.",
    )

    # Local codebase analysis (codebase index, theme templates, local scans)
    DRUPAL_ROOT: str | None = Field(
        default=None,
        description=(
            "Local path to the Drupal codebase. Enables the codebase index, "
            "hook/module search, theme template, and local file analysis tools."
        ),
    )
    DRUPAL_MODULES_PATH: str = Field(
        default="modules",
        description="Modules directory relative to DRUPAL_ROOT ('web/modules' for composer installs)",
    )

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
    OPENAI_API_KEY: str | None = Field(default=None, description="OpenAI API key")
    OPENAI_MODEL: str = Field(default="gpt-4o-mini", description="OpenAI model name")

    # Anthropic
    ANTHROPIC_API_KEY: str | None = Field(default=None, description="Anthropic API key")
    ANTHROPIC_MODEL: str = Field(default="claude-3-5-haiku-20241022", description="Anthropic model name")

    # NVIDIA NIM
    NVIDIA_NIM_API_KEY: str | None = Field(default=None, description="NVIDIA NIM API key")
    NVIDIA_NIM_BASE_URL: str = Field(default="https://integrate.api.nvidia.com/v1", description="NVIDIA NIM base URL")
    NVIDIA_NIM_MODEL: str = Field(default="nvidia/nemotron-3-ultra", description="NVIDIA NIM model name")

    # MCP Server
    MCP_SERVER_NAME: str = Field(default="drupal-mcp-server", description="MCP server name")
    MCP_TRANSPORT: str = Field(default="stdio", description="MCP transport type")
    MCP_HOST: str = Field(
        default="127.0.0.1",
        description=(
            "MCP HTTP bind host. Loopback by default: the tools execute "
            "drush/composer/shell commands, so a network-visible bind is a "
            "deliberate decision, not a default."
        ),
    )
    MCP_PORT: int = Field(default=8000, description="MCP HTTP port")
    MCP_ALLOW_INSECURE_HTTP: bool = Field(
        default=False,
        description=(
            "Permit an HTTP transport without OAuth configured. The server "
            "refuses to serve command-execution tools over a socket "
            "unauthenticated unless this is set."
        ),
    )
    MCP_LOG_LEVEL: str = Field(default="INFO", description="Logging level")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()