import os

import yaml

REQUIRED_CONFIG_KEYS = ["mode", "source", "backup", "archive", "file_types", "devicename", "reports_path"]


def _is_blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _normalize_path(path_value):
    return os.path.abspath(os.path.expanduser(path_value))


def _normalize_path_from_base(path_value, base_dir=None):
    expanded = os.path.expanduser(path_value)
    if os.path.isabs(expanded) or not base_dir:
        return os.path.abspath(expanded)
    return os.path.abspath(os.path.join(base_dir, expanded))


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a dictionary.")

    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in config or _is_blank(config[key])]
    if missing:
        raise ValueError(f"Missing required config fields: {', '.join(missing)}")

    mode = config["mode"]
    if mode not in {"incremental", "full"}:
        raise ValueError("Config field 'mode' must be either 'incremental' or 'full'.")

    source = config["source"]
    if not isinstance(source, str) or not os.path.isdir(source):
        raise ValueError("Config field 'source' must be an existing directory path.")

    for key in ["backup", "archive", "reports_path"]:
        value = config[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Config field '{key}' must be a non-empty string path.")

    destination = config.get("destination")
    if destination is not None:
        if not isinstance(destination, str) or not destination.strip():
            raise ValueError("Config field 'destination' must be a non-empty string path when provided.")

    devicename = config["devicename"]
    if not isinstance(devicename, str) or not devicename.strip():
        raise ValueError("Config field 'devicename' must be a non-empty string.")

    file_types = config["file_types"]
    if not isinstance(file_types, list) or not file_types:
        raise ValueError("Config field 'file_types' must be a non-empty list of extensions.")
    if any(not isinstance(ext, str) or not ext.startswith(".") for ext in file_types):
        raise ValueError("Each entry in 'file_types' must be a valid file extension like '.mp3'.")

    return config


def load_config(config_file="config.yaml"):
    normalized_config_path = _normalize_path(config_file)

    with open(normalized_config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if config is None:
        raise ValueError("Configuration file is empty or invalid.")

    config_dir = os.path.dirname(normalized_config_path)
    normalized_config = dict(config)
    for key in ("source", "backup", "archive", "reports_path", "destination"):
        value = normalized_config.get(key)
        if isinstance(value, str) and value.strip():
            normalized_config[key] = _normalize_path_from_base(value, config_dir)

    validated = dict(validate_config(normalized_config))
    validated["config_path"] = normalized_config_path

    return validated
