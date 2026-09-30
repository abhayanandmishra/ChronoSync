# ChronoSync Specification

## Source of Truth
This file is the authoritative product specification for ChronoSync.

- [spec.md](spec.md) is the source of truth.
- [plan-prompt.md](plan-prompt.md) is a revision prompt used to update this file.
- [impl-prompt.md](impl-prompt.md) is the engineering prompt used to implement this specification.
- Any conflict between these files must be resolved in favor of this file.

This document defines the required behavior, acceptance criteria, and constraints for the project. It is the contract that implementation must satisfy.

## 1. Overview
ChronoSync is a Python-based backup and synchronization utility designed to copy configured media and file types from a source directory to destination, backup, and archive locations. The system must preserve file integrity, handle conflicts safely, reduce unnecessary re-copying in incremental mode, and generate clear run reports and error logs.

## 2. Objective
Create a reliable backup workflow that helps users protect files while preserving data integrity and minimizing accidental overwrite and duplication issues.

## 3. Scope
### In scope
- recursive source scanning
- extension-based filtering
- incremental and full sync execution
- copy operations to destination / backup / archive
- checksum validation
- conflict-safe naming strategy
- summary reporting and logging
- YAML configuration
- CLI entrypoints
- unit testing with edge cases

### Out of scope
- GUI interface
- cloud storage integration
- file versioning beyond timestamped/hash-suffixed copies
- real-time synchronization monitoring

## 4. Functional Requirements

### 4.1 Configuration
The system shall load a YAML config file containing runtime settings such as:
- source
- destination
- backup
- archive
- file_types
- mode
- devicename
- reports_path (optional)

The system shall:
- validate required configuration keys before performing any file operation
- require these keys: mode, source, destination, backup, archive, file_types
- reject empty or invalid values with clear errors
- ensure mode is either "incremental" or "full"
- ensure source is an existing directory path
- ensure destination, backup, and archive are valid paths or can be created
- ensure file_types is a non-empty list of extensions such as .mp3, .jpg, .png
- allow an optional `reports_path` value to override the default location where report and error files are written
- if `reports_path` is not supplied, store report output under the default device-specific reports directory, such as `reports/<device>/`
- read YAML safely using standard parsing methods
- raise clear exceptions when required values are missing or invalid

The runtime interface shall also allow the user to provide the config file location explicitly, such as `--config path/to/config.yaml`, while device-based resolution remains supported when appropriate.
The dashboard or UI shall also support loading a config file at runtime through a file-picker or a dedicated “Load Config” action so the user can select a YAML file without restarting the app or relying only on default discovery.
If no explicit config path is provided, the system may resolve the config from the default project locations or the current device context as defined by the application behavior.

### 4.2 Source File Discovery
The system shall:
- recursively scan the configured source directory
- detect files whose extensions match the configured file types
- skip unsupported files
- build a list of files to process before execution

### 4.3 Sync Modes
The system shall support two operating modes:

#### Incremental mode
- Only copy files that are missing or changed
- Compare source and target file timestamps and/or sizes before copying
- Skip unchanged files

#### Full mode
- Copy all files matching the configured extension list
- Ignore whether the target file already exists or is unchanged

### 4.4 Copy Operations
The system shall copy files to destination and archive locations as configured.

For each source file it must:
- ensure the target folder exists
- copy the file safely
- verify the target file successfully matches the source content
- track file-level status: copied, validated, skipped, or error

### 4.5 Conflict Resolution
When a target file already exists with different content, the system shall:
- avoid overwriting the original without a clear strategy
- create a safe alternative name, such as a timestamped or hash-suffixed file
- record the conflict as resolved
- continue processing subsequent files

Archive is the actual copied storage location. Backup is metadata-only and should not contain duplicate file content.

### Purge Destination and Archive Restore Operations
The system shall support explicit destination purge and archive restore actions as separate operational workflows.

