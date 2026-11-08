# Project build

**User problem.** A creator wants to recover spoken audio from a vlog with background music, check the subtitles and release the intended cut. The plugin keeps job state and release decisions visible in Hermes.

**What is new.** The prior KeepVoice service already separates media, transcribes speech and supports browser-based review. This entry adds a native Hermes integration, predictable job submission and a deterministic, revision-aware export handoff. Describe that distinction in the README and PR.

## Repository and runtime

Use repository `keepvoice-hermes` and proposed catalog ID `keepvoice-hermes`. Start with `plugin.yaml`, `__init__.py`, `client.py`, `tools.py`, `README.md` and focused tests. Confirm ID availability, tool schema format and installed Hermes compatibility. Use `register(ctx)` and `ctx.register_tool()`. Declare only the three actual tools and required secret in the current manifest schema. Use `KEEPVOICE_AGENT_TOKEN` as a masked Hermes secret. Keep v1 CLI-first to make the demo reproducible.

## Tool behavior

1. **keepvoice_submit** takes upload ID, explicit rights confirmation and source provenance. Create the job via the documented JSON endpoint. Show the job ID, current state and whether the backend replayed the request. Prompt for missing permission, never infer it.
2. **keepvoice_status** takes job ID. Report status, revision, warning codes, subtitle cue count and whether the current revision is approved. Include a safe next step. Keep raw subtitle content and artifacts out of this response.
3. **keepvoice_export** takes job ID. Fetch fresh state. Release only the final video when status is completed and approval matches the current revision. Surface replacement music credit if applicable. Provide the signed URL only in the authorized private session on explicit request. If the session cannot safely show a bearer link, direct the creator to review instead.

Show the first status immediately. On queued or processing, say to check again. Finalizing is a separate state from completed. Failed, rejected, expired and unknown states return no artifact. Prefer a manual recheck over a tight polling loop.

## Verification

- Exercise retries with the same upload/body, false rights, stale approval, absent final artifact, foreign-origin links and malformed responses. Test that the client never follows bearer redirects.
- Run `hermes plugins doctor /path/to/keepvoice-hermes` and `hermes plugins validate /path/to/keepvoice-hermes --install-deps` against the commit intended for pinning. Record the version and actual result. Resolve warnings that affect the submission.
- Use Hermes itself for the demo. A Python harness validates policy but cannot prove registration or model tool invocation.
- Capture a real job before approval, a human review decision and a completed export. Check the final video and subtitle quality. Record test media provenance and redact capability URLs. If live verification fails, record which part failed and why.

## Scope and disclosures

Disclose HTTPS requests to KeepVoice, the data sent, who operates the backend, observed storage and retention behavior, and the profile-scoped credential. Plugin installation needs no shell-driven media processing, autonomous publishing or model provider changes. State actual dependencies, background activity, file reads and telemetry behavior after reviewing the implementation. Treat separation as an editing aid. Results depend on the clip and do not establish clearance of music rights.
