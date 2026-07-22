### Deployment

**Two user services, both must restart on any config change:**
- `stt-server` — user service (local Whisper transcription)
- `stt-keylistener` — user service (key capture via `input` group, Deepgram streaming, typing)

**Prerequisite:** user must be in `input` group (`sudo usermod -a -G input $USER` + re-login).

```bash
# Deploy / redeploy all services (idempotent, no root needed)
bash deploy/deploy-services.sh
```

**Lesson:** after any change to `config.py`, `.env`, `deepgram_streaming_client.py`,
or `push_to_talk_session_streaming.py`, always restart **both** services and verify
with `systemctl status` that new PIDs are active. Stale processes silently run old code.

## Agent skills

### Issue tracker

[GitHub Issues](https://github.com/wayfarerboy/speech-to-text-for-ubuntu/issues) with `ready-for-agent` label. Planning artifacts (PRDs, ADRs, maps) under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical defaults — `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — `CONTEXT.md` + `docs/adr/` at repo root. See `docs/agents/domain.md`.
