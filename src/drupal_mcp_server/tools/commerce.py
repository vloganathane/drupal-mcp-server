"""Commerce Core tools for Drupal."""

import os
import yaml
import json
from typing import Any

from fastmcp import FastMCP


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    jsonapi = deps.get("jsonapi_client")

    def _ensure_dict(result: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
        """Ensure result is a dict, not a list."""
        if result is None:
            return {"error": "No response"}
        if isinstance(result, list):
            return {"error": f"Unexpected list response: {result}"}
        return result

    @mcp.tool()
    async def commerce_store_list(
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all commerce stores."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            result = await jsonapi.get_resource("commerce_store", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_store_get(
        store_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single commerce store by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("commerce_store", store_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_store_create(
        id: str,
        label: str,
        mail: str,
        address: dict[str, Any] | None = None,
        default_currency: str = "USD",
    ) -> dict[str, Any]:
        """Create a new commerce store."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            store_data: dict[str, Any] = {
                "type": "commerce_store",
                "id": id,
                "label": label,
                "mail": mail,
                "default_currency": default_currency,
            }
            if address:
                store_data["address"] = address
            
            result = await jsonapi.create_resource("commerce_store", store_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_store_update(
        store_id: str,
        label: str | None = None,
        mail: str | None = None,
        address: dict[str, Any] | None = None,
        default_currency: str | None = None,
    ) -> dict[str, Any]:
        """Update a commerce store."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id("commerce_store", store_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": store_id, "type": "commerce_store"}
            if label is not None:
                update_data["label"] = label
            if mail is not None:
                update_data["mail"] = mail
            if address is not None:
                update_data["address"] = address
            if default_currency is not None:
                update_data["default_currency"] = default_currency
            
            result = await jsonapi.update_resource("commerce_store", store_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_product_list(
        store_id: str | None = None,
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List commerce products."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if store_id:
                params["filter[store]"] = store_id
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("commerce_product", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_product_get(
        product_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single commerce product by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("commerce_product", product_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_product_create(
        id: str,
        title: str,
        store_id: str,
        price: dict[str, Any],
        sku: str | None = None,
        status: bool = True,
        variations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a new commerce product."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            product_data = {
                "type": "commerce_product",
                "id": id,
                "title": title,
                "store": store_id,
                "price": price,
                "status": status,
            }
            if sku:
                product_data["sku"] = sku
            if variations:
                product_data["variations"] = variations
            
            result = await jsonapi.create_resource("commerce_product", product_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_product_update(
        product_id: str,
        title: str | None = None,
        price: dict[str, Any] | None = None,
        sku: str | None = None,
        status: bool | None = None,
    ) -> dict[str, Any]:
        """Update a commerce product."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id("commerce_product", product_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": product_id, "type": "commerce_product"}
            if title is not None:
                update_data["title"] = title
            if price is not None:
                update_data["price"] = price
            if sku is not None:
                update_data["sku"] = sku
            if status is not None:
                update_data["status"] = status
            
            result = await jsonapi.update_resource("commerce_product", product_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_order_list(
        store_id: str | None = None,
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List commerce orders."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if store_id:
                params["filter[store]"] = store_id
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("commerce_order", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_order_get(
        order_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single commerce order by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("commerce_order", order_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_order_create(
        id: str,
        store_id: str,
        order_type: str = "default",
        billing_profile: dict[str, Any] | None = None,
        items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a new commerce order."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            order_data: dict[str, Any] = {
                "type": "commerce_order",
                "id": id,
                "store": store_id,
                "order_type": order_type,
            }
            if billing_profile:
                order_data["billing_profile"] = billing_profile
            if items:
                order_data["items"] = items
            
            result = await jsonapi.create_resource("commerce_order", order_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_order_update(
        order_id: str,
        state: str | None = None,
        billing_profile: dict[str, Any] | None = None,
        items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Update a commerce order."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id("commerce_order", order_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": order_id, "type": "commerce_order"}
            if state is not None:
                update_data["state"] = state
            if billing_profile is not None:
                update_data["billing_profile"] = billing_profile
            if items is not None:
                update_data["items"] = items
            
            result = await jsonapi.update_resource("commerce_order", order_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_payment_gateway_list(
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List payment gateways."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            result = await jsonapi.get_resource("commerce_payment_gateway", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_payment_gateway_get(
        gateway_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single payment gateway by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("commerce_payment_gateway", gateway_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_promotion_list(
        store_id: str | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List commerce promotions."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if store_id:
                params["filter[store]"] = store_id
            
            result = await jsonapi.get_resource("commerce_promotion", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_promotion_create(
        id: str,
        label: str,
        store_id: str,
        offer: dict[str, Any],
        conditions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a new commerce promotion."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            promo_data = {
                "type": "commerce_promotion",
                "id": id,
                "label": label,
                "store": store_id,
                "offer": offer,
            }
            if conditions:
                promo_data["conditions"] = conditions
            
            result = await jsonapi.create_resource("commerce_promotion", promo_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_shipping_method_list(
        store_id: str | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List shipping methods."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if store_id:
                params["filter[store]"] = store_id
            
            result = await jsonapi.get_resource("commerce_shipping_method", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def commerce_shipping_method_create(
        id: str,
        label: str,
        store_id: str,
        plugin: str,
        configuration: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new shipping method."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            shipping_data = {
                "type": "commerce_shipping_method",
                "id": id,
                "label": label,
                "store": store_id,
                "plugin": plugin,
            }
            if configuration:
                shipping_data["configuration"] = configuration
            
            result = await jsonapi.create_resource("commerce_shipping_method", shipping_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}
