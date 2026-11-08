# KeepVoice for Hermes

A native Hermes plugin for KeepVoice. It starts a voice-cleanup job from a clip
the creator already uploaded, reports what needs a human check, and returns the
final video only after the creator approves the current revision.

KeepVoice does the media work and owns the review. This plugin adds three tools
and an export gate; it does not process audio, edit subtitles or approve a cut.

## Requirements

- Hermes Agent **0.23.0 or newer** (validated against 0.23.0).
- Python 3.10+ with the standard library only. The plugin declares no Python
  dependencies.
- A KeepVoice agent token with agent API scope, stored as the Hermes secret
  `KEEPVOICE_AGENT_TOKEN` in the active profile.
- A clip uploaded through the KeepVoice review page. Binary upload stays in
  KeepVoice, so the plugin never handles the file itself.

## Install

```bash
git clone https://github.com/yablokolabs/keepvoice-hermes.git
hermes plugins install ./keepvoice-hermes
hermes plugins enable keepvoice-hermes
```

Hermes prompts for `KEEPVOICE_AGENT_TOKEN` during install because it is declared
under `requires_env` with `secret: true`. The value is stored in the active
Hermes profile, not in this repository. Set or replace it through Hermes, and
never commit it.

## Tools

### `keepvoice_submit`

Takes `upload_id`, `rights_confirmed` and `source_provenance`.

- The upload ID must be 32 lowercase hex characters from the KeepVoice upload
  page.
- `rights_confirmed` must be the literal value `true`, after the creator
  explicitly confirms they are authorized to process the clip. The plugin never
  infers authorization and rejects `false`, `"true"`, `1` and a missing value
  before any request is made.
- Provenance is 5-500 characters with no control characters.

The request uses `Idempotency-Key: keepvoice-hermes:<upload_id>` and the exact
same body on every retry. A `409` is reported as a consumed upload or idempotency
conflict and is never retried with a fresh key. The result shows the job ID, the
current state and whether KeepVoice replayed an earlier submission.

### `keepvoice_status`

Fetches the job and reports status, revision, whether the current revision is
approved, the approval revision, warning codes and the subtitle cue count. It
returns no subtitle text, warning prose or artifact links.

Queued and processing jobs say to check again in about a minute. `finalizing` is
reported as its own state, separate from `completed`. `failed`, `rejected`,
`expired` and unrecognized states release nothing.

### `keepvoice_export`

Takes a fresh authenticated `GET` and releases the signed final-video link only
when all of these hold:

1. the returned job ID matches the request;
2. `status` is `completed`;
3. `revision` is a valid integer;
4. an `approval` record exists with the same revision;
5. `artifacts.final_video.url` is HTTPS on `keepvoice.yablokolabs.com`, with no
   user information, port or fragment, on exactly
   `/v1/artifacts/<job_id>/<artifact name>`.

Anything else withholds the link and explains the failed condition. A music
attribution from `music.attribution` is surfaced when present.

The link is shown only in a private Hermes session (`cli`, `tui`, `desktop`,
`acp`). On a gateway or unknown surface the plugin withholds it and points to the
KeepVoice review page. Signed links are short-lived private credentials: request a
fresh export when one expires, and keep them out of public material. Hermes may
retain a link in local session history on the user's host.

## Failure codes

The tools return stable codes with a recovery action: `invalid_upload_id`,
`invalid_job_id`, `invalid_provenance`, `rights_confirmation_required`,
`missing_credential`, `auth_failed`, `not_found`, `conflict`,
`invalid_request`, `rate_limited` (with `retry_after_seconds`), `backend_error`,
`network_error`, `redirect_refused`, `invalid_response`, `response_too_large`,
`not_completed`, `approval_missing`, `approval_stale`, `artifact_missing`,
`untrusted_artifact_url`.

## Network and data disclosures

Catalog rule 13 disclosures for what this plugin actually does:

