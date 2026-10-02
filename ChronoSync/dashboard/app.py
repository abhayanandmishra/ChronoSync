import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st
import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config_loader import load_config, validate_config
from core.device_registry import (
    delete_device_config,
    get_saved_backup_drive,
    load_registry,
    remember_backup_drive,
    register_shutdown_backup,
    restore_registry_from_backup,
    save_device_config,
)

CONFIG_CANDIDATES = [
    ROOT_DIR / "config.yaml",
    ROOT_DIR / "configs" / "config.yaml",
]


def resolve_config_path(explicit_path=None):
    if explicit_path:
        candidate = Path(explicit_path).expanduser()
        if candidate.exists():
            return candidate.resolve()

    for config_path in CONFIG_CANDIDATES:
        if config_path.exists():
            return config_path.resolve()

    return None


def load_config_file(config_path=None, uploaded_file=None):
    if uploaded_file is not None:
        contents = uploaded_file.read() if hasattr(uploaded_file, "read") else uploaded_file
        try:
            config = yaml.safe_load(contents) or {}
            if isinstance(config, dict):
                config["config_path"] = "<uploaded>"
            return config
        except yaml.YAMLError:
            return {}

    resolved_path = resolve_config_path(config_path)
    if resolved_path is None:
        return {}

    try:
        return load_config(str(resolved_path))
    except (OSError, ValueError, yaml.YAMLError):
        return {}


def load_reports_base(config=None):
    active_config = config or load_config_file()
    configured = active_config.get("reports_path")
    if configured:
        return Path(configured).expanduser().resolve()

    return (ROOT_DIR / "reports").resolve()


def load_report_data(report_file):
    if not report_file or not report_file.exists():
        return []

    try:
        with report_file.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return [payload]
    except (json.JSONDecodeError, OSError):
        return []
    return []


def load_error_rows(error_file):
    if not error_file or not error_file.exists():
        return []

    try:
        with error_file.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except (OSError, ValueError):
        return []


def sort_reports_desc(reports):
    def sort_key(item):
        timestamp = item.get("Run Timestamp", "1970-01-01 00:00:00")
        try:
            return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return datetime.min

    return sorted(reports, key=sort_key, reverse=True)


def as_number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def latest_operational_report(reports):
    if not reports:
        return {}

    non_rollback = [report for report in reports if str(report.get("Status", "")).lower() != "rollback"]
    return non_rollback[0] if non_rollback else reports[0]


def build_history_chart_data(reports):
    if not reports:
        return {"Copied": [], "Validated": [], "Skipped": [], "Conflicts": []}

    history = {"Copied": [], "Validated": [], "Skipped": [], "Conflicts": []}
    for report in reports:
        history["Copied"].append(as_number(report.get("Files copied this run", 0)))
        history["Validated"].append(as_number(report.get("Files validated (hash match)", 0)))
        history["Skipped"].append(as_number(report.get("Files skipped (already up-to-date)", 0)))
        history["Conflicts"].append(as_number(report.get("Conflicts resolved (hash-suffixed alternative copies)", report.get("Conflicts resolved (timestamped backup)", 0))))
    return history


def render_metric_grid(metrics):
    cols = st.columns(len(metrics))
    for col, (label, value) in zip(cols, metrics.items()):
        col.metric(label, value)


