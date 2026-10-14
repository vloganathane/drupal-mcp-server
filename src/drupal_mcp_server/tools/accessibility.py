"""Accessibility (WCAG) tools for Drupal."""

import json
from datetime import UTC, datetime
from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def accessibility_axe_scan(
        url: str,
        rules: list[str] | None = None,
        format: str = "json",
    ) -> dict[str, Any]:
        """Run axe-core accessibility scan on a URL."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Validate URL to prevent injection
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                return {"error": f"Invalid URL: {url}"}
            cmd = ["exec", [
                f"\\$scan = require_once 'vendor/autoload.php'; "
                f"\\$axe = new \\\\Deque\\\\Axe\\\\Axe(); "
                f"\\$results = \\$axe->analyze('{url}'); "
                f"print_r(json_encode(\\$results));"
            ]]
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def accessibility_wcag_check(
        entity_type: str,
        entity_id: str,
        level: str = "AA",
    ) -> dict[str, Any]:
        """Check WCAG compliance for entity content."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            entity = await jsonapi.get_by_id(entity_type, entity_id)
            entity = _ensure_dict(entity)
            if entity.get("error"):
                return entity
            
            attributes = entity.get("data", {}).get("attributes", {})
            body = attributes.get("body", {}).get("value", "")
            
            issues = []
            
            # Check for alt text on images
            if '<img' in body and 'alt=' not in body:
                issues.append({
                    "rule": "image-alt",
                    "level": "A",
                    "message": "Images must have alt text",
                })
            
            # Check heading structure
            import re
            headings = re.findall(r'<h([1-6])', body)
            if headings:
                levels = [int(h) for h in headings]
                for i in range(1, len(levels)):
                    if levels[i] > levels[i-1] + 1:
                        issues.append({
                            "rule": "heading-order",
                            "level": "AA",
                            "message": f"Heading level skipped: h{levels[i-1]} to h{levels[i]}",
                        })
            
            # Check color contrast (placeholder)
            if 'color:' in body or 'background-color:' in body:
                issues.append({
                    "rule": "color-contrast",
                    "level": "AA",
                    "message": "Manual review needed for color contrast",
                })
            
            # Check link text
            links = re.findall(r'<a[^>]*>([^<]+)</a>', body)
            for link_text in links:
                if link_text.strip().lower() in ['click here', 'read more', 'more', 'link']:
                    issues.append({
                        "rule": "link-purpose",
                        "level": "A",
                        "message": f"Link text '{link_text}' is not descriptive",
                    })
            
            return _ensure_dict({
                "entity": f"{entity_type}:{entity_id}",
                "level": level,
                "issues": issues,
                "passed": len(issues) == 0,
            })
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def accessibility_color_contrast(
        foreground: str,
        background: str,
    ) -> dict[str, Any]:
        """Check color contrast ratio."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Simple hex color parsing
            def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
                hex_color = hex_color.lstrip('#')
                if len(hex_color) == 3:
                    hex_color = ''.join([c*2 for c in hex_color])
                return (
                    int(hex_color[0:2], 16),
                    int(hex_color[2:4], 16),
                    int(hex_color[4:6], 16),
                )
            
            def luminance(rgb: tuple[int, int, int]) -> float:
                r, g, b = [c/255.0 for c in rgb]
                r = r/12.92 if r <= 0.03928 else ((r+0.055)/1.055)**2.4
                g = g/12.92 if g <= 0.03928 else ((g+0.055)/1.055)**2.4
                b = b/12.92 if b <= 0.03928 else ((b+0.055)/1.055)**2.4
                return 0.2126*r + 0.7152*g + 0.0722*b
            
            fg_rgb = hex_to_rgb(foreground)
            bg_rgb = hex_to_rgb(background)
            
            fg_lum = luminance(fg_rgb)
            bg_lum = luminance(bg_rgb)
            
            ratio = (max(fg_lum, bg_lum) + 0.05) / (min(fg_lum, bg_lum) + 0.05)
            
            return _ensure_dict({
                "foreground": foreground,
                "background": background,
                "ratio": round(ratio, 2),
                "aa_normal": ratio >= 4.5,
                "aa_large": ratio >= 3.0,
                "aaa_normal": ratio >= 7.0,
                "aaa_large": ratio >= 4.5,
            })
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def accessibility_aria_validate(
        entity_type: str,
        entity_id: str,
    ) -> dict[str, Any]:
        """Validate ARIA attributes on entity."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            entity = await jsonapi.get_by_id(entity_type, entity_id)
            entity = _ensure_dict(entity)
            if entity.get("error"):
                return entity
            
            attributes = entity.get("data", {}).get("attributes", {})
            body = attributes.get("body", {}).get("value", "")
            
            issues = []
            
            import re
            # Check for aria-label without accessible name
            aria_labels = re.findall(r'aria-label="([^"]*)"', body)
            for label in aria_labels:
                if not label.strip():
                    issues.append({
                        "rule": "aria-label-empty",
                        "message": "aria-label is empty",
                    })
            
            # Check for role without required attributes
            roles = re.findall(r'role="([^"]*)"', body)
            for role in roles:
                if role in ['button', 'link', 'menuitem'] and 'tabindex' not in body:
                    issues.append({
                        "rule": "role-tabindex",
                        "message": f"Role '{role}' requires tabindex",
                    })
            
            # Check for duplicate IDs
            ids = re.findall(r'id="([^"]*)"', body)
            duplicates = [id for id in set(ids) if ids.count(id) > 1]
            for dup in duplicates:
                issues.append({
                    "rule": "duplicate-id",
                    "message": f"Duplicate ID: {dup}",
                })
            
            return _ensure_dict({
                "entity": f"{entity_type}:{entity_id}",
                "issues": issues,
                "passed": len(issues) == 0,
            })
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def accessibility_report_generate(
        urls: list[str],
        level: str = "AA",
        output_dir: str = "./accessibility-report",
    ) -> dict[str, Any]:
        """Generate comprehensive accessibility report."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            import os
            os.makedirs(output_dir, exist_ok=True)
            
            report: dict[str, Any] = {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": level,
                "pages": [],
            }
            
            from urllib.parse import urlparse
            for url in urls:
                parsed = urlparse(url)
                if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                    return {"error": f"Invalid URL: {url}"}
                # Run axe scan
                cmd = ["exec", [
                    f"\\$axe = new \\\\Deque\\\\Axe\\\\Axe(); "
                    f"\\$results = \\$axe->analyze('{url}'); "
                    f"print_r(json_encode(\\$results));"
                ]]
                result = await drush.run(*cmd)
                report["pages"].append({
                    "url": url,
                    "axe_results": result,
                })
            
            # Save report
            report_file = os.path.join(output_dir, "accessibility-report.json")
            with open(report_file, "w") as f:
                json.dump(report, f, indent=2)
            
            return _ensure_dict({
                "report_file": report_file,
                "pages_analyzed": len(urls),
            })
        except Exception as e:
            return {"error": str(e)}
