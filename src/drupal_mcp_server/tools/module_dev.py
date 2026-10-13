"""Module development scaffolding tools for Drupal."""

import os
import yaml
from typing import Any

from fastmcp import FastMCP


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")

    def _ensure_dict(result: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
        """Ensure result is a dict, not a list."""
        if result is None:
            return {"error": "No response"}
        if isinstance(result, list):
            return {"error": f"Unexpected list response: {result}"}
        return result

    @mcp.tool()
    async def module_create(
        name: str,
        machine_name: str | None = None,
        description: str = "",
        package: str = "Custom",
        core_version_requirement: str = "^10 || ^11",
        dependencies: list[str] | None = None,
        generate_routing: bool = True,
        generate_services: bool = True,
        generate_permissions: bool = True,
        generate_config_schema: bool = True,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Drupal module with full scaffolding."""
        if not drush:
            return {"error": "Drush not available"}
        
        machine_name = machine_name or name.lower().replace(" ", "_")
        if not machine_name.isidentifier():
            return {"error": f"Invalid machine name: {machine_name}"}
        
        module_path = path or f"modules/custom/{machine_name}"
        
        # Create module directory
        os.makedirs(module_path, exist_ok=True)
        
        # Generate .info.yml
        info_yml = {
            "name": name,
            "type": "module",
            "description": description or f"Custom module: {name}",
            "package": package,
            "core_version_requirement": core_version_requirement,
        }
        if dependencies:
            info_yml["dependencies"] = dependencies  # type: ignore[assignment]
        
        info_path = os.path.join(module_path, f"{machine_name}.info.yml")
        with open(info_path, "w") as f:
            yaml.dump(info_yml, f, default_flow_style=False, sort_keys=False)
        
        # Generate .module file with hook examples
        module_content = f"""<?php

/**
 * @file
 * {description or f"Custom module: {name}"}
 */

/**
 * Implements hook_help().
 */
function {machine_name}_help($route_name, \Drupal\Core\Routing\RouteMatchInterface $route_match) {{
  switch ($route_name) {{
    case 'help.page.{machine_name}':
      return '<p>' . t('{description or f"Custom module: {name}"}') . '</p>';
  }}
}}

/**
 * Implements hook_theme().
 */
function {machine_name}_theme($existing, $type, $theme, $path) {{
  return [];
}}

/**
 * Implements hook_permissions().
 */
function {machine_name}_permissions() {{
  return [
    'administer {machine_name}' => [
      'title' => t('Administer {name}'),
      'description' => t('Perform administration tasks for {name}.'),
    ],
  ];
}}
"""
        module_file = os.path.join(module_path, f"{machine_name}.module")
        with open(module_file, "w") as f:
            f.write(module_content)
        
        # Generate services.yml
        if generate_services:
            services_yml = {
                "services": {
                    f"{machine_name}.example_service": {
                        "class": f"Drupal\\{machine_name}\\Service\\ExampleService",
                        "arguments": ["@database"],
                    },
                },
            }
            services_path = os.path.join(module_path, f"{machine_name}.services.yml")
            with open(services_path, "w") as f:
                yaml.dump(services_yml, f, default_flow_style=False, sort_keys=False)
            
            # Create service class
            service_dir = os.path.join(module_path, "src", "Service")
            os.makedirs(service_dir, exist_ok=True)
            service_class = f"""<?php

namespace Drupal\\{machine_name}\\Service;

use Drupal\Core\Database\Connection;

class ExampleService {{
  protected $database;

  public function __construct(Connection $database) {{
    $this->database = $database;
  }}

  public function doSomething() {{
    // Your service logic here
  }}
}}
"""
            service_file = os.path.join(service_dir, "ExampleService.php")
            with open(service_file, "w") as f:
                f.write(service_class)
        
        # Generate permissions.yml
        if generate_permissions:
            perms_yml = {
                f"administer {machine_name}": {
                    "title": f"Administer {name}",
                    "description": f"Perform administration tasks for {name}.",
                },
            }
            perms_path = os.path.join(module_path, f"{machine_name}.permissions.yml")
            with open(perms_path, "w") as f:
                yaml.dump(perms_yml, f, default_flow_style=False, sort_keys=False)
        
        # Generate config schema
        if generate_config_schema:
            schema_yml = {
                f"{machine_name}.settings": {
                    "type": "config_object",
                    "label": f"{name} settings",
                    "mapping": {
                        "enabled": {
                            "type": "boolean",
                            "label": "Enabled",
                        },
                    },
                },
            }
            schema_dir = os.path.join(module_path, "config", "schema")
            os.makedirs(schema_dir, exist_ok=True)
            schema_path = os.path.join(schema_dir, f"{machine_name}.schema.yml")
            with open(schema_path, "w") as f:
                yaml.dump(schema_yml, f, default_flow_style=False, sort_keys=False)
        
        # Generate routing.yml
        if generate_routing:
            routing_yml = {
                f"{machine_name}.content": {
                    "path": f"/{machine_name}",
                    "defaults": {
                        "_controller": f"\\Drupal\\{machine_name}\\Controller\\{machine_name.capitalize()}Controller::content",
                        "_title": name,
                    },
                    "requirements": {
                        "_permission": f"administer {machine_name}",
                    },
                },
            }
            routing_path = os.path.join(module_path, f"{machine_name}.routing.yml")
            with open(routing_path, "w") as f:
                yaml.dump(routing_yml, f, default_flow_style=False, sort_keys=False)
            
            # Create controller
            controller_dir = os.path.join(module_path, "src", "Controller")
            os.makedirs(controller_dir, exist_ok=True)
            controller_class = f"""<?php

namespace Drupal\\{machine_name}\\Controller;

use Drupal\Core\Controller\ControllerBase;

class {machine_name.capitalize()}Controller extends ControllerBase {{
  public function content() {{
    return [
      '#markup' => $this->t('{name} module is working!'),
    ];
  }}
}}
"""
            controller_file = os.path.join(controller_dir, f"{machine_name.capitalize()}Controller.php")
            with open(controller_file, "w") as f:
                f.write(controller_class)
        
        return {
            "success": True,
            "machine_name": machine_name,
            "path": module_path,
            "files_created": [
                f"{machine_name}.info.yml",
                f"{machine_name}.module",
                f"{machine_name}.services.yml" if generate_services else None,
                f"{machine_name}.permissions.yml" if generate_permissions else None,
                f"{machine_name}.schema.yml" if generate_config_schema else None,
                f"{machine_name}.routing.yml" if generate_routing else None,
                "src/Service/ExampleService.php" if generate_services else None,
                "src/Controller/{machine_name.capitalize()}Controller.php" if generate_routing else None,
            ],
        }

    @mcp.tool()
    async def module_service_create(
        machine_name: str,
        service_name: str,
        class_name: str | None = None,
        arguments: list[str] | None = None,
        tags: list[dict[str, Any]] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Create a service definition with PHP class stub."""
        if not drush:
            return {"error": "Drush not available"}
        
        module_path = path or f"modules/custom/{machine_name}"
        services_file = os.path.join(module_path, f"{machine_name}.services.yml")
        
        if not os.path.exists(module_path):
            return {"error": f"Module not found: {module_path}"}
        
        class_name = class_name or f"{machine_name.capitalize()}{service_name.replace('_', ' ').title().replace(' ', '')}Service"
        service_id = f"{machine_name}.{service_name}"
        
        # Read existing services.yml or create new
        if os.path.exists(services_file):
            with open(services_file, "r") as f:
                services_yml = yaml.safe_load(f) or {"services": {}}
        else:
            services_yml = {"services": {}}
        
        # Build service definition
        service_def: dict[str, Any] = {"class": f"Drupal\\{machine_name}\\Service\\{class_name}"}
        if arguments:
            service_def["arguments"] = arguments
        if tags:
            service_def["tags"] = tags
        
        services_yml["services"][service_id] = service_def
        
        with open(services_file, "w") as f:
            yaml.dump(services_yml, f, default_flow_style=False, sort_keys=False)
        
        # Create service class
        service_dir = os.path.join(module_path, "src", "Service")
        os.makedirs(service_dir, exist_ok=True)
        
        # Generate constructor with arguments
        constructor_params = ""
        constructor_body = ""
        if arguments:
            for i, arg in enumerate(arguments):
                param_name = f"${arg.replace('@', '')}"
                constructor_params += f"{param_name}, "
                constructor_body += f"        $this->{arg.replace('@', '')} = {param_name};\n"
            constructor_params = constructor_params.rstrip(", ")
        
        service_class = f"""<?php

namespace Drupal\\{machine_name}\\Service;

class {class_name} {{
{constructor_body}
  public function __construct({constructor_params}) {{
{constructor_body}  }}
}}

"""
        service_file = os.path.join(service_dir, f"{class_name}.php")
        with open(service_file, "w") as f:
            f.write(service_class)
        
        return {
            "success": True,
            "service_id": service_id,
            "class_name": class_name,
            "service_file": service_file,
            "services_file": services_file,
            "arguments": arguments or [],
        }

    @mcp.tool()
    async def module_plugin_create(
        machine_name: str,
        plugin_type: str,
        plugin_id: str,
        label: str,
        class_name: str | None = None,
        description: str = "",
        annotations: dict[str, Any] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Create a plugin (block, field, views, etc.) with proper scaffolding."""
        if not drush:
            return {"error": "Drush not available"}
        
        module_path = path or f"modules/custom/{machine_name}"
        
        if not os.path.exists(module_path):
            return {"error": f"Module not found: {module_path}"}
        
        # Valid plugin types and their base classes
        plugin_types = {
            "block": {
                "base_class": "Drupal\\Core\\Block\\BlockBase",
                "namespace": "Plugin\\Block",
                "annotation_class": "Drupal\\Core\\Annotation\\Block",
                "required_annotations": ["id", "admin_label"],
            },
            "field_widget": {
                "base_class": "Drupal\\Core\\Field\\WidgetBase",
                "namespace": "Plugin\\Field\\FieldWidget",
                "annotation_class": "Drupal\\Core\\Annotation\\FieldWidget",
                "required_annotations": ["id", "label", "field_types"],
            },
            "field_formatter": {
                "base_class": "Drupal\\Core\\Field\\FormatterBase",
                "namespace": "Plugin\\Field\\FieldFormatter",
                "annotation_class": "Drupal\\Core\\Annotation\\FieldFormatter",
                "required_annotations": ["id", "label", "field_types"],
            },
            "views_field": {
                "base_class": "Drupal\\views\\Plugin\\views\\field\\FieldPluginBase",
                "namespace": "Plugin\\views\\field",
                "annotation_class": "Drupal\\views\\Annotation\\ViewsField",
                "required_annotations": ["id", "title"],
            },
            "views_filter": {
                "base_class": "Drupal\\views\\Plugin\\views\\filter\\FilterPluginBase",
                "namespace": "Plugin\\views\\filter",
                "annotation_class": "Drupal\\views\\Annotation\\ViewsFilter",
                "required_annotations": ["id", "title"],
            },
            "views_argument": {
                "base_class": "Drupal\\views\\Plugin\\views\\argument\\ArgumentPluginBase",
                "namespace": "Plugin\\views\\argument",
                "annotation_class": "Drupal\\views\\Annotation\\ViewsArgument",
                "required_annotations": ["id", "title"],
            },
            "action": {
                "base_class": "Drupal\\Core\\Action\\ActionBase",
                "namespace": "Plugin\\Action",
                "annotation_class": "Drupal\\Core\\Annotation\\Action",
                "required_annotations": ["id", "label", "type"],
            },
            "condition": {
                "base_class": "Drupal\\Core\\Condition\\ConditionPluginBase",
                "namespace": "Plugin\\Condition",
                "annotation_class": "Drupal\\Core\\Annotation\\Condition",
                "required_annotations": ["id", "label"],
            },
            "migrate_source": {
                "base_class": "Drupal\\migrate\\Plugin\\migrate\\source\\SourcePluginBase",
                "namespace": "Plugin\\migrate\\source",
                "annotation_class": "Drupal\\migrate\\Annotation\\MigrateSource",
                "required_annotations": ["id", "source_module"],
            },
            "rest_resource": {
                "base_class": "Drupal\\rest\\Plugin\\ResourceBase",
                "namespace": "Plugin\\rest\\resource",
                "annotation_class": "Drupal\\rest\\Annotation\\RestResource",
                "required_annotations": ["id", "label", "uri_paths"],
            },
        }
        
        if plugin_type not in plugin_types:
            available = list(plugin_types.keys())
            return {"error": f"Unknown plugin type: {plugin_type}. Available: {available}"}
        
        plugin_info = plugin_types[plugin_type]
        class_name = class_name or f"{machine_name.capitalize()}{plugin_id.replace('_', ' ').title().replace(' ', '')}{plugin_type.replace('_', ' ').title().replace(' ', '')}"
        
        # Build plugin directory
        plugin_dir = os.path.join(module_path, "src", str(plugin_info["namespace"]))
        os.makedirs(plugin_dir, exist_ok=True)
        
        # Build annotations
        annotation_lines = []
        for key in plugin_info["required_annotations"]:
            if key == "id":
                annotation_lines.append(f'  id = "{plugin_id}",')
            elif key == "admin_label":
                annotation_lines.append(f'  admin_label = @Translation("{label}"),')
            elif key == "label":
                annotation_lines.append(f'  label = @Translation("{label}"),')
            elif key == "title":
                annotation_lines.append(f'  title = @Translation("{label}"),')
            elif key == "type":
                annotation_lines.append(f'  type = "custom",')
            elif key == "field_types":
                annotation_lines.append(f'  field_types = ["string"],')
            elif key == "source_module":
                annotation_lines.append(f'  source_module = "{machine_name}",')
            elif key == "uri_paths":
                annotation_lines.append(f'  uri_paths = {{\"canonical\" = \"/{plugin_id}\"}},')
        
        if annotations:
            for key, value in annotations.items():
                if isinstance(value, str):
                    annotation_lines.append(f'  {key} = "{value}",')
                elif isinstance(value, list):
                    annotation_lines.append(f'  {key} = {value},')
                else:
                    annotation_lines.append(f'  {key} = {value},')
        
        annotation_str = "\n".join(annotation_lines)
        annotation_class_short = str(plugin_info["annotation_class"]).split("\\")[-1]
        
        # Create plugin class
        plugin_class = f"""<?php

namespace Drupal\\{machine_name}\\{plugin_info["namespace"]};

use {plugin_info["base_class"]};
use {plugin_info["annotation_class"]};

/**
 * {description or f"Plugin: {label}"}
 *
 * @{annotation_class_short}(
{annotation_str}
)
"""
        plugin_class += f"""class {class_name} extends {plugin_info["base_class"]} {{
"""
        
        # Add type-specific methods
        if plugin_type == "block":
            plugin_class += """  /**
   * {@inheritdoc}
   */
  public function build() {
    return [
      '#markup' => $this->t('Hello from {label}!'),
    ];
  }
"""
        elif plugin_type in ("field_widget", "field_formatter"):
            plugin_class += """  /**
   * {@inheritdoc}
   */
  public function formElement($items, $delta, $element, $form, FormStateInterface $form_state) {
    $element['value'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Value'),
      '#default_value' => $items[$delta]->value ?? '',
    ];
    return $element;
  }
"""
        elif plugin_type == "views_field":
            plugin_class += """  /**
   * {@inheritdoc}
   */
  public function render(ResultRow $values) {
    return $this->t('Custom field output');
  }
"""
        elif plugin_type == "action":
            plugin_class += """  /**
   * {@inheritdoc}
   */
  public function execute($entity = NULL) {
    // Action logic here
  }
"""
        else:
            plugin_class += """  // Add your plugin logic here
"""
        
        plugin_class += "}\n"
        
        # Write plugin file
        plugin_file = os.path.join(plugin_dir, f"{class_name}.php")
        with open(plugin_file, "w") as f:
            f.write(plugin_class)
        
        return {
            "success": True,
            "plugin_type": plugin_type,
            "plugin_id": plugin_id,
            "class_name": class_name,
            "plugin_file": plugin_file,
            "base_class": plugin_info["base_class"],
            "namespace": f"Drupal\\{machine_name}\\{plugin_info['namespace']}",
        }

    @mcp.tool()
    async def module_event_subscriber_create(
        machine_name: str,
        subscriber_name: str,
        class_name: str | None = None,
        events: list[dict[str, Any]] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Create an event subscriber service with getSubscribedEvents method."""
        if not drush:
            return {"error": "Drush not available"}
        
        module_path = path or f"modules/custom/{machine_name}"
        
        if not os.path.exists(module_path):
            return {"error": f"Module not found: {module_path}"}
        
        class_name = class_name or f"{machine_name.capitalize()}{subscriber_name.replace('_', ' ').title().replace(' ', '')}EventSubscriber"
        service_id = f"{machine_name}.event_subscriber.{subscriber_name}"
        
        # Default events if not provided
        if not events:
            events = [
                {"event": "kernel.request", "method": "onKernelRequest", "priority": 0},
                {"event": "kernel.response", "method": "onKernelResponse", "priority": 0},
            ]
        
        # Read existing services.yml or create new
        services_file = os.path.join(module_path, f"{machine_name}.services.yml")
        if os.path.exists(services_file):
            with open(services_file, "r") as f:
                services_yml = yaml.safe_load(f) or {"services": {}}
        else:
            services_yml = {"services": {}}
        
        # Build service definition with event_subscriber tag
        service_def: dict[str, Any] = {
            "class": f"Drupal\\{machine_name}\\EventSubscriber\\{class_name}",
            "tags": [{"name": "event_subscriber"}],
        }
        
        services_yml.setdefault("services", {})[service_id] = service_def
        
        with open(services_file, "w") as f:
            yaml.dump(services_yml, f, default_flow_style=False, sort_keys=False)
        
        # Create event subscriber class
        event_subscriber_dir = os.path.join(module_path, "src", "EventSubscriber")
        os.makedirs(event_subscriber_dir, exist_ok=True)
        
        # Build getSubscribedEvents method
        event_methods = []
        for event in events:
            event_name = event.get("event", "kernel.request")
            method_name = event.get("method", "onKernelRequest")
            priority = event.get("priority", 0)
            event_methods.append(f'      "{event_name}" => [["{method_name}", {priority}]],')
        
        events_str = "\n".join(event_methods)
        
        event_subscriber_class = f"""<?php

namespace Drupal\\{machine_name}\\EventSubscriber;

use Symfony\\Component\\EventDispatcher\\EventSubscriberInterface;
use Symfony\\Component\\HttpKernel\\KernelEvents;
use Symfony\\Component\\HttpKernel\\Event\\RequestEvent;
use Symfony\\Component\\HttpKernel\\Event\\ResponseEvent;

class {class_name} implements EventSubscriberInterface {{
  /**
   * {{@inheritdoc}}
   */
  public static function getSubscribedEvents() {{
    return [
{events_str}
    ];
  }}

  public function onKernelRequest(RequestEvent $event) {{
    // Handle kernel.request event
  }}

  public function onKernelResponse(ResponseEvent $event) {{
    // Handle kernel.response event
  }}
}}
"""
        event_subscriber_file = os.path.join(event_subscriber_dir, f"{class_name}.php")
        with open(event_subscriber_file, "w") as f:
            f.write(event_subscriber_class)
        
        # Also update services.yml to include the event_subscriber tag
        services_file = os.path.join(module_path, f"{machine_name}.services.yml")
        if os.path.exists(services_file):
            with open(services_file, "r") as f:
                services_yml = yaml.safe_load(f) or {"services": {}}
        else:
            services_yml = {"services": {}}
        
        services_yml.setdefault("services", {})[service_id] = {
            "class": f"Drupal\\{machine_name}\\EventSubscriber\\{class_name}",
            "tags": [{"name": "event_subscriber"}],
        }
        
        with open(services_file, "w") as f:
            yaml.dump(services_yml, f, default_flow_style=False, sort_keys=False)
        
        return {
            "success": True,
            "service_id": service_id,
            "class_name": class_name,
            "subscriber_file": os.path.join("src", "EventSubscriber", f"{class_name}.php"),
            "services_file": services_file,
            "events": events,
        }

    @mcp.tool()
    async def module_hook_implement(
        machine_name: str,
        hook: str,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Implement a hook in an existing module."""
        if not drush:
            return {"error": "Drush not available"}
        
        module_path = path or f"modules/custom/{machine_name}"
        module_file = os.path.join(module_path, f"{machine_name}.module")
        
        if not os.path.exists(module_file):
            return {"error": f"Module file not found: {module_file}"}
        
        # Hook implementations mapping
        hook_templates = {
            "hook_help": f"""
/**
 * Implements hook_help().
 */
function {machine_name}_help($route_name, \Drupal\Core\Routing\RouteMatchInterface $route_match) {{
  switch ($route_name) {{
    case 'help.page.{machine_name}':
      return '<p>' . t('Help text for {machine_name}.') . '</p>';
  }}
}}
""",
            "hook_form_alter": f"""
/**
 * Implements hook_form_alter().
 */
function {machine_name}_form_alter(&$form, \Drupal\Core\Form\FormStateInterface $form_state, $form_id) {{
  // Add your form alterations here
}}
""",
            "hook_entity_presave": f"""
/**
 * Implements hook_entity_presave().
 */
function {machine_name}_entity_presave(\Drupal\Core\Entity\EntityInterface $entity) {{
  // Add your presave logic here
}}
""",
            "hook_cron": f"""
/**
 * Implements hook_cron().
 */
function {machine_name}_cron() {{
  // Add your cron tasks here
}}
""",
            "hook_install": f"""
/**
 * Implements hook_install().
 */
function {machine_name}_install() {{
  // Add your installation logic here
}}
""",
            "hook_uninstall": f"""
/**
 * Implements hook_uninstall().
 */
function {machine_name}_uninstall() {{
  // Add your uninstall logic here
}}
""",
            "hook_config_import_create": f"""
/**
 * Implements hook_config_import_create().
 */
function {machine_name}_config_import_create($config_name, $config_storage) {{
  // Add your config import create logic here
}}
""",
        }
        
        template = hook_templates.get(hook)
        if not template:
            available = list(hook_templates.keys())
            return {"error": f"Unknown hook: {hook}. Available: {available}"}
        
        # Read existing module file
        with open(module_file, "r") as f:
            content = f.read()
        
        # Check if hook already exists
        hook_func = f"function {machine_name}_{hook.replace('hook_', '')}"
        if hook_func in content:
            return {"error": f"Hook {hook} already implemented in {machine_name}"}
        
        # Append hook implementation
        with open(module_file, "a") as f:
            f.write(f"\n{template}\n")
        
        return {
            "success": True,
            "hook": hook,
            "module": machine_name,
            "message": f"Implemented {hook} in {module_file}",
        }

    @mcp.tool()
    async def module_info_generate(
        machine_name: str,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Generate .info.yml from existing module code (reverse engineering)."""
        if not drush:
            return {"error": "Drush not available"}
        
        module_path = path or f"modules/custom/{machine_name}"
        module_file = os.path.join(module_path, f"{machine_name}.module")
        info_file = os.path.join(module_path, f"{machine_name}.info.yml")
        
        if not os.path.exists(module_file):
            return {"error": f"Module file not found: {module_file}"}
        
        # Read module file to extract info
        with open(module_file, "r") as f:
            content = f.read()
        
        # Try to extract name from hook_help or comments
        import re
        name_match = re.search(r'name["\']?\s*[=>:]\s*["\']([^"\']+)["\']', content)
        desc_match = re.search(r'description["\']?\s*[=>:]\s*["\']([^"\']+)["\']', content)
        
        info_yml = {
            "name": name_match.group(1) if name_match else machine_name.replace("_", " ").title(),
            "type": "module",
            "description": desc_match.group(1) if desc_match else f"Auto-generated module: {machine_name}",
            "package": "Custom",
            "core_version_requirement": "^10 || ^11",
        }
        
        # Check for dependencies in hook implementations
        deps = set()
        if "hook_form_alter" in content:
            deps.add("form")
        if "hook_entity" in content:
            deps.add("entity")
        if "hook_cron" in content:
            deps.add("cron")
        if "hook_views" in content:
            deps.add("views")
        
        if deps:
            info_yml["dependencies"] = sorted(list(deps))
        
        with open(info_file, "w") as f:
            yaml.dump(info_yml, f, default_flow_style=False, sort_keys=False)
        
        return {
            "success": True,
            "machine_name": machine_name,
            "info_file": info_file,
            "generated": info_yml,
        }
