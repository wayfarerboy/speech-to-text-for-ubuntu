# 05 — Cleanup: remove dead code, update tests

**Type:** task
**Status:** needs-triage
**Blocked by:** 04 (key_listener refactored)

## What to build

Remove or simplify `PushToTalkSession` to recording-only (transcription and typing responsibilities moved to coordinator). Update tests to reflect new architecture. Remove any remaining references to the old subprocess-based client invocation pattern. All existing tests pass; new integration coverage for the coordinator path.

## Acceptance criteria

- [ ] `PushToTalkSession` no longer references `TranscriptionClient` or `TextTyper` (or is removed if unused)
- [ ] `speech_to_text_client.py` updated or removed if superseded by coordinator
- [ ] All existing unit tests pass
- [ ] Test coverage exists for coordinator timeout and failure paths
- [ ] No dead imports or orphaned code
- [ ] `tickets.md` updated: old tickets marked complete, new section for "Separate coordinator" work
