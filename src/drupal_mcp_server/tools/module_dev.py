"""Module development scaffolding tools for Drupal."""

import os
import re
from typing import Any

import yaml
from fastmcp import FastMCP


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")

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
function {machine_name}_help($route_name, \\Drupal\\Core\\Routing\\RouteMatchInterface $route_match) {{
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

use Drupal\\Core\\Database\\Connection;

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

use Drupal\\Core\\Controller\\ControllerBase;

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
            with open(services_file) as f:
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
            for _i, arg in enumerate(arguments):
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
                annotation_lines.append('  type = "custom",')
            elif key == "field_types":
                annotation_lines.append('  field_types = ["string"],')
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
    async def module_form_create(
        machine_name: str,
        form_name: str,
        form_type: str = "ConfigForm",
        class_name: str | None = None,
        form_id: str | None = None,
        fields: list[dict[str, Any]] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Create a form class (ConfigForm, ConfirmForm, FormBase, etc.) with proper scaffolding."""
        if not drush:
            return {"error": "Drush not available"}
        
        module_path = path or f"modules/custom/{machine_name}"
        
        if not os.path.exists(module_path):
            return {"error": f"Module not found: {module_path}"}
        
        # Valid form types and their base classes
        form_types = {
            "ConfigForm": {
                "base_class": "Drupal\\Core\\Form\\ConfigFormBase",
                "namespace": "Form",
                "requires_config": True,
            },
            "ConfirmForm": {
                "base_class": "Drupal\\Core\\Form\\ConfirmFormBase",
                "namespace": "Form",
                "requires_config": False,
            },
            "FormBase": {
                "base_class": "Drupal\\Core\\Form\\FormBase",
                "namespace": "Form",
                "requires_config": False,
            },
            "EntityForm": {
                "base_class": "Drupal\\Core\\Entity\\EntityForm",
                "namespace": "Form",
                "requires_config": False,
            },
        }
        
        if form_type not in form_types:
            available = list(form_types.keys())
            return {"error": f"Unknown form type: {form_type}. Available: {available}"}
        
        form_info = form_types[form_type]
        class_name = class_name or f"{machine_name.capitalize()}{form_name.replace('_', ' ').title().replace(' ', '')}{form_type}"
        form_id = form_id or f"{machine_name}_{form_name}"
        
        # Build form directory
        form_dir = os.path.join(module_path, "src", str(form_info["namespace"]))
        os.makedirs(form_dir, exist_ok=True)
        
        # Build form class
        form_class = f"""<?php

namespace Drupal\\{machine_name}\\{form_info["namespace"]};

use {form_info["base_class"]};
use Drupal\\Core\\Form\\FormStateInterface;
"""
        if form_info["requires_config"]:
            form_class += "use Drupal\\Core\\Config\\ConfigFactoryInterface;\nuse Symfony\\Component\\DependencyInjection\\ContainerInterface;\n"
        
        form_class += f"""\nclass {class_name} extends {form_info["base_class"]} {{"""
        
        if form_type == "ConfigForm":
            form_class += f"""
  /**
   * {{@inheritdoc}}
   */
  protected $configFactory;

  public function __construct(ConfigFactoryInterface $config_factory) {{
    $this->configFactory = $config_factory;
  }}

  public static function create(ContainerInterface $container) {{
    return new static(
      $container->get('config.factory')
    );
  }}

  /**
   * {{@inheritdoc}}
   */
  protected function getEditableConfigNames() {{
    return [
      '{machine_name}.settings',
    ];
  }}

  /**
   * {{@inheritdoc}}
   */
  public function getFormId() {{
    return '{form_id}';
  }}

  /**
   * {{@inheritdoc}}
   */
  public function buildForm(array $form, FormStateInterface $form_state) {{
    $config = $this->config('{machine_name}.settings');
"""
            
            # Add form fields
            if fields:
                for field in fields:
                    field_name = field.get("name", "field")
                    field_type = field.get("type", "textfield")
                    field_title = field.get("title", field_name.replace("_", " ").title())
                    field_default = field.get("default", "")
                    
                    form_class += f"""
    $form['{field_name}'] = [
      '#type' => '{field_type}',
      '#title' => $this->t('{field_title}'),
      '#default_value' => $config->get('{field_name}') ?? '{field_default}',
    ];"""
            else:
                form_class += """
    $form['example_field'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Example field'),
      '#default_value' => $config->get('example_field') ?? '',
    ];"""
            
            form_class += f"""

    return parent::buildForm($form, $form_state);
  }}

  /**
   * {{@inheritdoc}}
   */
  public function submitForm(array &$form, FormStateInterface $form_state) {{
    $config = $this->config('{machine_name}.settings');
"""
            if fields:
                for field in fields:
                    field_name = field.get("name", "field")
                    form_class += f"""
    $config->set('{field_name}', $form_state->getValue('{field_name}'));"""
            else:
                form_class += """
    $config->set('example_field', $form_state->getValue('example_field'));"""
            
            form_class += """

    $config->save();
    parent::submitForm($form, $form_state);
  }

"""
        
        elif form_type == "ConfirmForm":
            form_class += f"""
  /**
   * {{@inheritdoc}}
   */
  public function getFormId() {{
    return '{form_id}';
  }}

  /**
   * {{@inheritdoc}}
   */
  public function getQuestion() {{
    return $this->t('Are you sure you want to proceed?');
  }}

  /**
   * {{@inheritdoc}}
   */
  public function getConfirmText() {{
    return $this->t('Confirm');
  }}

  /**
   * {{@inheritdoc}}
   */
  public function getCancelText() {{
    return $this->t('Cancel');
  }}

  /**
   * {{@inheritdoc}}
   */
  public function getCancelUrl() {{
    return new \\Drupal\\Core\\Url('<front>');
  }}

  /**
   * {{@inheritdoc}}
   */
  public function buildForm(array $form, FormStateInterface $form_state) {{
    return parent::buildForm($form, $form_state);
  }}

  /**
   * {{@inheritdoc}}
   */
  public function submitForm(array &$form, FormStateInterface $form_state) {{
    // Add your confirmation logic here
    parent::submitForm($form, $form_state);
  }}

"""
        
        else:  # FormBase
            form_class += f"""
  /**
   * {{@inheritdoc}}
   */
  public function getFormId() {{
    return '{form_id}';
  }}

  /**
   * {{@inheritdoc}}
   */
  public function buildForm(array $form, FormStateInterface $form_state) {{
"""
            
            if fields:
                for field in fields:
                    field_name = field.get("name", "field")
                    field_type = field.get("type", "textfield")
                    field_title = field.get("title", field_name.replace("_", " ").title())
                    field_default = field.get("default", "")
                    
                    form_class += f"""
    $form['{field_name}'] = [
      '#type' => '{field_type}',
      '#title' => $this->t('{field_title}'),
      '#default_value' => '{field_default}',
    ];"""
            else:
                form_class += """
    $form['example_field'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Example field'),
      '#default_value' => '',
    ];"""
            
            form_class += """

    return $form;
  }

  /**
   * {@inheritdoc}
   */
  public function submitForm(array &$form, FormStateInterface $form_state) {
    // Add your submit logic here
  }

"""
        
        form_class += "}\n"
        
        # Write form file
        form_file = os.path.join(form_dir, f"{class_name}.php")
        with open(form_file, "w") as f:
            f.write(form_class)
        
        # Update routing.yml
        routing_file = os.path.join(module_path, f"{machine_name}.routing.yml")
        if os.path.exists(routing_file):
            with open(routing_file) as f:
                routing_yml = yaml.safe_load(f) or {}
        else:
            routing_yml = {}
        
        route_name = f"{machine_name}.{form_name}"
        routing_yml[route_name] = {
            "path": f"/{machine_name}/{form_name}",
            "defaults": {
                "_form": f"\\Drupal\\{machine_name}\\Form\\{class_name}",
                "_title": form_name.replace("_", " ").title(),
            },
            "requirements": {
                "_permission": f"administer {machine_name}",
            },
        }
        
        with open(routing_file, "w") as f:
            yaml.dump(routing_yml, f, default_flow_style=False, sort_keys=False)
        
        # Update services.yml if ConfigForm
        if form_info["requires_config"]:
            services_file = os.path.join(module_path, f"{machine_name}.services.yml")
            if os.path.exists(services_file):
                with open(services_file) as f:
                    services_yml = yaml.safe_load(f) or {"services": {}}
            else:
                services_yml = {"services": {}}
            
            service_id = f"{machine_name}.form.{form_name}"
            services_yml.setdefault("services", {})[service_id] = {
                "class": f"Drupal\\{machine_name}\\Form\\{class_name}",
                "arguments": ["@config.factory"],
            }
            
            with open(services_file, "w") as f:
                yaml.dump(services_yml, f, default_flow_style=False, sort_keys=False)
        
        return {
            "success": True,
            "form_type": form_type,
            "form_id": form_id,
            "class_name": class_name,
            "form_file": os.path.join("src", "Form", f"{class_name}.php"),
            "routing_file": routing_file,
            "base_class": form_info["base_class"],
        }

    @mcp.tool()
    async def module_controller_create(
        machine_name: str,
        controller_name: str,
        class_name: str | None = None,
        methods: list[dict[str, Any]] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Create a controller class with routing."""
        if not drush:
            return {"error": "Drush not available"}
        
        module_path = path or f"modules/custom/{machine_name}"
        
        if not os.path.exists(module_path):
            return {"error": f"Module not found: {module_path}"}
        
        class_name = class_name or f"{machine_name.capitalize()}{controller_name.replace('_', ' ').title().replace(' ', '')}Controller"
        
        # Build controller directory
        controller_dir = os.path.join(module_path, "src", "Controller")
        os.makedirs(controller_dir, exist_ok=True)
        
        # Default methods if not provided
        if not methods:
            methods = [
                {"name": "content", "route": f"/{machine_name}", "title": f"{machine_name} page"},
            ]
        
        # Build controller class
        controller_class = f"""<?php

namespace Drupal\\{machine_name}\\Controller;

use Drupal\\Core\\Controller\\ControllerBase;
use Symfony\\Component\\HttpFoundation\\JsonResponse;
use Symfony\\Component\\HttpFoundation\\Response;
"""
        
        for method in methods:
            method_name = method.get("name", "content")
            controller_class += f"""
  /**
   * {method.get('description', f'{method_name} method')}.
   */
  public function {method_name}() {{
    return [
      '#markup' => $this->t('{method_name} method of {machine_name} controller'),
    ];
  }}
"""
        
        controller_class += "}\n"
        
        # Write controller file
        controller_file = os.path.join(controller_dir, f"{class_name}.php")
        with open(controller_file, "w") as f:
            f.write(controller_class)
        
        # Update routing.yml
        routing_file = os.path.join(module_path, f"{machine_name}.routing.yml")
        if os.path.exists(routing_file):
            with open(routing_file) as f:
                routing_yml = yaml.safe_load(f) or {}
        else:
            routing_yml = {}
        
        for method in methods:
            method_name = method.get("name", "content")
            route_path = method.get("route", f"/{machine_name}/{method_name}")
            route_title = method.get("title", method_name.replace("_", " ").title())
            
            routing_yml[f"{machine_name}.{method_name}"] = {
                "path": route_path,
                "defaults": {
                    "_controller": f"\\Drupal\\{machine_name}\\Controller\\{class_name}::{method_name}",
                    "_title": route_title,
                },
                "requirements": {
                    "_permission": "access content",
                },
            }
        
        with open(routing_file, "w") as f:
            yaml.dump(routing_yml, f, default_flow_style=False, sort_keys=False)
        
        return {
            "success": True,
            "class_name": class_name,
            "controller_file": os.path.join("src", "Controller", f"{class_name}.php"),
            "routing_file": routing_file,
            "methods": methods,
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
            with open(services_file) as f:
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
            with open(services_file) as f:
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
function {machine_name}_help($route_name, \\Drupal\\Core\\Routing\\RouteMatchInterface $route_match) {{
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
function {machine_name}_form_alter(&$form, \\Drupal\\Core\\Form\\FormStateInterface $form_state, $form_id) {{
  // Add your form alterations here
}}
""",
            "hook_entity_presave": f"""
/**
 * Implements hook_entity_presave().
 */
function {machine_name}_entity_presave(\\Drupal\\Core\\Entity\\EntityInterface $entity) {{
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
        with open(module_file) as f:
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
        with open(module_file) as f:
            content = f.read()
        
        # Try to extract name from hook_help or comments
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

    @mcp.tool()
    async def module_permission_create(
        machine_name: str,
        permissions: list[dict[str, Any]] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Create or update permissions.yml with custom permissions."""
        if not drush:
            return {"error": "Drush not available"}
        
        module_path = path or f"modules/custom/{machine_name}"
        
        if not os.path.exists(module_path):
            return {"error": f"Module not found: {module_path}"}
        
        perms_file = os.path.join(module_path, f"{machine_name}.permissions.yml")
        
        # Default permissions if not provided
        if not permissions:
            permissions = [
                {
                    "id": f"administer {machine_name}",
                    "title": f"Administer {machine_name.replace('_', ' ').title()}",
                    "description": f"Perform administration tasks for {machine_name.replace('_', ' ').title()}.",
                },
                {
                    "id": f"access {machine_name} content",
                    "title": f"Access {machine_name.replace('_', ' ').title()} content",
                    "description": f"View {machine_name.replace('_', ' ').title()} content.",
                },
            ]
        
        # Read existing permissions.yml or create new
        if os.path.exists(perms_file):
            with open(perms_file) as f:
                perms_yml = yaml.safe_load(f) or {}
        else:
            perms_yml = {}
        
        # Add/update permissions
        for perm in permissions:
            perm_id = perm.get("id", f"administer {machine_name}")
            perms_yml[perm_id] = {
                "title": perm.get("title", perm_id.replace("_", " ").title()),
                "description": perm.get("description", ""),
            }
        
        with open(perms_file, "w") as f:
            yaml.dump(perms_yml, f, default_flow_style=False, sort_keys=False)
        
        return {
            "success": True,
            "permissions_file": perms_file,
            "permissions_added": len(permissions),
            "permissions": list(perms_yml.keys()),
        }

    @mcp.tool()
    async def module_config_schema_create(
        machine_name: str,
        schema_name: str | None = None,
        schema: dict[str, Any] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Create or update config schema YAML for module settings."""
        if not drush:
            return {"error": "Drush not available"}
        
        module_path = path or f"modules/custom/{machine_name}"
        
        if not os.path.exists(module_path):
            return {"error": f"Module not found: {module_path}"}
        
        schema_name = schema_name or f"{machine_name}.settings"
        schema_file = os.path.join(module_path, "config", "schema", f"{machine_name}.schema.yml")
        
        # Default schema if not provided
        if not schema:
            schema = {
                schema_name: {
                    "type": "config_object",
                    "label": f"{machine_name.replace('_', ' ').title()} settings",
                    "mapping": {
                        "enabled": {
                            "type": "boolean",
                            "label": "Enabled",
                        },
                    },
                },
            }
        
        # Read existing schema or create new
        schema_dir = os.path.join(module_path, "config", "schema")
        os.makedirs(schema_dir, exist_ok=True)
        
        if os.path.exists(schema_file):
            with open(schema_file) as f:
                schema_yml = yaml.safe_load(f) or {}
        else:
            schema_yml = {}
        
        # Merge schema
        schema_yml.update(schema)
        
        with open(schema_file, "w") as f:
            yaml.dump(schema_yml, f, default_flow_style=False, sort_keys=False)
        
        return {
            "success": True,
            "schema_file": schema_file,
            "schema_name": schema_name,
            "schema": schema,
        }

    @mcp.tool()
    async def module_test_create(
        machine_name: str,
        test_name: str,
        test_type: str = "KernelTest",
        class_name: str | None = None,
        test_methods: list[str] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Create a PHPUnit/Kernel test skeleton."""
        if not drush:
            return {"error": "Drush not available"}
        
        module_path = path or f"modules/custom/{machine_name}"
        
        if not os.path.exists(module_path):
            return {"error": f"Module not found: {module_path}"}
        
        class_name = class_name or f"{machine_name.capitalize()}{test_name.replace('_', ' ').title().replace(' ', '')}Test"
        
        # Build test directory
        if test_type == "KernelTest":
            test_dir = os.path.join(module_path, "tests", "src", "Kernel")
            base_class = "Drupal\\KernelTests\\KernelTestBase"
        elif test_type == "UnitTest":
            test_dir = os.path.join(module_path, "tests", "src", "Unit")
            base_class = "PHPUnit\\Framework\\TestCase"
        elif test_type == "FunctionalTest":
            test_dir = os.path.join(module_path, "tests", "src", "Functional")
            base_class = "Drupal\\Tests\\BrowserTestBase"
        else:
            return {"error": f"Unknown test type: {test_type}. Available: KernelTest, UnitTest, FunctionalTest"}
        
        os.makedirs(test_dir, exist_ok=True)
        
        # Default test methods
        if not test_methods:
            test_methods = ["testExample"]
        
        # Build test class
        base_class_name = base_class.split("\\")[-1]
        test_class = f"""<?php

namespace Drupal\\Tests\\{machine_name}\\{test_type}s;

use {base_class};

/**
 * Tests for {machine_name}.
 *
 * @group {machine_name}
 */
class {class_name} extends {base_class_name} {{
"""
        
        if test_type == "KernelTest":
            test_class += f"""  /**
   * {{@inheritdoc}}
   */
  protected static \\$modules = ['{machine_name}'];
"""
        elif test_type == "FunctionalTest":
            test_class += """  /**
   * {@inheritdoc}
   */
  protected \\$defaultTheme = 'stark';
"""
        
        for method in test_methods:
            test_class += f"""
  public function test{method.replace('_', ' ').title().replace(' ', '')}() {{
    // TODO: Implement test
    \\$this->assertTrue(TRUE);
  }}
"""
        
        test_class += "}\n"
        
        # Write test file
        test_file = os.path.join(test_dir, f"{class_name}.php")
        with open(test_file, "w") as f:
            f.write(test_class)
        
        return {
            "success": True,
            "test_type": test_type,
            "class_name": class_name,
            "test_file": test_file,
            "methods": test_methods,
        }

    @mcp.tool()
    async def module_dependencies_analyze(
        machine_name: str,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Analyze module code and suggest missing dependencies."""
        if not drush:
            return {"error": "Drush not available"}
        
        module_path = path or f"modules/custom/{machine_name}"
        
        if not os.path.exists(module_path):
            return {"error": f"Module not found: {module_path}"}
        
        module_file = os.path.join(module_path, f"{machine_name}.module")
        info_file = os.path.join(module_path, f"{machine_name}.info.yml")
        
        if not os.path.exists(module_file):
            return {"error": f"Module file not found: {module_file}"}
        
        # Read module file
        with open(module_file) as f:
            content = f.read()
        
        # Read existing info.yml
        if os.path.exists(info_file):
            with open(info_file) as f:
                info_yml = yaml.safe_load(f) or {}
        else:
            info_yml = {}
        
        # Analyze for dependencies
        deps = set()
        
        # Check for service usage
        service_pattern = r'\\\([a-zA-Z_][a-zA-Z0-9_]*::class\)'
        for match in re.finditer(service_pattern, content):
            service = match.group(1)
            if service.startswith('Drupal\\'):
                parts = service.split('\\')
                if len(parts) >= 3 and parts[1] != machine_name:
                    deps.add(parts[1].lower())
        
        # Check for hook implementations that imply dependencies
        hook_deps = {
            "hook_form_alter": "form",
            "hook_entity_presave": "entity",
            "hook_entity_insert": "entity",
            "hook_entity_update": "entity",
            "hook_entity_delete": "entity",
            "hook_views_data": "views",
            "hook_views_data_alter": "views",
            "hook_views_query_alter": "views",
            "hook_field_widget_info": "field",
            "hook_field_formatter_info": "field",
            "hook_block_view": "block",
            "hook_menu": "menu",
            "hook_cron": "cron",
        }
        
        for hook, dep in hook_deps.items():
            if f"function {machine_name}_{hook.replace('hook_', '')}" in content:
                deps.add(dep)
        
        # Check for plugin types that imply dependencies
        plugin_deps = {
            "Plugin\\Block": "block",
            "Plugin\\Field\\FieldWidget": "field",
            "Plugin\\Field\\FieldFormatter": "field",
            "Plugin\\views": "views",
            "Plugin\\migrate": "migrate",
            "Plugin\\rest": "rest",
            "Plugin\\Action": "action",
            "Plugin\\Condition": "condition",
        }
        
        for plugin_ns, dep in plugin_deps.items():
            if plugin_ns in content:
                deps.add(dep)
        
        # Check for service injection
        if "ContainerInterface" in content:
            deps.add("container")
        
        # Check for config factory usage
        if "ConfigFactoryInterface" in content or "config.factory" in content:
            deps.add("config")
        
        # Read existing dependencies
        if os.path.exists(info_file):
            with open(info_file) as f:
                info_yml = yaml.safe_load(f) or {}
        else:
            info_yml = {}
        
        existing_deps = info_yml.get("dependencies", [])
        
        # Find missing dependencies
        missing_deps = deps - set(existing_deps)
        
        return {
            "success": True,
            "machine_name": machine_name,
            "existing_dependencies": existing_deps,
            "suggested_dependencies": sorted(list(missing_deps)),
            "all_detected": sorted(list(deps)),
        }
