"""Run the JSON:API-engine live smoke test for the D9 source to D11 target."""

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
    async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=60.0) as client:
        response = await client.get(
            f"{url.rstrip('/')}/jsonapi/{resource_type.replace('--', '/')}",
            params={"page[limit]": "100"},
            auth=(user, password),
            headers={"Accept": "application/vnd.api+json"},
        )
        response.raise_for_status()
        return response.json().get("data", [])


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-url", default=os.getenv("LIVE_SOURCE_URL", "https://drupal-mcp-d9-source.ddev.site"))
    parser.add_argument("--source-user", default=os.getenv("LIVE_SOURCE_USER", "admin"))
    parser.add_argument("--source-password", default=os.getenv("LIVE_SOURCE_PASSWORD", "admin"))
    parser.add_argument("--target-env", default=os.getenv("LIVE_TARGET_ENV", ".env.d9d11"))
    parser.add_argument("--migration-id", default="d9d11-live-smoke")
    args = parser.parse_args()

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

    resource_types = ["user--user", "taxonomy_term--departures", "node--article", "node--page"]
    service.create_plan(
        args.migration_id,
        source={"url": args.source_url},
        target={"url": settings.DRUPAL_BASE_URL},
        entities=resource_types,
        notes="D9 to D11 live engine smoke test",
    )

    for resource_type in resource_types:
        print(f"Analyzing {resource_type}...")
        await service.analyze_source_site(
            source_url=args.source_url,
            resource_type=resource_type,
            token=None,
            migration_id=args.migration_id,
            verify_tls=False,
        )

    print("Dry run:")
    dry_result = await service.run_migration(args.migration_id, entity_types=resource_types, dry_run=True, verify_tls=False)
    print(dry_result["totals"])

    print("Live run:")
    live_result = await service.run_migration(args.migration_id, entity_types=resource_types, dry_run=False, verify_tls=False)
    print(live_result["totals"])
    if live_result.get("totals", {}).get("failed"):
        for item in live_result.get("results", []):
            if isinstance(item, dict) and item.get("failed"):
                print("  failure:", item.get("entity_type"), item.get("results"))

    print("Status:", service.migration_status(args.migration_id))
    print("Reconciliation:", await service.reconcile_counts(args.migration_id, resource_types))


if __name__ == "__main__":
    asyncio.run(main())