# ChronoSync Implementation Prompt

This file is the engineering brief derived from [spec.md](spec.md).
It is intentionally limited to implementation execution details and must not duplicate product requirements.

## Role
- [spec.md](spec.md) is the authoritative product specification.
- [plan-prompt.md](plan-prompt.md) is used to revise or refine [spec.md](spec.md).
- This file translates the approved spec into implementation tasks, code structure and update the code.
- If anything in this file conflicts with [spec.md](spec.md), the specification wins and this file must be corrected before work continues.

## Objective
Implement the ChronoSync Python backup and synchronization utility described by [spec.md](spec.md).

## Implementation scope
Build the behaviors required by the current product specification, including:
- YAML configuration loading and required-field validation
- persistent device-config registry handling under ~/.chronosync/config, including save/update/delete behavior and registry backup restore support on a separate backup drive or backup location
- required `reports_path` handling in config for report and error output including validation of path existence, writability, and proper permissions
- explicit config-location support via CLI config path resolution and runtime dashboard config loading through a file picker or load-config action, including config files outside the project tree
- load-time handling for the saved device registry so the application can prompt for whether to use stored mappings, restore from backup, choose the backup drive location, or load a different config, while reusing a previously provided backup location without asking again unless it changes
- recursive matching of source files
- incremental and full sync logic
- archive-first copy behavior with optional destination sync and conflict handling
- metadata-only backup records with a single current entry per tracked file
- archive as the persisted copy location
- hash-based validation and integrity checks
- destination purge modes: single-file, multi-file, and full purge
- archive restore modes: single-file, multi-file, and run-based restore
- explicit separation between purge destination, restore archive, and rollback operations
- rollback status and report integrity: when a run is rolled back, the report entry must be marked with status = "rollback" and remain auditable even if backup metadata is cleaned up
- report handling for not_found rollback attempts without mutating unrelated run history
- per-run metadata and report generation
- propagation of config path and reports path into operational metadata and report context
- structured dashboard/reporting sections: Overview, Trends, History / Audit, Rollback Status, and Error Log
- responsive dashboard UI with sidebar config loading, device selection, overview cards, trends charts, history/audit tables, rollback summary, and error log views
- overview-level destination, backup, and archive state summaries for the latest run
- details/history view for previous runs and lifecycle events
- rollback by run_id
- CLI support for config, device, rollback, purge, and archive restore flows
- resilient logging for per-file failures
- automated tests with the required coverage target

## Required project structure
Use a modular layout similar to:
- `backup_sync.py`
- `core/config_loader.py`
- `core/sync_engine.py`
- `core/validation.py`
- `core/reporting.py`
- `utils/metrics.py`
- `tests/`

## Engineering expectations
- Keep code modular and readable.
- Keep functions small and deterministic.
- Separate config, sync, validation, reporting, and utility logic.
- Do not invent new product behavior not defined in [spec.md](spec.md).
- Treat [spec.md](spec.md) as the contract and implement only what it requires.
- Keep report output rooted under the configured `reports_path` in a device-specific folder such as `<reports_path>/<device>/`.
- Preserve the reporting structure defined by the current specification: Overview, Trends, History / Audit, Rollback Status, and Error Log.
- Keep the dashboard layout consistent with the product spec: the Overview area contains summary cards, while History / Audit is the detailed records view.
- Keep backup metadata metadata-only and avoid duplicating file content.
- Keep destination handling optional without degrading archive, rollback, purge, reporting, or dashboard behavior.
- Keep one current metadata entry per tracked file instead of accumulating duplicate backup entries for repeated syncs of the same file.
- Keep rollback isolated and keyed by run_id.

## Final instruction
Implement the project exactly as defined by [spec.md](spec.md). Keep this file focused on execution, code structure, and engineering quality rather than re-stating product requirements.
