# Resume KeepVoice for Hermes

Open the checkout and read `docs/PROGRESS.md`. Inspect Git status, the latest
commit and local diffs. Resume the first incomplete milestone.

The plugin is implemented and validated at commit
`f1d93aa2b62b60b6f0f168f95cc60d85cdffcbda`, which is the SHA pinned in
`submission/keepvoice-hermes.yaml`. Re-run the checks if the code moved:

```bash
python3 -m unittest discover -s tests -v
hermes plugins doctor . --ci
hermes plugins validate . --install-deps
```

The remaining work is the consented live job: set `KEEPVOICE_AGENT_TOKEN` in the
active profile, upload an authorized clip in KeepVoice, submit it from Hermes,
observe `needs_review`, have the creator approve the current revision in
KeepVoice, then run `keepvoice_export` and check the returned video. After that,
open the catalog PR against `NousResearch/hermes-agent` with
`submission/keepvoice-hermes.yaml` at `plugin-catalog/keepvoice-hermes.yaml`, post
the demo, and submit the PR and post links.

Checkpoint after each milestone or 30 minutes: date/time, commit, commands and
results, job state (redacted), blockers and one concrete next action. Store no
credentials, signed artifact URLs or private transcripts. Session memory uses the
Hindsight bank `keepvoice-hermes` with sanitized notes only.
