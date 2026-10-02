import csv
import json
import sys

import yaml

import backup_sync
from core.config_loader import load_config, validate_config
from core.reporting import generate_report, save_error_log, save_report_csv, save_report_json
from core.sync_engine import run_sync
from dashboard.app import load_reports_base, resolve_config_path


def test_generate_report_aggregates_source_and_dest_stats(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "track1.mp3").write_bytes(b"abc")
    (source_dir / "track2.txt").write_text("hello", encoding="utf-8")

    dest_dir = tmp_path / "destination"
    dest_dir.mkdir()
    (dest_dir / "track1.mp3").write_bytes(b"abc")

    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()

    config = {
        "source": str(source_dir),
        "destination": str(dest_dir),
        "backup": str(backup_dir),
        "archive": str(archive_dir),
        "devicename": "USB-Device",
        "reports_path": str(tmp_path / "reports"),
        "mode": "incremental",
        "file_types": [".mp3", ".txt"],
    }

    report = generate_report(config, copied_count=1, validated_count=2, skipped_count=3, conflict_count=4, errors=[("x", "dest", "oops")])

    assert report["Device"] == "USB-Device"
    assert report["Source file count"] == 2
    assert report["Files copied this run"] == 1
    assert report["Files validated (hash match)"] == 2
    assert report["Files skipped (already up-to-date)"] == 3
    assert report["Conflicts resolved (timestamped backup)"] == 4
    assert report["Errors this run"] == 1
    assert report["Status"] == "completed"


def test_save_report_functions_write_expected_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report = {"Run Timestamp": "2024-01-01 00:00:00", "Device": "demo", "Mode": "full"}

    save_report_csv(report, "demo")
    save_report_json(report, "demo")
    save_error_log([("track.mp3", "destination", "copy failed")], "demo", run_id="run-001", config_path="/tmp/demo.yaml")

    csv_path = tmp_path / "reports" / "demo" / "demo_backup_report.csv"
    json_path = tmp_path / "reports" / "demo" / "demo_backup_report.json"
    errors_path = tmp_path / "reports" / "demo" / "demo_backup_errors.csv"

    assert csv_path.exists()
    assert json_path.exists()
    assert errors_path.exists()

    with csv_path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
        assert rows[0]["Device"] == "demo"

    with json_path.open() as fh:
        payload = json.load(fh)
        assert payload[0]["Mode"] == "full"

    with errors_path.open(newline="") as fh:
        rows = list(csv.reader(fh))
        assert rows[0][0] == "Run Timestamp"
        assert rows[0][1] == "run_id"
        assert rows[0][2] == "Config Path"
        assert rows[1][1] == "run-001"
        assert rows[1][2] == "/tmp/demo.yaml"
        assert rows[1][3] == "track.mp3"
        assert rows[1][4] == "destination"
        assert "copy failed" in rows[1][5]


def test_save_report_csv_writes_header_for_empty_existing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "reports" / "demo"
    folder.mkdir(parents=True)
    csv_path = folder / "demo_backup_report.csv"
    csv_path.write_text("", encoding="utf-8")

    report = {"Run Timestamp": "2024-01-01 00:00:00", "Device": "demo", "Mode": "full"}
    save_report_csv(report, "demo")

    with csv_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))

    assert rows[0] == ["Run Timestamp", "Device", "Mode"]
    assert rows[1][1] == "demo"
    assert rows[1][2] == "full"


def test_report_includes_run_id_and_matches_csv_json_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report = {
        "run_id": "2024-01-01 00:00:00",
        "Run Timestamp": "2024-01-01 00:00:00",
        "Device": "demo",
        "Config Path": "/tmp/demo.yaml",
        "Reports Path": "/tmp/reports",
        "Mode": "full",
        "Destination configured": "yes",
        "Destination Path": "/tmp/destination",
        "Total files at destination": 5,
        "Destination total size (MB)": 12.0,
        "Total files at backup": 2,
        "Backup total size (MB)": 3.5,
        "Total files at archive": 7,
        "Archive total size (MB)": 42.0,
    }

    save_report_csv(report, "demo")
    save_report_json(report, "demo")

    csv_path = tmp_path / "reports" / "demo" / "demo_backup_report.csv"
    with csv_path.open(newline="", encoding="utf-8") as fh:
        csv_rows = list(csv.DictReader(fh))

    json_path = tmp_path / "reports" / "demo" / "demo_backup_report.json"
    with json_path.open(encoding="utf-8") as fh:
        json_payload = json.load(fh)

    assert csv_rows[0]["run_id"] == "2024-01-01 00:00:00"
    assert json_payload[0]["run_id"] == "2024-01-01 00:00:00"
    assert set(csv_rows[0].keys()) == set(json_payload[0].keys())
    assert csv_rows[0]["Total files at destination"] == "5"
    assert json_payload[0]["Total files at destination"] == 5


def test_run_sync_generates_distinct_run_id_and_timestamp(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "song.mp3").write_bytes(b"audio")

    config = {
        "source": str(source_dir),
        "destination": str(tmp_path / "destination"),
        "backup": str(tmp_path / "backup"),
        "archive": str(tmp_path / "archive"),
        "devicename": "demo",
        "reports_path": str(tmp_path / "reports"),
        "file_types": [".mp3"],
        "mode": "full",
    }

    report, errors = run_sync(config, max_workers=1)

    assert errors == []
    assert report["run_id"]
    assert report["Run Timestamp"]
    assert report["run_id"] != report["Run Timestamp"]


