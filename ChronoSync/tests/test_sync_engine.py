import os
import warnings

import json

from core.reporting import save_backup_metadata
from core.sync_engine import copy_and_validate, needs_copy, process_file, rollback_run, run_sync, safe_copy


def test_needs_copy_returns_true_for_missing_dest(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("content", encoding="utf-8")
    dest = tmp_path / "missing.txt"

    assert needs_copy(str(src), str(dest)) is True


def test_needs_copy_returns_false_when_files_are_identical(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("same-data", encoding="utf-8")
    dest = tmp_path / "dest.txt"
    dest.write_text("same-data", encoding="utf-8")

    same_time = 1700000000
    os.utime(src, (same_time, same_time))
    os.utime(dest, (same_time, same_time))

    assert needs_copy(str(src), str(dest)) is False


def test_safe_copy_uses_hash_suffix_for_conflicting_content(tmp_path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"alpha")
    dest = tmp_path / "dest.bin"
    dest.write_bytes(b"beta")

    final_dest = safe_copy(str(src), str(dest))

    assert final_dest != str(dest)
    assert os.path.exists(final_dest)
    assert final_dest.endswith(".bin")


def test_copy_and_validate_returns_success_on_same_file_hash(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("validate-me", encoding="utf-8")
    dest = tmp_path / "dest.txt"
    dest.write_text("validate-me", encoding="utf-8")

    ok, err, final_dest = copy_and_validate(str(src), str(dest))

    assert ok is True
    assert err is None
    assert final_dest == str(dest)


def test_process_file_handles_full_sync_and_skips_up_to_date_file(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    src = source_dir / "track.mp3"
    src.write_bytes(b"music-data")

    dest_dir = tmp_path / "destination"
    archive_dir = tmp_path / "archive"
    config = {
        "destination": str(dest_dir),
        "archive": str(archive_dir),
        "backup": str(tmp_path / "backup"),
        "reports_path": str(tmp_path / "reports"),
        "file_types": [".mp3"],
        "mode": "full",
    }

    copied, validated, skipped, conflicts, errors = process_file(
        str(src), src.name, config, "20240101_000000", "full"
    )

    assert copied == 1
    assert validated == 2
    assert skipped == 0
    assert conflicts == 0
    assert errors == []
    assert (dest_dir / src.name).exists()
    assert (archive_dir / src.name).exists()

    second_run = process_file(
        str(src), src.name, config, "20240101_000000", "incremental"
    )
    assert second_run[2] == 2


def test_run_sync_copies_destination_and_tracks_conflicts(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    src = source_dir / "song.mp3"
    src.write_bytes(b"song-bytes")

    destination_dir = tmp_path / "destination"
    backup_dir = tmp_path / "backup"
    archive_dir = tmp_path / "archive"
    backup_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "source": str(source_dir),
        "destination": str(destination_dir),
        "backup": str(backup_dir),
        "archive": str(archive_dir),
        "devicename": "demo-device",
        "reports_path": str(tmp_path / "reports"),
        "file_types": [".mp3"],
        "mode": "full",
    }

    report, errors = run_sync(config, max_workers=1)

    assert errors == []
    assert report["Files copied this run"] == 1
    assert report["Files validated (hash match)"] == 2
    assert (destination_dir / src.name).exists()
    assert (archive_dir / src.name).exists()
    assert not (backup_dir / src.name).exists()

    metadata_file = backup_dir / "backup_metadata.json"
    assert metadata_file.exists()
    payload = __import__("json").loads(metadata_file.read_text(encoding="utf-8"))
    assert payload[0]["file_name"] == src.name
    assert "source_size_mb" in payload[0]
    assert "archive_size_mb" in payload[0]
    assert payload[0]["source_size_mb"] == round(len(b"song-bytes") / (1024 * 1024), 2)
    assert payload[0]["archive_size_mb"] == payload[0]["source_size_mb"]

    conflicting_archive = archive_dir / src.name
    conflicting_archive.write_bytes(b"different-bytes")
    conflict_report, conflict_errors = run_sync(config, max_workers=1)

    assert isinstance(conflict_report["Conflicts resolved (timestamped backup)"], int)
    assert isinstance(conflict_errors, list)
    assert len(list(archive_dir.glob("*song.mp3*"))) >= 1


def test_process_file_skips_when_existing_target_hash_matches(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    src = source_dir / "song.mp3"
    src.write_bytes(b"same-data")

    destination_dir = tmp_path / "destination"
    archive_dir = tmp_path / "archive"
    destination_dir.mkdir()
    archive_dir.mkdir()
    (destination_dir / "song.mp3").write_bytes(b"same-data")
    (archive_dir / "song.mp3").write_bytes(b"same-data")

    config = {
        "destination": str(destination_dir),
        "archive": str(archive_dir),
        "backup": str(tmp_path / "backup"),
        "reports_path": str(tmp_path / "reports"),
        "file_types": [".mp3"],
        "mode": "full",
    }

    copied, validated, skipped, conflicts, errors = process_file(
        str(src), src.name, config, "20240101_000000", "full"
    )

    assert copied == 0
    assert skipped == 2
    assert conflicts == 0
    assert errors == []


def test_process_file_creates_archive_when_destination_already_matches(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    src = source_dir / "song.mp3"
    src.write_bytes(b"same-data")

    destination_dir = tmp_path / "destination"
    archive_dir = tmp_path / "archive"
    destination_dir.mkdir()
    archive_dir.mkdir()
    (destination_dir / "song.mp3").write_bytes(b"same-data")

    config = {
        "destination": str(destination_dir),
        "archive": str(archive_dir),
        "backup": str(tmp_path / "backup"),
        "reports_path": str(tmp_path / "reports"),
        "file_types": [".mp3"],
        "mode": "incremental",
    }

    copied, validated, skipped, conflicts, errors = process_file(
        str(src), src.name, config, "20240101_000000", "incremental"
    )

    assert copied == 1
    assert validated == 1
    assert skipped == 1
    assert conflicts == 0
    assert errors == []
    assert (archive_dir / src.name).exists()


def test_run_sync_does_not_emit_tqdm_deprecation_warning(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    src = source_dir / "song.mp3"
    src.write_bytes(b"song-bytes")

    config = {
        "source": str(source_dir),
        "destination": str(tmp_path / "destination"),
        "backup": str(tmp_path / "backup"),
        "archive": str(tmp_path / "archive"),
        "devicename": "demo-device",
        "reports_path": str(tmp_path / "reports"),
        "file_types": [".mp3"],
        "mode": "full",
    }

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        report, errors = run_sync(config, max_workers=1)

    assert errors == []
    assert report["Files copied this run"] == 1


def test_rollback_run_removes_matching_files_and_metadata(tmp_path):
    source_dir = tmp_path / "source"
    dest_dir = tmp_path / "destination"
    archive_dir = tmp_path / "archive"
    backup_dir = tmp_path / "backup"
    for path in (source_dir, dest_dir, archive_dir, backup_dir):
        path.mkdir(parents=True, exist_ok=True)

    file_name = "song.mp3"
    src_path = source_dir / file_name
    src_path.write_bytes(b"rollback-me")

    dest_path = dest_dir / file_name
    archive_path = archive_dir / file_name
    dest_path.write_bytes(b"rollback-me")
    archive_path.write_bytes(b"rollback-me")

    metadata_file = backup_dir / "backup_metadata.json"
    metadata = [
        {
            "file_name": file_name,
            "source_path": str(src_path),
            "destination_path": str(dest_path),
            "archive_path": str(archive_path),
            "run_id": "run-123",
            "status": "copied",
        },
        {
            "file_name": "other.mp3",
            "source_path": str(source_dir / "other.mp3"),
            "destination_path": str(dest_dir / "other.mp3"),
            "archive_path": str(archive_dir / "other.mp3"),
            "run_id": "run-999",
            "status": "copied",
        },
    ]
    metadata_file.write_text(json.dumps(metadata), encoding="utf-8")

    config = {
        "source": str(source_dir),
        "destination": str(dest_dir),
        "archive": str(archive_dir),
        "backup": str(backup_dir),
        "devicename": "demo",
        "reports_path": str(tmp_path / "reports"),
        "file_types": [".mp3"],
        "mode": "incremental",
    }

    result = rollback_run(config, "run-123")

    assert not dest_path.exists()
    assert not archive_path.exists()
    assert result["removed"][0].endswith("song.mp3")
    payload = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert len(payload) == 1
    assert payload[0]["run_id"] == "run-999"


def test_rollback_run_reports_missing_run_id_explicitly(tmp_path):
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    (backup_dir / "backup_metadata.json").write_text(
        json.dumps([{"file_name": "song.mp3", "run_id": "run-actual"}]),
        encoding="utf-8",
    )

    config = {"backup": str(backup_dir), "destination": str(tmp_path / "destination"), "archive": str(tmp_path / "archive")}
    result = rollback_run(config, "run-missing")

    assert result["not_found"] is True
    assert "run-missing" in result["message"]


def test_rollback_run_marks_report_status_as_rollback_without_removing_history(tmp_path):
    source_dir = tmp_path / "source"
    dest_dir = tmp_path / "destination"
    archive_dir = tmp_path / "archive"
    backup_dir = tmp_path / "backup"
    for path in (source_dir, dest_dir, archive_dir, backup_dir):
        path.mkdir(parents=True, exist_ok=True)

    file_name = "song.mp3"
    src_path = source_dir / file_name
    src_path.write_bytes(b"rollback-me")

    dest_path = dest_dir / file_name
    archive_path = archive_dir / file_name
    dest_path.write_bytes(b"rollback-me")
    archive_path.write_bytes(b"rollback-me")

    metadata_file = backup_dir / "backup_metadata.json"
    metadata = [
        {
            "file_name": file_name,
            "source_path": str(src_path),
            "destination_path": str(dest_path),
            "archive_path": str(archive_path),
            "run_id": "run-123",
            "status": "copied",
        },
        {
            "file_name": "other.mp3",
            "source_path": str(source_dir / "other.mp3"),
            "destination_path": str(dest_dir / "other.mp3"),
            "archive_path": str(archive_dir / "other.mp3"),
            "run_id": "run-999",
            "status": "copied",
        },
    ]
    metadata_file.write_text(json.dumps(metadata), encoding="utf-8")

    reports_dir = tmp_path / "reports" / "demo"
    reports_dir.mkdir(parents=True)
    report_path = reports_dir / "demo_backup_report.json"
    report_path.write_text(
        json.dumps([
            {"run_id": "run-123", "Run Timestamp": "2024-01-01 00:00:00", "Device": "demo", "Mode": "full", "Status": "completed"},
            {"run_id": "run-999", "Run Timestamp": "2024-01-02 00:00:00", "Device": "demo", "Mode": "full", "Status": "completed"},
        ]),
        encoding="utf-8",
    )

    config = {
        "source": str(source_dir),
        "destination": str(dest_dir),
        "archive": str(archive_dir),
        "backup": str(backup_dir),
        "devicename": "demo",
        "reports_path": str(tmp_path / "reports"),
        "file_types": [".mp3"],
        "mode": "incremental",
    }

    result = rollback_run(config, "run-123")

    assert result["not_found"] is False
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    run_entry = next(item for item in payload if item["run_id"] == "run-123")
    other_entry = next(item for item in payload if item["run_id"] == "run-999")
    assert run_entry["Status"] == "rollback"
    assert "rolled_back_at" in run_entry
    assert run_entry["result"] in {"success", "partial"}
    assert run_entry["affected_files_count"] >= 1
    assert other_entry["Status"] == "completed"


def test_save_backup_metadata_does_not_duplicate_existing_entries(tmp_path):
    config = {"backup": str(tmp_path), "reports_path": str(tmp_path / "reports"), "config_path": "/tmp/config.yaml", "run_id": "run-001"}
    entry = {
        "file_name": "song.mp3",
        "source_path": "src/song.mp3",
        "archive_path": "archive/song.mp3",
        "copied_at": "2024-01-01 00:00:00",
        "source_size_mb": 1.0,
        "archive_size_mb": 1.0,
        "sha256": "abc123",
        "sync_mode": "incremental",
        "status": "copied",
    }

    save_backup_metadata(config, entry)
    updated_entry = dict(entry)
    updated_entry["sha256"] = "def456"
    updated_entry["status"] = "validated"
    config["run_id"] = "run-002"
    save_backup_metadata(config, updated_entry)

    payload = __import__("json").loads((tmp_path / "backup_metadata.json").read_text(encoding="utf-8"))
    assert len(payload) == 1
    assert payload[0]["file_name"] == "song.mp3"
    assert payload[0]["sha256"] == "def456"
    assert payload[0]["run_id"] == "run-002"
    assert payload[0]["config_path"] == "/tmp/config.yaml"


def test_run_sync_supports_archive_only_when_destination_is_omitted(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    src = source_dir / "song.mp3"
    src.write_bytes(b"song-bytes")

    archive_dir = tmp_path / "archive"
    backup_dir = tmp_path / "backup"
    config = {
        "source": str(source_dir),
        "backup": str(backup_dir),
        "archive": str(archive_dir),
        "devicename": "archive-only",
        "reports_path": str(tmp_path / "reports"),
        "file_types": [".mp3"],
        "mode": "full",
    }

    report, errors = run_sync(config, max_workers=1)

    assert errors == []
    assert report["Destination configured"] == "no"
    assert report["Destination Path"] == "(not configured)"
    assert report["Total files at destination"] == 0
    assert (archive_dir / src.name).exists()
    assert not (tmp_path / "destination" / src.name).exists()


def test_purge_destination_single_file(tmp_path):
    from core.sync_engine import purge_destination
    
    source_dir = tmp_path / "source"
    dest_dir = tmp_path / "destination"
    backup_dir = tmp_path / "backup"
    for path in (source_dir, dest_dir, backup_dir):
        path.mkdir(parents=True, exist_ok=True)
    
    file_path = dest_dir / "song.mp3"
    file_path.write_bytes(b"song-data")
    
    config = {
        "destination": str(dest_dir),
        "backup": str(backup_dir),
        "file_types": [".mp3"],
    }
    
    result = purge_destination(config, "single", run_id="run-123", file_paths=[str(file_path)])
    
    assert result["success"] is True
    assert result["deleted"] == 1
    assert not file_path.exists()
    
    purge_log = backup_dir / "purge_actions.json"
    assert purge_log.exists()
    actions = json.loads(purge_log.read_text(encoding="utf-8"))
    assert len(actions) == 1
    assert actions[0]["file_name"] == "song.mp3"
    assert actions[0]["run_id"] == "run-123"
    assert actions[0]["status"] == "deleted"


def test_purge_destination_multi_file(tmp_path):
    from core.sync_engine import purge_destination
    
    dest_dir = tmp_path / "destination"
    backup_dir = tmp_path / "backup"
    dest_dir.mkdir(parents=True)
    backup_dir.mkdir()
    
    file1 = dest_dir / "song1.mp3"
    file2 = dest_dir / "song2.mp3"
    file1.write_bytes(b"data1")
    file2.write_bytes(b"data2")
    
    config = {
        "destination": str(dest_dir),
        "backup": str(backup_dir),
        "file_types": [".mp3"],
    }
    
    result = purge_destination(config, "multi", run_id="run-456", file_paths=[str(file1), str(file2)])
    
    assert result["success"] is True
    assert result["deleted"] == 2
    assert not file1.exists()
    assert not file2.exists()


def test_purge_destination_full_run_by_run_id(tmp_path):
    from core.sync_engine import purge_destination
    
    dest_dir = tmp_path / "destination"
    backup_dir = tmp_path / "backup"
    dest_dir.mkdir(parents=True)
    backup_dir.mkdir()
    
    file1 = dest_dir / "song1.mp3"
    file2 = dest_dir / "song2.mp3"
    file1.write_bytes(b"data1")
    file2.write_bytes(b"data2")
    
    metadata = [
        {
            "file_name": "song1.mp3",
            "destination_path": str(file1),
            "archive_path": str(dest_dir / "archive" / "song1.mp3"),
            "run_id": "run-111",
        },
        {
            "file_name": "song2.mp3",
            "destination_path": str(file2),
            "archive_path": str(dest_dir / "archive" / "song2.mp3"),
            "run_id": "run-222",
        },
    ]
    (backup_dir / "backup_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    
    config = {
        "destination": str(dest_dir),
        "backup": str(backup_dir),
        "file_types": [".mp3"],
    }
    
    result = purge_destination(config, "full_run", run_id="run-111")
    
    assert result["success"] is True
    assert result["deleted"] == 1
    assert not file1.exists()
    assert file2.exists()  # Only run-111 files should be deleted


def test_purge_destination_full_all_does_not_require_run_id(tmp_path):
    from core.sync_engine import purge_destination

    dest_dir = tmp_path / "destination"
    backup_dir = tmp_path / "backup"
    dest_dir.mkdir(parents=True)
    backup_dir.mkdir()

    file1 = dest_dir / "song1.mp3"
    file2 = dest_dir / "song2.mp3"
    file1.write_bytes(b"data1")
    file2.write_bytes(b"data2")

    metadata = [
        {
            "file_name": "song1.mp3",
            "destination_path": str(file1),
            "archive_path": str(dest_dir / "archive" / "song1.mp3"),
            "run_id": "run-111",
        },
        {
            "file_name": "song2.mp3",
            "destination_path": str(file2),
            "archive_path": str(dest_dir / "archive" / "song2.mp3"),
            "run_id": "run-222",
        },
    ]
    (backup_dir / "backup_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    config = {
        "destination": str(dest_dir),
        "backup": str(backup_dir),
        "file_types": [".mp3"],
    }

    result = purge_destination(config, "full_all")

    assert result["success"] is True
    assert result["deleted"] == 2
    assert not file1.exists()
    assert not file2.exists()


def test_restore_archive_single_file(tmp_path):
    from core.sync_engine import restore_archive
    
    archive_dir = tmp_path / "archive"
    dest_dir = tmp_path / "destination"
    backup_dir = tmp_path / "backup"
    for path in (archive_dir, dest_dir, backup_dir):
        path.mkdir(parents=True, exist_ok=True)
    
    archive_file = archive_dir / "song.mp3"
    archive_file.write_bytes(b"song-data")
    dest_file = dest_dir / "song.mp3"
    
    from core.validation import file_hash
    hash_val = file_hash(str(archive_file))
    
    metadata = [
        {
            "file_name": "song.mp3",
            "archive_path": str(archive_file),
            "destination_path": str(dest_file),
            "sha256": hash_val,
            "run_id": "run-555",
        }
    ]
    (backup_dir / "backup_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    
    config = {
        "archive": str(archive_dir),
        "destination": str(dest_dir),
        "backup": str(backup_dir),
    }
    
    result = restore_archive(config, "single", file_paths=[str(archive_file)])
    
    assert result["success"] is True
    assert result["restored"] == 1
    assert dest_file.exists()


def test_restore_archive_conflict_without_force(tmp_path):
    from core.sync_engine import restore_archive
    from core.validation import file_hash
    
    archive_dir = tmp_path / "archive"
    dest_dir = tmp_path / "destination"
    backup_dir = tmp_path / "backup"
    for path in (archive_dir, dest_dir, backup_dir):
        path.mkdir(parents=True, exist_ok=True)
    
    archive_file = archive_dir / "song.mp3"
    archive_file.write_bytes(b"archive-data")
    dest_file = dest_dir / "song.mp3"
    dest_file.write_bytes(b"different-data")
    
    archive_hash = file_hash(str(archive_file))
    
    metadata = [
        {
            "file_name": "song.mp3",
            "archive_path": str(archive_file),
            "destination_path": str(dest_file),
            "sha256": archive_hash,
            "run_id": "run-666",
        }
    ]
    (backup_dir / "backup_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    
    config = {
        "archive": str(archive_dir),
        "destination": str(dest_dir),
        "backup": str(backup_dir),
    }
    
    result = restore_archive(config, "single", file_paths=[str(archive_file)], force_restore=False)
    
    assert result["success"] is True
    assert result["conflicts"] == 1
    assert len(result["errors"]) > 0  # Conflict should be logged


def test_restore_archive_conflict_with_force(tmp_path):
    from core.sync_engine import restore_archive
    from core.validation import file_hash
    
    archive_dir = tmp_path / "archive"
    dest_dir = tmp_path / "destination"
    backup_dir = tmp_path / "backup"
    for path in (archive_dir, dest_dir, backup_dir):
        path.mkdir(parents=True, exist_ok=True)
    
    archive_file = archive_dir / "song.mp3"
    archive_file.write_bytes(b"archive-data")
    dest_file = dest_dir / "song.mp3"
    dest_file.write_bytes(b"different-data")
    
    archive_hash = file_hash(str(archive_file))
    
    metadata = [
        {
            "file_name": "song.mp3",
            "archive_path": str(archive_file),
            "destination_path": str(dest_file),
            "sha256": archive_hash,
            "run_id": "run-777",
        }
    ]
    (backup_dir / "backup_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    
    config = {
        "archive": str(archive_dir),
        "destination": str(dest_dir),
        "backup": str(backup_dir),
    }
    
    result = restore_archive(config, "single", file_paths=[str(archive_file)], force_restore=True)
    
    assert result["success"] is True
    assert result["restored"] == 1
    assert dest_file.read_bytes() == b"archive-data"
