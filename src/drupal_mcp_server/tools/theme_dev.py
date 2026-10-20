"""Theme development tools for Drupal."""

import os
from typing import Any

import yaml
from fastmcp import FastMCP


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    _jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def theme_create(
        name: str,
        machine_name: str | None = None,
        description: str = "",
        base_theme: str = "stable9",
        package: str = "Custom",
        core_version_requirement: str = "^10 || ^11",
        regions: dict[str, str] | None = None,
        libraries: dict[str, Any] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Drupal theme with full scaffolding."""
        if not drush:
            return {"error": "Drush not available"}
        
        machine_name = machine_name or name.lower().replace(" ", "_")
        if not machine_name.isidentifier():
            return {"error": f"Invalid machine name: {machine_name}"}
        
        theme_path = path or f"themes/custom/{machine_name}"
        
        # Create theme directory
        os.makedirs(theme_path, exist_ok=True)
        
        # Default regions
        if regions is None:
            regions = {
                "header": "Header",
                "primary_menu": "Primary menu",
                "secondary_menu": "Secondary menu",
                "highlighted": "Highlighted",
                "help": "Help",
                "content": "Content",
                "sidebar_first": "Sidebar first",
                "sidebar_second": "Sidebar second",
                "footer": "Footer",
            }
        
        # Generate .info.yml
        info_yml = {
            "name": name,
            "type": "theme",
            "description": description or f"Custom theme: {name}",
            "base theme": base_theme,
            "package": package,
            "core_version_requirement": core_version_requirement,
            "regions": regions,
        }
        
        info_path = os.path.join(theme_path, f"{machine_name}.info.yml")
        with open(info_path, "w") as f:
            yaml.dump(info_yml, f, default_flow_style=False, sort_keys=False)
        
        # Generate .theme file
        theme_content = f"""<?php

/**
 * @file
 * {description or f"Custom theme: {name}"}
 */

/**
 * Implements hook_theme_suggestions_HOOK_alter().
 */
function {machine_name}_theme_suggestions_page_alter(array &$suggestions, array $variables) {{
  // Add custom template suggestions
}}

/**
 * Implements hook_preprocess_HOOK().
 */
function {machine_name}_preprocess_page(&$variables) {{
  // Add custom preprocessing
}}
"""
        theme_file = os.path.join(theme_path, f"{machine_name}.theme")
        with open(theme_file, "w") as f:
            f.write(theme_content)
        
        # Create templates directory
        templates_dir = os.path.join(theme_path, "templates")
        os.makedirs(templates_dir, exist_ok=True)
        
        # Create default page template
        page_template = """{#
/**
 * @file
 * Default theme implementation to display a page.
 */
#}
<!DOCTYPE html>
<html{{ html_attributes }}>
  <head>
    <head-placeholder token="{{ placeholder_token }}">
    <title>{{ head_title|safe_join(' | ') }}</title>
    <css-placeholder token="{{ placeholder_token }}">
    <js-placeholder token="{{ placeholder_token }}">
  </head>
  <body{{ attributes }}>
    {#
      Keyboard navigation/accessibility link to main content section.
    #}
    <a href="#main-content" class="visually-hidden focusable skip-link">
      {{ 'Skip to main content'|t }}
    </a>
    {{ page_top }}
    {{ page }}
    {{ page_bottom }}
  </body>
</html>
"""
        page_template_file = os.path.join(templates_dir, "page.html.twig")
        with open(page_template_file, "w") as f:
            f.write(page_template)
        
        # Create node template
        node_template = """{#
/**
 * @file
 * Theme override for a node.
 */
#}
<article{{ attributes }}>
  {{ title_prefix }}
  {{ title_suffix }}
  <header>
    {{ node.label }}
  </header>
  {{ content }}
</article>
"""
        node_template_file = os.path.join(templates_dir, "node.html.twig")
        with open(node_template_file, "w") as f:
            f.write(node_template)
        
        # Create block template
        block_template = """{#
/**
 * @file
 * Theme override for a block.
 */
#}
<div{{ attributes }}>
  {{ title_prefix }}
  {{ title_suffix }}
  <div{{ content_attributes }}>
    {{ content }}
  </div>
</div>
"""
        block_template_file = os.path.join(templates_dir, "block.html.twig")
        with open(block_template_file, "w") as f:
            f.write(block_template)
        
        # Create libraries.yml if libraries provided
        if libraries:
            libs_file = os.path.join(theme_path, f"{machine_name}.libraries.yml")
            with open(libs_file, "w") as f:
                yaml.dump(libraries, f, default_flow_style=False, sort_keys=False)
        
        # Create breakpoints.yml
        breakpoints_yml = {
            f"{machine_name}.mobile": {
                "label": "Mobile",
                "mediaQuery": "(min-width: 0px)",
                "weight": 0,
                "multipliers": ["1x"],
            },
            f"{machine_name}.tablet": {
                "label": "Tablet",
                "mediaQuery": "(min-width: 768px)",
                "weight": 1,
                "multipliers": ["1x"],
            },
            f"{machine_name}.desktop": {
                "label": "Desktop",
                "mediaQuery": "(min-width: 1024px)",
                "weight": 2,
                "multipliers": ["1x"],
            },
        }
        breakpoints_file = os.path.join(theme_path, f"{machine_name}.breakpoints.yml")
        with open(breakpoints_file, "w") as f:
            yaml.dump(breakpoints_yml, f, default_flow_style=False, sort_keys=False)
        
        # Create src directory for potential PHP classes
        src_dir = os.path.join(theme_path, "src")
        os.makedirs(src_dir, exist_ok=True)
        
        return {
            "success": True,
            "machine_name": machine_name,
            "path": theme_path,
            "base_theme": base_theme,
            "files_created": [
                f"{machine_name}.info.yml",
                f"{machine_name}.theme",
                "templates/page.html.twig",
                "templates/node.html.twig",
                "templates/block.html.twig",
                f"{machine_name}.libraries.yml" if libraries else None,
                f"{machine_name}.breakpoints.yml",
            ],
        }

    @mcp.tool()
    async def theme_library_create(
        machine_name: str,
        library_name: str,
        css: dict[str, Any] | None = None,
        js: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a theme library."""
        if not drush:
            return {"error": "Drush not available"}
        
        theme_path = path or f"themes/custom/{machine_name}"
        
        if not os.path.exists(theme_path):
            return {"error": f"Theme not found: {theme_path}"}
        
        libs_file = os.path.join(theme_path, f"{machine_name}.libraries.yml")
        
        if os.path.exists(libs_file):
            with open(libs_file) as f:
                libs_yml = yaml.safe_load(f) or {}
        else:
            libs_yml = {}
        
        lib_def: dict[str, Any] = {}
        if css:
            lib_def["css"] = css
        if js:
            lib_def["js"] = js
        if dependencies:
            lib_def["dependencies"] = dependencies
        
        libs_yml[library_name] = lib_def
        
        with open(libs_file, "w") as f:
            yaml.dump(libs_yml, f, default_flow_style=False, sort_keys=False)
        
        return {
            "success": True,
            "library_name": library_name,
            "library_definition": lib_def,
        }

    @mcp.tool()
    async def theme_region_create(
        machine_name: str,
        region_name: str,
        region_label: str,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Add a region to theme."""
        if not drush:
            return {"error": "Drush not available"}
        
        theme_path = path or f"themes/custom/{machine_name}"
        info_file = os.path.join(theme_path, f"{machine_name}.info.yml")
        
        if not os.path.exists(info_file):
            return {"error": f"Theme info file not found: {info_file}"}
        
        with open(info_file) as f:
            info_yml = yaml.safe_load(f) or {}
        
        if "regions" not in info_yml:
            info_yml["regions"] = {}
        
        info_yml["regions"][region_name] = region_label
        
        with open(info_file, "w") as f:
            yaml.dump(info_yml, f, default_flow_style=False, sort_keys=False)
        
        return {
            "success": True,
            "region_name": region_name,
            "region_label": region_label,
            "all_regions": info_yml["regions"],
        }

    @mcp.tool()
    async def theme_template_override(
        machine_name: str,
        template_name: str,
        template_content: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Create a template override in theme."""
        if not drush:
            return {"error": "Drush not available"}
        
        theme_path = path or f"themes/custom/{machine_name}"
        if not os.path.exists(theme_path):
            # The sibling writers all guard this; without the check the tool
            # makedirs'd a stray half-theme for a name that does not exist.
            return {"error": f"Theme not found: {theme_path}"}
        templates_dir = os.path.join(theme_path, "templates")
        template_file = os.path.join(templates_dir, template_name)
        # os.path.join discards templates_dir when template_name is absolute,
        # and `..` climbs out of it: either would write anywhere the server
        # process can. Nested names like views/views-view-table.html.twig are
        # legitimate (and common), so the subdirectory is created below.
        if os.path.isabs(template_name) or not os.path.abspath(
            os.path.normpath(template_file)
        ).startswith(os.path.abspath(templates_dir) + os.sep):
            return {
                "error": (
                    "template_name must stay inside the theme's templates/ "
                    f"directory: {template_name}"
                )
            }
        template_file = os.path.normpath(template_file)
        os.makedirs(os.path.dirname(template_file), exist_ok=True)
        
        if template_content is None:
            # Generate default based on template name
            if template_name.startswith("page"):
                template_content = """{#
/**
 * @file
 * Page template override.
 */
#}
<!DOCTYPE html>
<html{{ html_attributes }}>
  <head>
    <head-placeholder token="{{ placeholder_token }}">
    <title>{{ head_title|safe_join(' | ') }}</title>
    <css-placeholder token="{{ placeholder_token }}">
    <js-placeholder token="{{ placeholder_token }}">
  </head>
  <body{{ attributes }}>
    <a href="#main-content" class="visually-hidden focusable skip-link">
      {{ 'Skip to main content'|t }}
    </a>
    {{ page_top }}
    {{ page }}
    {{ page_bottom }}
  </body>
</html>
"""
            elif template_name.startswith("node"):
                template_content = """{#
/**
 * @file
 * Node template override.
 */
#}
<article{{ attributes }}>
  {{ title_prefix }}
  {{ title_suffix }}
  <header>
    {{ node.label }}
  </header>
  {{ content }}
</article>
"""
            elif template_name.startswith("block"):
                template_content = """{#
/**
 * @file
 * Block template override.
 */
#}
<div{{ attributes }}>
  {{ title_prefix }}
  {{ title_suffix }}
  <div{{ content_attributes }}>
    {{ content }}
  </div>
</div>
"""
            else:
                template_content = "{# Custom template override #}\n{{ content }}"
        
        with open(template_file, "w") as f:
            f.write(template_content)
        
        return {
            "success": True,
            "template_file": template_file,
            "template_name": template_name,
        }

    @mcp.tool()
    async def theme_preprocess_function(
        machine_name: str,
        hook: str,
        code: str,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Add a preprocess function to theme."""
        if not drush:
            return {"error": "Drush not available"}
        
        theme_path = path or f"themes/custom/{machine_name}"
        theme_file = os.path.join(theme_path, f"{machine_name}.theme")
        
        if not os.path.exists(theme_file):
            return {"error": f"Theme file not found: {theme_file}"}
        
        preprocess_func = f"""
/**
 * Implements hook_preprocess_{hook}().
 */
function {machine_name}_preprocess_{hook}(&$variables) {{
{code}
}}
"""
        
        with open(theme_file, "a") as f:
            f.write(f"\n{preprocess_func}\n")
        
        return {
            "success": True,
            "hook": hook,
            "message": f"Added preprocess function for {hook}",
        }

    @mcp.tool()
    async def theme_breakpoint_create(
        machine_name: str,
        breakpoint_id: str,
        label: str,
        media_query: str,
        weight: int = 0,
        multipliers: list[str] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Add a breakpoint to theme."""
        if not drush:
            return {"error": "Drush not available"}
        
        theme_path = path or f"themes/custom/{machine_name}"
        if not os.path.exists(theme_path):
            # Without this the open() below raised FileNotFoundError uncaught
            # for a theme that does not exist: a traceback, not an answer.
            return {"error": f"Theme not found: {theme_path}"}
        bp_file = os.path.join(theme_path, f"{machine_name}.breakpoints.yml")
        
        if multipliers is None:
            multipliers = ["1x"]
        
        if os.path.exists(bp_file):
            with open(bp_file) as f:
                bp_yml = yaml.safe_load(f) or {}
        else:
            bp_yml = {}
        
        bp_yml[breakpoint_id] = {
            "label": label,
            "mediaQuery": media_query,
            "weight": weight,
            "multipliers": multipliers,
        }
        
        with open(bp_file, "w") as f:
            yaml.dump(bp_yml, f, default_flow_style=False, sort_keys=False)
        
        return {
            "success": True,
            "breakpoint_id": breakpoint_id,
            "label": label,
            "media_query": media_query,
        }

    @mcp.tool()
    async def theme_base_change(
        machine_name: str,
        new_base_theme: str,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Change the base theme."""
        if not drush:
            return {"error": "Drush not available"}
        
        theme_path = path or f"themes/custom/{machine_name}"
        info_file = os.path.join(theme_path, f"{machine_name}.info.yml")
        
        if not os.path.exists(info_file):
            return {"error": f"Theme info file not found: {info_file}"}
        
        with open(info_file) as f:
            info_yml = yaml.safe_load(f) or {}
        
        old_base = info_yml.get("base theme", "none")
        info_yml["base theme"] = new_base_theme
        
        with open(info_file, "w") as f:
            yaml.dump(info_yml, f, default_flow_style=False, sort_keys=False)
        
        return {
            "success": True,
            "old_base_theme": old_base,
            "new_base_theme": new_base_theme,
        }

    @mcp.tool()
    async def theme_settings_form(
        machine_name: str,
        settings: dict[str, Any] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Generate theme settings form."""
        if not drush:
            return {"error": "Drush not available"}
        
        theme_path = path or f"themes/custom/{machine_name}"
        if not os.path.exists(theme_path):
            # Without the check this wrote a src/Form tree, routing.yml and
            # services.yml into a theme that does not exist.
            return {"error": f"Theme not found: {theme_path}"}
        
        # Create theme settings form
        form_dir = os.path.join(theme_path, "src", "Form")
        os.makedirs(form_dir, exist_ok=True)
        
        # The class must load on core 10 and 11. Ground truth, core 11.4
        # (see ConfigFormBaseTrait): getEditableConfigNames() is declared
        # `abstract protected` -- non-static -- on both majors. D11's
        # ConfigFormBase constructor gained a required
        # TypedConfigManagerInterface and dropped create(), so a constructor
        # override either breaks the container (one argument registered) or
        # leaves the typed property uninitialized and config() throws on the
        # first build. No constructor plus a create() that passes both
        # services is the shape that works on both; D10's one-argument
        # constructor ignores the extra argument.
        form_class = f"""<?php

namespace Drupal\\{machine_name}\\Form;

use Drupal\\Core\\Form\\ConfigFormBase;
use Drupal\\Core\\Form\\FormStateInterface;
use Symfony\\Component\\DependencyInjection\\ContainerInterface;

class ThemeSettingsForm extends ConfigFormBase {{

  /**
   * {{@inheritdoc}}
   */
  public static function create(ContainerInterface $container) {{
    return new static(
      $container->get('config.factory'),
      $container->get('config.typed')
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
    return '{machine_name}_theme_settings';
  }}

  /**
   * {{@inheritdoc}}
   */
  public function buildForm(array $form, FormStateInterface $form_state) {{
    $config = $this->config('{machine_name}.settings');
"""
        
        if settings:
            for key, value in settings.items():
                setting_type = value.get("type", "textfield")
                form_class += f"""
    $form['{key}'] = [
      '#type' => '{setting_type}',
      '#title' => $this->t('{value.get('title', key.replace('_', ' ').title())}'),
      '#default_value' => $config->get('{key}') ?? '{value.get('default', '')}',
    ];"""
        else:
            form_class += """
    $form['example_setting'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Example setting'),
      '#default_value' => $config->get('example_setting') ?? '',
    ];"""
        
        form_class += """

    return parent::buildForm($form, $form_state);
  }

  /**
   * {@inheritdoc}
   */
  public function submitForm(array &$form, FormStateInterface $form_state) {
    $config = $this->config('{machine_name}.settings');
"""
        if settings:
            for key in settings:
                form_class += f"""
    $config->set('{key}', $form_state->getValue('{key}'));"""
        else:
            form_class += """
    $config->set('example_setting', $form_state->getValue('example_setting'));"""
        
        form_class += """
    $config->save();
    parent::submitForm($form, $form_state);
  }
}
"""
        
        form_file = os.path.join(theme_path, "src", "Form", "ThemeSettingsForm.php")
        with open(form_file, "w") as f:
            f.write(form_class)
        
        # Update routing.yml
        routing_file = os.path.join(theme_path, f"{machine_name}.routing.yml")
        if os.path.exists(routing_file):
            with open(routing_file) as f:
                routing_yml = yaml.safe_load(f) or {}
        else:
            routing_yml = {}
        
        routing_yml[f"{machine_name}.theme_settings"] = {
            "path": f"/admin/appearance/settings/{machine_name}",
            "defaults": {
                "_form": f"\\Drupal\\{machine_name}\\Form\\ThemeSettingsForm",
                "_title": f"{machine_name} theme settings",
            },
            "requirements": {
                "_permission": "administer themes",
            },
        }
        
        with open(routing_file, "w") as f:
            yaml.dump(routing_yml, f, default_flow_style=False, sort_keys=False)
        
        # Update services.yml
        services_file = os.path.join(theme_path, f"{machine_name}.services.yml")
        if os.path.exists(services_file):
            with open(services_file) as f:
                services_yml = yaml.safe_load(f) or {"services": {}}
        else:
            services_yml = {"services": {}}
        
        services_yml.setdefault("services", {})[f"{machine_name}.theme_settings_form"] = {
            "class": f"Drupal\\{machine_name}\\Form\\ThemeSettingsForm",
            # D11's ConfigFormBase constructor requires the typed config
            # manager as well; with only @config.factory the container
            # cannot build this service at all.
            "arguments": ["@config.factory", "@config.typed"],
        }
        
        with open(services_file, "w") as f:
            yaml.dump(services_yml, f, default_flow_style=False, sort_keys=False)
        
        return {
            "success": True,
            "form_file": form_file,
            "settings": settings or {},
        }

    @mcp.tool()
    async def theme_asset_optimize(
        machine_name: str,
        optimize_css: bool = True,
        optimize_js: bool = True,
        aggregate: bool = True,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Configure theme asset optimization."""
        if not drush:
            return {"error": "Drush not available"}
        
        # The four system.performance keys that control aggregation and
        # gzip; each is a real config object on every Drupal site.
        commands = []
        if optimize_css:
            commands.append(("config:set", "system.performance css.preprocess 1"))
        if optimize_js:
            commands.append(("config:set", "system.performance js.preprocess 1"))
        if aggregate:
            commands.append(("config:set", "system.performance css.gzip 1"))
            commands.append(("config:set", "system.performance js.gzip 1"))
        
        results = []
        failures = []
        for cmd, args in commands:
            result = await drush.run(cmd, args.split())
            results.append({"command": f"{cmd} {args}", "result": result})
            # A failed config:set left the site exactly where it was; the
            # tool used to report success:True whatever drush answered.
            if result.get("returncode") not in (None, 0):
                reason = str(result.get("stderr") or "").strip() or (
                    f"exited {result.get('returncode')}"
                )
                failures.append(f"{cmd} {args}: {reason}")
        
        payload: dict[str, Any] = {
            "success": not failures,
            "optimizations": {
                "css": optimize_css,
                "js": optimize_js,
                "aggregate": aggregate,
            },
            "results": results,
        }
        if failures:
            payload["error"] = "; ".join(failures)
        return payload

    @mcp.tool()
    async def theme_debug_enable(
        machine_name: str,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Enable theme debugging (Twig debug, etc.)."""
        # Twig debug is a container parameter (core/services.yml
        # `twig.config`), not a config object. What this tool used to run --
        # three `config:set twig.config …` calls, one of them a single
        # malformed argument string, against a config object that does not
        # exist, with the results discarded -- moved nothing on any site it
        # ever ran against, while the payload claimed twig_debug:True. The
        # real switch is a settings.php line; answering honestly is the only
        # thing a tool may do here.
        return {
            "error": (
                "Twig debug cannot be enabled over Drush: it is a container "
                "parameter (core/services.yml `twig.config`), not a config "
                "object. In the site's settings.php add: "
                "$settings['container_yamls'][] = DRUPAL_ROOT . "
                "'/sites/development.services.yml;' and in "
                "development.services.yml: parameters: twig.config: "
                "{debug: true, auto_reload: true, cache: false}."
            ),
        }

    @mcp.tool()
    async def theme_lint_twig(
        machine_name: str,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Lint Twig templates in theme."""
        if not drush:
            return {"error": "Drush not available"}
        
        theme_path = path or f"themes/custom/{machine_name}"
        templates_dir = os.path.join(theme_path, "templates")
        
        if not os.path.exists(templates_dir):
            return {"error": "Templates directory not found"}
        
        # Find all twig files
        twig_files = []
        for root, _dirs, files in os.walk(templates_dir):
            for file in files:
                if file.endswith(".twig"):
                    twig_files.append(os.path.join(root, file))
        
        # Basic syntax check
        errors = []
        for twig_file in twig_files:
            with open(twig_file) as f:
                content = f.read()
            
            # Check for balanced braces
            if content.count("{{") != content.count("}}"):
                errors.append({"file": twig_file, "error": "Unbalanced {{ }} braces"})
            if content.count("{%") != content.count("%}"):
                errors.append({"file": twig_file, "error": "Unbalanced {% %} tags"})
            if content.count("{#") != content.count("#}"):
                errors.append({"file": twig_file, "error": "Unbalanced {# #} comments"})
        
        return {
            "success": True,
            "theme": machine_name,
            "files_checked": len(twig_files),
            "errors": errors,
        }
