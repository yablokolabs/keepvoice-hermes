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

Commit `82a88af262835e3ffa7a991edb87d837223fe261` (pinned for the catalog entry)
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
  `hermes plugins install yablokolabs/keepvoice-hermes --ref 82a88af262835e3ffa7a991edb87d837223fe261 --enable --yes-deps`.
  `hermes plugins list --plain` shows `enabled git pinned@82a88af2 0.1.0 keepvoice-hermes`.
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

## Reference reuse

The plugin reuses the KeepVoice API contract (`docs/API_CONTRACT.md`,
`docs/openapi.snapshot.json`) and carries the MIT notice from
`yablokolabs/keepvoice` in `LICENSE`. No source code from that repository is
copied: it performs local Demucs/torch/ffmpeg separation, which this plugin
deliberately leaves to the KeepVoice service.