#### Purge destination
The system shall support three purge modes for the destination:
- single-file purge: delete one file from the destination
- multi-file purge: delete multiple selected files from the destination in one operation
- full purge: delete all tracked destination files for the selected scope, such as all files from a run_id or all currently tracked destination files

For each purge action, the system must record:
- file name
- run_id
- action type
- timestamp
- status such as deleted, missing, or conflict

Purge destination must operate only on destination content. It must not delete archive copies unless a separate restore, rollback, or explicit archive-removal workflow is requested.

#### Restore archive
The system shall support three archive restore modes:
- single-file restore: restore one archived file back to the destination
- multi-file restore: restore multiple selected archived files back to the destination in one operation
- run-based restore: restore all archived files associated with a specific run_id

For each restore action, the system shall validate integrity before overwriting destination content:
- if the destination file does not exist, restore it
- if the destination file exists and the hash matches, skip it
- if the destination file exists and the hash does not match, raise a conflict and require explicit override or manual resolution

Archive restore is distinct from rollback. Rollback removes the files and metadata associated with a prior run, while archive restore selectively brings archived files back into the destination for recovery or replay.

### 4.6 Backup Metadata
The system shall maintain a metadata file inside the backup directory for each run or each copied file.

This metadata must include, at minimum:
- file_name
- source_path
- destination_path
- archive_path
- copied_at
- size_bytes
- sha256
- sync_mode
- status
- optional notes or conflict details
- run_id

The metadata entry should be stored in JSON format for readability and future lookup.

Backup is not intended to store duplicate file contents. It should only store what was copied, where it was copied, and when it was copied.
The run_id must uniquely identify the sync execution so that rollback can target the exact run without deleting records from other executions.

### Rollback Status and Report Integrity
When a rollback is performed for a specific run_id, the system shall clearly mark the affected run in the report history with a status of "rollback" instead of leaving it indistinguishable from a normal sync or cleanup action.

The system shall preserve historical report entries for auditability and must not silently make rollback appear as a generic successful operation. If the target run_id is found and rollback is executed, the report entry for that run shall include:
- run_id
- status = "rollback"
- rolled_back_at
- affected files count
- result = "success" or "partial"

If the target run_id is not found, the system shall return a clear "not_found" result and shall not mutate historical report records for unrelated runs.

Summary and trend views shall exclude rollback entries so that the current operational snapshot reflects the latest non-rollback run only. Rollback events shall remain visible in History and in a dedicated Rollback Status section in the Details view for auditability and lifecycle tracking.

Backup metadata may be removed for the rolled-back run as part of operational cleanup, but the report layer must remain clear and auditable. The historical report must still show that the run occurred and that it was later rolled back.

This rule ensures that destination cleanup, archive restore, and rollback remain distinct operations and that report history stays understandable.

### 4.7 Validation
The system shall validate integrity after copy by computing a hash (e.g., SHA-256) for the source and archive copy.

It must:
- confirm hash equality
- treat mismatch as a validation failure
- record errors with file and target context

### 4.8 Reporting
The system shall generate a run summary with:
- run timestamp
- device name
- mode
- files copied this run
- files validated
- files skipped
- conflicts resolved
- errors this run
- source and destination totals
- backup and archive totals

The reporting surface shall present the data in clear sections for:
- Overview
- Trends
- History / Audit
- Rollback Status
- Error Log

The Overview section shall provide the latest snapshot for the selected device and shall include the latest destination, backup, and archive state summaries for the current run.
The Trends section shall show previous runs in chronological order so the user can compare operational changes over time.
The History / Audit section shall show the full run history and audit trail, including prior runs and rollback lifecycle events.
The Rollback Status section shall clearly show rollback actions, results, and timestamps for auditability.
The Error Log section shall display any file-level errors captured during the run.

It shall support saving:
- CSV report
- JSON report
- CSV error log

Reports must be stored under a device-specific folder, such as:
- reports/<device>/

### 4.8 CLI
The system shall provide a command-line interface with these options:
- --config path/to/config.yaml
- --device device_name
- --rollback run_id

