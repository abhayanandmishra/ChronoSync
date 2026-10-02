
#attachment:plan-prompt.md flow 1 - from source file1 is copied to destination, backup (metadata) and archive.
flow 2 - file 1 is removed from destination purposely. backup will still have its metadata with status deleted. archive no change, file will keep on existing.

there should be sync between destination, backup (metadata) and archive.


#plan-prompt.md when this rollback happened, it is removing entries from backup_metadata.json file, but all other reports entries are already there which is confusing. correct
so if rollback for particular run_id happened, add status in report as rollback 


Archive metadata deduplication uses shallow identity (reporting.py)

Falls back to file_name if both source_path and archive_path are missing, which is correct but assumes file names are unique per run. If two devices have same-named files in the same backup, only one record survives. This is acceptable for the current multi-device workflow since each config has its own metadata file.
Optional destination requires restore/restore flows to compute path fallback (sync_engine.py)

Archive-only runs without destination are fully supported, but restore operations need resolve_destination_path() to reconstruct destination from metadata. This is correct but adds slight complexity to the restore contract.
No atomic rollback or transactional guarantees (sync_engine.py)

Rollback works on metadata deletion first, then deletes files. If file deletion fails partway through, metadata is already gone. This is acceptable for a backup tool (files remain safe) but not true ACID.

update spec with this feature
would like to store all config location and device in user directory with ~/.chronosync/config as key value
which will contain/save config location of devices which are added for 1st time and further. 
Add save and delete button to handle this. 