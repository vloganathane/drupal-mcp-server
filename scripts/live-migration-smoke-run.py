"""Run a minimal end-to-end migration smoke test against DDEV source/target sites.

This script is intentionally outside of CI. It expects:
  - source and target sites created by scripts/live-migration-smoke.sh
  - drupal-mcp-server installed in the active virtual environment

Example:
  LIVE_SOURCE_URL=https://drupal-mcp-source.ddev.site \
  LIVE_TARGET_ENV=/path/to/repo/.env.live-smoke \
  python scripts/live-migration-smoke-run.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import httpx

from drupal_mcp_server.auth import AuthManager
from drupal_mcp_server.clients import JSONAPIClient
from drupal_mcp_server.config import get_settings
from drupal_mcp_server.server import _login_session
from drupal_mcp_server.services.migration_service import MigrationService


async def fetch_source(url: str, resource_type: str, user: str, password: str) -> list[dict]:
    path = resource_type.replace("--", "/")
    async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=60.0) as client:
        response = await client.get(
            f"{url.rstrip('/')}/jsonapi/{path}",
            params={"page[limit]": "100"},
            auth=(user, password),
            headers={"Accept": "application/vnd.api+json"},
        )
        response.raise_for_status()
        return response.json().get("data", [])


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-url", default=os.getenv("LIVE_SOURCE_URL", "https://drupal-mcp-source.ddev.site")
    )
    parser.add_argument("--source-user", default=os.getenv("LIVE_SOURCE_USER", "admin"))
    parser.add_argument("--source-password", default=os.getenv("LIVE_SOURCE_PASSWORD", "admin"))
    parser.add_argument("--target-env", default=os.getenv("LIVE_TARGET_ENV", ".env.live-smoke"))
    parser.add_argument("--migration-id", default="ddev-live-smoke")
    args = parser.parse_args()

    # Load target settings from the generated env file.
    env_path = Path(args.target_env)
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

    settings = get_settings()
    auth_manager = AuthManager(settings)
    await _login_session(auth_manager)
    jsonapi = JSONAPIClient(settings, auth_manager)
    service = MigrationService(settings=settings, jsonapi_client=jsonapi)

    source_url = args.source_url
    plan = service.create_plan(
        args.migration_id,
        source={"url": source_url},
        target={"url": settings.DRUPAL_BASE_URL},
        entities=["user--user", "taxonomy_term--smoke_vocab", "node--article"],
        notes="DDEV live smoke migration",
    )
    print("Created plan:", plan["migration_id"])

    source_types = ["user--user", "taxonomy_term--smoke_vocab", "node--article"]
    for resource_type in source_types:
        print(f"Analyzing source {resource_type}...")
        analysis = await service.analyze_source_site(
            source_url=source_url,
            resource_type=resource_type,
            token=None,
            migration_id=args.migration_id,
            verify_tls=False,
        )
        print("  source count:", analysis.get("count"))

    for resource_type in source_types:
        print(f"Migrating {resource_type}...")
        records = await fetch_source(
            source_url, resource_type, args.source_user, args.source_password
        )
        result = await service.migrate_records(
            args.migration_id,
            entity_type=resource_type,
            records=records,
            dry_run=False,
        )
        print(
            f"  processed={result.get('processed')} created={result.get('created')} "
            f"updated={result.get('updated')} failed={result.get('failed')}"
        )
        if result.get("failed", 0):
            print("  errors:")
            for item in result.get("results", []):
                if not item.get("success"):
                    print("   ", item)

    print("Status:", service.migration_status(args.migration_id))
    print("Reconciliation:", await service.reconcile_counts(args.migration_id))


if __name__ == "__main__":
    asyncio.run(main())
