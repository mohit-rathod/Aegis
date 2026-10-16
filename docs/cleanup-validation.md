# Cleanup verification

This cleanup removes unused scaffolding and improves readability/documentation without changing the guarded support behavior.

- Removed 76 unused files: empty implementation/test/build scaffolds, duplicate non-runtime config/fixture notes, superseded setup/architecture documents, a one-use interruption wrapper and an unreferenced narration WAV. The removal manifest records each path.
- Restored eight working scripts omitted from the uploaded archive, so documented setup/evaluation commands exist in the delivered project.
- Formatted Python and frontend code, sorted Python imports, removed unused imports/local state, and connected retained provider protocols to actual consumer annotations. Added reproducible Ruff configuration and a pinned optional dev formatter.
- Added root ARCHITECTURE.md; rewrote README.md for a fresh checkout, including venv, credentials, Redis, mandatory first index build, voice setup, startup, tests and troubleshooting.

## Checks performed

| Check | Result |
| --- | --- |
| Python regression suite | 105 tests passed, no skips, with real ephemeral Redis 6.2.14 and native Piper synthesis/cancellation. |
| Ruff lint and format | Passed across source, scripts, evaluation and tests. |
| Frontend contract and formatting | Node text/auth/capture/resampling/cancellation checks passed; Prettier 3.6.2 check passed. |
| Script commands | All eight restored scripts return --help successfully. |
| Internal imports | Static references resolve; 84 installed wheel modules import successfully. |
| Packaging | Wheel builds; includes prompts, frontend and recovery audio, and excludes removed source modules. |
| Data preservation | Uploaded KB files and orders.json are byte-identical. |

Raw outputs are under evidence/runs/cleanup-validation/. The update package additionally verifies dry-run/application/reapplication and conflict detection against the uploaded baseline, backing up replaced/removed files before mutation.

## Limits

Regression tests use explicit provider doubles for Groq and embedding inference, except for real native speech components specified above. No new live Groq, physical microphone, full voice scenario replay or production capacity measurement was performed for this cleanup. Earlier voice/browser scenario logs are preserved unchanged as historical evidence; they are not new cleanup measurements. Dependency ranges are not a full lockfile. Large weights, credentials, Redis data and an existing index are not included in this update.