def render_key_value_grid(title, data):
    st.markdown(f"<div class='section-header'><h2>{title}</h2></div>", unsafe_allow_html=True)
    cols = st.columns(3)
    items = list(data.items())
    for index, (label, value) in enumerate(items):
        with cols[index % 3]:
            st.markdown(
                f"""
                <div class='card'>
                    <div class='card-label'>{label}</div>
                    <div class='card-value'>{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_empty_state(message, hint=None):
    st.info(message)
    if hint:
        st.caption(hint)


def main():
    st.set_page_config(page_title="ChronoSync Dashboard", layout="wide", initial_sidebar_state="expanded")
    if not st.session_state.get("registry_shutdown_registered"):
        register_shutdown_backup()
        st.session_state["registry_shutdown_registered"] = True
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.2rem; }
        .section-header { border-bottom: 2px solid #dfe3e8; margin: 1.1rem 0 0.85rem; padding-bottom: 0.3rem; }
        .section-header h2 { margin: 0; font-size: 1.2rem; color: #1f2937; }
        .card {
            background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            padding: 1rem 1rem 0.9rem;
            margin-bottom: 0.75rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
        }
        .card-label { color: #6b7280; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; }
        .card-value { color: #111827; font-size: 1.05rem; font-weight: 700; margin-top: 0.35rem; }
        .subtle { color: #6b7280; }
        div[data-testid='stMetric'] {
            background: #fff;
            border: 1px solid #e5e7eb;
            padding: 0.75rem 0.85rem;
            border-radius: 14px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("ChronoSync Dashboard")
    st.caption("Monitor backup runs, audit history, rollback activity, and file-level errors from a single view.")

    loaded_config = {}
    registry_entries = load_registry()
    remembered_backup_drive = get_saved_backup_drive()

    with st.sidebar:
        st.subheader("Configuration")
        if remembered_backup_drive:
            st.caption(f"Using remembered backup drive: {remembered_backup_drive}")
            change_backup_drive = st.checkbox("Change backup drive", value=False)
        else:
            st.warning("Choose a backup drive so ChronoSync can save and restore the registry backup.")
            change_backup_drive = True

        backup_drive_input = ""
        if change_backup_drive:
            backup_drive_input = st.text_input(
                "Registry backup drive",
                value=remembered_backup_drive,
                placeholder="Path to a separate drive or folder for registry backups",
                help="ChronoSync will remember this location and reuse it on the next load.",
            )

        active_backup_drive = backup_drive_input.strip() or remembered_backup_drive

        backup_action_cols = st.columns(2)
        with backup_action_cols[0]:
            if st.button("Remember backup drive"):
                if active_backup_drive:
                    remember_backup_drive(active_backup_drive)
                    st.success("Backup drive remembered.")
                else:
                    st.warning("Choose a backup drive first.")
        with backup_action_cols[1]:
            if st.button("Restore registry backup"):
                if active_backup_drive:
                    if restore_registry_from_backup(active_backup_drive):
                        registry_entries = load_registry()
                        st.success("Registry restored from backup.")
                    else:
                        st.warning("No registry backup was found for the selected backup drive.")
                else:
                    st.warning("Choose a backup drive first.")

        st.markdown("---")
        load_mode = st.radio(
            "Load config source",
            options=["Saved registry", "Config file"],
            index=0 if registry_entries else 1,
            horizontal=False,
            key="config_load_mode",
        )

        if load_mode == "Saved registry":
            if registry_entries:
                selected_registry_device = st.selectbox(
                    "Saved devices",
                    options=sorted(registry_entries.keys()),
                    key="saved_registry_device",
                )
                selected_registry_path = registry_entries.get(selected_registry_device, "")
                st.caption(f"Stored config: {selected_registry_path}")
                if selected_registry_path:
                    loaded_config = load_config_file(config_path=selected_registry_path)
            else:
                st.warning("No saved registry entries were found. Load a config file to create one.")

        if load_mode == "Config file":
            uploaded_config = st.file_uploader("Load Config", type=["yaml", "yml"], key="config_loader")
            default_path = resolve_config_path()
            custom_path = st.text_input(
                "Config path",
                value=str(default_path) if default_path else "",
                placeholder="Optional path to config.yaml",
                help="Load a specific config file at runtime without restarting the app.",
            )

            if uploaded_config is not None:
                loaded_config = load_config_file(uploaded_file=uploaded_config)
            elif custom_path.strip():
                loaded_config = load_config_file(config_path=custom_path.strip())
            else:
                loaded_config = load_config_file()

        if not loaded_config:
            st.warning("No config file was found. Select a saved device or provide a valid config path.")
            st.stop()

        try:
            validate_config(loaded_config)
        except ValueError as exc:
            st.error(f"Invalid config: {exc}")
            st.stop()

        st.success("Config loaded")
        st.caption(f"Device: {loaded_config.get('devicename', 'unknown')}")
        st.caption(f"Mode: {loaded_config.get('mode', 'unknown')}")
        st.caption(f"Config path: {loaded_config.get('config_path', 'unknown')}")
        st.caption(f"Reports path: {loaded_config.get('reports_path', 'unknown')}")

        action_cols = st.columns(2)
        config_path_value = loaded_config.get("config_path", "")
        can_save_registry = bool(config_path_value and config_path_value != "<uploaded>" and loaded_config.get("devicename"))
        if can_save_registry:
            with action_cols[0]:
                if st.button("Save device config"):
                    if active_backup_drive:
                        save_device_config(
                            loaded_config["devicename"],
                            config_path_value,
                            backup_drive=active_backup_drive,
                        )
                        st.success("Device config saved to the registry.")
                    else:
                        st.warning("Choose a backup drive first.")
            with action_cols[1]:
                if st.button("Delete device config"):
                    if active_backup_drive:
                        delete_device_config(
                            loaded_config["devicename"],
                            backup_drive=active_backup_drive,
                        )
                        st.warning("Device config deleted from the registry.")
                    else:
                        st.warning("Choose a backup drive first.")
        else:
            st.caption("Save/Delete actions are available only for configs loaded from a file path.")

    reports_base = load_reports_base(loaded_config)

    if not reports_base.exists():
        st.warning(f"Reports folder not found: {reports_base}")
        st.stop()

    device_dirs = sorted(item.name for item in reports_base.iterdir() if item.is_dir())

    if device_dirs:
        selected_device = st.selectbox("Select Device", device_dirs)
    else:
        selected_device = None
        st.warning(f"No device reports were found in {reports_base}")

    report_file = reports_base / selected_device / f"{selected_device}_backup_report.json" if selected_device else None
    error_file = reports_base / selected_device / f"{selected_device}_backup_errors.csv" if selected_device else None

    reports = sort_reports_desc(load_report_data(report_file)) if report_file else []
    error_rows = load_error_rows(error_file) if error_file else []

    rollback_reports = [report for report in reports if str(report.get("Status", "")).lower() == "rollback"]
    non_rollback_reports = [report for report in reports if str(report.get("Status", "")).lower() != "rollback"]
    latest = latest_operational_report(reports)

    header_cols = st.columns([2.4, 1, 1, 1])
    with header_cols[0]:
        st.subheader(selected_device or "No device selected")
        st.markdown(
            f"<div class='subtle'>Reports root: {reports_base}</div>",
            unsafe_allow_html=True,
        )
    with header_cols[1]:
        st.metric("Runs", len(reports))
    with header_cols[2]:
        st.metric("Rollback runs", len(rollback_reports))
    with header_cols[3]:
        st.metric("Errors", len(error_rows))

    if latest:
        st.markdown("<div class='section-header'><h2>Latest Run Snapshot</h2></div>", unsafe_allow_html=True)
        snapshot_metrics = {
            "Run ID": latest.get("run_id", "unknown"),
            "Timestamp": latest.get("Run Timestamp", "unknown"),
            "Status": latest.get("Status", "completed"),
            "Mode": latest.get("Mode", "unknown"),
            "Files Copied": latest.get("Files copied this run", 0),
            "Validated": latest.get("Files validated (hash match)", 0),
        }
        render_metric_grid(snapshot_metrics)

        render_key_value_grid(
            "Current State",
            {
                "Destination": f"{latest.get('Total files at destination', 0)} files | {latest.get('Destination total size (MB)', 0)} MB",
                "Backup": f"{latest.get('Total files at backup', 0)} records | {latest.get('Backup total size (MB)', 0)} MB",
                "Archive": f"{latest.get('Total files at archive', 0)} files | {latest.get('Archive total size (MB)', 0)} MB",
            },
        )
    else:
        render_empty_state(
            "No report data is available for the selected device.",
            "Load a config file and choose a device with existing reports to inspect ChronoSync activity.",
        )

    overview_tab, trends_tab, history_tab, rollback_tab, errors_tab = st.tabs(
        ["Overview", "Trends", "History / Audit", "Rollback Status", "Error Log"]
    )

    with overview_tab:
        if latest:
            overview_summary = {
                "Mode": latest.get("Mode", "unknown"),
                "Files Copied": latest.get("Files copied this run", 0),
                "Files Validated": latest.get("Files validated (hash match)", 0),
                "Files Skipped": latest.get("Files skipped (already up-to-date)", 0),
                "Conflicts Resolved": latest.get("Conflicts resolved (hash-suffixed alternative copies)", latest.get("Conflicts resolved (timestamped backup)", 0)),
                "Errors": latest.get("Errors this run", 0),
            }
            render_metric_grid(overview_summary)
            render_key_value_grid(
                "Overview Details",
                {
                    "Destination Summary": f"{latest.get('Total files at destination', 0)} files | {latest.get('Destination total size (MB)', 0)} MB",
                    "Backup Summary": f"{latest.get('Total files at backup', 0)} records | {latest.get('Backup total size (MB)', 0)} MB",
                    "Archive Summary": f"{latest.get('Total files at archive', 0)} files | {latest.get('Archive total size (MB)', 0)} MB",
                },
            )
        else:
            render_empty_state("No overview metrics are available yet.")

    with trends_tab:
        trend_reports = non_rollback_reports[:8] if non_rollback_reports else []
        history_data = build_history_chart_data(trend_reports)
        if history_data and any(history_data[key] for key in history_data):
            trend_cols = st.columns(2)
            with trend_cols[0]:
                st.subheader("Run Activity")
                st.line_chart(history_data, height=280)
            with trend_cols[1]:
                st.subheader("Storage Footprint")
                if latest:
                    storage_data = {
                        "Destination": as_number(latest.get("Total files at destination", 0)),
                        "Backup": as_number(latest.get("Total files at backup", 0)),
                        "Archive": as_number(latest.get("Total files at archive", 0)),
                    }
                    st.bar_chart(storage_data, height=280)
                else:
                    st.info("No storage summary is available.")
        else:
            render_empty_state("No historical trend data is available yet.", "Trends exclude rollback runs by design.")

    with history_tab:
        st.subheader("History / Audit")
        if reports:
            st.dataframe(reports, width='stretch', hide_index=True)
        else:
            render_empty_state("No history records are available for this device.")

    with rollback_tab:
        st.subheader("Rollback Status")
        if rollback_reports:
            outcome_counts = {"success": 0, "partial": 0, "not_found": 0}
            for row in rollback_reports:
                outcome = str(row.get("result", "")).lower()
                if outcome in outcome_counts:
                    outcome_counts[outcome] += 1
                elif str(row.get("Status", "")).lower() == "rollback":
                    outcome_counts["success"] += 1

            rollback_metrics = {
                "Rollback Runs": len(rollback_reports),
                "Successful": outcome_counts["success"],
                "Partial": outcome_counts["partial"],
                "Not Found": outcome_counts["not_found"],
            }
            render_metric_grid(rollback_metrics)

            rollback_columns = [
                "run_id",
                "Run Timestamp",
                "Status",
                "rolled_back_at",
                "affected_files_count",
                "result",
                "Device",
                "Mode",
            ]
            filtered_rollback = [
                {key: row.get(key, "") for key in rollback_columns if key in row}
                for row in rollback_reports
            ]
            st.dataframe(filtered_rollback, width='stretch', hide_index=True)
        else:
            render_empty_state("No rollback records are available for this device.")

    with errors_tab:
        st.subheader("Error Log")
        if error_rows:
            st.dataframe(error_rows, width='stretch', hide_index=True)
        else:
            render_empty_state("No file errors were recorded for this device.")


if __name__ == "__main__":
    main()
