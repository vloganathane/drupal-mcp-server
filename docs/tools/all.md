<!-- GENERATED FILE — do not edit by hand.
Regenerate with: python scripts/generate_tool_docs.py
To change a use case or status note, edit docs/tools/_tool_overrides.yaml. -->

# All Tools

Every tool the server registers (414 across 41 modules), generated from the source code and the live-test harness. Tool names are the runtime names an MCP client sees.

## How to read the status column

| Badge | Meaning |
|-------|---------|
| ✅ ddev / ✅ lando | Live sweep on that environment returned usable data |
| ⚠️ ddev / ⚠️ lando | Live sweep: the tool answered, but the answer was a refusal or lookup miss (often fixture- or site-dependent, not necessarily a bug) |
| 🧩 | Blocked on that environment: needs a module, binary, or subsystem the test site does not have |
| ⏭️ | Skipped by the sweep on purpose: it starts/stops the environment the sweep runs against |
| 💀 | Dead — a product bug (currently none) |
| 🧪 unit | Has offline unit-test coverage |
| ❔ no offline tests | No coverage in `tests/unit` — the weekly live sweep is its only check |

The live sweeps run against a provisioned local site (`tests/live/`); see that directory's README for what each verdict really measures. `REJECTED` counts are largely harness fixture artefacts — a tool asked for an id this site does not have — so read them as "not disproven" rather than "broken".

## Modules