- **Network.** HTTPS requests to `https://keepvoice.yablokolabs.com` only, on two
  fixed routes: `POST /v1/jobs/from-upload` and `GET /v1/jobs/<job_id>`. The API
  host is a constant in `client.py`; there is no user-configurable endpoint.
  Redirects are disabled, so the bearer cannot follow a `3xx` to another host.
  Each request has a 15-second default timeout (30-second cap) and each response
  is capped at 256 KiB. The plugin never fetches the signed artifact link.
- **Data sent.** The agent bearer token in the `Authorization` header, the upload
  ID, rights confirmation, provenance text, the job ID, and the idempotency key.
  No clip bytes, transcripts or subtitles leave Hermes through this plugin.
- **Operator.** The KeepVoice service at `keepvoice.yablokolabs.com` is operated
  by Yabloko Labs. Jobs, subtitles, review decisions and artifacts are stored
  there under that service's retention. The job payload reports
  `retention_days` and `expires_at`.
- **Credentials.** `KEEPVOICE_AGENT_TOKEN` is resolved per call with
  `agent.secret_scope.get_secret`, so it follows the active Hermes profile. The
  plugin never reads `.env` files, `auth.json` or another credential store. The
  reviewer credential stays in the KeepVoice review UI and is never handled here.
- **No background work.** No polling loop, timers, workers, subprocesses, shell
  commands or self-updating code. Every call is user-triggered.
- **Files.** The plugin reads no files outside its own source and writes no
  state. There is no telemetry, analytics or usage reporting.
- **Approval.** The plugin never approves, rejects or edits a cut, and it cannot
  clear music rights. Review and approval happen in KeepVoice.

## Development

```bash
python3 -m unittest discover -s tests -v
hermes plugins doctor . --ci
hermes plugins validate . --install-deps
```

The tests use synthetic fixtures and a fake transport, so they need no
credentials and make no network calls. They cover the submission retry and
conflict paths, false and missing rights confirmation, malformed responses, the
stale-approval and missing-artifact export paths, foreign-origin and wrong-route
artifact links, redirect refusal, rate limiting and public-session withholding.

## Reuse and license

This plugin is new work, but it follows the service implementation at
[`yablokolabs/keepvoice`](https://github.com/yablokolabs/keepvoice) rather than
inventing its own contract:

- `server/schemas.py` defines the submission, job, approval and artifact shapes,
  including the 32-lowercase-hex upload ID and the 5-500 character provenance.
  The plugin validates those bounds locally before any request.
- `server/artifacts.py` (`ArtifactSigner`) defines the signed route
  `<base>/v1/artifacts/<job_id>/<name>`. The export gate accepts only that exact
  route on HTTPS with no user information, port or fragment, which is why a link
  for another job or artifact is withheld.
- `server/app.py` and `docs/api/AGENTO.md` define the lifecycle
  (`queued` → `processing` → `needs_review` → `finalizing` → `completed`, plus
  `failed` and `rejected`) and the error envelope. `client.py` reads the stable
  `error.code` from that envelope (`upload_consumed`, `idempotency_conflict`,
  `queue_full`, `upload_expired`, and so on) and ignores unknown codes, falling
  back to the HTTP status.
- `docs/api/openapi.json` in the service matches `docs/openapi.snapshot.json`
  here and the deployed `/openapi.json`; the plugin's paths and fields were
  checked against all three.

No service source is copied or vendored. The plugin performs no media
processing, imports no Demucs, torch, ffmpeg or FastAPI code, and has no Python
dependencies. It carries the same MIT license notice as the service, with
copyright Yabloko Labs, in [LICENSE](LICENSE). There are no bundled executables,
assets or third-party libraries.

## Limits

- Uploading a clip is a browser step in KeepVoice; the plugin starts from an
  upload ID.
- A live end-to-end run needs the creator's KeepVoice token and a consented
  clip, so it is performed by the operator, not by the automated checks.
- Separation is an editing aid. Results depend on the clip and do not establish
  clearance of music rights.
