### Deployment

Use `pkexec` for privileged operations — `sudo` fails in agent contexts (no TTY). `pkexec` brings up a GUI auth dialog.

```bash
# Restart system services
pkexec systemctl restart stt-keylistener.service

# Deploy / redeploy all services (idempotent)
bash deploy/deploy-services.sh  # user service (no sudo needed)
pkexec systemctl restart stt-keylistener.service  # system service
```

The deploy script rewrites systemd unit files and restarts everything. Safe to re-run.

## Agent skills

### Issue tracker

[GitHub Issues](https://github.com/wayfarerboy/speech-to-text-for-ubuntu/issues) with `ready-for-agent` label. Planning artifacts (PRDs, ADRs, maps) under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical defaults — `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — `CONTEXT.md` + `docs/adr/` at repo root. See `docs/agents/domain.md`.
