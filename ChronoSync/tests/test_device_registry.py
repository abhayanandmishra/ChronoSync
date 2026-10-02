from pathlib import Path

import core.device_registry as device_registry


def test_device_registry_save_restore_and_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(device_registry.Path, "home", lambda: tmp_path)

    backup_drive = tmp_path / "backup-drive"
    config_path = tmp_path / "configs" / "demo.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("mode: full\n", encoding="utf-8")

    device_registry.remember_backup_drive(str(backup_drive))
    assert device_registry.get_saved_backup_drive() == str(backup_drive)

    device_registry.save_device_config("demo-device", str(config_path), backup_drive=str(backup_drive))

    active_registry_path = tmp_path / ".chronosync" / "config"
    backup_registry_path = backup_drive / ".chronosync" / "config"

    assert active_registry_path.exists()
    assert backup_registry_path.exists()
    assert device_registry.load_registry()["demo-device"] == str(config_path)
    assert device_registry.load_backup_registry(str(backup_drive))["demo-device"] == str(config_path)

    active_registry_path.unlink()
    assert device_registry.restore_registry_from_backup(str(backup_drive)) is True
    assert device_registry.load_registry()["demo-device"] == str(config_path)

    device_registry.delete_device_config("demo-device", backup_drive=str(backup_drive))
    assert device_registry.load_registry() == {}
    assert device_registry.load_backup_registry(str(backup_drive)) == {}
