"""JSON:API client for Drupal."""

import re
from typing import Any

from .base import DrupalBaseClient

# JSON:API addresses single resources by UUID. Drupal's internal IDs (nid, uid,
# tid, ...) are not usable in the path and must be resolved with a filter.
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Internal ID field names across core entity types, probed in order.
_ID_FIELDS = (
    "drupal_internal__nid",
    "drupal_internal__uid",
    "drupal_internal__tid",
    "drupal_internal__vid",
    "drupal_internal__mid",
    "drupal_internal__cid",
    "drupal_internal__fid",
    "drupal_internal__lid",
    "drupal_internal__id",
)


class JSONAPIClient(DrupalBaseClient):
    """Client for Drupal JSON:API endpoints."""

    # Drupal answers any other Content-Type with 415 Unsupported Media Type.
    _media_type = "application/vnd.api+json"

    def __init__(self, settings: Any, auth_manager: Any = None):
        super().__init__(settings, auth_manager)
        self._api_path = settings.DRUPAL_JSONAPI_PATH.strip("/")
        self._index_paths: dict[str, str] | None = None

    def _jsonapi_url(self, resource: str) -> str:
        return f"{self._api_path}/{resource.lstrip('/')}"

    async def get_index(self) -> dict[str, Any] | list[Any]:
        """Fetch the JSON:API root, which lists available resources.

        Hits ``/jsonapi`` directly. Do not route this through
        :meth:`get_resource`, which would produce ``/jsonapi/jsonapi``.
        """
        return await self.get(self._api_path)

    async def _path_map(self) -> dict[str, str]:
        """Map JSON:API resource types (``node--article``) to URL paths.

        Drupal serves resources at ``/jsonapi/node/article`` while the
        *type* string used in payloads stays ``node--article``. The index is
        the only reliable source for this mapping, and it also lets us expand
        a bare entity type (``node``) into its bundles.
        """
        if self._index_paths is not None:
            return self._index_paths
        try:
            index = await self.get_index()
        except Exception:
            self._index_paths = {}
            return self._index_paths
        mapping: dict[str, str] = {}
        links = index.get("links", {}) if isinstance(index, dict) else {}
        prefix = f"/{self._api_path}/"
        for key, value in links.items():
            if key == "self" or not isinstance(value, dict):
                continue
            href = str(value.get("href", ""))
            marker = href.find(prefix)
            if marker == -1:
                continue
            mapping[key] = href[marker + len(prefix):].split("?")[0]
        self._index_paths = mapping
        return mapping

    async def _candidates(self, resource_type: str) -> list[str]:
        """URL path candidates for a resource type, in priority order."""
        resource_type = resource_type.strip("/")
        if "--" in resource_type:
            return [resource_type.replace("--", "/")]
        mapping = await self._path_map()
        if resource_type in mapping:
            return [mapping[resource_type]]
        prefix = f"{resource_type}--"
        found = [path for key, path in mapping.items() if key.startswith(prefix)]
        return found or [resource_type]

    async def get_resource(self, resource_type: str, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
        candidates = await self._candidates(resource_type)
        if len(candidates) == 1:
            return await self.get(self._jsonapi_url(candidates[0]), params=params)
        return await self._merge(candidates, params)

    async def _merge(self, candidates: list[str], params: dict[str, Any] | None) -> dict[str, Any]:
        """Fetch several bundle collections and merge their data."""
        merged: dict[str, Any] = {"data": [], "included": []}
        for path in candidates:
            try:
                chunk = await self.get(self._jsonapi_url(path), params=params)
            except Exception:
                continue
            if not isinstance(chunk, dict):
                continue
            merged["data"].extend(chunk.get("data") or [])
            merged["included"].extend(chunk.get("included") or [])
            for key in ("meta", "links"):
                if key in chunk and key not in merged:
                    merged[key] = chunk[key]
        seen: set[str] = set()
        unique: list[Any] = []
        for item in merged["included"]:
            item_id = item.get("id")
            if item_id not in seen:
                seen.add(item_id)
                unique.append(item)
        merged["included"] = unique
        return merged

    async def _resolve_uuid(self, resource_type: str, resource_id: str) -> tuple[str, str]:
        """Turn an internal ID into ``(path, uuid)`` for a single resource."""
        resource_id = str(resource_id)
        candidates = await self._candidates(resource_type)

        if _UUID_RE.match(resource_id):
            if len(candidates) == 1:
                return candidates[0], resource_id
            # Bundle unknown: probe each candidate collection for the UUID.
            for path in candidates:
                try:
                    await self.get(self._jsonapi_url(f"{path}/{resource_id}"))
                except Exception:
                    continue
                return path, resource_id
            return candidates[0], resource_id

        matched_field: str | None = None
        for path in candidates:
            for field in _ID_FIELDS:
                # Field validity is per entity type, not per bundle, so a hit
                # (or a valid-but-empty result) is remembered across paths.
                candidate_field = matched_field or field
                response = await self.request(
                    "GET",
                    self._jsonapi_url(path),
                    params={f"filter[{candidate_field}]": resource_id},
                )
                if response.status_code == 400:
                    # Unknown filter key: try the next field name.
                    continue
                matched_field = candidate_field
                if response.status_code >= 400:
                    break
                rows = response.json().get("data") if response.content else None
                if rows:
                    return path, rows[0]["id"]
                # Valid filter, empty result: next bundle (or done).
                break
        raise LookupError(
            f"No resource of type {resource_type!r} with id {resource_id!r}"
        )

    async def get_by_id(
        self,
        resource_type: str,
        uuid: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Fetch a single resource by ID, optionally with relationship includes.

        Args:
            resource_type: JSON:API resource type (e.g. ``node``, ``user--user``).
            uuid: Resource UUID or Drupal internal ID (nid, uid, tid, ...).
            params: Optional query params, typically ``{"include": "..."}``.

        Returns:
            Parsed JSON:API response.
        """
        path, resource_id = await self._resolve_uuid(resource_type, uuid)
        return await self.get(self._jsonapi_url(f"{path}/{resource_id}"), params=params)

    # Sibling keys of ``attributes`` in a JSON:API resource object. Including
    # ``attributes`` matters: a caller that passes an already-structured
    # document must not have it nested as attributes.attributes.
    _RESOURCE_KEYS = frozenset(
        {"type", "id", "lid", "attributes", "relationships", "links", "meta"}
    )

    @classmethod
    def _payload(cls, body: Any) -> Any:
        """Normalise a payload into JSON:API document form.

        Most write tools assemble a flat dict (``{"title": ..., "type": ...}``),
        but Drupal requires ``{"data": {"type": ..., "attributes": {...}}}`` and
        rejects anything else with 400 "Resource object must include a type".
        Documents that are already wrapped are passed through untouched.
        """
        if not isinstance(body, dict) or "data" in body or not body:
            return body
        resource: dict[str, Any] = {}
        attributes: dict[str, Any] = {}
        for key, value in body.items():
            if key in cls._RESOURCE_KEYS:
                resource[key] = value
            else:
                attributes[key] = value
        if attributes:
            resource["attributes"] = attributes
        return {"data": resource}

    async def get_revision(
        self,
        resource_type: str,
        resource_id: str,
        revision_id: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Fetch one specific revision of a resource.

        JSON:API reads historical revisions through the ``resourceVersion``
        relationship (``id:<vid>``). It has no revision *collection*
        endpoint -- ``.../revisions`` answers 405 -- so this is the only
        revision access the module offers.
        """
        path, uuid = await self._resolve_uuid(resource_type, resource_id)
        query = dict(params or {})
        query["resourceVersion"] = f"id:{revision_id}"
        return await self.get(self._jsonapi_url(f"{path}/{uuid}"), params=query)

    async def create_resource(self, resource_type: str, data: dict[str, Any]) -> dict[str, Any] | list[Any]:
        # The payload keeps the ``node--article`` type; only the URL is a path.
        candidates = await self._candidates(resource_type)
        return await self.post(self._jsonapi_url(candidates[0]), json_body=self._payload(data))

    async def update_resource(self, resource_type: str, uuid: str, data: dict[str, Any]) -> dict[str, Any] | list[Any]:
        path, resource_id = await self._resolve_uuid(resource_type, uuid)
        body = self._payload(data)
        # Drupal addresses the resource by UUID, not by the internal ID the
        # caller may have passed in.
        if isinstance(body, dict) and isinstance(body.get("data"), dict):
            body["data"]["id"] = resource_id
        return await self.patch(self._jsonapi_url(f"{path}/{resource_id}"), json_body=body)

    async def delete_resource(self, resource_type: str, uuid: str) -> dict[str, Any] | list[Any]:
        path, resource_id = await self._resolve_uuid(resource_type, uuid)
        return await self.delete(self._jsonapi_url(f"{path}/{resource_id}"))
