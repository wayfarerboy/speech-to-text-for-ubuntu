# Issue tracker: GitHub Issues

Implementation issues live on [GitHub Issues](https://github.com/wayfarerboy/speech-to-text-for-ubuntu/issues) with the `ready-for-agent` label.

## Planning artifacts

PRDs, ADRs, domain research, and wayfinding maps live as local markdown under `.scratch/`:

- One feature per directory: `.scratch/<feature-slug>/`
- The PRD is `.scratch/<feature-slug>/PRD.md`
- Wayfinding map: `.scratch/<feature-slug>/map.md`

## When a skill says "publish to the issue tracker"

Create a GitHub issue on `wayfarerboy/speech-to-text-for-ubuntu` with the `ready-for-agent` label. Include blocking edges in the body under a `## Blocked by` heading.

Also create the corresponding planning files under `.scratch/<feature-slug>/` (PRD, map, and per-ticket `.md` files for local reference).

## When a skill says "fetch the relevant ticket"

Use `gh issue view <number>` or read the local `.scratch/<feature-slug>/issues/<NN>-<slug>.md` file.

## Triage labels

See `triage-labels.md` for the canonical label vocabulary.
