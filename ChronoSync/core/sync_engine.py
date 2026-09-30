# Placeholder for ChronoSync/core/sync_engine.py
import json
import os
import shutil
import datetime
import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.validation import file_hash
from utils.metrics import count_files_and_size
from core.reporting import generate_report, save_backup_metadata, update_report_run_status


def iter_completed_futures(futures):
    """Yield completed futures without relying on tqdm's deprecated progress bar."""
    for future in as_completed(futures):
        yield future

def needs_copy(src, dest):
    """Check if a file needs to be copied in incremental mode.

    Matching content is treated as already synced, even if timestamps differ.
    """
    if not os.path.exists(dest):
        return True

    try:
        return file_hash(src) != file_hash(dest)
    except OSError:
        return True

def safe_copy(src, dest):
    """Copy file safely, adding hash suffix if same name but different content."""
    if os.path.exists(dest):
        if file_hash(src) != file_hash(dest):
            base, ext = os.path.splitext(dest)
            dest = f"{base}_{file_hash(src)[:8]}{ext}"  # add short hash suffix
    shutil.copy2(src, dest)
    return dest

def copy_and_validate(src, dest):
    """Copy file and validate integrity with hash comparison."""
    try:
        final_dest = safe_copy(src, dest)
        return file_hash(src) == file_hash(final_dest), None, final_dest
    except Exception as e:
        return False, str(e), dest

def write_backup_metadata(config, src_path, file, archive_path, mode, status, destination_path=None):
    if "backup" not in config:
        return

    if destination_path is None and "destination" in config:
        destination_path = os.path.join(config["destination"], file)

    source_size = os.path.getsize(src_path) if os.path.exists(src_path) else 0
    entry = {
        "file_name": file,
        "source_path": src_path,
        "destination_path": destination_path,
        "archive_path": archive_path,
        "copied_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_size_mb": round(source_size / (1024 * 1024), 2),
        "archive_size_mb": round(source_size / (1024 * 1024), 2),
        "sha256": file_hash(src_path),
        "sync_mode": mode,
        "status": status,
    }
    save_backup_metadata(config, entry)


def process_file(src_path, file, config, timestamp, mode):
    validated_count = 0
    errors = []
    skipped = 0
    conflicts = 0
    copied = 0

    targets = []
    if "destination" in config:
        targets.append(("destination", os.path.join(config["destination"], file)))
    if "archive" in config:
        targets.append(("archive", os.path.join(config["archive"], file)))

    archive_path = None
    destination_path = None
    for target_name, target_path in targets:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        if target_name == "destination":
            destination_path = target_path

        if os.path.exists(target_path):
            try:
                if file_hash(src_path) == file_hash(target_path):
                    skipped += 1
                    if target_name == "archive":
                        continue
                    # Keep processing the remaining targets (such as the archive copy)
                    # even when the destination already matches.
                    continue
            except OSError as exc:
                errors.append((file, target_name, str(exc)))
                continue

            safe_target = safe_copy(src_path, target_path)
            if safe_target != target_path:
                conflicts += 1
            if file_hash(src_path) == file_hash(safe_target):
                validated_count += 1
            if target_name == "archive":
                archive_path = safe_target
                write_backup_metadata(config, src_path, file, archive_path, mode, "copied", destination_path=destination_path)
            copied = 1
            continue

        if mode == "full" or needs_copy(src_path, target_path):
            ok, err, final_dest = copy_and_validate(src_path, target_path)
            if ok:
                validated_count += 1
                copied = 1
                if target_name == "archive":
                    archive_path = final_dest
                    write_backup_metadata(config, src_path, file, archive_path, mode, "copied", destination_path=destination_path)
            elif err:
                errors.append((file, target_name, err))
        else:
            skipped += 1

    return copied, validated_count, skipped, conflicts, errors


def rollback_run(config, run_id):
    """Delete all files and metadata records associated with a specific run_id."""
    backup_dir = config.get("backup")
    if not backup_dir:
        return {"run_id": run_id, "removed": [], "skipped": [], "errors": [], "not_found": True, "message": f"No backup directory configured for run_id '{run_id}'."}

    metadata_path = os.path.join(backup_dir, "backup_metadata.json")
    if not os.path.exists(metadata_path):
        return {"run_id": run_id, "removed": [], "skipped": [], "errors": [], "not_found": True, "message": f"No backup metadata found for run_id '{run_id}'."}

    with open(metadata_path, "r", encoding="utf-8") as f:
        try:
            records = json.load(f)
        except json.JSONDecodeError:
            return {"run_id": run_id, "removed": [], "skipped": [], "errors": [], "not_found": True, "message": f"Backup metadata is invalid for run_id '{run_id}'."}

    if not isinstance(records, list):
        records = [records] if isinstance(records, dict) else []

    remaining = []
    removed = []
    skipped = []
    errors = []
    found_match = False

    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("run_id") == run_id:
            found_match = True
            for key in ("destination_path", "archive_path"):
                target_path = record.get(key)
                if not target_path:
                    continue
                if os.path.exists(target_path):
                    try:
                        os.remove(target_path)
                        removed.append(target_path)
                    except OSError as exc:
                        errors.append({"path": target_path, "error": str(exc)})
                else:
                    skipped.append(target_path)
        else:
            remaining.append(record)

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(remaining, f, indent=4)

    if not found_match:
        return {"run_id": run_id, "removed": [], "skipped": [], "errors": [], "not_found": True, "message": f"No metadata records found for run_id '{run_id}'."}

    devicename = config.get("devicename")
    if devicename:
        affected_files_count = len(removed) + len(skipped)
        result = "partial" if errors else "success"
        update_report_run_status(
            config,
            run_id,
            "rollback",
            devicename=devicename,
            rolled_back_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            affected_files_count=affected_files_count,
            result=result,
        )

    return {"run_id": run_id, "removed": removed, "skipped": skipped, "errors": errors, "not_found": False, "message": f"Rollback completed for run_id '{run_id}'."}


def run_sync(config, max_workers=4):
    """Main sync runner: handles full/incremental modes, conflict resolution, reporting."""
    run_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = config.get("run_id") or f"run-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    config = dict(config)
    config["run_id"] = run_id
    timestamp = run_timestamp
    copied_count, validated_count, skipped_count, conflict_count = 0, 0, 0, 0
    all_errors = []

    mode = config.get("mode", "incremental").lower()

    # Collect all files first
    files_to_process = []
    for root, _, files in os.walk(config["source"]):
        for file in files:
            if any(file.endswith(ext) for ext in config["file_types"]):
                src_path = os.path.join(root, file)
                files_to_process.append((src_path, file))

    total_files = len(files_to_process)
    completed_files = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(process_file, src_path, file, config, timestamp, mode)
            for src_path, file in files_to_process
        ]

        for future in iter_completed_futures(futures):
            copied, validated, skipped, conflicts, errors = future.result()
            copied_count += copied
            validated_count += validated
            skipped_count += skipped
            conflict_count += conflicts
            all_errors.extend(errors)
            completed_files += 1

            if total_files:
                percent = (completed_files / total_files) * 100
                print(f"\rProcessing files: {completed_files}/{total_files} ({percent:.0f}%)", end="", flush=True)

    if total_files:
        print()

    report = generate_report(config, copied_count, validated_count, skipped_count, conflict_count, all_errors)
    return report, all_errors

