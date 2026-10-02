import datetime
import os
import csv
import json
from utils.metrics import count_files_and_size


def normalize_metadata_entry(entry):
    if not isinstance(entry, dict):
        return {}

    normalized = dict(entry)

    if "source_size_mb" not in normalized:
        if "size_mb" in normalized:
            normalized["source_size_mb"] = normalized["size_mb"]
        elif "size_bytes" in normalized:
            size_bytes = normalized.get("size_bytes", 0)
            normalized["source_size_mb"] = round(size_bytes / (1024 * 1024), 2)

    if "archive_size_mb" not in normalized and "source_size_mb" in normalized:
        normalized["archive_size_mb"] = normalized["source_size_mb"]

    normalized.pop("size_bytes", None)
    normalized.pop("size_mb", None)
    return normalized


def save_backup_metadata(config, entry, filename="backup_metadata.json"):
    backup_dir = config.get("backup")
    if not backup_dir:
        return None

    run_id = config.get("run_id") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = dict(entry)
    entry.setdefault("run_id", run_id)
    entry.setdefault("config_path", config.get("config_path", ""))
    entry.setdefault("reports_path", resolve_reports_base(config=config))

    os.makedirs(backup_dir, exist_ok=True)
    filepath = os.path.join(backup_dir, filename)
    records = []

    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    records = data
                elif isinstance(data, dict):
                    records = [data]
            except json.JSONDecodeError:
                records = []

    records = [normalize_metadata_entry(record) for record in records]
    normalized_entry = normalize_metadata_entry(entry)

    identity = normalized_entry.get("source_path") or normalized_entry.get("archive_path") or normalized_entry.get("file_name")
    updated = False
    deduped_records = []
    for record in records:
        record_identity = record.get("source_path") or record.get("archive_path") or record.get("file_name")
        if record_identity == identity:
            if not updated:
                deduped_records.append(normalized_entry)
                updated = True
            continue
        deduped_records.append(record)

    if not updated:
        deduped_records.append(normalized_entry)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(deduped_records, f, indent=4)

    return filepath


def generate_report(config, copied_count, validated_count, skipped_count, conflict_count, errors):
    src_count, src_size = count_files_and_size(config["source"], config["file_types"])
    destination_path = config.get("destination")
    destination_configured = bool(destination_path)
    dest_count, dest_size = count_files_and_size(destination_path, config["file_types"]) if destination_configured else (0, 0)
    archive_count, archive_size = count_files_and_size(config.get("archive", ""), config["file_types"]) if "archive" in config else (0,0)

    backup_count = 0
    backup_size = 0
    if "backup" in config and config.get("backup"):
        metadata_path = os.path.join(config["backup"], "backup_metadata.json")
        if os.path.exists(metadata_path):
            with open(metadata_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    backup_count = len(data) if isinstance(data, list) else 1 if isinstance(data, dict) else 0
                    backup_size = os.path.getsize(metadata_path)
                except json.JSONDecodeError:
                    backup_count = 0
                    backup_size = 0

    run_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = config.get("run_id") or run_timestamp
    reports_path = resolve_reports_base(config=config)

    return {
        "run_id": run_id,
        "Run Timestamp": run_timestamp,
        "Device": config.get("devicename", "Unknown"),
        "Config Path": config.get("config_path", ""),
        "Reports Path": reports_path,
        "Mode": config.get("mode", "incremental"),
        "Status": "completed",
        "Destination configured": "yes" if destination_configured else "no",
        "Destination Path": destination_path or "(not configured)",
        "Source file count": src_count,
        "Source total size (MB)": round(src_size / (1024*1024), 2),
        "Files copied this run": copied_count,
        "Files validated (hash match)": validated_count,
        "Files skipped (already up-to-date)": skipped_count,
        "Conflicts resolved (timestamped backup)": conflict_count,
        "Errors this run": len(errors),
        "Total files at destination": dest_count,
        "Destination total size (MB)": round(dest_size / (1024*1024), 2),
        "Total files at backup": backup_count,
        "Backup total size (MB)": round(backup_size / (1024*1024), 2),
        "Total files at archive": archive_count,
        "Archive total size (MB)": round(archive_size / (1024*1024), 2),
    }

def update_report_run_status(config, run_id, status, devicename=None, filename="backup_report.json", rolled_back_at=None, affected_files_count=None, result=None):
    if not (config or devicename) or not run_id:
        return False

    devicename = devicename or config.get("devicename")
    if not devicename:
        return False

    updated = False
    timestamp = rolled_back_at or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if affected_files_count is None:
        affected_files_count = 0
    if result is None:
        result = "success"

    folder = os.path.join(resolve_reports_base(config=config), devicename)
    json_path = os.path.join(folder, f"{devicename}_{filename}")
    csv_path = os.path.join(folder, f"{devicename}_backup_report.csv")

    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            try:
                payload = json.load(f)
            except json.JSONDecodeError:
                payload = []

        if isinstance(payload, list):
            for row in payload:
                if isinstance(row, dict) and row.get("run_id") == run_id:
                    row.pop("status", None)
                    row["Status"] = status
                    row["rolled_back_at"] = timestamp
                    row["affected_files_count"] = affected_files_count
                    row["result"] = result
                    updated = True

        if updated:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=4)

    if os.path.exists(csv_path):
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)

        for field in ("Status", "rolled_back_at", "affected_files_count", "result"):
            if field not in fieldnames and field.lower() not in fieldnames:
                fieldnames.append(field)

        csv_updated = False
        for row in rows:
            if row.get("run_id") == run_id:
                row.pop("status", None)
                row["Status"] = status
                row["rolled_back_at"] = timestamp
                row["affected_files_count"] = str(affected_files_count)
                row["result"] = result
                csv_updated = True

        if csv_updated and fieldnames:
            updated = True
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

    return updated