Exactly one execution mode is required at a time:
- sync mode: --config or --device
- rollback mode: --rollback together with either --config or --device

If neither sync nor rollback inputs are supplied, the system shall fail with a clear message.
If the chosen config file does not exist, the system shall raise a file-not-found error.
The rollback command must load the backup metadata for the target run_id, remove the destination and archive copies created by that run, and delete the matching metadata records without affecting other runs.

### 4.9 Error Handling
The system shall:
- continue processing when one file fails
- log errors without aborting the full run
- handle missing directories, permission problems, invalid config, malformed JSON, and failed copy operations cleanly
- avoid silent data loss

## 5. Non-Functional Requirements
### 5.1 Reliability
- Must not overwrite conflicting files blindly.
- Must preserve source data integrity.
- Must keep a record of failed copies.

### 5.2 Maintainability
- Code must be modular and readable.
- File responsibilities should be separated by function or module.

### 5.3 Testability
- Core logic should be covered by unit tests.
- Tests must validate real behavior, not mocks-only assertions.

### 5.4 Performance
- The tool should scale reasonably for moderate file counts.
- Multi-worker execution may be used when appropriate.

## 6. Data Model
### Configuration object
A YAML config file may include:
```
mode: "incremental"
source: "/path/to/source"
destination: "/path/to/destination"
backup: "/path/to/backup"
archive: "/mnt/external_drive/archive"
file_types:
  - ".mp3"
  - ".jpg"
  - ".png"
devicename: "USB-Device"
```

### Report structure
The report is a dictionary including string and numeric metrics, for example:
- Run Timestamp
- Device
- Mode
- Source file count
- Source total size (MB)
- Files copied this run
- Files validated (hash match)
- Files skipped (already up-to-date)
- Conflicts resolved (timestamped backup)
- Errors this run
- Total files at destination
- Destination total size (MB)
- Total files at backup
- Backup total size (MB)
- Total files at archive
- Archive total size (MB)

### Error record structure
Each error record contains:
- file name
- target name
- error message

## 7. Edge Cases
The implementation must handle these scenarios:
- source directory does not exist
- destination directory does not exist
- backup file already exists with different content
- file extension is unsupported
- file cannot be copied due to permissions or I/O errors
- config file is missing or malformed
- existing JSON report file contains invalid content
- file hash validation fails after copy
- incremental mode sees file already up to date
- full mode copies duplicate or stale files consistently

## 8. Acceptance Criteria
The project is accepted when all of the following are true:
1. It reads YAML config files successfully.
2. It recursively processes source files matching configured extensions.
3. It copies files to one or more configured targets.
4. It supports both incremental and full sync modes.
5. It safely handles conflicting existing files.
6. It validates copies by hash comparison.
7. It generates CSV and JSON reports with correct metrics.
8. It writes per-file error entries.
9. It exposes CLI behavior for config or device-based execution.
10. Tests pass successfully.
11. Test coverage is at least 90%.

## 9. Test Plan
### Unit tests
- file hash generation for valid file
- file hash generation for custom algorithm
- file hash failure for missing file
- file copy success case
- file copy validation success case
- file copy validation failure case
- needs_copy returns true when file missing
- needs_copy returns false for identical files
- safe_copy creates a hash-suffixed file when needed
- process_file handles copy and validation outcomes
- run_sync processes multiple files and tracks summary counts

### Integration-style tests
- run_sync with full mode on sample directories
- run_sync with incremental mode on unchanged files
- backup conflict file path creation with timestamped naming
- report generation with real temporary directories
- JSON report recovery from invalid data
- CLI invocation with config file

### Coverage target
- coverage >= 90%

## 10. Deliverables
The implementation must provide:
- the full Python source code
- modular project structure
- YAML config example files
- report and error log output
- unit tests covering edge cases
- CLI usage instructions

## 11. Success Definition
ChronoSync is successful when it can be run in a real workspace, sync files safely, verify them with hashes, identify conflicts without data loss, and generate accurate audit reports with passing automated tests.
