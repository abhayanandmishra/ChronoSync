# ChronoSync Spec Update Prompt

This file is not the product specification.
It is the revision prompt used to update the source-of-truth specification in [spec.md](spec.md).

## Role
- [spec.md](spec.md) is the authoritative product specification.
- This file is only for proposing or updating requirements in [spec.md](spec.md).
- [impl-prompt.md](impl-prompt.md) is the engineering prompt that implements the approved specification.
- If any requirement conflicts, [spec.md](spec.md) wins.

## When to use this file
Use this prompt when the team needs to revise product scope, clarify behavior, add requirements, or change acceptance criteria for ChronoSync.

## Instructions
1. Read [spec.md](spec.md) first.
2. Update the relevant requirement sections in [spec.md](spec.md).
3. Keep the wording clear, testable, and product-focused.
4. Preserve reporting/dashboard structure requirements such as Overview, Trends, History / Audit, Rollback Status, and Error Log where relevant.
5. Add config-level requirements for a `reports_path` (or equivalent) option so the reporting output location is explicitly configurable in YAML.
6. Include persistent device-config registry behavior in the spec, including a registry backup stored on a separate backup drive chosen at load time, a startup/load-time prompt that lets the user confirm or choose that backup location, remembered backup-drive reuse so the user is not prompted again when a location was already provided, and save-on-exit behavior so the registry is written to the backup drive when the application closes.
7. Ensure the dashboard layout reflects the intended information architecture: individual report summaries belong in the Overview section, while the Details area is treated as the History / Audit view.
8. Do not add implementation details, code, CLI behavior, or engineering decisions here beyond the product contract itself.
9. Do not treat this file as the canonical requirement document.
10. After the spec changes, update [impl-prompt.md](impl-prompt.md) to match the new requirement set.

## Mandatory constraint
This prompt must never become the authoritative requirement source.
The only source of truth is [spec.md](spec.md).
If this file and [spec.md](spec.md) diverge, [spec.md](spec.md) is correct and this file must be updated to match before continuing work.

## Expected outcome
The result of using this prompt is a revised [spec.md](spec.md) that remains the single approved definition of ChronoSync behavior.
