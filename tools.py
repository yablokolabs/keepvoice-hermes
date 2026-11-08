"""KeepVoice tool policy and handlers.

Policy lives here so it can be exercised without Hermes or the network:
input validation happens before any request, the export gate fails closed, and
every failure returns a stable code with a concrete recovery action.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

try:  # loaded as a package by Hermes
    from . import client
except ImportError:  # imported standalone by the checks in tests/
    import client  # type: ignore[no-redef]

TOKEN_ENV = "KEEPVOICE_AGENT_TOKEN"
IDEMPOTENCY_PREFIX = "keepvoice-hermes:"
FINAL_ARTIFACT_KEY = "final_video"

UPLOAD_ID_RE = re.compile(r"^[a-f0-9]{32}$")
JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
ARTIFACT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

PROVENANCE_MIN = 5
PROVENANCE_MAX = 500

# Surfaces where a signed artifact link is shown in the private session. Any
# other surface (unknown, gateway chat) withholds the link.
PRIVATE_SURFACES = frozenset({"cli", "tui", "desktop", "acp"})

KNOWN_STATUSES = frozenset(
    {"queued", "processing", "finalizing", "needs_review", "completed", "failed", "rejected", "expired"}
)

_RECOVERY = {
    "auth_failed": "Check KEEPVOICE_AGENT_TOKEN in the active Hermes profile and that it has agent API scope.",
    "not_found": "Check the upload or job ID, and that this credential owns it.",
    "invalid_request": "Correct the rights confirmation and source provenance; KeepVoice rejected the body.",
    "backend_error": "KeepVoice returned a server error. Check its /health endpoint and retry.",
    "network_error": (
        "Could not reach KeepVoice. Check connectivity and retry. If a submission outcome is uncertain, "
        "reuse the same idempotency key and the exact same body."
    ),
    "redirect_refused": (
        "KeepVoice returned a redirect. The plugin never follows one with the agent token; "
        "report this to the KeepVoice operator."
    ),
    "invalid_response": "KeepVoice returned an unexpected response. No artifact was released; retry or check the service.",
    "response_too_large": "KeepVoice returned more data than a tool result may carry. No artifact was released.",
    "http_error": "KeepVoice returned an unexpected HTTP status. Check the service and retry.",
}


def agent_token() -> str:
    """Resolve the agent token at call time from the active Hermes profile."""
    try:
        from agent.secret_scope import get_secret

        return (get_secret(TOKEN_ENV) or "").strip()
    except Exception:
        return ""


def _ok(**fields: Any) -> dict:
    return {"ok": True, **fields}


def _err(code: str, message: str, recovery: str, **fields: Any) -> dict:
    return {"ok": False, "code": code, "message": message, "recovery": recovery, **fields}


def _missing_credential() -> dict:
    return _err(
        "missing_credential",
        f"{TOKEN_ENV} is not configured for this Hermes profile.",
        f"Add {TOKEN_ENV} to the active Hermes profile (the plugin prompts for it at install) and retry.",
    )


def _client_error(exc: client.ClientError, *, action: str, job_id: Optional[str] = None) -> dict:
    recovery = _RECOVERY.get(exc.code, "Retry, or check KeepVoice service health.")
    fields: dict[str, Any] = {}
    if job_id:
        fields["job_id"] = job_id
    if exc.retry_after is not None:
        fields["retry_after_seconds"] = exc.retry_after
        recovery = f"Retry in {exc.retry_after} second(s)." if exc.retry_after else "Retry shortly."
    if exc.code == "conflict" and action == "submit":
        recovery = (
            "The upload may already be consumed, or the submission body changed after the first attempt. "
            "Keep the same idempotency key and the exact same body; do not create a new key. "
            "Use the existing job ID if you have it."
        )
    return _err(exc.code, exc.message, recovery, **fields)


def build_submission(
    upload_id: Any, rights_confirmed: Any, source_provenance: Any
) -> tuple[Optional[tuple[dict, str]], Optional[dict]]:
    """Validate a submission. Returns ``((body, key), None)`` or ``(None, error)``."""
    if not isinstance(upload_id, str) or not UPLOAD_ID_RE.match(upload_id):
        return None, _err(
            "invalid_upload_id",
            "The upload ID must be the 32-character lowercase hex value from the KeepVoice upload page.",
            "Copy the upload ID from KeepVoice and retry the submission.",
        )
    if rights_confirmed is not True:
        return None, _err(
            "rights_confirmation_required",
            "Rights confirmation must be an explicit, literal true from the creator.",
            "Ask the creator to confirm they are authorized to process this clip, then call the tool with "
            "rights_confirmed=true. The plugin never infers authorization.",
        )
    if not isinstance(source_provenance, str):
        return None, _err(
            "invalid_provenance",
            "Source provenance must be text describing where the clip came from.",
            "Pass the clip's origin in 5-500 characters, for example who recorded it and where.",
        )
    provenance = source_provenance.strip()
    if not (PROVENANCE_MIN <= len(provenance) <= PROVENANCE_MAX):
        return None, _err(
            "invalid_provenance",
            f"Source provenance must be {PROVENANCE_MIN}-{PROVENANCE_MAX} characters.",
            "Describe where the clip came from in 5-500 characters and retry.",
        )
    if _CONTROL_RE.search(provenance):
        return None, _err(
            "invalid_provenance",
            "Source provenance contains control characters.",
            "Remove line breaks and control characters from the provenance and retry.",
        )
    body = {
        "upload_id": upload_id,
        "rights_confirmed": True,
        "source_provenance": provenance,
    }
    return (body, f"{IDEMPOTENCY_PREFIX}{upload_id}"), None


def submit(
    token: str,
    upload_id: Any,
    rights_confirmed: Any,
    source_provenance: Any,
    *,
    opener: Any = None,
) -> dict:
    prepared, error = build_submission(upload_id, rights_confirmed, source_provenance)
    if error is not None:
        return error
    if not token:
        return _missing_credential()
    body, key = prepared  # type: ignore[misc]
    try:
        response = client.request_json(
            "POST",
            client.SUBMIT_PATH,
            body=body,
            idempotency_key=key,
            token=token,
            opener=opener,
        )
    except client.ClientError as exc:
        return _client_error(exc, action="submit")
    try:
        job = _coerce_job(response.body)
    except client.ClientError as exc:
        return _client_error(exc, action="submit")
    return _ok(
        job_id=job["job_id"],
        status=job["status"],
        revision=job["revision"],
        replayed=bool(job.get("replayed") is True),
        next_step=_status_next_step(job, _approved(job)),
    )


def status(token: str, job_id: Any, *, opener: Any = None) -> dict:
    if not isinstance(job_id, str) or not JOB_ID_RE.match(job_id):
        return _err(
            "invalid_job_id",
            "That job ID is not valid.",
            "Use the job ID returned by keepvoice_submit.",
        )
    if not token:
        return _missing_credential()
    try:
        job = _get_job(token, job_id, opener=opener)
    except client.ClientError as exc:
        return _client_error(exc, action="status", job_id=job_id)

    approved, approval_revision = _approved(job)
    warnings = job.get("warnings")
    warnings = warnings if isinstance(warnings, list) else []
    codes: list[str] = []
    for warning in warnings:
        if isinstance(warning, dict) and isinstance(warning.get("code"), str) and warning["code"] not in codes:
            codes.append(warning["code"])
    subtitles = job.get("subtitles")
    cues = subtitles.get("cues") if isinstance(subtitles, dict) else None
    cue_count = len(cues) if isinstance(cues, list) else 0

    return _ok(
        job_id=job["job_id"],
        status=job["status"],
        revision=job["revision"],
        approved=approved,
        approval_revision=approval_revision,
        warning_codes=codes,
        warning_count=len(warnings),
        subtitle_cue_count=cue_count,
        expires_at=job.get("expires_at"),
        next_step=_status_next_step(job, (approved, approval_revision)),
    )


def export(token: str, job_id: Any, *, surface: str, opener: Any = None) -> dict:
    """Release the final video only for an approved, completed revision."""
    if not isinstance(job_id, str) or not JOB_ID_RE.match(job_id):
        return _err(
            "invalid_job_id",
            "That job ID is not valid.",
            "Use the job ID returned by keepvoice_submit.",
        )
    if not token:
        return _missing_credential()
    try:
        job = _get_job(token, job_id, opener=opener)
    except client.ClientError as exc:
        return _client_error(exc, action="export", job_id=job_id)

    revision = job["revision"]
    state = {"job_id": job["job_id"], "status": job["status"], "revision": revision}

    if job["status"] != "completed":
        return _err(
            "not_completed",
            f"The job is {job['status']}, not completed, so no export is released.",
            _status_next_step(job, _approved(job)),
            **state,
        )

    approved, approval_revision = _approved(job)
    if approval_revision is None:
        return _err(
            "approval_missing",
            "The current revision has no recorded human approval.",
            f"Review and approve revision {revision} in KeepVoice at {client.REVIEW_URL}. "
            "The plugin cannot approve on the creator's behalf.",
            **state,
        )
    if not approved:
        return _err(
            "approval_stale",
            f"The recorded approval covers revision {approval_revision}, but the current revision is {revision}.",
            f"Review the current revision {revision} in KeepVoice at {client.REVIEW_URL} and approve it, "
            "then request the export again.",
            **state,
        )

    artifacts = job.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    link = artifacts.get(FINAL_ARTIFACT_KEY)
    if not isinstance(link, dict) or not link.get("url"):
        return _err(
            "artifact_missing",
            "No final video is attached to the approved revision yet.",
            "Wait for finalization to finish, then request the export again. Finalizing is a separate state "
            "from completed.",
            **state,
        )

    artifact_name = link.get("name")
    url = link.get("url")
    if not isinstance(artifact_name, str) or not ARTIFACT_NAME_RE.match(artifact_name):
        return _err(
            "untrusted_artifact_url",
            "The final video entry has an unexpected artifact name.",
            "The link was withheld. Review the job in KeepVoice and report this to the KeepVoice operator.",
            **state,
        )
    if not client.trusted_artifact_url(url, job["job_id"], artifact_name):
        return _err(
            "untrusted_artifact_url",
            "The final video link is not the expected KeepVoice artifact route, so it was withheld.",
            "Open the job in KeepVoice to review it and report the link to the KeepVoice operator.",
            **state,
        )

    attribution = None
    music = job.get("music")
    if isinstance(music, dict):
        candidate = music.get("attribution")
        if isinstance(candidate, str) and candidate.strip():
            attribution = candidate.strip()

    if surface not in PRIVATE_SURFACES:
        return _ok(
            **state,
            export_ready=True,
            download_url=None,
            restricted=True,
            attribution=attribution,
            next_step=(
                "This is not a private Hermes session, so the signed download link is withheld. "
                f"Open the job in KeepVoice at {client.REVIEW_URL}, or run keepvoice_export from the Hermes CLI."
            ),
        )

    return _ok(
        **state,
        export_ready=True,
        download_url=url,
        restricted=False,
        attribution=attribution,
        next_step=(
            "The signed link is time limited and appears in this Hermes session history on your host. "
            "Request a fresh export if it expires."
        ),
    )


def _get_job(token: str, job_id: str, *, opener: Any = None) -> dict:
    response = client.request_json("GET", f"/v1/jobs/{job_id}", token=token, opener=opener)
    return _coerce_job(response.body, expected_job_id=job_id)


def _coerce_job(payload: Any, expected_job_id: Optional[str] = None) -> dict:
    if not isinstance(payload, dict):
        raise client.ClientError("invalid_response", "KeepVoice returned an unexpected job shape.")
    job_id = payload.get("job_id")
    if not isinstance(job_id, str) or not JOB_ID_RE.match(job_id):
        raise client.ClientError("invalid_response", "KeepVoice returned a job without a usable job ID.")
    if expected_job_id is not None and job_id != expected_job_id:
        raise client.ClientError("invalid_response", "KeepVoice returned a different job than the one requested.")
    status = payload.get("status")
    if not isinstance(status, str) or not status:
        raise client.ClientError("invalid_response", "KeepVoice returned a job without a status.")
    revision = payload.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool):
        raise client.ClientError("invalid_response", "KeepVoice returned a job without a valid revision.")
    return payload


def _approved(job: dict) -> tuple[bool, Optional[int]]:
    approval = job.get("approval")
    if not isinstance(approval, dict):
        return False, None
    revision = approval.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool):
        return False, None
    return revision == job.get("revision"), revision


def _status_next_step(job: dict, approved: tuple[bool, Optional[int]]) -> str:
    status = job.get("status")
    revision = job.get("revision")
    is_approved, approval_revision = approved
    if status in ("queued", "processing"):
        return "KeepVoice is still working on this job. Check again in about a minute; there is no need to poll tightly."
    if status == "finalizing":
        return "KeepVoice is finalizing the cut. Finalizing is a separate state from completed; check again shortly."
    if status == "needs_review":
        return (
            f"The current cut needs a human check. Open {client.REVIEW_URL}, review revision {revision} and "
            "approve it there; the plugin cannot approve on the creator's behalf."
        )
    if status == "completed":
        if is_approved:
            return "The current revision is approved. Ask for the export."
        return (
            f"The job is completed but revision {revision} is not approved"
            + (f" (the approval covers revision {approval_revision})" if approval_revision is not None else "")
            + f". Review and approve revision {revision} at {client.REVIEW_URL}."
        )
    if status in ("failed", "rejected", "expired"):
        return (
            f"The job ended as {status}, so no artifact is available. Review the job in KeepVoice; "
            "a new attempt needs a fresh upload."
        )
    return "This status is not one the plugin recognizes. Recheck the job before acting; no artifact is released."


def as_json(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, sort_keys=True)
