import json
from datetime import datetime
from pathlib import Path

import streamlit as st
import yaml

from core.config_loader import validate_config

ROOT_DIR = Path(__file__).resolve().parents[1]
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
            return yaml.safe_load(contents) or {}
        except yaml.YAMLError:
            return {}

    resolved_path = resolve_config_path(config_path)
    if resolved_path is None:
        return {}

    try:
        with resolved_path.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return {}

    return config


def load_reports_base(config=None):
    active_config = config or load_config_file()
    configured = active_config.get("reports_path") or active_config.get("reports_dir")
    if configured:
        return Path(configured).expanduser().resolve()

    return (ROOT_DIR / "reports").resolve()


def load_report_data(report_file):
    if not report_file.exists():
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
    if not error_file.exists():
        return []

    try:
        with error_file.open("r", newline="", encoding="utf-8") as handle:
            rows = list(__import__("csv").DictReader(handle))
    except (OSError, ValueError):
        return []
    return rows


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


def build_history_chart_data(reports):
    if not reports:
        return {"Copied": [], "Validated": [], "Skipped": [], "Conflicts": []}

    history = {"Copied": [], "Validated": [], "Skipped": [], "Conflicts": []}
    for report in reports:
        history["Copied"].append(as_number(report.get("Files copied this run", 0)))
        history["Validated"].append(as_number(report.get("Files validated (hash match)", 0)))
        history["Skipped"].append(as_number(report.get("Files skipped (already up-to-date)", 0)))
        history["Conflicts"].append(as_number(report.get("Conflicts resolved (timestamped backup)", 0)))
    return history


