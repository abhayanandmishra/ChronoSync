import os

import yaml

REQUIRED_CONFIG_KEYS = ["mode", "source", "destination", "backup", "archive", "file_types"]


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a dictionary.")

    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in config or config[key] in (None, "")]
    if missing:
        raise ValueError(f"Missing required config fields: {', '.join(missing)}")

    mode = config["mode"]
    if mode not in {"incremental", "full"}:
        raise ValueError("Config field 'mode' must be either 'incremental' or 'full'.")

    source = config["source"]
    if not isinstance(source, str) or not os.path.isdir(source):
        raise ValueError("Config field 'source' must be an existing directory path.")

    for key in ["destination", "backup", "archive"]:
        value = config[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Config field '{key}' must be a non-empty string path.")

    file_types = config["file_types"]
    if not isinstance(file_types, list) or not file_types:
        raise ValueError("Config field 'file_types' must be a non-empty list of extensions.")
    if any(not isinstance(ext, str) or not ext.startswith(".") for ext in file_types):
        raise ValueError("Each entry in 'file_types' must be a valid file extension like '.mp3'.")

    reports_path = config.get("reports_path") or config.get("reports_dir")
    if reports_path is not None:
        if not isinstance(reports_path, str) or not reports_path.strip():
            raise ValueError("Config field 'reports_path' must be a non-empty string path when provided.")

    return config


def load_config(config_file="config.yaml"):
    with open(config_file, "r") as f:
        config = yaml.safe_load(f)

    if config is None:
        raise ValueError("Configuration file is empty or invalid.")

    return validate_config(config)
