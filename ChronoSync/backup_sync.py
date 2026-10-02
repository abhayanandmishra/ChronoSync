import argparse
import os

from core.config_loader import load_config
from core.device_registry import get_saved_backup_drive, register_shutdown_backup
from core.reporting import save_report_csv, save_report_json, save_error_log
from core.sync_engine import purge_destination, restore_archive, rollback_run, run_sync


def resolve_config_file(config_path=None, device_name=None):
    if config_path:
        return config_path
    if device_name:
        return f"configs/{device_name}.yaml"
    raise ValueError("You must specify either --config or --device")

def main():
    register_shutdown_backup(get_saved_backup_drive())

    parser = argparse.ArgumentParser(description="ChronoSync - Multi-device backup suite")
    parser.add_argument("--config", help="Path to config YAML file")
    parser.add_argument("--device", help="Device name (will look for configs/<device>.yaml)")
    parser.add_argument("--rollback", help="Run ID to rollback from the backup metadata log")
    parser.add_argument("--purge", choices=["single", "multi", "full_run", "full_all"], help="Purge operation mode")
    parser.add_argument("--restore", choices=["single", "multi", "run"], help="Restore operation mode")
    parser.add_argument("--file", nargs="*", help="File path(s) for single/multi purge or restore")
    parser.add_argument("--run-id", help="Run ID for full_run purge mode or run-based restore")
    parser.add_argument("--force-restore", action="store_true", help="Force overwrite conflicts during restore")
    parser.add_argument("--force-overwrite", action="store_true", help="Force purge/restore without prompts")
    args = parser.parse_args()

    # Rollback mode
    if args.rollback:
        if not (args.config or args.device):
            raise ValueError("Rollback requires either --config or --device to locate the config file.")
        config_file = resolve_config_file(args.config, args.device)

        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")

        config = load_config(config_file)
        result = rollback_run(config, args.rollback)
        print(f"\n=== ChronoSync Rollback ({args.rollback}) ===")
        if result.get("not_found"):
            print(result.get("message", "No matching metadata found."))
            print(f"Removed: {len(result['removed'])} file(s)")
            print(f"Skipped: {len(result['skipped'])} file(s)")
            return
        print(f"Removed: {len(result['removed'])} file(s)")
        print(f"Skipped: {len(result['skipped'])} file(s)")
        if result["errors"]:
            print(f"Errors: {len(result['errors'])}")
        print(result.get("message", ""))
        return

    # Purge mode
    if args.purge:
        if not (args.config or args.device):
            raise ValueError("Purge requires either --config or --device to locate the config file.")
        config_file = resolve_config_file(args.config, args.device)

        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")

        config = load_config(config_file)
        result = purge_destination(config, args.purge, run_id=args.run_id, file_paths=args.file, force_overwrite=args.force_overwrite)
        print(f"\n=== ChronoSync Purge ({args.purge}) ===")
        print(result.get("message", "Purge operation completed."))
        if result.get("errors"):
            print(f"Errors: {len(result['errors'])}")
            for err in result['errors']:
                print(f"  - {err}")
        return

    # Restore mode
    if args.restore:
        if not (args.config or args.device):
            raise ValueError("Restore requires either --config or --device to locate the config file.")
        config_file = resolve_config_file(args.config, args.device)

        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")

        config = load_config(config_file)
        result = restore_archive(config, args.restore, run_id=args.run_id, file_paths=args.file, force_restore=args.force_restore)
        print(f"\n=== ChronoSync Restore ({args.restore}) ===")
        print(result.get("message", "Restore operation completed."))
        if result.get("errors"):
            print(f"Errors/Conflicts: {len(result['errors'])}")
            for err in result['errors']:
                print(f"  - {err}")
        return

    # Sync mode (default)
    config_file = resolve_config_file(args.config, args.device)

    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Config file not found: {config_file}")

    # Load config
    config = load_config(config_file)
    devicename = config.get("devicename", os.path.splitext(os.path.basename(config_file))[0])

    # Run sync
    report, errors = run_sync(config)

    # Print summary
    print(f"\n=== ChronoSync Backup Report ({devicename}) ===")
    for key, value in report.items():
        print(f"{key}: {value}")

    reports_base = config.get("reports_path")
    save_report_csv(report, devicename, reports_base=reports_base)
    save_report_json(report, devicename, reports_base=reports_base)
    if errors:
        run_id = report.get("run_id")
        save_error_log(
            errors,
            devicename,
            reports_base=reports_base,
            run_id=run_id,
            config_path=config.get("config_path"),
        )
        print(f"Errors logged for {devicename}: {len(errors)} issues")

if __name__ == "__main__":
    main()