def test_save_report_json_handles_invalid_existing_content(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "reports" / "demo"
    folder.mkdir(parents=True)
    broken_file = folder / "demo_backup_report.json"
    broken_file.write_text("{not valid json", encoding="utf-8")

    report = {"Run Timestamp": "2024-01-01 00:00:00", "Device": "demo"}
    save_report_json(report, "demo")

    with broken_file.open() as fh:
        payload = json.load(fh)
        assert payload[0]["Device"] == "demo"


def test_save_report_functions_follow_custom_reports_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    custom_root = tmp_path / "custom_reports"
    report = {"Run Timestamp": "2024-01-01 00:00:00", "Device": "demo", "Mode": "full"}

    save_report_csv(report, "demo", reports_base=str(custom_root))
    save_report_json(report, "demo", reports_base=str(custom_root))
    save_error_log([("track.mp3", "destination", "copy failed")], "demo", reports_base=str(custom_root))

    csv_path = custom_root / "demo" / "demo_backup_report.csv"
    json_path = custom_root / "demo" / "demo_backup_report.json"
    errors_path = custom_root / "demo" / "demo_backup_errors.csv"

    assert csv_path.exists()
    assert json_path.exists()
    assert errors_path.exists()
    assert not (tmp_path / "reports" / "demo" / "demo_backup_report.csv").exists()


def test_load_config_reads_yaml_file(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"
    backup_dir = tmp_path / "backup"
    archive_dir = tmp_path / "archive"

    config_path = tmp_path / "device.yaml"
    config = {
        "mode": "full",
        "source": str(source_dir),
        "destination": str(dest_dir),
        "backup": str(backup_dir),
        "archive": str(archive_dir),
        "devicename": "demo-device",
        "reports_path": str(tmp_path / "reports"),
        "file_types": [".mp3"],
    }
    with config_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(config, fh)

    loaded = load_config(str(config_path))
    for key, value in config.items():
        assert loaded[key] == value
    assert loaded["config_path"] == str(config_path.resolve())


def test_load_config_resolves_relative_paths_from_config_location(tmp_path):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    source_dir = config_dir / "source"
    source_dir.mkdir()

    config_path = config_dir / "device.yaml"
    config = {
        "mode": "full",
        "source": "source",
        "backup": "backup",
        "archive": "archive",
        "reports_path": "reports",
        "devicename": "demo-device",
        "file_types": [".mp3"],
    }
    with config_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(config, fh)

    loaded = load_config(str(config_path))

    assert loaded["source"] == str((config_dir / "source").resolve())
    assert loaded["backup"] == str((config_dir / "backup").resolve())
    assert loaded["archive"] == str((config_dir / "archive").resolve())
    assert loaded["reports_path"] == str((config_dir / "reports").resolve())


def test_resolve_config_path_prefers_explicit_runtime_file(tmp_path):
    explicit = tmp_path / "runtime.yaml"
    explicit.write_text("mode: full\n", encoding="utf-8")
    assert resolve_config_path(str(explicit)) == explicit.resolve()


def test_load_reports_base_uses_runtime_config_reports_path(tmp_path):
    custom_root = tmp_path / "custom_reports"
    config = {"reports_path": str(custom_root)}
    assert load_reports_base(config) == custom_root.resolve()


def test_validate_config_rejects_missing_or_invalid_required_fields(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    valid = {
        "mode": "incremental",
        "source": str(source_dir),
        "backup": str(tmp_path / "backup"),
        "archive": str(tmp_path / "archive"),
        "devicename": "demo-device",
        "reports_path": str(tmp_path / "reports"),
        "file_types": [".mp3"],
    }

    assert validate_config(valid) == valid

    valid_with_destination = dict(valid)
    valid_with_destination["destination"] = str(tmp_path / "dest")
    assert validate_config(valid_with_destination) == valid_with_destination

    invalid_missing = dict(valid)
    invalid_missing.pop("mode")
    try:
        validate_config(invalid_missing)
        assert False, "Expected ValueError for missing mode"
    except ValueError:
        pass

    invalid_mode = dict(valid)
    invalid_mode["mode"] = "invalid"
    try:
        validate_config(invalid_mode)
        assert False, "Expected ValueError for invalid mode"
    except ValueError:
        pass

    invalid_extensions = dict(valid)
    invalid_extensions["file_types"] = []
    try:
        validate_config(invalid_extensions)
        assert False, "Expected ValueError for empty file_types"
    except ValueError:
        pass

    invalid_reports = dict(valid)
    invalid_reports.pop("reports_path")
    try:
        validate_config(invalid_reports)
        assert False, "Expected ValueError for missing reports_path"
    except ValueError:
        pass


def test_backup_sync_main_reads_config_and_saves_reports(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "track.mp3").write_bytes(b"audio")

    dest_dir = tmp_path / "destination"
    config = {
        "devicename": "demo-device",
        "mode": "full",
        "source": str(source_dir),
        "destination": str(dest_dir),
        "backup": str(tmp_path / "backup"),
        "archive": str(tmp_path / "archive"),
        "reports_path": str(tmp_path / "reports_out"),
        "file_types": [".mp3"],
    }

    config_path = tmp_path / "config.yaml"
    with config_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(config, fh)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["backup_sync.py", "--config", str(config_path)])

    backup_sync.main()

    report_file = tmp_path / "reports_out" / "demo-device" / "demo-device_backup_report.csv"
    assert report_file.exists()
    assert (dest_dir / "track.mp3").exists()
