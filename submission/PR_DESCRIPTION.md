# Catalog PR: add `keepvoice-hermes`

## What it does

`keepvoice-hermes` adds three tools to Hermes for the existing KeepVoice media
service. A creator uploads a clip in KeepVoice, then from Hermes:

- `keepvoice_submit` starts a cleanup job from the upload ID, with explicit
  rights confirmation and source provenance.
- `keepvoice_status` reports status, revision, approval state, warning codes and
  subtitle cue count.
- `keepvoice_export` returns the signed final video only when the job is
  completed, the approval covers the current revision, and the artifact link is
  on the expected KeepVoice route.

## Public Hermes extension points used

`plugin.yaml` plus `register(ctx)` and `ctx.register_tool()` only. No hooks,
middleware, core overrides, subprocesses or background workers. The agent token
is resolved per call with `agent.secret_scope.get_secret`. Session privacy for
the signed link uses `ctx.session_surface()`.

## Reuse versus new work

KeepVoice already separates speech from music, stores subtitles and runs
browser-based human review. New here: the native Hermes integration, pre-network
input validation, a stable idempotency key per upload, and a revision-aware
export gate that fails closed. Media processing is untouched and stays in the
service. The plugin implements the documented API contract and carries the MIT
notice from `yablokolabs/keepvoice`; no source code from that repository is
copied because it performs local Demucs/torch/ffmpeg processing that this plugin
does not do.

## Validation

Run at the pinned SHA on Hermes 0.23.0:

```
python3 -m unittest discover -s tests -v   # 30 tests, OK
hermes plugins doctor . --ci               # exit 0, 3 tools, 0 hooks
hermes plugins validate . --install-deps    # Validation passed, security scan safe
```

The fixture tests cover submission retry and conflict, false and missing rights
confirmation, malformed and oversized responses, redirect refusal, auth and rate
limit failures, stale approval, missing artifact, foreign-origin and wrong-route
artifact links, and withholding the link on a public surface. They need no
credentials and make no network calls.

## Catalog rule 13 disclosures

- HTTPS requests only to `https://keepvoice.yablokolabs.com`, two fixed routes:
  `POST /v1/jobs/from-upload` and `GET /v1/jobs/<job_id>`. Endpoint is a
  constant; redirects disabled; 15 s timeout (30 s cap); 256 KiB response cap.
  The plugin never fetches the signed artifact link.
- Sends the agent bearer, upload ID, rights confirmation, provenance, job ID and
  idempotency key. Sends no clip bytes, transcripts or subtitles.
- The backend is operated by Yabloko Labs; it stores jobs, subtitles, review
  decisions and artifacts under its own retention. Payloads report
  `retention_days` and `expires_at`.
- `KEEPVOICE_AGENT_TOKEN` is profile-scoped through Hermes. Reviewer credentials
  stay in the KeepVoice review UI. No `.env`, `auth.json` or other credential
  store is read.
- No background activity, files written, telemetry or usage reporting.
- The plugin never approves, rejects or edits a cut.

## Reviewer access

The automated checks are credential-free. For a live end-to-end run, a reviewer
needs their own `KEEPVOICE_AGENT_TOKEN` and a clip they are authorized to
process, uploaded through `https://keepvoice.yablokolabs.com`. The repository
README documents the full sequence: upload, submit, review, approve, export.
