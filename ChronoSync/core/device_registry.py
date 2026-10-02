import atexit
import json
from pathlib import Path


REGISTRY_DIR_NAME = ".chronosync"
REGISTRY_FILE_NAME = "config"
SETTINGS_FILE_NAME = "settings.json"


def _home_registry_dir():
    return Path.home() / REGISTRY_DIR_NAME


def get_registry_path():
    return _home_registry_dir() / REGISTRY_FILE_NAME


def get_settings_path():
    return _home_registry_dir() / SETTINGS_FILE_NAME


def _ensure_parent(path):
    path.parent.mkdir(parents=True, exist_ok=True)


def _atomic_write_text(path, content):
    _ensure_parent(path)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def _parse_key_value_registry(text):
    registry = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            registry[key] = value
    return registry


def _serialize_key_value_registry(registry):
    if not registry:
        return ""
    lines = [f"{key}={registry[key]}" for key in sorted(registry)]
    return "\n".join(lines) + "\n"


def load_registry(registry_path=None):
    path = Path(registry_path) if registry_path else get_registry_path()
    if not path.exists():
        return {}

    try:
        return _parse_key_value_registry(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def save_registry(registry, registry_path=None):
    path = Path(registry_path) if registry_path else get_registry_path()
    _atomic_write_text(path, _serialize_key_value_registry(registry))
    return path


def _load_settings():
    path = get_settings_path()
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_settings(settings):
    path = get_settings_path()
    _atomic_write_text(path, json.dumps(settings, indent=2, sort_keys=True))
    return path


def get_saved_backup_drive():
    return _load_settings().get("backup_drive", "")


def remember_backup_drive(backup_drive):
    backup_drive = (backup_drive or "").strip()
    settings = _load_settings()
    if backup_drive:
        settings["backup_drive"] = backup_drive
    else:
        settings.pop("backup_drive", None)
    _save_settings(settings)
    return backup_drive


def clear_saved_backup_drive():
    settings = _load_settings()
    settings.pop("backup_drive", None)
    _save_settings(settings)


def get_backup_registry_path(backup_drive=None):
    backup_drive = (backup_drive or get_saved_backup_drive() or "").strip()
    if not backup_drive:
        return None
    return Path(backup_drive).expanduser() / REGISTRY_DIR_NAME / REGISTRY_FILE_NAME


def load_backup_registry(backup_drive=None):
    backup_path = get_backup_registry_path(backup_drive)
    if backup_path is None or not backup_path.exists():
        return {}
    return load_registry(backup_path)


def restore_registry_from_backup(backup_drive=None):
    registry = load_backup_registry(backup_drive)
    if not registry:
        return False
    save_registry(registry)
    return True


def persist_registry_backup(backup_drive=None):
    backup_path = get_backup_registry_path(backup_drive)
    if backup_path is None:
        return False

    registry = load_registry()
    save_registry(registry, backup_path)
    return True


def save_device_config(device_name, config_path, backup_drive=None):
    device_name = (device_name or "").strip()
    config_path = (config_path or "").strip()
    if not device_name or not config_path:
        raise ValueError("device_name and config_path are required to save a registry entry.")

    registry = load_registry()
    registry[device_name] = config_path
    save_registry(registry)

    if backup_drive is not None:
        remember_backup_drive(backup_drive)
    persist_registry_backup(backup_drive)
    return registry


def delete_device_config(device_name, backup_drive=None):
    device_name = (device_name or "").strip()
    if not device_name:
        raise ValueError("device_name is required to delete a registry entry.")

    registry = load_registry()
    registry.pop(device_name, None)
    save_registry(registry)

    if backup_drive is not None:
        remember_backup_drive(backup_drive)
    persist_registry_backup(backup_drive)
    return registry


def register_shutdown_backup(backup_drive=None):
    def _persist():
        persist_registry_backup(backup_drive)

    atexit.register(_persist)
    return _persist