def resolve_reports_base(config=None, reports_base=None):
    if reports_base:
        path = os.path.abspath(str(reports_base))
        os.makedirs(path, exist_ok=True)
        return path

    if isinstance(config, dict):
        configured = config.get("reports_path") or config.get("reports_dir")
        if configured:
            path = os.path.abspath(str(configured))
            os.makedirs(path, exist_ok=True)
            return path

    return os.path.abspath("reports")


def save_report_csv(report, devicename, filename="backup_report.csv", reports_base=None):
    folder = os.path.join(resolve_reports_base(reports_base=reports_base), devicename)
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, f"{devicename}_{filename}")
    file_exists = os.path.isfile(filepath)
    needs_header = not file_exists or os.path.getsize(filepath) == 0
    with open(filepath, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=report.keys())
        if needs_header:
            writer.writeheader()
        writer.writerow(report)
    return filepath

def save_report_json(report, devicename, filename="backup_report.json", reports_base=None):
    folder = os.path.join(resolve_reports_base(reports_base=reports_base), devicename)
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, f"{devicename}_{filename}")
    reports = []
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                reports = json.load(f)
            except json.JSONDecodeError:
                reports = []
    reports.append(report)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=4)
    return filepath

def save_error_log(errors, devicename, filename="backup_errors.csv", reports_base=None, run_id=None, config_path=None):
    folder = os.path.join(resolve_reports_base(reports_base=reports_base), devicename)
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, f"{devicename}_{filename}")
    file_exists = os.path.isfile(filepath)
    needs_header = not file_exists or os.path.getsize(filepath) == 0
    with open(filepath, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if needs_header:
            writer.writerow(["Run Timestamp", "run_id", "Config Path", "File", "Target", "Error"])
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for error in errors:
            if isinstance(error, dict):
                file = error.get("file_name") or error.get("file") or ""
                target = error.get("target_name") or error.get("target") or ""
                err = error.get("error_message") or error.get("error") or ""
                row_run_id = error.get("run_id", run_id or "")
                row_timestamp = error.get("timestamp", timestamp)
                row_config_path = error.get("config_path", config_path or "")
            else:
                file, target, err = error
                row_run_id = run_id or ""
                row_timestamp = timestamp
                row_config_path = config_path or ""
            writer.writerow([row_timestamp, row_run_id, row_config_path, file, target, err])
    return filepath