| Category | Module | Tools | Detailed docs |
|----------|--------|------:|---------------|
| Content & Entities | [content](#content) | 14 | 2 of 14 |
| Content & Entities | [users](#users) | 12 | 1 of 12 |
| Content & Entities | [taxonomy](#taxonomy) | 10 | — |
| Content & Entities | [comments](#comments) | 10 | — |
| Content & Entities | [revisions](#revisions) | 5 | — |
| Content & Entities | [paragraphs](#paragraphs) | 10 | — |
| Content & Entities | [media_enhanced](#media_enhanced) | 8 | — |
| Configuration & Structure | [config](#config) | 8 | 1 of 8 |
| Configuration & Structure | [fields](#fields) | 10 | — |
| Configuration & Structure | [menus](#menus) | 10 | — |
| Configuration & Structure | [views](#views) | 7 | — |
| Configuration & Structure | [layout_builder](#layout_builder) | 15 | — |
| Configuration & Structure | [pathauto](#pathauto) | 8 | — |
| Configuration & Structure | [redirects](#redirects) | 7 | — |
| Configuration & Structure | [metatag](#metatag) | 9 | — |
| Search, Feeds & Multilingual | [search_api](#search_api) | 13 | — |
| Search, Feeds & Multilingual | [feeds](#feeds) | 12 | — |
| Search, Feeds & Multilingual | [multilingual](#multilingual) | 18 | — |
| Workflow, Forms & Contact | [moderation](#moderation) | 13 | — |
| Workflow, Forms & Contact | [webform](#webform) | 16 | — |
| Workflow, Forms & Contact | [contact](#contact) | 9 | — |
| Workflow, Forms & Contact | [commerce](#commerce) | 18 | — |
| Site Status, Database & DevOps | [status](#status) | 4 | 4 of 4 |
| Site Status, Database & DevOps | [database](#database) | 4 | — |
| Site Status, Database & DevOps | [devops](#devops) | 20 | 1 of 20 |
| Site Status, Database & DevOps | [scheduler](#scheduler) | 7 | — |
| Site Status, Database & DevOps | [performance](#performance) | 7 | — |
| Migration & Analysis | [migration](#migration) | 17 | — |
| Migration & Analysis | [analysis](#analysis) | 9 | 3 of 9 |
| Migration & Analysis | [ai](#ai) | 4 | — |
| Codebase, Module & Theme Development | [codebase](#codebase) | 12 | — |
| Codebase, Module & Theme Development | [module_dev](#module_dev) | 12 | — |
| Codebase, Module & Theme Development | [theme_dev](#theme_dev) | 11 | — |
| Codebase, Module & Theme Development | [theme_analysis](#theme_analysis) | 8 | 4 of 8 |
| Codebase, Module & Theme Development | [code_audit](#code_audit) | 7 | — |
| Security | [security_audit](#security_audit) | 10 | 2 of 10 |
| Headless & Integrations | [headless](#headless) | 10 | — |
| Headless & Integrations | [drupal_org](#drupal_org) | 12 | — |
| Testing, Accessibility & Export | [testing](#testing) | 9 | — |
| Testing, Accessibility & Export | [accessibility](#accessibility) | 5 | — |
| Testing, Accessibility & Export | [exports](#exports) | 4 | 1 of 4 |

## content

Content — 14 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| [`create_node`](index.md#create_node) | Create a single node of the specified bundle with given fields.<br>_Publish an article from an agent-driven content workflow_ | `{"bundle": "article", "fields": {"title": "Hello"}}` | ✅ ddev · 🧩 lando · 🧪 unit |
| `get_node` | Get a single node by ID with optional relationship includes.<br>_Fetch one node with its referenced entities in a single request_ | `{"nid": "123"}` | ✅ ddev · ⚠️ lando · ❔ no offline tests |
| `update_node` | Update a single node by ID with given fields.<br>_Apply an editor's field changes to an existing page without rewriting the whole bundle_ | `{"nid": "123", "fields": {"title": "Hello"}}` | ✅ ddev · ⚠️ lando · 🧪 unit |
| `delete_node` | Delete a single node by ID.<br>_Remove a draft or duplicate node as part of site cleanup after content review_ | `{"nid": "123"}` | ✅ ddev · ⚠️ lando · 🧪 unit |
| [`query_nodes`](index.md#query_nodes) | Query nodes with filters, sorts, includes, and pagination.<br>_Build a listing page by filtering, sorting, and paginating nodes in one request_ | `{}` | ✅ ddev · 🧩 lando · 🧪 unit |
| `upload_media` | Upload a file to the media library.<br>_Add a locally generated image or document to the media library for use in content_ | `{"file_path": "value"}` | 🧩 ddev · 🧩 lando · 🧪 unit |
| `create_media` | Create media entity from a remote URL (image, video, document, etc.).<br>_Attach a remote video or image to content without downloading the file first_ | `{"media_type": "value", "source_url": "value", "name": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `clean_nodes_ai` | Clean duplicate or malformed nodes using AI. Requires confirm=True to execute deletions.<br>_Audit a bundle for duplicate or malformed nodes before a confirmed cleanup run_ | `{"entity_type": "node", "bundle": "article"}` | ⚠️ ddev · 🧩 lando · ❔ no offline tests |
| `map_fields_ai` | Suggest AI-powered field mappings from a source field list to a target bundle.<br>_Plan a content migration by mapping legacy source fields onto a target content type_ | `{"source_fields": [], "target_bundle": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `bulk_update_nodes` | Apply the same field updates to every node matching a set of filters.<br>_Apply one field change across many nodes at once, such as relabeling a shared term_ | `{"bundle": "article", "filters": {"status": "1"}, "updates": {}}` | ✅ ddev · 🧩 lando · ❔ no offline tests |
| `fix_media_references` | Find broken media references across a content type.<br>_Diagnose missing images on a content type after media entities were removed_ | `{"content_type": "value"}` | ✅ ddev · 🧩 lando · ❔ no offline tests |
| `bulk_update_aliases` | Regenerate URL aliases for a content type.<br>_Regenerate URL aliases for a content type after changing Pathauto patterns_ | `{"bundle": "article", "pattern": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `analyze_content_quality` | Analyze content quality with AI for specific nodes or an entire type.<br>_Review recent articles for thin or inconsistent content before a quality audit_ | `{}` | ⚠️ ddev · 🧩 lando · ❔ no offline tests |
| `generate_test_content` | Generate sample nodes for a bundle to populate a development site.<br>_Populate a development site with sample nodes to test layouts and views_ | `{"bundle": "article"}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## users

Users — 12 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| [`create_user`](index.md#create_user) | Create a user account.<br>_Onboard a new team member with an account and roles in one step_ | `{"mail": "value", "name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `get_user` | Get a user by ID with optional relationship includes.<br>_Inspect a specific account including its relationships when handling a support request_ | `{"uid": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `get_user_by_email` | Get a user by email address.<br>_Look up an account when only the person's email address is known_ | `{"mail": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `update_user` | Update a user account.<br>_Correct account details like email or display name during user administration_ | `{"uid": "value", "fields": {"title": "Hello"}}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `delete_user` | Delete a user account.<br>_Remove a spam or test account as part of periodic user maintenance_ | `{"uid": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `list_users` | List users with filters and pagination.<br>_Page through or filter the site's accounts for an access review or audit report_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `assign_role` | Assign a role to a user.<br>_Grant an editor elevated permissions after a promotion or project kickoff_ | `{"uid": "value", "role": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `remove_role` | Remove a role from a user.<br>_Revoke elevated access when someone leaves a project or changes responsibilities_ | `{"uid": "value", "role": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `list_roles` | List all available roles.<br>_Discover which roles exist before assigning one to a user_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `get_user_roles` | Get roles assigned to a user.<br>_Verify a user's current permissions before troubleshooting an access problem_ | `{"uid": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `block_user` | Block a user account.<br>_Suspend an account immediately after reported spam while preserving its content_ | `{"uid": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `unblock_user` | Unblock a user account.<br>_Restore access for a legitimately suspended user after their issue is resolved_ | `{"uid": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## taxonomy

Taxonomy — 10 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `create_vocabulary` | Create a taxonomy vocabulary.<br>_Set up a new classification scheme, such as product categories, on a fresh site_ | `{"vid": "1", "name": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `get_vocabulary` | Get a taxonomy vocabulary by ID.<br>_Check a vocabulary's name and description before adding terms to it_ | `{"vid": "1"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `update_vocabulary` | Update a taxonomy vocabulary.<br>_Rename or re-describe a taxonomy as part of an information architecture cleanup_ | `{"vid": "1", "fields": {"title": "Hello"}}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `delete_vocabulary` | Delete a taxonomy vocabulary.<br>_Remove an obsolete classification scheme during a site restructuring_ | `{"vid": "1"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `list_vocabularies` | List all taxonomy vocabularies.<br>_Survey the site's classification schemes before tagging or migration work_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `create_term` | Create a taxonomy term in a vocabulary.<br>_Add a new topic to an existing vocabulary as part of ongoing content categorization_ | `{"vid": "1", "name": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `get_term` | Get a taxonomy term by ID.<br>_Verify a term's ID or parent before assigning it to content_ | `{"vid": "1", "tid": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `update_term` | Update a taxonomy term.<br>_Rename or re-parent a term when the taxonomy structure evolves_ | `{"vid": "1", "tid": "value", "fields": {"title": "Hello"}}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `delete_term` | Delete a taxonomy term.<br>_Prune an unused term while tidying up a taxonomy vocabulary_ | `{"vid": "1", "tid": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `list_terms` | List terms in a vocabulary with filters and pagination.<br>_Fetch a vocabulary's terms to populate a filter or autocomplete widget_ | `{"vid": "1"}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## comments

Comments — 10 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `comment_list` | List comments.<br>_Review recent site comments, optionally scoped to one piece of content_ | `{}` | 🧩 ddev · 🧩 lando · ❔ no offline tests |
| `comment_get` | Get a single comment by ID.<br>_Read one comment in full, including its author, when investigating a report_ | `{"comment_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `comment_create` | Create a new comment.<br>_Post a reply or moderation note onto an existing piece of content_ | `{"entity_type": "node", "entity_id": "value", "subject": "value", "body": "value"}` | 🧩 ddev · 🧩 lando · ❔ no offline tests |
| `comment_update` | Update a comment.<br>_Fix a typo or correct a status on a comment during moderation_ | `{"comment_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `comment_delete` | Delete a comment.<br>_Remove a comment confirmed as spam during routine moderation cleanup_ | `{"comment_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `comment_thread_list` | List comment thread for an entity.<br>_Reconstruct a full reply thread under an article to review a discussion_ | `{"entity_type": "node", "entity_id": "value"}` | 🧩 ddev · 🧩 lando · ❔ no offline tests |
| `comment_approve` | Approve a comment (set status to published).<br>_Publish a pending comment after a moderator reviews it and finds it acceptable_ | `{"comment_id": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `comment_unapprove` | Unapprove a comment (set status to unpublished).<br>_Hide a comment from public view pending further moderation review_ | `{"comment_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `comment_field_settings` | Get comment field settings for entity type/bundle.<br>_Check how comments are configured on a content type before adjusting moderation_ | `{"entity_type": "node", "bundle": "article"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `comment_field_configure` | Configure comment field settings.<br>_Enable threaded comments or adjust per-page limits when tuning community features_ | `{"entity_type": "node", "bundle": "article"}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## revisions

Revisions — 5 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `revision_list` | List revisions for an entity.<br>_Check the current revision of an entity when tracking its edit history_ | `{"entity_type": "node", "entity_id": "value"}` | ✅ ddev · ⚠️ lando · 🧪 unit |
| `revision_get` | Get a specific revision of an entity.<br>_Retrieve the exact state of a node at a past revision when auditing an edit_ | `{"entity_type": "node", "entity_id": "value", "revision_id": "value"}` | 🧩 ddev · ⚠️ lando · 🧪 unit |
| `revision_revert` | Revert an entity to a specific revision.<br>_Roll back a page to its last good state after an erroneous edit goes live_ | `{"entity_type": "node", "entity_id": "value", "revision_id": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `revision_delete` | Delete a specific revision of an entity.<br>_Attempt to remove a sensitive stale revision before a public release_ | `{"entity_type": "node", "entity_id": "value", "revision_id": "value"}` | 🧩 ddev · 🧩 lando · 🧪 unit |
| `revision_diff` | Diff two revisions of an entity.<br>_Compare two versions of a page to see exactly which fields changed and how_ | `{"entity_type": "node", "entity_id": "value", "revision_id_1": "value", "revision_id_2": "value"}` | ✅ ddev · ⚠️ lando · 🧪 unit |

## paragraphs

Paragraphs — 10 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `paragraphs_type_list` | List all paragraph types on a Drupal site.<br>_Checking which paragraph bundles already exist before adding a new one to a content type_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `paragraphs_type_get` | Get a single paragraph type configuration by ID.<br>_Inspecting a paragraph type's settings before mirroring the same structure elsewhere_ | `{"type_id": "value"}` | ✅ ddev · ⚠️ lando · 🧪 unit |
| `paragraphs_type_create` | Create a new paragraph type.<br>_Standing up a new paragraph type while building out a modular landing-page layout_ | `{"type_id": "value", "label": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `paragraphs_type_update` | Update an existing paragraph type.<br>_Renaming or reordering a paragraph type after a content restructure_ | `{"type_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `paragraphs_type_delete` | Delete a paragraph type.<br>_Removing an unused paragraph type during cleanup once no content references it_ | `{"type_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `paragraphs_item_list` | List paragraph items, optionally filtered by type.<br>_Auditing existing paragraph instances to see how a layout type is really used in content_ | `{}` | ✅ ddev · ⚠️ lando · 🧪 unit |
| `paragraphs_item_get` | Get a single paragraph item by ID.<br>_Troubleshooting a misrendering paragraph by pulling its stored field values_ | `{"paragraph_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `paragraphs_item_create` | Create a new paragraph item of the specified type.<br>_Populating content entities with paragraph blocks as part of a scripted migration_ | `{"type_id": "value", "fields": {"title": "Hello"}}` | ⚠️ ddev · 🧩 lando · ❔ no offline tests |
| `paragraphs_item_update` | Update a paragraph item.<br>_Fixing copy in an embedded paragraph when an editor reports outdated text on a live page_ | `{"paragraph_id": "value", "fields": {"title": "Hello"}}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `paragraphs_item_delete` | Delete a paragraph item.<br>_Purging orphaned paragraph records during content cleanup after a migration_ | `{"paragraph_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |

## media_enhanced

Media Enhanced — 8 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `media_type_list` | List all media types.<br>_Finding out which media types a site defines before ingesting a new kind of asset_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `media_type_get` | Get a single media type by ID.<br>_Checking a media type's source field before wiring up oEmbed or file imports_ | `{"media_type_id": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `media_type_create` | Create a new media type.<br>_Adding a media type for a new source, such as remote images, during site buildout_ | `{"id": "1", "label": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `media_create_from_url` | Create media from URL (oEmbed).<br>_Embedding a YouTube or Vimeo video in content without downloading the file first_ | `{"url": "value", "media_type": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `media_create_from_base64` | Create media from base64 encoded file data.<br>_Uploading a logo or PDF produced by another tool when no public URL is available_ | `{"base64_data": "value", "filename": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `media_derivative_generate` | Generate a specific derivative for media.<br>_Rebuilding a missing image size after an image style's dimensions were changed_ | `{"media_id": "value", "derivative_id": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `media_bulk_import` | Bulk import media files from directory.<br>_Seeding a fresh environment with the asset directory used by an existing site_ | `{"source_dir": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `media_library_list` | List media library items.<br>_Checking whether an asset already exists before uploading a duplicate to the library_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## config

Config — 8 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `config_get` | Get a single configuration object by name.<br>_Looking up a config object's live values before deciding what to change_ | `{"name": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `config_set` | Set a single configuration value.<br>_Tweaking a single setting, like the site name, without running a full config import_ | `{"name": "value", "value": {}}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `export_config` | Export Drupal configuration to files.<br>_Snapshotting active configuration into files before starting a deployment_ | `{}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `import_config` | Import Drupal configuration from files.<br>_Applying configuration committed to the repo after deploying new code_ | `{}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `sync_config` | Sync configuration between environments via Drush.<br>_Previewing then pushing config changes from one environment to another after review_ | `{"source_env": "value", "target_env": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `diff_config` | Show differences in configuration between environments.<br>_Explaining why two environments behave differently before touching either one_ | `{"config_name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `split_config` | Split configuration into separate directories for atomic deployment.<br>_Extracting only the config objects a feature needs so deploys can ship independently_ | `{"config_names": []}` | 🧩 ddev · 🧩 lando · ❔ no offline tests |
| [`config_status`](index.md#config_status) | Compare active configuration with the exported sync directory.<br>_Checking pending configuration changes before deciding whether an import is safe_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |

## fields

Fields — 10 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `field_config_list` | List all field configurations on a Drupal site.<br>_Auditing which fields exist before adding a new content type_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `field_config_get` | Get a single field configuration by ID.<br>_Reviewing one field's settings, like allowed values, before writing content to it_ | `{"config_id": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `field_config_create` | Create a new field configuration.<br>_Attaching a new field to a content type during a content model rollout_ | `{"field_name": "value", "field_type": "value", "entity_type": "node", "bundle": "article", "label": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `field_config_update` | Update a field configuration.<br>_Making a field optional after editors report they cannot save drafts without it_ | `{"config_id": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `field_config_delete` | Delete a field configuration.<br>_Dropping an abandoned field during content model cleanup once its data is retired_ | `{"config_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `field_storage_list` | List all field storage configurations on a Drupal site.<br>_Checking whether shared storage already exists before adding the field to another bundle_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `field_storage_get` | Get a single field storage configuration by ID.<br>_Confirming a field's cardinality or storage type before changing how content is entered_ | `{"config_id": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `field_storage_create` | Create a new field storage configuration.<br>_Defining storage for a field that will be reused across several content types_ | `{"field_name": "value", "field_type": "value", "label": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `field_storage_update` | Update a field storage configuration.<br>_Raising a field's maximum cardinality when editors need more than one value_ | `{"config_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `field_storage_delete` | Delete a field storage configuration.<br>_Retiring shared field storage during schema cleanup after confirming no bundle uses it_ | `{"config_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |

## menus

Menus — 10 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `menu_list` | List all menus on a Drupal site.<br>_Seeing which menus exist before placing a new navigation link_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `menu_get` | Get a single menu configuration by ID.<br>_Checking a menu's label before referencing it in a theme's navigation config_ | `{"menu_id": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `menu_create` | Create a new menu.<br>_Setting up a dedicated footer menu while building out site navigation_ | `{"menu_id": "value", "label": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `menu_update` | Update an existing menu.<br>_Renaming a menu after a restructure so the admin UI matches the new terminology_ | `{"menu_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `menu_delete` | Delete a menu.<br>_Cleaning up a leftover menu during site rebuilds after its links were migrated_ | `{"menu_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `menu_link_list` | List menu links, optionally filtered by menu.<br>_Reviewing a menu's current links before reordering navigation for a redesign_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| `menu_link_get` | Get a single menu link by ID.<br>_Inspecting a link's parent and weight when a nested menu item renders in the wrong place_ | `{"link_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `menu_link_create` | Create a new menu link.<br>_Adding a newly published page to the main navigation after content goes live_ | `{"menu_id": "value", "title": "value", "link": {}}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `menu_link_update` | Update a menu link.<br>_Repointing a menu link after a page slug changed, or nesting it under a new parent_ | `{"link_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `menu_link_delete` | Delete a menu link.<br>_Removing a link to a retired page during navigation cleanup_ | `{"link_id": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |

## views

Views — 7 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `views_list` | List all views on a Drupal site.<br>_Survey every View on the site to find the one powering a given listing page_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| `views_get` | Get a single view configuration by ID.<br>_Inspect one View's full config to learn its displays, filters, or field setup_ | `{"view_id": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `views_create` | Create a new view.<br>_Stand up a new listing page by defining its fields, filters, and pager up front_ | `{"view_id": "value", "label": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `views_update` | Update an existing view.<br>_Change an existing View's label, fields, or exposed filters without touching others_ | `{"view_id": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `views_delete` | Delete a view.<br>_Remove a retired View left behind after a content architecture cleanup_ | `{"view_id": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `views_execute` | Execute a view and return its rows.<br>_Preview the rows a View actually returns for a given display and filter combination_ | `{"view_id": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `views_export` | Export a view as configuration YAML or JSON.<br>_Grab a View's config as YAML or JSON to commit to version control or clone_ | `{"view_id": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |

## layout_builder

Layout Builder — 15 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `block_list` | List all blocks.<br>_Find which blocks exist and where they sit before rearranging a sidebar_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `block_get` | Get a single block by ID.<br>_Read a single block's plugin, settings, and visibility rules_ | `{"block_id": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `block_create` | Create a new block.<br>_Add a new block to a region with specific settings and visibility conditions_ | `{"id": "1", "label": "value", "plugin": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `block_update` | Update a block.<br>_Adjust a block's label, region, settings, or visibility rules_ | `{"block_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `block_delete` | Delete a block.<br>_Remove a stale block that is no longer needed on the site_ | `{"block_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `block_place` | Place a block in a region with weight.<br>_Reorder a block within its region by giving it a new weight_ | `{"block_id": "value", "region": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `layout_builder_list` | Report which entity view displays have Layout Builder enabled.<br>_See which bundles already have Layout Builder enabled before enabling more_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `layout_builder_get` | Read the Layout Builder layout for an entity type and bundle.<br>_Read a bundle's full section and component structure to understand its layout_ | `{"entity_type": "node", "bundle": "article"}` | ✅ ddev · ⚠️ lando · 🧪 unit |
| `layout_builder_create` | Replace the Layout Builder layout for a bundle.<br>_Set a bundle's layout from scratch, replacing every section in one pass_ | `{"entity_type": "node", "bundle": "article", "layout": {}}` | ✅ ddev · ⚠️ lando · ❔ no offline tests |
| `layout_builder_update` | Update the Layout Builder layout for a bundle.<br>_Swap in a new section set for a bundle or just toggle component locking_ | `{"entity_type": "node", "bundle": "article"}` | ✅ ddev · ⚠️ lando · ❔ no offline tests |
| `layout_builder_sections_list` | List the sections in a bundle's Layout Builder layout.<br>_List a bundle's sections and components to see what will change before an edit_ | `{"entity_type": "node", "bundle": "article"}` | ✅ ddev · ⚠️ lando · ❔ no offline tests |
| `layout_builder_section_add` | Append a section to a bundle's Layout Builder layout.<br>_Append a new section with chosen components to the end of a bundle's layout_ | `{"entity_type": "node", "bundle": "article", "section": {}}` | ✅ ddev · ⚠️ lando · 🧪 unit |
| `block_plugin_list` | List available block plugins.<br>_Discover which block plugins are available to place in a layout_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `block_region_list` | List available regions for a theme.<br>_Check a theme's region names before placing a block into one_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `layout_builder_override_remove` | Remove a Layout Builder override so an entity falls back to the default.<br>_Revert an entity's one-off Layout Builder tweaks so it follows the default again_ | `{"entity_type": "node", "bundle": "article"}` | ✅ ddev · ⚠️ lando · 🧪 unit |

## pathauto

Pathauto — 8 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `pathauto_pattern_list` | List pathauto patterns.<br>_List existing URL patterns before adding or changing one for a new content type_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `pathauto_pattern_get` | Get a single pathauto pattern by ID.<br>_Read a single pattern's definition to confirm its tokens and target bundle_ | `{"pattern_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `pathauto_pattern_create` | Create a new pathauto pattern.<br>_Add a new URL pattern so new content of a bundle gets consistent aliases_ | `{"id": "1", "label": "value", "entity_type": "node", "bundle": "article", "pattern": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `pathauto_pattern_update` | Update a pathauto pattern.<br>_Change a pattern's token string or weight when the URL scheme is revised_ | `{"pattern_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `pathauto_pattern_delete` | Delete a pathauto pattern.<br>_Retire an obsolete pattern as part of cleaning up URL generation rules_ | `{"pattern_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `pathauto_generate` | Generate pathauto aliases.<br>_Backfill aliases for content created before a pattern existed or was fixed_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `pathauto_token_list` | List available pathauto tokens.<br>_Find valid tokens to use when writing or debugging a pathauto pattern_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `redirect_pattern_list` | List redirect patterns.<br>_Review existing redirect patterns before adding or pruning redirects_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## redirects

Redirects — 7 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `redirect_list` | List all redirects on a Drupal site.<br>_Survey current redirects to check for duplicates or loops_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `redirect_get` | Get a single redirect configuration by ID.<br>_Inspect one redirect's source, target, and status code_ | `{"redirect_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `redirect_create` | Create a new redirect.<br>_Send an old URL to its new home after a page move_ | `{"redirect_source": "value", "redirect_redirect": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `redirect_update` | Update an existing redirect.<br>_Fix a redirect that points to the wrong target or uses the wrong status code_ | `{"redirect_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `redirect_delete` | Delete a redirect.<br>_Remove a redirect that is no longer needed after a URL settles_ | `{"redirect_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `redirect_bulk_create` | Create multiple redirects in bulk.<br>_Seed many redirects at once from a mapping after a site migration_ | `{"redirects": {}}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `redirect_bulk_delete` | Delete multiple redirects in bulk.<br>_Clear out a batch of obsolete redirects during a cleanup_ | `{"redirect_ids": []}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## metatag

Metatag — 9 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `metatag_config_list` | List all metatag configurations.<br>_Survey metatag defaults per entity type and bundle before changing site-wide SEO_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `metatag_config_get` | Get a single metatag configuration by ID.<br>_Inspect a single metatag defaults record to see its configured tags_ | `{"config_id": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `metatag_config_create` | Create a new metatag configuration.<br>_Add a new metatag defaults record for an entity type or bundle_ | `{"id": "1", "label": "value", "entity_type": "node"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `metatag_config_update` | Update a metatag configuration.<br>_Change the default tags shown for a content type's listing or detail pages_ | `{"config_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `metatag_defaults_get` | Get default metatag values for entity type/bundle.<br>_Fetch the effective default metatag values for a specific entity and bundle_ | `{"entity_type": "node"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `metatag_defaults_set` | Set default metatag values for entity type/bundle.<br>_Apply a standard set of title, description, and Open Graph defaults_ | `{"entity_type": "node"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `metatag_token_list` | List available metatag tokens.<br>_Find valid tokens to reference entity fields in metatag defaults_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `metatag_canonical_set` | Set canonical URL for an entity.<br>_Point a page at its canonical URL to avoid duplicate-content SEO issues_ | `{"entity_type": "node", "entity_id": "value", "canonical_url": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `metatag_jsonld_generate` | Generate JSON-LD structured data for entity.<br>_Produce JSON-LD structured data for a page to check rich-result markup_ | `{"entity_type": "node", "entity_id": "value"}` | ✅ ddev · ⚠️ lando · ❔ no offline tests |

## search_api

Search API — 13 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `search_api_server_list` | List all Search API servers.<br>_Checking which search backends exist before wiring up a new index_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `search_api_server_get` | Get a single Search API server by ID.<br>_Inspecting a server's backend settings when searches return unexpected results_ | `{"server_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `search_api_server_create` | Create a new Search API server.<br>_Standing up a search backend on a site that has none configured yet_ | `{"id": "1", "label": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `search_api_index_list` | List Search API indexes.<br>_Finding the right index to query or reindex before touching search config_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `search_api_index_get` | Get a single Search API index by ID.<br>_Reviewing an index's datasource and processors to debug missing results_ | `{"index_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `search_api_index_create` | Create a new Search API index.<br>_Adding search to a new content type by wiring an index to an existing server_ | `{"id": "1", "label": "value", "server_id": "value", "datasource": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `search_api_index_update` | Update a Search API index.<br>_Tuning processors or renaming an index after a content model change_ | `{"index_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `search_api_index_reindex` | Trigger reindexing of a Search API index.<br>_Content changed outside Drupal and search results are stale_ | `{"index_id": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `search_api_index_clear` | Clear a Search API index.<br>_Rebuilding a corrupted or outdated index from scratch during maintenance_ | `{"index_id": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `search_api_server_enable` | Enable a Search API server.<br>_Turning search back on after maintenance on the backend is finished_ | `{"server_id": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `search_api_server_disable` | Disable a Search API server.<br>_Taking search offline temporarily while the backend is being migrated_ | `{"server_id": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `search_api_facet_list` | List Search API facets.<br>_Checking which facets exist and their facet\_source\_id before wiring up a block_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `search_api_facet_create` | Create a Search API facet.<br>_Letting visitors narrow search results by a category or tag field_ | `{"id": "1", "label": "value", "index_id": "value", "field": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |

## feeds

Feeds — 12 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `feeds_feed_list` | List all feeds.<br>_Surveying existing imports before adding another data feed to the site_ | `{}` | 🧩 ddev · 🧩 lando · ❔ no offline tests |
| `feeds_feed_get` | Get a single feed by ID.<br>_Checking a feed's fetcher, parser and processor when an import behaves oddly_ | `{"feed_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `feeds_feed_create` | Create a new feed.<br>_Setting up recurring content import from an external CSV or RSS source_ | `{"id": "1", "label": "value"}` | 🧩 ddev · 🧩 lando · ❔ no offline tests |
| `feeds_feed_update` | Update a feed.<br>_Changing a feed's source URL or column mapping after the upstream format shifts_ | `{"feed_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `feeds_feed_delete` | Delete a feed.<br>_Cleaning up a one-off import feed after a content migration is done_ | `{"feed_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `feeds_import` | Run a feed import.<br>_Running an import right now instead of waiting for the next cron pass_ | `{"feed_id": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `feeds_import_status` | Get feed import status.<br>_Checking whether an import kicked off earlier finished or hit errors_ | `{"feed_id": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `feeds_log_list` | List feed import logs.<br>_Looking for import history and being redirected to feeds\_import\_status instead_ | `{}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `feeds_tamper_list` | List tamper plugins for a feed.<br>_Auditing field cleanup plugins chained onto a feed before editing import logic_ | `{"feed_id": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `feeds_parser_list` | List available feed parsers.<br>_Getting the exact parser plugin IDs when configuring a new feed_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `feeds_fetcher_list` | List available feed fetchers.<br>_Confirming which fetcher plugins are installed before creating a feed_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `feeds_processor_list` | List available feed processors.<br>_Finding what a feed can write to before creating the import_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## multilingual

Multilingual — 18 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `language_list` | List all languages.<br>_Checking which languages a site already has before enabling translations_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `language_get` | Get a single language by langcode.<br>_Verifying a language's direction and weight before translating content into it_ | `{"langcode": "en"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `language_add` | Add a new language.<br>_A new locale is launching and the site needs its language registered_ | `{"langcode": "en", "name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `language_enable` | Enable a language.<br>_Turning a previously disabled language back on for an upcoming launch_ | `{"langcode": "en"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `language_disable` | Disable a language.<br>_Pausing a language when translators aren't ready yet but content exists_ | `{"langcode": "en"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `language_delete` | Delete a language.<br>_Removing a language that was added in error before any content uses it_ | `{"langcode": "en"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `content_translation_enable` | Enable content translation for entity type/bundle.<br>_Letting editors translate a content type after a client asks for it_ | `{"entity_type": "node"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `translation_status` | Get translation status for an entity.<br>_Checking which translations already exist before assigning work to a translator_ | `{"entity_type": "node", "entity_id": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `translation_add` | Add translation for an entity.<br>_A node exists only in the source language and now needs its first translation_ | `{"entity_type": "node", "entity_id": "value", "langcode": "en"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `translation_update` | Update translation for an entity.<br>_Source content changed and existing translations now carry outdated copy_ | `{"entity_type": "node", "entity_id": "value", "langcode": "en"}` | ✅ ddev · ⚠️ lando · ❔ no offline tests |
| `interface_translation_list` | List the interface translations Drupal holds.<br>_Finding which UI strings are already translated when localizing the admin_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| `interface_translation_add` | Add an interface translation for one source string.<br>_Fixing a wrong button label in one language without a full .po import_ | `{"source": "value", "langcode": "en", "translation": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `interface_translation_update` | Change an existing interface translation.<br>_A client wording change means an existing UI translation is now stale_ | `{"source": "value", "langcode": "en", "translation": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `interface_translation_delete` | Remove an interface translation from one language.<br>_Reverting a bad UI string fix so the standard .po import value takes over_ | `{"source": "value", "langcode": "en"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `config_translation_list` | List the config objects that support translation.<br>_Before translating menu labels or content types, checking what the site supports_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `config_translation_add` | Translate a config entity.<br>_Localizing a content type name or menu link label for a new language_ | `{"config_name": "value", "langcode": "en", "translation": {}}` | ✅ ddev · ⚠️ lando · 🧪 unit |
| `language_negotiation_get` | Get language negotiation configuration.<br>_Debugging why a translated page serves the wrong language URL prefix_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `language_negotiation_set` | Set language negotiation method.<br>_Choosing between path prefixes, domains or session detection for language URLs_ | `{"method": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## moderation

Moderation — 13 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `moderation_state_list` | List all moderation states.<br>_Mapping the states content can sit in across this site's workflows_ | `{}` | 🧩 ddev · 🧩 lando · ❔ no offline tests |
| `moderation_state_get` | Get a single moderation state by ID.<br>_Checking a state's label and ordering after an editor reports a confusing name_ | `{"state_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `moderation_state_create` | Create a new moderation state.<br>_Adding a legal review step to a workflow that currently jumps straight to publish_ | `{"workflow_id": "value", "state_id": "value", "label": "value"}` | 🧩 ddev · 🧩 lando · ❔ no offline tests |
| `moderation_state_update` | Update a moderation state.<br>_Renaming a state editors keep misreading or moving it up the approval order_ | `{"state_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `moderation_state_delete` | Delete a moderation state.<br>_Cleaning up a leftover state after a workflow was simplified during a migration_ | `{"state_id": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `moderation_transition_list` | List a workflow's moderation transitions.<br>_Working out which steps an editor is actually allowed to take next_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| `moderation_transition_get` | Get a single moderation transition by ID.<br>_Tracing where a transition leads before automating an approval step around it_ | `{"transition_id": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `moderation_transition_create` | Create a new moderation transition on a workflow.<br>_Adding a sign-off path so reviewed drafts can advance to the next stage_ | `{"workflow_id": "value", "transition_id": "value", "label": "value", "from_states": [], "to_state": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `moderation_transition_delete` | Delete a moderation transition from a workflow.<br>_Retiring a redundant approval step while consolidating duplicate workflows_ | `{"workflow_id": "value", "transition_id": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `moderation_transition_execute` | Execute a moderation transition on an entity.<br>_Moving an editor's approved draft forward on their behalf after sign-off offline_ | `{"entity_type": "node", "entity_id": "value", "transition_id": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `content_moderation_dashboard` | Get content pending moderation - dashboard view.<br>_Morning check of everything not yet published so nothing stalls in the queue_ | `{}` | ✅ ddev · 🧩 lando · ❔ no offline tests |
| `workflow_list` | List all workflows.<br>_Figuring out which workflows exist before pointing a content type at one_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `workflow_get` | Get a single workflow by ID.<br>_Inspecting a workflow's states after an editor reports a draft got stuck_ | `{"workflow_id": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |

## webform

Webform — 16 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `webform_list` | List all webforms.<br>_Finding the right form id before wiring an automation or reviewing responses_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `webform_get` | Get a single webform by ID.<br>_Checking a form's settings before linking to it from a new landing page_ | `{"webform_id": "contact"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `webform_create` | Create a new webform.<br>_Standing up a signup form for a campaign that was just approved_ | `{"id": "1", "label": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `webform_update` | Update a webform.<br>_Changing a form's label or taking it offline after a campaign deadline passed_ | `{"webform_id": "contact"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `webform_delete` | Delete a webform.<br>_Removing a duplicate test form left over from a campaign setup attempt_ | `{"webform_id": "contact"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `webform_submission_list` | List webform submissions.<br>_Support asks how many people registered for the webinar through the site_ | `{}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `webform_submission_get` | Get a single webform submission by ID.<br>_Pulling one enquiry in full to answer a customer citing a ticket number_ | `{"submission_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `webform_submission_delete` | Delete a webform submission.<br>_Purging test submissions before handing real data to the marketing team_ | `{"submission_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `webform_element_list` | List elements in a webform.<br>_Auditing what fields a form actually asks for before mapping it to a CRM_ | `{"webform_id": "contact"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `webform_element_create` | Add an element to a webform.<br>_Adding the phone number field a client just requested to a signup form_ | `{"webform_id": "contact", "element_key": "value", "element_type": "value", "label": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `webform_handler_list` | List the handlers attached to a webform.<br>_Tracing where submissions go after a client reports notifications went missing_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| `webform_handler_create` | Create a webform handler (email, remote post, etc.).<br>_Wiring an email or webhook handler so new submissions reach the team's inbox_ | `{"id": "1", "webform_id": "contact", "handler_type": "value", "label": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `webform_handler_update` | Update a webform handler.<br>_Pointing a notification handler at a new recipient after a team member left_ | `{"handler_id": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `webform_handler_delete` | Delete a webform handler from its webform.<br>_Removing a broken integration handler while cleaning up dead submission routing_ | `{"handler_id": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `webform_token_list` | List available webform tokens.<br>_Writing an email template and needing the exact placeholder for a field_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `webform_export_submissions` | Export webform submissions.<br>_Handing marketing a CSV of contest entries without granting site access_ | `{"webform_id": "contact"}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## contact

Contact — 9 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `contact_form_list` | List all contact forms.<br>_Checking which contact forms exist before adding one to the site footer_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `contact_form_get` | Get a single contact form by ID.<br>_Confirming who currently receives messages from the press enquiry form_ | `{"form_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `contact_form_create` | Create a new contact form.<br>_Creating a dedicated support form after the general inbox got too noisy_ | `{"id": "1", "label": "value", "recipients": []}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `contact_form_update` | Update a contact form.<br>_Redirecting form notifications to a new mailbox when someone changes roles_ | `{"form_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `contact_form_delete` | Delete a contact form.<br>_Cleaning up a duplicate contact form left behind during a site rebuild_ | `{"form_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `contact_message_list` | List contact form submissions.<br>_Seeing what visitors have written through the site's contact forms this week_ | `{}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `contact_message_get` | Get a single contact message by ID.<br>_Reading one message in full so support can follow up on a specific complaint_ | `{"message_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `contact_message_delete` | Delete a contact message.<br>_Deleting test messages that accumulated while a form was being developed_ | `{"message_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `contact_spam_check` | Check if a contact message is spam.<br>_Deciding whether a suspicious message should be kept or purged from the inbox_ | `{"message_id": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## commerce

Commerce — 18 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `commerce_store_list` | List all commerce stores.<br>_Checking which stores exist before adding products for a new sales channel_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `commerce_store_get` | Get a single commerce store by ID.<br>_Confirming a store's contact email and currency ahead of launch_ | `{"store_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `commerce_store_create` | Create a new commerce store.<br>_Opening a second store to sell into a different currency region_ | `{"id": "1", "label": "value", "mail": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `commerce_store_update` | Update a commerce store.<br>_Updating the store's support address after a team handover_ | `{"store_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `commerce_product_list` | List commerce products.<br>_Merchandiser wants every product still unpublished before the catalog goes live_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `commerce_product_get` | Get a single commerce product by ID.<br>_Verifying one product's price and SKU against a supplier's price list_ | `{"product_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `commerce_product_create` | Create a new commerce product.<br>_Adding a newly launched item to the catalog ahead of the seasonal sale_ | `{"id": "1", "title": "value", "store_id": "value", "price": {}}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `commerce_product_update` | Update a commerce product.<br>_Applying a supplier's price change to a product before the sale starts_ | `{"product_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `commerce_order_list` | List commerce orders.<br>_Checking which orders are awaiting fulfilment at the start of the day_ | `{}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `commerce_order_get` | Get a single commerce order by ID.<br>_Investigating a customer's complaint about what their order contains_ | `{"order_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `commerce_order_create` | Create a new commerce order.<br>_Recording a phone order from a customer who cannot use the website_ | `{"id": "1", "store_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `commerce_order_update` | Update a commerce order.<br>_Correcting an order state after a refund was handled outside the site_ | `{"order_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `commerce_payment_gateway_list` | List payment gateways.<br>_Answering which payment methods the store can accept before checkout edits_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `commerce_payment_gateway_get` | Get a single payment gateway by ID.<br>_Checking a gateway's configuration before taking it out of test mode_ | `{"gateway_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `commerce_promotion_list` | List commerce promotions.<br>_Reviewing active discounts before the holiday sale schedule is finalised_ | `{}` | 🧩 ddev · 🧩 lando · ❔ no offline tests |
| `commerce_promotion_create` | Create a new commerce promotion.<br>_Setting up a launch discount for a promotion announced next week_ | `{"id": "1", "label": "value", "store_id": "value", "offer": {}}` | 🧩 ddev · 🧩 lando · ❔ no offline tests |
| `commerce_shipping_method_list` | List shipping methods.<br>_Checking delivery options before editing the checkout page_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `commerce_shipping_method_create` | Create a new shipping method.<br>_Adding a flat-rate shipping option for a new regional delivery zone_ | `{"id": "1", "label": "value", "store_id": "value", "plugin": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |

## status

Status — 4 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| [`status_report`](index.md#status_report) | Run the site's status report (what /admin/reports/status shows).<br>_When a client asks what is wrong, pull the site status report without logging into /admin/reports_ | `{}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| [`database_updates`](index.md#database_updates) | List pending database updates (read-only; runs nothing).<br>_After a composer update, see whether new module schema changes are waiting before touching the site_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| [`available_updates`](index.md#available_updates) | List packages with newer versions available, from composer.<br>_When planning an upgrade, list outdated core and contrib packages, or only those with security advisories_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| [`health_check`](index.md#health_check) | Check that this server can actually reach a working Drupal site.<br>_When other tools return opaque connection errors, pinpoint whether Drush, the database or JSON:API is failing_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |

## database

Database — 4 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `db_query` | Execute a single read-only SELECT query on the Drupal database.<br>_Answering a question straight from the database when no Views export or JSON:API resource exposes it_ | `{"query": "keyword"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `db_tables` | List all database tables.<br>_Before querying an unfamiliar site, see which tables exist and how they are named_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| `db_table_info` | Get table schema information.<br>_Needing column names and types of one table before writing a WHERE clause or a report_ | `{"table": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `db_count` | Count rows in a table.<br>_A quick row count, optionally filtered, to sanity-check content volumes or migration results_ | `{"table": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |

## devops

Devops — 20 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| [`drush_command`](index.md#drush_command) | Execute any Drush command.<br>_Run a Drush command no dedicated tool covers and get structured output_ | `{"command": "status"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `ddev_setup` | Generate .ddev/config.yaml for a local Drupal environment.<br>_Bootstrapping a local DDEV environment for a project that has no .ddev config yet_ | `{}` | ⚠️ ddev · ✅ lando · 🧪 unit |
| `ddev_start` | Start the DDEV project under ``project_name``.<br>_Before anything else can reach the site, bring a stopped DDEV environment back up_ | `{}` | ⏭️ ddev · ⏭️ lando · 🧪 unit |
| `ddev_stop` | Stop the DDEV project under ``project_name`` (a directory).<br>_Freeing local ports and memory at the end of a session, or before restarting cleanly_ | `{}` | ⏭️ ddev · ⏭️ lando · 🧪 unit |
| `ddev_exec` | Run ``command`` in the container of the DDEV project under ``project_name`` (a directory containing ``.ddev``).<br>_Running a one-off container command, like a build step, that needs the DDEV shell not Drush_ | `{"command": "status"}` | ✅ ddev · ⚠️ lando · 🧪 unit |
| `lando_start` | Start the Lando project under ``project_name`` (a directory).<br>_Bringing a Lando-based local site back up when the other tools report connection failures_ | `{}` | ⏭️ ddev · ⏭️ lando · 🧪 unit |
| `lando_stop` | Stop the Lando project under ``project_name`` (a directory).<br>_Shutting down a Lando site's containers to free ports between sessions or before a reset_ | `{}` | ⏭️ ddev · ⏭️ lando · 🧪 unit |
| `lando_exec` | Run ``command`` in the container of the Lando project under ``project_name`` (a directory).<br>_Running a one-off command inside the Lando container, such as a build step or file fix_ | `{"command": "status"}` | ⏭️ ddev · ⏭️ lando · 🧪 unit |
| `lando_setup` | Generate .lando.yml for a local Drupal environment.<br>_Generating a starter .lando.yml for a Drupal project that has no Lando config yet_ | `{}` | ✅ ddev · ⚠️ lando · 🧪 unit |
| `acquia_deploy` | Deploy to Acquia Cloud via acquia-cli or Drush acquia integration.<br>_Shipping a tested branch to an Acquia environment, with database updates and cache rebuild included_ | `{"environment": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `backup_database` | Create database backup via Drush.<br>_Taking a database dump first, before running updates, imports or other risky changes_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `cache_rebuild` | Clear and rebuild all Drupal caches via Drush.<br>_After enabling a module or editing code, make the change take effect immediately instead of waiting_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `composer_install` | Run composer install.<br>_A fresh clone or CI step where vendor is missing and the lock file must be installed_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| `composer_require` | Require one or more packages via composer.<br>_Adding one or several contributed modules to the project straight through composer_ | `{"package": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `composer_update` | Run composer update.<br>_When ready to adopt newer dependency versions, run the update in the project directory_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `drush_cron` | Run cron.<br>_Triggering cron now so queues and aggregations run without waiting for the schedule_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `drush_watchdog` | Show recent log entries from watchdog.<br>_Debugging a reported error by pulling recent log entries filtered by type or severity_ | `{}` | ✅ ddev · 🧩 lando · ❔ no offline tests |
| `cache_clear` | Clear specific cache bins.<br>_Isolating stale output by clearing only the suspect cache bin rather than everything_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| `drush_updb` | Run database updates.<br>_After the pending update list is checked, apply schema updates once a database backup exists_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `drush_php_eval` | Execute arbitrary PHP code via Drush.<br>_A quick one-line Drupal API call, like resetting a state key, without writing a module_ | `{"code": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |

## scheduler

Scheduler — 7 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `cron_run` | Run cron.<br>_Running scheduled work immediately when the site's own cron has not fired on its own_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `cron_list` | List the jobs Drupal runs on cron, and when cron last ran.<br>_When something did not process, see which modules implement hook\_cron and when cron last ran_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| `queue_list` | List all queues.<br>_Checking which queues exist and how backed up they are before a bulk import run_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| `queue_run` | Run a specific queue.<br>_After a bulk operation, drain a specific queue so its pending items get processed now_ | `{"queue_name": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `queue_delete` | Delete queue items: one by id, the oldest `count`, or the whole queue.<br>_Clearing a queue stuck with poison or leftover test items before a clean retry_ | `{"queue_name": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `queue_info` | Get queue information.<br>_Checking one queue's item count and detail before draining or deleting anything_ | `{"queue_name": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `queue_create` | Create a queue and make it ready to accept items.<br>_Preparing a named queue to accept its first items when wiring up or testing a worker_ | `{"queue_name": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |

## performance

Performance — 7 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `performance_query_log` | Get slow query log.<br>_Hunting a slow page by finding which queries the site logged as slow in watchdog_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `performance_cache_stats` | Get cache performance statistics.<br>_Seeing whether cache bins are being churned instead of serving hits under traffic_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `performance_redis_info` | Get Redis server info.<br>_Diagnosing cache backend health when Redis is backing the site's cache bins_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `performance_bigpipe_status` | Check BigPipe status and configuration.<br>_Confirming whether BigPipe is enabled before investigating why page delivery looks plain_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `performance_bigpipe_enable` | Enable or disable BigPipe.<br>_Toggling BigPipe during a performance test, a reversible config change to revert afterwards_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `performance_memcached_stats` | Get Memcached statistics.<br>_Spotting evictions or memory limits in Memcached that explain repeated cache misses_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `performance_page_load_analyze` | Analyze page load performance.<br>_Getting a rough before and after number when comparing a page's response times_ | `{"url": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## migration

Migration — 17 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `generate_migration_yaml` | Generate migration YAML configuration.<br>_Kicking off a new migration and needing a correctly shaped YAML stub to fill in_ | `{"migration_type": "value", "source": {}, "destination": {}}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `generate_module_migration` | Generate migration module for a custom module with source plugin, process plugins, and migration template.<br>_Scaffolding a custom migration module for a legacy source without hand-writing plugin boilerplate_ | `{"module_name": "value", "source_version": "value", "target_version": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `run_migration_test` | Test migration with limited records.<br>_Importing only a handful of records to confirm mappings before committing to a full run_ | `{"migration_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `validate_migration` | Validate migration configuration.<br>_Confirming a migration is registered and seeing how many records it has already processed_ | `{"migration_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `rollback_migration` | Rollback a completed migration.<br>_Undoing a test import so the same migration can run again cleanly after its mapping is fixed_ | `{"migration_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `sync_media_files` | Sync media files between paths.<br>_Copying image files onto the new server before the content that references them is imported_ | `{"source_path": "value", "destination_path": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `migrate_taxonomy` | Migrate taxonomy vocabularies and their terms.<br>_Rebuilding vocabularies and terms first so incoming content has somewhere to point_ | `{"vocabularies": {}}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `create_migration_plan` | Create or replace a persisted migration plan.<br>_Starting a multi-day migration and needing one persisted record of scope, mappings, and notes_ | `{"migration_id": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `get_migration_plan` | Read a persisted migration plan and its tracked state.<br>_Picking a migration back up in a new session and needing its source, mappings, and tracked state_ | `{"migration_id": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `list_migration_plans` | List all persisted migration plans.<br>_Figuring out which migrations exist on this site and where each one stands_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `migration_status` | Summarize migration progress for a persisted plan.<br>_Reporting how far a planned migration has progressed and whether anything is failing_ | `{"migration_id": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `migrate_records` | Copy a batch of source records into the target Drupal site through JSON:API.<br>_Pushing an already-extracted batch of source rows into the target site through JSON:API_ | `{"migration_id": "value", "entity_type": "node", "records": {}}` | ✅ ddev · ✅ lando · 🧪 unit |
| `record_migration_result` | Record the outcome of a manually executed migration operation.<br>_Logging outcomes from a hand-run import so the plan's counts stay trustworthy later_ | `{"migration_id": "value", "entity_type": "node", "legacy_id": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `analyze_source_site` | Analyze a source Drupal JSON:API resource type and optionally store counts in a plan.<br>_Counting what the legacy site really exposes, authenticating so field-level access is not undercounted_ | `{}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `reconcile_migration_counts` | Compare recorded source counts with current target-site counts.<br>_After an import run, spotting which entity types still fall short of the recorded source counts_ | `{"migration_id": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `run_migration_wave` | Fetch and migrate one resource type from the plan's source site into the target site.<br>_Migrating one resource type at a time so any failure stays contained to a single wave_ | `{"migration_id": "value", "resource_type": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `run_migration` | Run an ordered end-to-end migration for one or all planned entity types.<br>_Executing the whole plan in dependency order once the plan exists and dry runs look right_ | `{"migration_id": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |

## analysis

Analysis — 9 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `analyze_d7_site` | Analyze a Drupal 7 site for D10 upgrade readiness.<br>_Scoping a Drupal 7 retirement before committing to a timeline_ | `{"site_url": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `analyze_d9_site` | Analyze a Drupal 9+ site for deprecated code and APIs.<br>_Before starting a D10 upgrade, knowing which removed APIs custom code still depends on_ | `{"site_url": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `inventory_content_types` | List all content types on a Drupal site.<br>_Mapping the content model of an unfamiliar site before planning field or migration work_ | `{"site_url": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `inventory_modules` | List all modules on a Drupal site.<br>_Checking which contrib and custom modules a site runs before estimating upgrade effort_ | `{"site_url": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `map_modules_d7_to_d10` | Map Drupal 7 modules to D10 equivalents using AI + known mappings.<br>_Turning a legacy module list into replacement decisions when known mappings do not cover everything_ | `{"module_list": []}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `find_deprecated_code` | Scan custom modules for deprecated Drupal APIs.<br>_Triaging a custom codebase by pointing at the specific files still calling removed APIs_ | `{"site_path": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| [`find_entity_references`](index.md#find_entity_references) | Find which bundles use reference fields targeting an entity type.<br>_Before retiring a vocabulary or content type, seeing which bundles reference it_ | `{"entity_type": "node"}` | ✅ ddev · ✅ lando · 🧪 unit |
| [`search_entities`](index.md#search_entities) | Case-insensitive substring search across entity titles and names.<br>_Given a title or username from a support ticket, locating the entity without knowing its id_ | `{"query": "keyword"}` | ✅ ddev · ✅ lando · 🧪 unit |
| [`find_entity_by_path`](index.md#find_entity_by_path) | Resolve a URL path or alias ("/about", "/node/123") to its entity.<br>_Tracing a URL from analytics back to the node, term, or user that actually serves it_ | `{"path": "/about"}` | ✅ ddev · ✅ lando · 🧪 unit |

## ai

AI — 4 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `ai_analyze_content_quality` | Analyze content quality using AI.<br>_Reviewing node bodies at volume for thin or poorly structured text before publication_ | `{"content": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `ai_suggest_field_mappings` | Suggest field mappings using AI.<br>_When source field names do not match the target bundle, getting a first-pass mapping to review_ | `{"source_fields": [], "target_bundle": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `ai_generate_migration_plan` | Generate migration plan using AI.<br>_Early in an unfamiliar upgrade, wanting a draft migration approach to refine with the team_ | `{"source_type": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `ai_translate_content` | Translate content using AI.<br>_Localizing a body of content into another language without a human translator in the loop_ | `{"content": "value", "target_lang": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |

## codebase

Codebase — 12 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `codebase_index_refresh` | Rebuild the local codebase module index.<br>_Right after installing or creating modules, making sure the other codebase tools see them_ | `{}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `codebase_search` | Search the local codebase for modules providing a capability.<br>_Looking for existing code that already provides a capability before writing a new module_ | `{"query": "keyword"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `codebase_module_list` | List indexed local modules with metadata.<br>_Auditing what custom, contrib, and core code ships with the project docroot_ | `{}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `codebase_module_describe` | Describe one local module in full.<br>_Deciding whether to touch a module by seeing its hooks, routes, and reverse dependencies first_ | `{"module": "mymodule"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `codebase_unused_modules` | List custom/contrib modules nothing references and that define no hooks.<br>_Preparing a cleanup pass and needing modules nothing depends on or hooks through_ | `{}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `codebase_redundancy_check` | Check whether the local codebase already covers a capability.<br>_Before scaffolding new code, confirming the capability is not already covered nearby_ | `{"query": "keyword"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `codebase_hooks_find` | Find which local modules implement a hook, with file and line.<br>_Debugging unexpected behavior by finding which modules implement a given hook, with file and line_ | `{"hook_name": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `codebase_paths_list` | Show the configured docroot and the module directories indexed.<br>_When search results look incomplete, verifying which directories are actually indexed_ | `{}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `codebase_files_list` | List every file in a local module as module-relative paths.<br>_Getting the exact module-relative path before reading a file or pulling out a function_ | `{"module": "mymodule"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `codebase_directory_tree` | Show a local module's directory structure as a nested tree.<br>_Getting a quick sense of an unfamiliar module's layout before reading into it_ | `{"module": "mymodule"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `codebase_file_read` | Read one file from a local module.<br>_Reviewing a module's .module or YAML from the agent without opening a terminal on the server_ | `{"module": "mymodule", "path": "/about"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `codebase_function_read` | Extract a single PHP function (with its docblock) from a module.<br>_Pulling one hook or method with its docblock instead of paging through whole files_ | `{"module": "mymodule", "function_name": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |

## module_dev

Module Dev — 12 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `module_create` | Create a new Drupal module with full scaffolding.<br>_Starting a custom module and wanting routing, services, permissions, and schema in place at once_ | `{"name": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `module_service_create` | Create a service definition with PHP class stub.<br>_Adding an injectable service to an existing module without hand-editing services.yml and the class_ | `{"machine_name": "value", "service_name": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `module_plugin_create` | Create a plugin (block, field, views, etc.) with proper scaffolding.<br>_Needing a block, Views plugin, or field widget with the right base class and annotations wired_ | `{"machine_name": "value", "plugin_type": "value", "plugin_id": "value", "label": "value"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `module_form_create` | Create a form class (ConfigForm, ConfirmForm, FormBase, etc.) with proper scaffolding.<br>_Adding a settings or confirmation form and wanting its route and service registration handled too_ | `{"machine_name": "value", "form_name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `module_controller_create` | Create a controller class with routing.<br>_Standing up a new page backed by a controller class with matching routing entries_ | `{"machine_name": "value", "controller_name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `module_event_subscriber_create` | Create an event subscriber service with getSubscribedEvents method.<br>_Replacing a deprecated hook or Rules reaction with a subscriber correctly tagged in the container_ | `{"machine_name": "value", "subscriber_name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `module_hook_implement` | Implement a hook in an existing module.<br>_Dropping a standard hook implementation into an existing module instead of typing boilerplate_ | `{"machine_name": "value", "hook": "value"}` | 🧩 ddev · 🧩 lando · ❔ no offline tests |
| `module_info_generate` | Generate .info.yml from existing module code (reverse engineering).<br>_Adopting a module missing its .info.yml and inferring one from the code that already exists_ | `{"machine_name": "value"}` | 🧩 ddev · 🧩 lando · ❔ no offline tests |
| `module_permission_create` | Create or update permissions.yml with custom permissions.<br>_Adding permission strings so roles can be granted access without editing YAML by hand_ | `{"machine_name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `module_config_schema_create` | Create or update config schema YAML for module settings.<br>_Before config export or upgrade, giving module settings a typed schema Drupal will validate_ | `{"machine_name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `module_test_create` | Create a PHPUnit/Kernel test skeleton.<br>_Starting coverage for a module and needing the right base class, directory, and group annotation_ | `{"machine_name": "value", "test_name": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `module_dependencies_analyze` | Analyze module code and suggest missing dependencies.<br>_Before shipping, catching dependencies used in code but missing from the info.yml_ | `{"machine_name": "value"}` | 🧩 ddev · 🧩 lando · ❔ no offline tests |

## theme_dev

Theme Dev — 11 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `theme_create` | Create a new Drupal theme with full scaffolding.<br>_Kicking off a new custom theme without hand-writing the info.yml, .theme, and templates_ | `{"name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `theme_library_create` | Create or update a theme library.<br>_Adding or versioning a CSS/JS library so the theme can finally attach new assets_ | `{"machine_name": "value", "library_name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `theme_region_create` | Add a region to theme.<br>_A layout needs one more sidebar without hand-editing the region list in info.yml_ | `{"machine_name": "value", "region_name": "value", "region_label": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `theme_template_override` | Create a template override in theme.<br>_Copying a core template into the theme so markup can be edited without patching core_ | `{"machine_name": "value", "template_name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `theme_preprocess_function` | Add a preprocess function to theme.<br>_Exposing an extra variable to Twig without remembering the exact hook signature_ | `{"machine_name": "value", "hook": "value", "code": "value"}` | 🧩 ddev · 🧩 lando · ❔ no offline tests |
| `theme_breakpoint_create` | Add a breakpoint to theme.<br>_Defining breakpoints that match the designer's specs for responsive images_ | `{"machine_name": "value", "breakpoint_id": "value", "label": "value", "media_query": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `theme_base_change` | Change the base theme.<br>_Moving off a starter theme once the design system no longer needs it_ | `{"machine_name": "value", "new_base_theme": "value"}` | 🧩 ddev · 🧩 lando · ❔ no offline tests |
| `theme_settings_form` | Generate theme settings form.<br>_Giving site builders a settings form for logo, color, or layout toggles in the UI_ | `{"machine_name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `theme_asset_optimize` | Configure theme asset optimization.<br>_Trimming CSS/JS aggregation settings while chasing a slow first paint_ | `{"machine_name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `theme_debug_enable` | Enable theme debugging (Twig debug, etc.).<br>_Chasing which Twig template actually rendered a block when the output looks wrong_ | `{"machine_name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `theme_lint_twig` | Lint Twig templates in theme.<br>_Catching a syntax slip before a cache rebuild white-screens the page_ | `{"machine_name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## theme_analysis

Theme Analysis — 8 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| [`theme_active`](index.md#theme_active) | List the site's themes: default, admin, and every enabled one.<br>_Confirming which theme owns the front end versus the admin before making changes_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| `theme_info` | Describe one theme: metadata, base-theme chain, regions, libraries.<br>_Checking a theme's base-theme chain and libraries before building on top of it_ | `{"theme_name": "olivero"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `theme_regions` | Region layout of a theme with the blocks placed in each one.<br>_Planning a block layout and needing to know which regions actually exist_ | `{"theme_name": "olivero"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| [`theme_blocks`](index.md#theme_blocks) | List placed blocks with optional theme, region, and text filters.<br>_Hunting down which region a stray block is placed in across enabled themes_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| `theme_templates` | List a theme's Twig templates (``*.html.twig``) with sizes.<br>_Surveying how many templates a theme ships before deciding where to add overrides_ | `{"theme_name": "olivero"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `theme_template_overrides` | Which core/module templates a theme overrides, and which it invented.<br>_Checking whether your theme already overrides a module template you are about to edit_ | `{"theme_name": "olivero"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| [`template_suggestions`](index.md#template_suggestions) | Twig template names Drupal will try for an entity, specific first.<br>_Naming a template like node--article--unpublished.html.twig and verifying Drupal looks for it_ | `{"entity_type": "node"}` | ✅ ddev · ✅ lando · 🧪 unit |
| [`view_template_info`](index.md#view_template_info) | Template names for overriding a Views display, verified against the site.<br>_Overriding a Views display and needing the exact template names the site will try_ | `{"view_name": "content"}` | 🧩 ddev · 🧩 lando · 🧪 unit |

## code_audit

Code Audit — 7 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `code_audit_phpstan` | Run PHPStan static analysis on Drupal custom modules.<br>_Finding type errors and dead code in a custom module before it hits code review_ | `{"path": "/about"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `drupal_check` | Run Drupal Check for deprecated code detection.<br>_Upgrading to Drupal 11 and needing to know which custom code uses deprecated APIs_ | `{"path": "/about"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `code_sniffer` | Run PHP_CodeSniffer with Drupal coding standards.<br>_Checking a patch against Drupal coding standards before submitting it_ | `{"path": "/about"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `deprecation_scan` | Scan for deprecated Drupal API usage.<br>_Scoping how much work a core upgrade will take across the whole custom codebase_ | `{"path": "/about"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `security_audit` | Run security-focused static analysis.<br>_Getting a strict static analysis pass over hand-written code prior to an external review_ | `{"path": "/about"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `composer_audit` | Run Composer security audit on dependencies.<br>_Before deploying, checking whether installed dependencies carry known advisories_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `code_quality_report` | Run multiple code quality tools and generate combined report.<br>_Wanting one combined lint and analysis summary instead of running three tools separately_ | `{"path": "/about"}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## security_audit

Security Audit — 10 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `security_scan` | Run security-focused SAST using PHPStan with security extensions.<br>_A pre-release SAST pass on custom code where only PHPStan and its security extension matter_ | `{"path": "/about"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `dependency_scan` | Scan dependencies for vulnerabilities using Composer audit and other tools.<br>_Checking composer packages against vulnerability advisories before tagging a release_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `config_security_check` | Check Drupal configuration for security issues.<br>_Auditing exported config for risky settings before pushing it to production_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `permission_audit` | Audit user permissions and roles.<br>_After a role change, confirming no regular user quietly gained an admin-only permission_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| `sql_injection_scan` | Scan for SQL injection vulnerabilities in custom code.<br>_Reviewing custom database queries for unsanitized input before the code goes live_ | `{"path": "/about"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `xss_scan` | Scan for XSS vulnerabilities in custom code.<br>_Checking custom output for unescaped user-supplied input ahead of a security review_ | `{"path": "/about"}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `csp_audit` | Content Security Policy audit.<br>_The browser console shows CSP violations and you need to know which directive to relax_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `file_permissions_audit` | Audit file permissions for security issues.<br>_Hardening a public files directory where an uploaded executable would be a problem_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| [`code_security_scan`](index.md#code_security_scan) | Scan custom code for vulnerability patterns — no tools to install.<br>_A quick vulnerability-pattern sweep of custom modules with no vendor tools installed_ | `{}` | 🧩 ddev · 🧩 lando · 🧪 unit |
| [`route_access_audit`](index.md#route_access_audit) | Classify every route's access control from *.routing.yml files.<br>_Finding routes with no access check before the site is exposed publicly_ | `{}` | 🧩 ddev · 🧩 lando · 🧪 unit |

## headless

Headless — 10 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `jsonapi_schema_get` | Get JSON:API schema (OpenAPI/Swagger).<br>_Building a front-end client and needing the whole JSON:API surface in OpenAPI form_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `jsonapi_include_optimize` | Get optimized include paths for entity type.<br>_A JSON:API request is round-tripping several times and you want the correct include path_ | `{"entity_type": "node", "includes": []}` | ⚠️ ddev · ⚠️ lando · ❔ no offline tests |
| `jsonapi_sparse_fieldsets` | Get entity with sparse fieldsets (only requested fields).<br>_Shrinking a heavy JSON:API response down to only the fields the page renders_ | `{"entity_type": "node", "fields": {"title": "Hello"}}` | ✅ ddev · 🧩 lando · 🧪 unit |
| `graphql_schema_get` | Get GraphQL schema.<br>_Writing a GraphQL query without knowing which types and fields the site exposes_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| `graphql_query` | Execute a GraphQL query.<br>_Fetching exactly the content fields a component needs from a decoupled front end_ | `{"query": "keyword"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `graphql_schema_extend` | Extend GraphQL schema with custom fields (requires schema customization module).<br>_A component needs a computed field that Drupal's default schema does not expose_ | `{"type_name": "value", "fields": {"title": "Hello"}}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `nextjs_helpers_generate` | Generate Next.js helper functions for Drupal entities.<br>_Scaffolding typed fetch helpers for a Next.js site consuming Drupal content_ | `{"entity_types": []}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `gatsby_helpers_generate` | Generate Gatsby source plugin config and helpers.<br>_Wiring a Gatsby site to Drupal data without writing the source plugin config by hand_ | `{"entity_types": []}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `jsonapi_resources_list` | List all available JSON:API resources.<br>_Discovering which endpoints exist before writing a single API request_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `jsonapi_resource_types` | Get all resource types available in JSON:API.<br>_Checking available types and bundles before filtering a JSON:API collection query_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## drupal_org

Drupal.org — 12 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `module_search` | Search Drupal.org for modules by name or description.<br>_Looking for an existing contributed solution before deciding to build a custom module_ | `{"query": "keyword"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `module_get` | Get module details from Drupal.org by machine name.<br>_Vetting a module's maintenance status before adding it to the composer require list_ | `{"project_id": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `module_versions` | Get all available releases for a module.<br>_Pinning an exact release in composer.lock instead of guessing at a tag_ | `{"project_id": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `module_dependencies` | Get the packages a module release requires.<br>_Checking what a module will pull into a lean build before committing to it_ | `{"project_id": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `theme_search` | Search Drupal.org for themes by name or description.<br>_Hunting for a contributed theme to base a new client site on_ | `{"query": "keyword"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `theme_get` | Get theme details from Drupal.org by machine name.<br>_Confirming a contrib theme is actively maintained before adopting it_ | `{"project_id": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `release_history` | Get release history for a project.<br>_Judging whether a project is alive by looking at its release cadence_ | `{"project_id": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `project_usage` | Get download/usage statistics for a project.<br>_Weighing a module choice by how many production sites actually run it_ | `{"project_id": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `module_compatibility` | Check whether a project has releases for a given core version.<br>_Before a Drupal 11 upgrade, checking which contrib projects still publish releases_ | `{"project_id": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `module_issues_search` | Search a module's drupal.org issue queue for issues that match a problem.<br>_A contrib bug is blocking you and you want to see whether someone already filed it_ | `{"module_name": "value", "problem_description": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `module_popular` | List the most-installed modules on Drupal.org, newest usage first.<br>_Browsing what the community widely installs when the shortlist is still empty_ | `{}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `module_recommendation` | Recommend modules for a need: what the local codebase already ships, plus drupal.org options.<br>_Turning a plain need like add a newsletter into options filtered by what is already installed_ | `{"need": "value"}` | ✅ ddev · ✅ lando · 🧪 unit |

## testing

Testing — 9 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `test_run_phpunit` | Run PHPUnit tests.<br>_Verifying a change to custom logic did not break existing unit behavior before committing_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `test_run_kernel` | Run Kernel tests.<br>_Exercising hooks and entity storage against a real Drupal kernel after a change_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `test_run_behat` | Run Behat tests.<br>_Checking a user-facing workflow end to end before calling a feature done_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `test_run_nightwatch` | Run Nightwatch tests.<br>_Validating browser-side JS and admin UI behavior ahead of a release_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `test_scaffold_phpunit` | Scaffold a PHPUnit test class.<br>_Starting a test for a custom class without recalling the Drupal TestCase boilerplate_ | `{"module": "mymodule"}` | ✅ ddev · ✅ lando · 🧪 unit |
| `test_scaffold_behat` | Scaffold a Behat feature file.<br>_Turning a user story into an executable feature file in one step_ | `{"module": "mymodule", "feature_name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `test_scaffold_nightwatch` | Scaffold a Nightwatch test.<br>_Adding browser coverage for a new admin workflow the team just shipped_ | `{"module": "mymodule", "test_name": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `test_coverage_report` | Generate test coverage report.<br>_Seeing which parts of a custom module still have zero test coverage_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `test_list_suites` | List available test suites.<br>_Not sure which runner applies, so checking what test suites this site exposes_ | `{}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## accessibility

Accessibility — 5 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| `accessibility_axe_scan` | Run axe-core accessibility scan on a URL.<br>_Running an automated accessibility check on a key page before an audit or launch_ | `{"url": "value"}` | ✅ ddev · ✅ lando · ❔ no offline tests |
| `accessibility_wcag_check` | Check WCAG compliance for entity content.<br>_Before publishing, checking a content type's rendered output against WCAG criteria_ | `{"entity_type": "node", "entity_id": "value"}` | ✅ ddev · ⚠️ lando · ❔ no offline tests |
| `accessibility_color_contrast` | Check color contrast ratio.<br>_Choosing a brand color pairing that still passes AA contrast on text_ | `{"foreground": "value", "background": "value"}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `accessibility_aria_validate` | Validate ARIA attributes on entity.<br>_A custom template's accordion misbehaves and the ARIA markup may be at fault_ | `{"entity_type": "node", "entity_id": "value"}` | ✅ ddev · ⚠️ lando · 🧪 unit |
| `accessibility_report_generate` | Generate comprehensive accessibility report.<br>_Handing an auditor one consolidated report instead of scattered scan results_ | `{"urls": []}` | ✅ ddev · ✅ lando · ❔ no offline tests |

## exports

Exports — 4 tools.

| Tool | Description & use case | Example | Status |
|------|------------------------|---------|--------|
| [`export_nodes`](index.md#export_nodes) | Export a node inventory to a CSV or Excel file on disk.<br>_Handing a client a full content inventory without exporting by hand_ | `{}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `export_users` | Export the site's user accounts to a CSV or Excel file on disk.<br>_Preparing a user list for a migration or an account cleanup review_ | `{}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
| `export_media` | Export the media library to a CSV or Excel file on disk.<br>_Auditing the media library for unused assets before a cleanup sprint_ | `{}` | ✅ ddev · ✅ lando · 🧪 unit |
| `export_taxonomy` | Export taxonomy terms to a CSV or Excel file on disk.<br>_Mapping existing terms into a new vocabulary structure during a re-architecture_ | `{}` | ⚠️ ddev · ⚠️ lando · 🧪 unit |
