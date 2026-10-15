"""Migration orchestration service."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class MigrationService:
    """Orchestrates multi-step Drupal migrations using persisted plans."""

    def __init__(
        self,
        settings: Any = None,
        jsonapi_client: Any = None,
        drush_client: Any = None,
        ai_service: Any = None,
        site_manager: Any = None,
        storage_dir: Any = None,
    ):
        self.settings = settings
        self.jsonapi = jsonapi_client
        self.drush = drush_client
        self.ai = ai_service
        self.site_manager = site_manager
        if storage_dir is None:
            storage_dir = getattr(settings, "MIGRATION_STORAGE_DIR", None) if settings else None
        self.storage_dir = Path(storage_dir or ".drupal-mcp/migrations")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_id(migration_id: str) -> None:
        if not migration_id or not re.fullmatch(r"[A-Za-z0-9_.-]+", migration_id):
            raise ValueError(
                "migration_id must contain only letters, numbers, dots, dashes or underscores"
            )

    def _plan_path(self, migration_id: str) -> Path:
        self._validate_id(migration_id)
        return self.storage_dir / f"{migration_id}.json"

    def create_plan(
        self,
        migration_id: str,
        source: dict[str, Any] | None = None,
        target: dict[str, Any] | None = None,
        entities: list[str] | None = None,
        field_mappings: dict[str, Any] | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        self._validate_id(migration_id)
        plan = {
            "migration_id": migration_id,
            "source": source or {},
            "target": target or {},
            "entities": entities or [],
            "field_mappings": field_mappings or {},
            "notes": notes,
            "source_counts": {},
            "state": {
                "status": "planned",
                "created_at": self._now(),
                "updated_at": self._now(),
                "entities": {},
            },
        }
        self._save(plan)
        return self._summary(plan)

    def get_plan(self, migration_id: str) -> dict[str, Any]:
        path = self._plan_path(migration_id)
        if not path.exists():
            return {"error": f"Migration plan not found: {migration_id}"}
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {"error": f"Invalid migration plan: {migration_id}"}
        return data

    def list_plans(self) -> list[dict[str, Any]]:
        plans = []
        for path in sorted(self.storage_dir.glob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as fh:
                    plan = json.load(fh)
                plans.append(self._summary(plan))
            except (OSError, json.JSONDecodeError):
                continue
        return plans

    def migration_status(self, migration_id: str) -> dict[str, Any]:
        plan = self.get_plan(migration_id)
        if "error" in plan:
            return plan
        state = plan["state"]
        entity_states = state.get("entities", {})
        totals = {"processed": 0, "created": 0, "updated": 0, "failed": 0, "skipped": 0}
        for values in entity_states.values():
            for key in totals:
                totals[key] += int(values.get(key, 0))
        return {
            "migration_id": migration_id,
            "status": state.get("status", "unknown"),
            "entities": entity_states,
            "totals": totals,
            "entity_types": plan.get("entities", []),
            "created_at": state.get("created_at"),
            "updated_at": state.get("updated_at"),
        }

    def record_entity_result(
        self,
        migration_id: str,
        entity_type: str,
        legacy_id: str,
        target_id: str | None = None,
        status: str = "created",
        error: str | None = None,
    ) -> dict[str, Any]:
        plan = self.get_plan(migration_id)
        if "error" in plan:
            return plan
        entity_state = (
            plan["state"]
            .setdefault("entities", {})
            .setdefault(
                entity_type,
                {
                    "processed": 0,
                    "created": 0,
                    "updated": 0,
                    "failed": 0,
                    "skipped": 0,
                    "records": {},
                },
            )
        )
        entity_state["processed"] += 1
        if status in entity_state:
            entity_state[status] += 1
        if legacy_id and target_id:
            entity_state.setdefault("records", {})[str(legacy_id)] = target_id
        if error:
            entity_state.setdefault("errors", []).append({"legacy_id": legacy_id, "error": error})
        self._touch(plan)
        self._save(plan)
        return self.migration_status(migration_id)

    async def analyze_source_site(
        self,
        source_url: str,
        resource_type: str,
        token: str | None = None,
        migration_id: str | None = None,
    ) -> dict[str, Any]:
        import httpx

        base = source_url.rstrip("/")
        path = resource_type.replace("--", "/")
        url = f"{base}/jsonapi/{path}"
        headers = {"Accept": "application/vnd.api+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, params={"page[limit]": "1"}, headers=headers)
            response.raise_for_status()
            body = response.json()
        data = body.get("data") or []
        first = data[0] if data and isinstance(data[0], dict) else {}
        attributes = list((first.get("attributes") or {}).keys())
        relationships = list((first.get("relationships") or {}).keys())
        count = (body.get("meta") or {}).get("count")
        if count is None:
            count = len(data)
        result = {
            "source_url": base,
            "resource_type": resource_type,
            "count": count,
            "attributes": attributes,
            "relationships": relationships,
        }
        if migration_id:
            plan = self.get_plan(migration_id)
            if "error" not in plan:
                plan.setdefault("source_counts", {})[resource_type] = count
                self._touch(plan)
                self._save(plan)
        return result

    async def reconcile_counts(
        self,
        migration_id: str,
        target_resource_types: list[str] | None = None,
    ) -> dict[str, Any]:
        plan = self.get_plan(migration_id)
        if "error" in plan:
            return plan
        target_types = target_resource_types or plan.get("entities", [])
        comparison = {}
        for resource_type in target_types:
            count = await self._target_count(resource_type)
            comparison[resource_type] = {
                "source": (plan.get("source_counts") or {}).get(resource_type),
                "target": count,
            }
        return {"migration_id": migration_id, "comparison": comparison}

    async def _target_count(self, resource_type: str) -> int | None:
        if not self.jsonapi:
            return None
        try:
            response = await self.jsonapi.get_resource(resource_type, {"page[limit]": "0"})
        except Exception:
            return None
        if isinstance(response, dict):
            if "meta" in response and isinstance(response["meta"], dict):
                count = response["meta"].get("count")
                if count is not None:
                    return int(count)
            data = response.get("data")
            if isinstance(data, list):
                return len(data)
        if isinstance(response, list):
            return len(response)
        return None

    async def migrate_records(
        self,
        migration_id: str,
        entity_type: str,
        records: list[dict[str, Any]],
        field_mapping: dict[str, str] | None = None,
        idempotency_key: str = "id",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        plan = self.get_plan(migration_id)
        if "error" in plan:
            return plan
        if not self.jsonapi:
            return {"error": "JSON:API client not available"}

        entity_state = (
            plan["state"]
            .setdefault("entities", {})
            .setdefault(
                entity_type,
                {
                    "processed": 0,
                    "created": 0,
                    "updated": 0,
                    "failed": 0,
                    "skipped": 0,
                    "records": {},
                    "errors": [],
                },
            )
        )
        field_mapping = field_mapping or plan.get("field_mappings", {}).get(entity_type, {})
        created = updated = failed = skipped = 0
        results: list[dict[str, Any]] = []

        for record in records or []:
            legacy_id = self._legacy_id(record, idempotency_key)
            attributes = self._extract_attributes(record)
            attributes = self._apply_mapping(attributes, field_mapping)
            attributes = {
                key: value
                for key, value in attributes.items()
                if not key.startswith("drupal_internal__")
            }

            target_id = entity_state.get("records", {}).get(legacy_id) if legacy_id else None
            if dry_run:
                results.append(
                    {
                        "legacy_id": legacy_id,
                        "target_id": target_id,
                        "action": "would_update" if target_id else "would_create",
                        "success": True,
                    }
                )
                skipped += 1
                continue

            payload = {"type": entity_type, "attributes": attributes}
            try:
                if target_id:
                    response = await self.jsonapi.update_resource(entity_type, target_id, payload)
                    action = "updated"
                else:
                    response = await self.jsonapi.create_resource(entity_type, payload)
                    action = "created"
                    new_id = self._response_id(response)
                    if new_id:
                        target_id = new_id
                        entity_state.setdefault("records", {})[legacy_id] = new_id
            except Exception as exc:  # noqa: BLE001 - report per-record failure
                response = {"error": str(exc)}
                action = "failed"

            success = not (isinstance(response, dict) and response.get("error"))
            if success:
                if action == "created":
                    created += 1
                elif action == "updated":
                    updated += 1
            else:
                failed += 1
                entity_state.setdefault("errors", []).append(
                    {
                        "legacy_id": legacy_id,
                        "error": response.get("error")
                        if isinstance(response, dict)
                        else str(response),
                    }
                )

            results.append(
                {
                    "legacy_id": legacy_id,
                    "target_id": target_id,
                    "action": action,
                    "success": success,
                }
            )

        entity_state["processed"] += len(records or [])
        entity_state["created"] += created
        entity_state["updated"] += updated
        entity_state["failed"] += failed
        entity_state["skipped"] += skipped
        self._touch(plan)
        self._save(plan)
        return {
            "migration_id": migration_id,
            "entity_type": entity_type,
            "processed": len(records or []),
            "created": created,
            "updated": updated,
            "failed": failed,
            "skipped": skipped,
            "results": results,
        }

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def _touch(self, plan: dict[str, Any]) -> None:
        plan["state"]["updated_at"] = self._now()

    def _save(self, plan: dict[str, Any]) -> None:
        path = self._plan_path(plan["migration_id"])
        with path.open("w", encoding="utf-8") as fh:
            json.dump(plan, fh, indent=2, sort_keys=True)

    def _summary(self, plan: dict[str, Any]) -> dict[str, Any]:
        state = plan.get("state", {})
        return {
            "migration_id": plan["migration_id"],
            "entities": plan.get("entities", []),
            "status": state.get("status", "unknown"),
            "updated_at": state.get("updated_at"),
            "notes": plan.get("notes", ""),
        }

    @staticmethod
    def _legacy_id(record: dict[str, Any], idempotency_key: str) -> str | None:
        if not isinstance(record, dict):
            return None
        if idempotency_key in record:
            return str(record[idempotency_key])
        attrs = record.get("attributes")
        if isinstance(attrs, dict) and idempotency_key in attrs:
            return str(attrs[idempotency_key])
        if "id" in record:
            return str(record["id"])
        return None

    @staticmethod
    def _extract_attributes(record: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(record, dict):
            return {}
        if isinstance(record.get("attributes"), dict):
            result = dict(record["attributes"])
        else:
            result = {
                key: value
                for key, value in record.items()
                if key not in {"id", "type", "meta", "relationships", "links"}
            }
        if isinstance(record.get("relationships"), dict):
            result["_relationships"] = record["relationships"]
        return result

    @staticmethod
    def _apply_mapping(attributes: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
        result = dict(attributes)
        for source_field, target_field in (mapping or {}).items():
            if source_field in attributes:
                result[target_field] = attributes[source_field]
                if source_field != target_field:
                    result.pop(source_field, None)
        return result

    @staticmethod
    def _response_id(response: Any) -> str | None:
        if isinstance(response, dict):
            data = response.get("data")
            if isinstance(data, dict):
                return data.get("id")
            if isinstance(data, list) and data and isinstance(data[0], dict):
                return data[0].get("id")
        return None