def main():
    st.set_page_config(page_title="ChronoSync Dashboard", layout="wide")
    st.markdown("<style>div[data-testid='stSelectbox'] label { font-size: 1.1rem; font-weight: 600; }</style>", unsafe_allow_html=True)
    st.markdown("<style>div[data-testid='stMetric'] > div { font-size: 1.1rem; }</style>", unsafe_allow_html=True)
    st.markdown("<style>.stMetric > label { font-size: 1.15rem !important; }</style>", unsafe_allow_html=True)
    st.markdown("<style>div.section-header { border-bottom: 2px solid #dfe3e8; margin: 1.2rem 0 0.8rem; padding-bottom: 0.35rem; }</style>", unsafe_allow_html=True)
    st.title("ChronoSync Dashboard")
    st.caption("Monitor backup runs, archive activity, and sync validation results.")

    with st.sidebar:
        st.subheader("Config")
        uploaded_config = st.file_uploader("Load Config", type=["yaml", "yml"], key="config_loader")
        default_path = resolve_config_path()
        custom_path = st.text_input(
            "Config path",
            value=str(default_path) if default_path else "",
            placeholder="Optional path to config.yaml",
            help="Load a specific config file at runtime without restarting the app.",
        )

        if uploaded_config is not None:
            try:
                loaded_config = yaml.safe_load(uploaded_config.read()) or {}
            except yaml.YAMLError:
                loaded_config = {}
        elif custom_path.strip():
            loaded_config = load_config_file(config_path=custom_path.strip())
        else:
            loaded_config = load_config_file()

        if not loaded_config:
            st.warning("No config file was found. Select a YAML file or provide a valid config path.")
            st.stop()

        try:
            validate_config(loaded_config)
        except ValueError as exc:
            st.error(f"Invalid config: {exc}")
            st.stop()

    reports_base = load_reports_base(loaded_config)

    if not reports_base.exists():
        st.warning(f"Reports folder not found: {reports_base}")
        st.stop()

    device_dirs = sorted([
        item.name for item in reports_base.iterdir() if item.is_dir()
    ])

    if not device_dirs:
        st.warning(f"No device reports were found in {reports_base}")
        st.stop()

    selected_device = st.selectbox("Select Device", device_dirs)
    report_file = reports_base / selected_device / f"{selected_device}_backup_report.json"
    error_file = reports_base / selected_device / f"{selected_device}_backup_errors.csv"
    reports = sort_reports_desc(load_report_data(report_file))
    error_rows = load_error_rows(error_file)

    if not reports:
        st.warning(f"No report data found for {selected_device}")
        st.stop()

    rollback_reports = [
        report for report in reports
        if str(report.get("Status", "")).lower() == "rollback"
    ]
    non_rollback_reports = [
        report for report in reports
        if str(report.get("Status", "")).lower() != "rollback"
    ]
    latest = non_rollback_reports[0] if non_rollback_reports else reports[0]

    overview_tab, trends_tab, history_tab, rollback_tab, errors_tab = st.tabs(["Overview", "Trends", "History / Audit", "Rollback", "Errors"])

    with overview_tab:
        st.subheader(f"Latest Snapshot for {selected_device}")
        summary_metrics = {
            "Mode": latest.get("Mode", "unknown"),
            "Files copied": latest.get("Files copied this run", 0),
            "Validated": latest.get("Files validated (hash match)", 0),
            "Skipped": latest.get("Files skipped (already up-to-date)", 0),
            "Conflicts": latest.get("Conflicts resolved (timestamped backup)", 0),
            "Errors": latest.get("Errors this run", 0),
        }

        cols = st.columns(len(summary_metrics))
        for col, (label, value) in zip(cols, summary_metrics.items()):
            col.metric(label, value)

        st.markdown("<div class='section-header'><h2>Current state</h2></div>", unsafe_allow_html=True)
        location_summary = {
            "Destination Files": latest.get("Total files at destination", 0),
            "Destination Size (MB)": latest.get("Destination total size (MB)", 0),
            "Tracked Backup Files": latest.get("Total files at backup", 0),
            "Backup Size (MB)": latest.get("Backup total size (MB)", 0),
            "Archive Files": latest.get("Total files at archive", 0),
            "Archive Size (MB)": latest.get("Archive total size (MB)", 0),
        }

        location_cols = st.columns(3)
        for idx, (title, value) in enumerate([
            ("Destination", {"Files": location_summary["Destination Files"], "Size (MB)": location_summary["Destination Size (MB)"]}),
            ("Backup", {"Tracked Backup Files": location_summary["Tracked Backup Files"], "Size (MB)": location_summary["Backup Size (MB)"]}),
            ("Archive", {"Files": location_summary["Archive Files"], "Size (MB)": location_summary["Archive Size (MB)"]}),
        ]):
            with location_cols[idx]:
                st.markdown(f"<h4 style='margin-bottom: 0.5rem;'>{title}</h4>", unsafe_allow_html=True)
                for key, val in value.items():
                    st.markdown(f"<div style='font-size: 1.05rem; margin: 0.15rem 0;'><strong>{key}:</strong> {val}</div>", unsafe_allow_html=True)

    with trends_tab:
        trend_reports = non_rollback_reports[:8] if non_rollback_reports else []
        history_data = build_history_chart_data(trend_reports)
        if history_data and any(history_data[key] for key in history_data):
            trend_cols = st.columns(2)
            with trend_cols[0]:
                st.subheader("Run activity")
                st.line_chart(history_data, height=260)
            with trend_cols[1]:
                st.subheader("Current storage footprint")
                storage_data = {
                    "Destination": as_number(latest.get("Total files at destination", 0)),
                    "Tracked Backup": as_number(latest.get("Total files at backup", 0)),
                    "Archive": as_number(latest.get("Total files at archive", 0)),
                }
                st.bar_chart(storage_data, height=260)
        else:
            st.info("No historical trend data is available yet.")

    with history_tab:
        st.subheader("History / Audit")
        st.dataframe(reports, use_container_width=True)

    with rollback_tab:
        if rollback_reports:
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

            st.subheader("Rollback Status")
            summary_cols = st.columns(3)
            outcome_counts = {"success": 0, "partial": 0, "not_found": 0}
            for row in rollback_reports:
                outcome = str(row.get("result", "")).lower()
                if outcome in outcome_counts:
                    outcome_counts[outcome] += 1
                elif str(row.get("Status", "")).lower() == "rollback":
                    outcome_counts["success"] += 1

            for idx, (label, count) in enumerate(outcome_counts.items()):
                with summary_cols[idx]:
                    st.metric(label.title(), count)

            st.dataframe(filtered_rollback, use_container_width=True)
        else:
            st.info("No rollback records are available for this device.")

    with errors_tab:
        if error_rows:
            st.subheader("Error Log")
            st.dataframe(error_rows, use_container_width=True)
        else:
            st.info("No file errors were recorded for this device.")


if __name__ == "__main__":
    main()
