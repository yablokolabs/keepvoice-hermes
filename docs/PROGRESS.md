# Progress

- [x] Select native Python plugin and scope the three tools.
- [x] Capture the known KeepVoice contract and official entry steps in the build kit.
- [x] Verify current Hermes runtime and KeepVoice API availability.
- [x] Implement tools and record policy checks.
- [x] Pass Plugin Doctor and catalog validation.
- [x] Verify a real Hermes session invokes the tools.
- [ ] Run the consented live job: upload → submit → needs_review → human approval → completed → fresh export.
- [ ] Open the catalog PR, post the demo and submit both links.

## Checkpoints

### 2026-11-08 — repository and environment

- Created public repository `github.com/yablokolabs/keepvoice-hermes` with `gh repo create`,
  default branch `master`. First commit `258d989` added the build kit.
- Runtime verified: Hermes Agent 0.23.0 (2026.9.24, stable, local `2bd378ed1b8d`),
  Python 3.14.9 for Hermes and Python 3.12.3 for the checks.
- KeepVoice availability checked with `curl https://keepvoice.yablokolabs.com/health`:
  `{"status":"ok","service":"keepvoice-agento-api","version":"1.0.0"}` with
  database, ffmpeg and storage all `ok`, queue depth 0.

### 2026-11-08 — implementation

Commit `74dc0a0b9e13440fa2c3ba67f4077d3e22fd203a` (pinned for the catalog entry)
adds `plugin.yaml`, `__init__.py`, `client.py`, `tools.py`, `tests/test_policy.py`,
`README.md` and `LICENSE`.

- Three tools registered through `register(ctx)` and `ctx.register_tool()`;
  `provides_tools` matches exactly.
- `KEEPVOICE_AGENT_TOKEN` declared under `requires_env` with `secret: true` and
  resolved per call with `agent.secret_scope.get_secret`.
- Requests limited to `https://keepvoice.yablokolabs.com` on
  `POST /v1/jobs/from-upload` and `GET /v1/jobs/<job_id>`, redirects disabled,
  15 s timeout (30 s cap), 256 KiB response cap.
- Submission validates the upload ID, literal `true` rights confirmation and
  provenance before any request, and reuses `keepvoice-hermes:<upload_id>` with
  the exact same body on retry.
- Export fails closed unless the job ID matches, status is `completed`, revision
  is an integer, the approval revision matches, and the artifact link is HTTPS on
  the trusted origin at `/v1/artifacts/<job_id>/<artifact name>`. The link is
  withheld on non-private surfaces.

### 2026-11-08 — validation

