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
        verify_tls: bool = True,
        username: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        import httpx

        base = source_url.rstrip("/")
        path = resource_type.replace("--", "/")
        url = f"{base}/jsonapi/{path}"
        headers = {"Accept": "application/vnd.api+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        auth = (username, password) if username and password else None
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, verify=verify_tls) as client:
            response = await client.get(
                url, params={"page[limit]": "1"}, headers=headers, auth=auth
            )
            response.raise_for_status()
            body = response.json()
        data = body.get("data") or []
        first = data[0] if data and isinstance(data[0], dict) else {}
        attributes = list((first.get("attributes") or {}).keys())
        relationships = list((first.get("relationships") or {}).keys())
        # JSON:API exposes no total count, so a single-record probe cannot
        # produce one; count by walking the collection instead.
        count = (body.get("meta") or {}).get("count")
        if count is None:
            count = await self._count_collection(
                base_url=base,
                resource_type=resource_type,
                token=token,
                verify_tls=verify_tls,
                username=username,
                password=password,
            )
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
        """Count records of a resource type on the target site.

        JSON:API exposes no total count and rejects ``page[limit]=0``, so the
        collection must be walked using the authenticated client.
        """
        if not self.jsonapi:
            return None
        try:
            count = 0
            response = await self.jsonapi.get_resource(resource_type, {"page[limit]": "200"})
            if isinstance(response, dict):
                count += len(response.get("data") or [])
                links = response.get("links") or {}
                next_link = links.get("next")
                pages = 0
                while isinstance(next_link, dict) and next_link.get("href") and pages < 1000:
                    pages += 1
                    # The next link is absolute; the client joins onto the
                    # base URL, so strip that prefix to make it relative.
                    href = str(next_link["href"])
                    base = str(getattr(self.jsonapi, "_base_url", "")).rstrip("/")
                    if base and href.startswith(base):
                        href = href[len(base):]
                    next_response = await self.jsonapi.get(href)
                    if not isinstance(next_response, dict):
                        break
                    count += len(next_response.get("data") or [])
                    next_link = (next_response.get("links") or {}).get("next")
                return count
            if isinstance(response, list):
                return len(response)
            return None
        except Exception:
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
            source_relationships = attributes.pop("_relationships", None)
            if not isinstance(source_relationships, dict):
                source_relationships = record.get("relationships")
            attributes = self._apply_mapping(attributes, field_mapping)
            attributes = self._sanitize_attributes(attributes)
            relationships = self._map_relationships(source_relationships, plan)

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
            if relationships:
                payload["relationships"] = relationships
            response, action, target_id = await self._write_with_fallback(
                entity_type=entity_type,
                payload=payload,
                target_id=target_id,
                entity_state=entity_state,
                legacy_id=legacy_id,
            )
            # Persist the legacy->target mapping so a re-run updates instead
            # of creating a duplicate.
            if action == "created" and target_id and legacy_id:
                entity_state.setdefault("records", {})[str(legacy_id)] = target_id

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

    # Drupal's JSON:API rejections that name a single offending field or
    # sub-property. Each is recoverable by dropping the named member and
    # retrying the same record.
    _RE_FIELD = re.compile(
        r"(?:The current user is not allowed to POST the selected field|"
        r"The current user is not allowed to PATCH the selected field|"
        r"The attribute) \((?P<attr>[\w.]+)\)"
        r"|The attribute (?P<attr2>[\w.]+) does not exist on the"
        r"|The property '(?P<sub>[\w]+)' does not exist on the '(?P<field>[\w]+)' field"
    )

    # Computed members Drupal exposes in reads but never accepts in writes.
    # Stripped proactively to save a round trip per record. Audit timestamps
    # (``created``/``changed``) are deliberately NOT here: they are writable on
    # nodes and worth preserving, and unreadable only on some entity types --
    # the adaptive retry drops them where a site refuses.
    _READ_ONLY_ATTRS = frozenset(
        {
            "display_name",
            "revision_timestamp",
            "revision_log",
            "revision_translation_affected",
        }
    )
    _READ_ONLY_SUBPROPS = frozenset({"processed", "summary", "pid"})

    def _sanitize_attributes(self, attributes: dict[str, Any]) -> dict[str, Any]:
        """Drop members Drupal's JSON:API will refuse to write.

        Source records carry computed and audit fields (``body.processed``,
        ``changed``, ``path.pid``, ...) that exist only for reads. Copying them
        verbatim produces 403/422 rejections, so strip them before the first
        request. Field access and enabled modules still vary per site, so the
        adaptive retry in :meth:`_write_with_fallback` handles the rest.
        """
        clean: dict[str, Any] = {}
        for key, value in attributes.items():
            if key in self._READ_ONLY_ATTRS or key.startswith("drupal_internal__"):
                continue
            if isinstance(value, dict):
                value = {k: v for k, v in value.items() if k not in self._READ_ONLY_SUBPROPS}
            elif isinstance(value, list):
                value = [
                    {k: v for k, v in item.items() if k not in self._READ_ONLY_SUBPROPS}
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            clean[key] = value
        return clean

    @staticmethod
    def _drop_member(payload: dict[str, Any], token: str, field: str | None, sub: str | None) -> bool:
        """Remove one offending attribute/sub-property/relationship from a payload.

        Drupal reports a missing field the same way whether it arrived as an
        attribute or a relationship (``field_image does not exist on the
        node--article resource type``), so both containers are checked.
        """
        if sub and field:
            attributes = payload.get("attributes")
            if isinstance(attributes, dict):
                value = attributes.get(field)
                if isinstance(value, dict) and sub in value:
                    value.pop(sub)
                    return True
                if isinstance(value, list):
                    changed = False
                    for item in value:
                        if isinstance(item, dict) and sub in item:
                            item.pop(sub)
                            changed = True
                    if changed:
                        return True
            return False
        name = field or token
        if not name:
            return False
        attributes = payload.get("attributes")
        if isinstance(attributes, dict) and name in attributes:
            attributes.pop(name)
            return True
        relationships = payload.get("relationships")
        if isinstance(relationships, dict) and name in relationships:
            relationships.pop(name)
            return True
        return False

    async def _write_with_fallback(
        self,
        entity_type: str,
        payload: dict[str, Any],
        target_id: str | None,
        entity_state: dict[str, Any],
        legacy_id: str | None,
        max_attempts: int = 8,
    ) -> tuple[Any, str, str | None]:
        """Create or update a record, dropping fields Drupal refuses.

        Source and target schemas drift: a module may be enabled on only one
        side, field storage may differ, or the migrating user may lack write
        access to a field. Drupal names the offending member in each rejection,
        so parse it out, remove just that member, and retry the same record.
        Giving up after ``max_attempts`` guards against a rejection that names
        nothing actionable.
        """
        attempt_payload = json.loads(json.dumps(payload))
        last_error: Exception | None = None
        dropped: list[str] = []
        for _ in range(max_attempts):
            try:
                if target_id:
                    response = await self.jsonapi.update_resource(entity_type, target_id, attempt_payload)
                    return response, "updated", target_id
                response = await self.jsonapi.create_resource(entity_type, attempt_payload)
                new_id = self._response_id(response)
                return response, "created", new_id or target_id
            except Exception as exc:  # noqa: BLE001 - recoverable per-field rejections
                last_error = exc
                match = self._RE_FIELD.search(str(exc))
                if not match:
                    break
                token = match.group("attr") or match.group("attr2") or ""
                field = match.group("field")
                sub = match.group("sub")
                if not self._drop_member(attempt_payload, token, field, sub):
                    break
                dropped.append(f"{field}.{sub}" if field and sub else (field or token))
        if last_error is not None and dropped:
            entity_state.setdefault("dropped_fields", [])
            for name in dropped:
                if name not in entity_state["dropped_fields"]:
                    entity_state["dropped_fields"].append(name)
        error_payload: Any = {"error": str(last_error)} if last_error is not None else {"error": "unknown failure"}
        return error_payload, "failed", target_id

    async def run_migration_wave(
        self,
        migration_id: str,
        resource_type: str,
        batch_size: int = 100,
        dry_run: bool = False,
        field_mapping: dict[str, str] | None = None,
        source_token: str | None = None,
        verify_tls: bool = True,
        source_username: str | None = None,
        source_password: str | None = None,
    ) -> dict[str, Any]:
        plan = self.get_plan(migration_id)
        if "error" in plan:
            return plan
        source = plan.get("source") or {}
        source_url = str(source.get("url") or "")
        if not source_url:
            return {"error": "Migration plan does not contain a source URL"}
        token = source_token or source.get("token")
        # Credentials may live in the plan (preferred, so waves are
        # self-contained) or be supplied per call.
        username = source_username or source.get("username")
        password = source_password or source.get("password")
        # Per-resource-type JSON:API filters from the plan let a wave exclude
        # records the target should not receive (the anonymous user, staged
        # or unpublished content, and so on).
        plan_filters = source.get("filters")
        filters: dict[str, str] | None = None
        if isinstance(plan_filters, dict):
            entry = plan_filters.get(resource_type)
            if isinstance(entry, dict):
                filters = {str(k): str(v) for k, v in entry.items()}
        records = await self._fetch_source_records(
            source_url=source_url,
            resource_type=resource_type,
            token=token,
            batch_size=batch_size,
            verify_tls=verify_tls,
            username=username,
            password=password,
            filters=filters,
        )
        mapping = field_mapping or (plan.get("field_mappings") or {}).get(resource_type)
        result = await self.migrate_records(
            migration_id=migration_id,
            entity_type=resource_type,
            records=records,
            field_mapping=mapping,
            dry_run=dry_run,
        )
        result["fetched"] = len(records)
        return result

    async def run_migration(
        self,
        migration_id: str,
        entity_types: list[str] | None = None,
        dry_run: bool = False,
        source_token: str | None = None,
        verify_tls: bool = True,
        source_username: str | None = None,
        source_password: str | None = None,
        continue_on_error: bool = False,
    ) -> dict[str, Any]:
        plan = self.get_plan(migration_id)
        if "error" in plan:
            return plan
        if not entity_types:
            entity_types = plan.get("entities") or []
        if not entity_types:
            return {"error": "No entity types supplied and the plan has none"}
        results = []
        for resource_type in entity_types:
            wave_result = await self.run_migration_wave(
                migration_id=migration_id,
                resource_type=resource_type,
                dry_run=dry_run,
                source_token=source_token,
                verify_tls=verify_tls,
                source_username=source_username,
                source_password=source_password,
            )
            results.append(wave_result)
            # A failed wave usually means a schema or auth problem that will
            # repeat for every later type; stop unless the caller wants the
            # remaining waves attempted anyway.
            if not continue_on_error and isinstance(wave_result, dict) and wave_result.get("failed"):
                break
        totals = {"processed": 0, "created": 0, "updated": 0, "failed": 0, "skipped": 0}
        for result in results:
            if isinstance(result, dict):
                for key in totals:
                    totals[key] += int(result.get(key, 0))
        return {"migration_id": migration_id, "dry_run": dry_run, "results": results, "totals": totals}

    async def _count_collection(
        self,
        base_url: str,
        resource_type: str,
        token: str | None,
        verify_tls: bool,
        username: str | None = None,
        password: str | None = None,
    ) -> int:
        """Count records by walking the JSON:API collection.

        JSON:API provides no total-count metadata, so a real count requires
        following the pagination links. Bounded to avoid runaway requests on
        very large sites.
        """
        import httpx

        base = base_url.rstrip("/")
        path = resource_type.replace("--", "/")
        headers = {"Accept": "application/vnd.api+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        auth = (username, password) if username and password else None
        count = 0
        next_url: str | None = f"{base}/jsonapi/{path}"
        params: dict[str, str] = {"page[limit]": "200"}
        pages = 0
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, verify=verify_tls) as client:
            while next_url and pages < 1000:
                pages += 1
                response = await client.get(next_url, params=params, headers=headers, auth=auth)
                response.raise_for_status()
                body = response.json()
                count += len(body.get("data") or [])
                params = {}
                links = body.get("links") or {}
                next_link = links.get("next")
                if isinstance(next_link, dict):
                    next_url = str(next_link.get("href") or "") or None
                elif isinstance(next_link, str):
                    next_url = next_link
                else:
                    next_url = None
        return count

    async def _fetch_source_records(
        self,
        source_url: str,
        resource_type: str,
        token: str | None,
        batch_size: int,
        verify_tls: bool,
        username: str | None = None,
        password: str | None = None,
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        import httpx

        base = source_url.rstrip("/")
        path = resource_type.replace("--", "/")
        headers = {"Accept": "application/vnd.api+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        # JSON:API field access hides attributes from anonymous users (user
        # name/mail, for example), so migrations of those types need source
        # credentials to read a complete record.
        auth = (username, password) if username and password else None
        page_size = max(1, min(batch_size, 200))
        records: list[dict[str, Any]] = []
        next_url: str | None = f"{base}/jsonapi/{path}"
        params: dict[str, str] = {"page[limit]": str(page_size)}
        # Filters shape which records are migrated (exclude the anonymous
        # user, unpublished content, and so on). They apply to the first page;
        # Drupal bakes them into the ``next`` links that follow.
        for key, value in (filters or {}).items():
            params[str(key)] = str(value)
        seen_pages = 0
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, verify=verify_tls) as client:
            while next_url and seen_pages < 1000:
                seen_pages += 1
                response = await client.get(next_url, params=params, headers=headers, auth=auth)
                response.raise_for_status()
                body = response.json()
                records.extend(body.get("data") or [])
                params = {}
                links = body.get("links") or {}
                next_link = links.get("next")
                if isinstance(next_link, dict):
                    href = next_link.get("href")
                    next_url = str(href) if href else None
                elif isinstance(next_link, str):
                    next_url = next_link
                else:
                    next_url = None
                if not next_url:
                    break
        return records

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

    # Bundle pointers (node_type, vocabulary) are already encoded in the
    # resource type itself -- ``node--article``, ``taxonomy_term--departures``
    # -- and their UUIDs are site-local config entities that never match on
    # the target, so sending them produces a 404. Revision/authorship
    # bookkeeping is likewise not accepted on JSON:API writes.
    _DROP_RELATIONSHIPS = frozenset(
        {
            "node_type",
            "vid",
            "revision_uid",
            "revision_user",
            "uid_revision",
        }
    )

    @staticmethod
    def _map_relationships(relationships: Any, plan: dict[str, Any]) -> dict[str, Any] | None:
        """Remap source relationship references onto target UUIDs.

        A relationship whose target was migrated in this run resolves to the
        new target UUID. One that points at a type outside the migration (or
        at a record not yet migrated) cannot be resolved, and sending the
        source UUID would make the whole write 404 -- so it is dropped rather
        than forwarded. Explicit nulls and empty lists are kept: they carry
        the meaning "clear this field".
        """
        if not isinstance(relationships, dict):
            return None
        entity_states = (plan.get("state") or {}).get("entities", {})
        result: dict[str, Any] = {}
        for relation_name, spec in relationships.items():
            if relation_name in MigrationService._DROP_RELATIONSHIPS:
                continue
            if not isinstance(spec, dict):
                continue
            data = spec.get("data")
            if data is None:
                result[relation_name] = {"data": None}
                continue
            if data == []:
                result[relation_name] = {"data": []}
                continue
            mapped_data = MigrationService._map_relationship_data(data, entity_states)
            if mapped_data is None:
                # Nothing resolvable survived; omit the relationship so the
                # write does not fail on a dangling source UUID.
                continue
            result[relation_name] = {"data": mapped_data}
        return result if result else None

    @staticmethod
    def _map_relationship_data(data: Any, entity_states: dict[str, Any]) -> Any:
        """Map relationship data, returning None if nothing resolvable remains."""
        if isinstance(data, list):
            mapped = [
                MigrationService._map_relationship_data(item, entity_states)
                for item in data
            ]
            # JSON:API represents the taxonomy-root placeholder as a fake
            # "virtual" item; it is not a real term and must not be forwarded.
            mapped = [item for item in mapped if item is not None]
            return mapped or None
        if not isinstance(data, dict):
            return None
        resource_type = data.get("type")
        source_id = data.get("id")
        if not resource_type or not source_id or source_id == "virtual":
            return None
        state = entity_states.get(resource_type, {})
        records = state.get("records", {}) if isinstance(state, dict) else {}
        target_id = records.get(str(source_id))
        if not target_id:
            # Not migrated in this run: dropping beats a 404 on a dangling
            # source UUID.
            return None
        return {"type": resource_type, "id": target_id}

    @staticmethod
    def _response_id(response: Any) -> str | None:
        if isinstance(response, dict):
            data = response.get("data")
            if isinstance(data, dict):
                return data.get("id")
            if isinstance(data, list) and data and isinstance(data[0], dict):
                return data[0].get("id")
        return None
