# PRD: Separate Coordinator Process

Separate the monolithic key_listener into two concerns: a lean key_listener that only reads input events and spawns work, and a short-lived coordinator that transcribes and types. Add timeouts, clipboard fallback, and systemd auto-restart so transient failures don't kill the system.

See [ADR 0001](../../docs/adr/0001-separate-coordinator-process.md) for the architectural rationale.