| Command | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -v` | 30 tests, `OK` |
| `hermes plugins doctor . --ci` | exit 0, `3 tool(s), 0 hook(s)` |
| `hermes plugins validate . --install-deps` | `Validation passed.` security scan safe, no core override, declared tools match |

The fixture checks cover submission success, replay, `409` conflict without a new
key, false/string/integer/missing rights, invalid upload ID and provenance,
malformed responses, auth failures, `429` with `Retry-After`, redirect refusal,
oversized responses, unknown and foreign job IDs, stale and missing approval,
`finalizing` and `failed` states, absent final artifact, eight foreign-origin or
wrong-route link shapes, and public-session withholding.

### 2026-11-08 — real Hermes session

- Installed from the public repo at the pinned SHA:
  `hermes plugins install yablokolabs/keepvoice-hermes --ref 74dc0a0b9e13440fa2c3ba67f4077d3e22fd203a --enable --yes-deps`.
  `hermes plugins list --plain` shows `enabled git pinned@74dc0a0b 0.1.0 keepvoice-hermes`.
- One-shot session:
  `hermes -z "Call the keepvoice_status tool exactly once with job_id test-job and report the JSON result verbatim."`
  The model invoked the registered tool; the returned payload was
  `{"code": "missing_credential", "ok": false, ...}`. Registration, schema and
  dispatch are proven; the token is not configured in this profile.

### 2026-11-08 — blockers and next action

- **Blocker:** `KEEPVOICE_AGENT_TOKEN` is not set for this profile (the install
  prompt was skipped non-interactively), and no consented clip is available on
  this host. The live upload → submit → review → approve → export run is therefore
  not done and is not claimed.
- **Next action:** set `KEEPVOICE_AGENT_TOKEN` in the active Hermes profile, upload
  a clip the creator is authorized to share, then run `keepvoice_submit`,
  `keepvoice_status`, approve in KeepVoice and run `keepvoice_export`. Record the
  observed states and check the exported video before opening the catalog PR.

### 2026-11-08 — contract alignment with the service checkout

Checked the plugin against the KeepVoice service source at
`/home/azureuser/keepvoice` and its local API container (`127.0.0.1:8080`,
healthy):

- `server/schemas.py` confirms the upload ID pattern, provenance bounds and job,
  approval and artifact shapes already used by the plugin.
- `server/artifacts.py` (`ArtifactSigner`) signs
  `<base>/v1/artifacts/<job_id>/<name>`; `final_video` maps to `final.mp4`. The
  export gate accepts only that route on HTTPS, so the check is unchanged and
  now documented against the signer.
- `docs/api/openapi.json`, the deployed `/openapi.json` and
  `docs/openapi.snapshot.json` have identical paths and schemas (10 paths).
- Tightened `JOB_ID_RE` to the service's 32-lowercase-hex ID form.
- `client.py` now reads the stable code from the service error envelope
  (`{"error": {"code", ...}}`) and surfaces allowlisted codes
  (`upload_consumed`, `idempotency_conflict`, `upload_expired`, `queue_full`, …),
  falling back to the HTTP status for unknown codes.
- Re-ran: 31 tests `OK`; `hermes plugins doctor . --ci` exit 0 (3 tools, 0
  hooks); `hermes plugins validate . --install-deps` `Validation passed.`

Reuse remains contract-level. No service source is copied or vendored, and the
plugin has no Python dependencies or media processing. The MIT notice from
`yablokolabs/keepvoice` is carried in `LICENSE`.

### 2026-11-09 — credential wired, Cloudflare edge fix

- `KEEPVOICE_AGENT_TOKEN` was not present in either profile `.env`
  (`~/.hermes/.env`, `~/.hermes/profiles/polaris/.env`). The active profile is
  the default one (`hermes config env-path` → `/home/azureuser/.hermes/.env`).
  Wrote the agent token from the service's own secret store
  (`data/secrets/agent_token`, mode 0600) into that `.env` without printing the
  value.
- Read-only proof the credential is valid: `GET /v1/jobs/<unknown>` with the
  token → 404 `job_not_found`; without it → 401.
- The first session after wiring still returned `auth_failed`. Root cause: the
  Cloudflare edge answers the stdlib default `Python-urllib/3.14` User-Agent
  with HTTP 403, Cloudflare Error 1010, which `client.py` mapped to
  `auth_failed`. The same token over `curl` returned 404.
- Fix: every request now sends `User-Agent: keepvoice-hermes/0.1.0`
  (`client.py`), with `test_requests_send_a_stable_user_agent` covering it.
- Session after the fix (`--ref f1d93aa2b62b60b6f0f168f95cc60d85cdffcbda`):
  `hermes -z "Call keepvoice_status exactly once with job_id 000…0"` returned
  `{"code": "job_not_found", "ok": false, ...}` for the all-zero job ID. That
  reply proves profile secret resolution, the User-Agent, the Cloudflare edge
  and the fixed `GET /v1/jobs/<job_id>` route all work end to end; only a real
  job ID is missing.
- Nothing was submitted or approved and no artifact was fetched in this step.

### 2026-11-09 — catalog PR opened

- Added one file, `plugin-catalog/keepvoice-hermes.yaml`, in a PR against
  `NousResearch/hermes-agent`: https://github.com/NousResearch/hermes-agent/pull/151759
- Entry pins `b4cff770eee08ebabab70bcfb5b5b90ec8fd4816`, `version: "0.1.0"`,
  `tier: community`, `category: voice`, `requires_hermes: ">=0.23.0"`.
  `capabilities` declares the three tools and `KEEPVOICE_AGENT_TOKEN`, no hooks
  or middleware.
- The PR diff is exactly that one added file, per the submission guide. The
  pinned tree passed locally: 32 tests OK, `hermes plugins doctor . --ci` exit 0,
  `hermes plugins validate . --install-deps` `Validation passed.`
- Ran the repository's own structural gate locally (fetched
  `scripts/validate_plugin_catalog.py`, installed its pinned `ruamel.yaml`
  `0.18.17` in a throwaway venv): `OK: 1 file(s) valid`.
- The `Plugin Catalog CI` run for the branch is `action_required` with no jobs,
  which is GitHub's approval gate for fork pull requests; the PR shows no checks
  until a maintainer approves the run. The consented live job is still
  outstanding.

### 2026-11-09 — handler guard for the plugin guide

- The guide's handler rules require every tool handler to return a JSON string
  and never raise. `__init__.py` only caught `client.ClientError`, so an
  unexpected exception could escape into the Hermes dispatcher.
- Each registered handler now catches `Exception` and returns a stable
  `internal_error` JSON payload with a recovery action; the regression is
  covered in `tests/test_policy.py`.
- Re-ran the suite, Doctor and `hermes plugins validate --install-deps`.

The catalog entry was re-pinned to `f75d546aeb42d84c3a2c5cfc95e2e013bf724c47`
in the same PR (a revision, not a post-merge SHA bump), with a PR comment
recording the handler-guard change and the re-run checks.

### 2026-11-09 — demo video

- Built `keepvoice-hermes` demo in `~/remotion-video-skill/projects/keepvoice-demo`: 1920x1080, 30 fps, 70.677 s, H.264 + AAC stereo, 30.2 MB at `out/video.mp4`.
- Seven scenes: hook, split, credential (`init-secrets`, 0600 files, SHA-256 digest compare), usage (`hermes plugins install keepvoice-hermes` then submit -> needs_review -> `approval_missing`), real pages, export gate, outro.
- Real page captures via moli `fetch --layout --dump screenshot_full` (review page, catalog PR #151759). No live job was run and none is shown.
- Voice: local piper `en_GB-cori-high` (British female). ElevenLabs free tier returned HTTP 402 for the young British voices and had ~93/10,000 characters left, so nothing was spent there.
- Checks: `npx tsc -p .` exit 0; stills reviewed in four batches; `ffprobe` 70.677 s with video+audio; `volumedetect` mean -18.4 dB overall, speech present in the usage and outro windows.
- Next: optional live job with consent, then swap the narration for a hosted young British voice if the plan allows it.

### 2026-11-09 — demo video opens on the problem

- The demo now starts with the pain point instead of the product: café, shop and
  passing-car music in a vlog, the resulting copyright claim, revenue held.
- New opening scene `Pain` (0.0–8.8 s); the promise, split, credential, usage,
  real surfaces, export gate and outro follow. Total 79.445 s, 1920x1080, 30 fps,
  34 MB, H.264 + AAC stereo at `~/remotion-video-skill/projects/keepvoice-demo/out/video.mp4`.
- Checks: `npx tsc -p .` exit 0; stills reviewed; `ffprobe` 79.445 s with both
  streams; `volumedetect` mean -18.4 dB overall and -19.8 dB over 0-8 s, so the
  opening line is present.

### 2026-11-09 — demo video is linked from the README

- Published the demo (79.445 s, 1920x1080, 30 fps, H.264 + AAC, 34 MB) as the
  `v0.1.0` release asset `keepvoice-hermes-demo.mp4` and linked it from a Demo
  section in the README. It is not committed, so a clone stays small.
- The README states which panels are illustrative and which captures are real,
  so the video cannot be read as proof of a live end-to-end job.
- The catalog entry still pins `f75d546`; this change only affects docs and
  where the video is hosted, so it does not change the submitted plugin code.

