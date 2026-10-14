# DevOps Tools

## Drush

| Tool | Description |
|------|-------------|
| `drush_command` | Execute any Drush command |
| `drush_cron` | Run cron |
| `drush_updb` | Run database updates |
| `drush_watchdog` | Show recent log entries |
| `drush_php_eval` | Execute PHP code via Drush |

## DDEV/Lando

| Tool | Description |
|------|-------------|
| `ddev_start` | Start DDEV project |
| `ddev_stop` | Stop DDEV project |
| `ddev_exec` | Execute command in DDEV container |
| `ddev_setup` | Generate .ddev/config.yaml |
| `lando_start` | Start Lando project |
| `lando_stop` | Stop Lando project |
| `lando_exec` | Execute command in Lando container |
| `lando_setup` | Generate .lando.yml |

## Database

| Tool | Description |
|------|-------------|
| `db_query` | Execute a SELECT query |
| `db_tables` | List all database tables |
| `db_table_info` | Get table schema |
| `db_count` | Count rows in a table |

## Composer

| Tool | Description |
|------|-------------|
| `composer_install` | Run composer install |
| `composer_require` | Require a package |
| `composer_update` | Run composer update |

## Cache & Performance

| Tool | Description |
|------|-------------|
| `cache_rebuild` | Clear and rebuild all caches |
| `cache_clear` | Clear specific cache bins |
| `backup_database` | Create database backup |

## Notes

- The `composer_*` tools run the `composer` binary directly — Drush ships no
  `composer` command. Composer must be on `PATH` or at `./vendor/bin/composer`.
  They do not require Drush, and `composer_audit` runs against the working
  directory's dependencies.
- `ddev_setup` writes `docroot:`, which is the key DDEV 1.24 reads. It refuses to
  overwrite an existing `.ddev/config.yaml` unless `force` is set. An unrecognised
  `webroot:` key would be dropped silently, leaving an empty docroot so that nginx
  serves the project root and every request 404s.
