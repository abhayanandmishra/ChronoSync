# ChronoSync Project Archetype Creator
# Run this script in PowerShell to generate the folder structure and starter files

# Root project folder
$projectRoot = "ChronoSync"

# Define subfolders
$folders = @(
    "$projectRoot/core",
    "$projectRoot/utils",
    "$projectRoot/reports",
    "$projectRoot/tests"
)

# Create folders
foreach ($folder in $folders) {
    if (-not (Test-Path $folder)) {
        New-Item -ItemType Directory -Path $folder | Out-Null
        Write-Host "Created folder: $folder"
    }
}

# Create main files
$files = @{
    "$projectRoot/backup_sync.py" = @"
# Entry point for ChronoSync
from core.config_loader import load_config
from core.sync_engine import run_sync
from core.reporting import save_report_csv, save_error_log

if __name__ == "__main__":
    config = load_config()
    report, errors = run_sync(config)

    print("\n=== Backup Report ===")
    for key, value in report.items():
        print(f"{key}: {value}")

    save_report_csv(report)
    if errors:
        save_error_log(errors)
        print(f"Errors logged: {len(errors)} issues")
"@

    "$projectRoot/config.yaml" = @"
mode: "incremental"   # options: "incremental" or "full"
source: "/path/to/source"
destination: "/path/to/destination"
backup: "/path/to/backup"
archive: "/mnt/external_drive/archive"
file_types:
  - ".mp3"
  - ".jpg"
  - ".png"
"@

    "$projectRoot/requirements.txt" = "PyYAML"
    "$projectRoot/core/__init__.py" = ""
    "$projectRoot/utils/__init__.py" = ""
    "$projectRoot/tests/__init__.py" = ""
}

# Write files
foreach ($file in $files.Keys) {
    if (-not (Test-Path $file)) {
        $content = $files[$file]
        $content | Out-File -FilePath $file -Encoding utf8
        Write-Host "Created file: $file"
    }
}

# Create placeholder modules
$placeholders = @(
    "$projectRoot/core/config_loader.py",
    "$projectRoot/core/sync_engine.py",
    "$projectRoot/core/validation.py",
    "$projectRoot/core/reporting.py",
    "$projectRoot/utils/file_ops.py",
    "$projectRoot/utils/logging.py",
    "$projectRoot/utils/metrics.py",
    "$projectRoot/tests/test_sync_engine.py",
    "$projectRoot/tests/test_validation.py",
    "$projectRoot/tests/test_reporting.py"
)

foreach ($ph in $placeholders) {
    if (-not (Test-Path $ph)) {
        "# Placeholder for $ph" | Out-File -FilePath $ph -Encoding utf8
        Write-Host "Created placeholder: $ph"
    }
}

Write-Host "`nChronoSync project structure created successfully!"
