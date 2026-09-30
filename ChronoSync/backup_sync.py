# Entry point for ChronoSync
from core.config_loader import load_config
from core.sync_engine import run_sync, rollback_run
from core.reporting import save_report_csv, save_error_log

import argparse
import os
from core.config_loader import load_config
from core.sync_engine import run_sync, rollback_run
from core.reporting import save_report_csv, save_report_json, save_error_log

def main():
    parser = argparse.ArgumentParser(description="ChronoSync - Multi-device backup suite")
    parser.add_argument("--config", help="Path to config YAML file")
    parser.add_argument("--device", help="Device name (will look for configs/<device>.yaml)")
    parser.add_argument("--rollback", help="Run ID to rollback from the backup metadata log")
    args = parser.parse_args()

    if args.rollback:
        if args.config:
            config_file = args.config
        elif args.device:
            config_file = f"configs/{args.device}.yaml"
        else:
            raise ValueError("Rollback requires either --config or --device to locate the config file.")

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

    # Determine config file
    if args.config:
        config_file = args.config
    elif args.device:
        config_file = f"configs/{args.device}.yaml"
    else:
        raise ValueError("You must specify either --config or --device")

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

    reports_base = config.get("reports_path") or config.get("reports_dir")
    save_report_csv(report, devicename, reports_base=reports_base)
    save_report_json(report, devicename, reports_base=reports_base)
    if errors:
        save_error_log(errors, devicename, reports_base=reports_base)
        print(f"Errors logged for {devicename}: {len(errors)} issues")

if __name__ == "__main__":
    main()
