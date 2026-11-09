"""Bounded HTTPS client for the KeepVoice agent API.

Only two fixed routes are reachable, always on the KeepVoice origin, with
redirects disabled and a hard cap on the response size. The agent bearer token
is passed in by the caller for every request and is never attached to an
artifact or download link.
"""

from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Optional

BASE_URL = "https://keepvoice.yablokolabs.com"
API_HOST = "keepvoice.yablokolabs.com"
REVIEW_URL = BASE_URL + "/review"
# The service sits behind a Cloudflare edge that answers the default
# ``Python-urllib`` agent with Error 1010 (403). Send a stable, honest agent
# instead of letting the stdlib default decide whether requests are served.
USER_AGENT = "keepvoice-hermes/0.1.0"

SUBMIT_PATH = "/v1/jobs/from-upload"
_JOB_PATH_PREFIX = "/v1/jobs/"

MAX_RESPONSE_BYTES = 256 * 1024
DEFAULT_TIMEOUT_S = 15.0
MAX_TIMEOUT_S = 30.0

MAX_RETRY_AFTER_S = 3600
MAX_ERROR_BODY_BYTES = 4096

# Stable codes from the KeepVoice error envelope (server/errors.py, docs/api/AGENTO.md).
# Any other server code is ignored and the HTTP status mapping is used instead.
_SERVER_ERROR_CODES = frozenset(
    {
        "unauthorized",
        "reviewer_required",
        "artifact_link_invalid",
        "job_not_found",
        "upload_not_found",
        "upload_expired",
        "upload_consumed",
        "idempotency_conflict",
        "approval_conflict",
        "invalid_state",
        "stale_revision",
        "stale_subtitles",
        "stale_music",
        "upload_too_large",
        "invalid_media",
        "invalid_music",
        "invalid_subtitles",
        "music_rights_required",
        "source_rights_required",
        "queue_full",
        "human_confirmation_required",
    }
)
_SERVER_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ClientError(Exception):
    """Stable transport/HTTP failure with an actionable recovery hint."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: Optional[int] = None,
        retry_after: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retry_after = retry_after


@dataclass(frozen=True)
class Response:
    status: int
    body: dict


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect so the bearer cannot reach another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


def build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_NoRedirect)


def api_path(path: str) -> bool:
    """True when *path* is one of the two fixed API routes this plugin uses."""
    if path == SUBMIT_PATH:
        return True
    if not path.startswith(_JOB_PATH_PREFIX):
        return False
    job_id = path[len(_JOB_PATH_PREFIX):]
    return bool(job_id) and "/" not in job_id and "?" not in job_id and "#" not in job_id


def request_json(
    method: str,
    path: str,
    *,
    body: Optional[Mapping[str, Any]] = None,
    idempotency_key: Optional[str] = None,
    token: str = "",
    timeout: float = DEFAULT_TIMEOUT_S,
    opener: Any = None,
) -> Response:
    """Call one KeepVoice API route and return its JSON object.

    Raises :class:`ClientError` with a stable code for every failure path.
    """
    if not api_path(path):
        raise ClientError("invalid_path", "Refused a path outside the KeepVoice agent API.")

    timeout = max(1.0, min(float(timeout), MAX_TIMEOUT_S))
    data = json.dumps(dict(body)).encode("utf-8") if body is not None else None

    request = urllib.request.Request(BASE_URL + path, data=data, method=method)
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", USER_AGENT)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if idempotency_key:
        request.add_header("Idempotency-Key", idempotency_key)
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    active_opener = opener if opener is not None else build_opener()
    try:
        result = active_opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        status = int(getattr(exc, "code", 0) or 0)
        raw = b""
        try:
            raw = exc.read(MAX_ERROR_BODY_BYTES)
        except Exception:
            raw = b""
        raise _error_for_status(status, getattr(exc, "headers", None), raw) from None
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
        raise ClientError(
            "network_error",
            "Could not reach KeepVoice.",
        ) from None

    status = int(getattr(result, "status", 0) or 0)
    if not 200 <= status < 300:
        raise _error_for_status(status, getattr(result, "headers", None), b"")

    try:
        raw = result.read(MAX_RESPONSE_BYTES + 1)
    except (socket.timeout, TimeoutError, OSError):
        raise ClientError("network_error", "The KeepVoice response could not be read.") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ClientError(
            "response_too_large",
            "The KeepVoice response exceeded the size limit for an agent tool result.",
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ClientError(
            "invalid_response",
            "KeepVoice returned a response that was not JSON.",
        ) from None
    if not isinstance(payload, dict):
        raise ClientError("invalid_response", "KeepVoice returned an unexpected JSON shape.")
    return Response(status=status, body=payload)


def _error_for_status(status: int, headers: Any, raw: bytes = b"") -> ClientError:
    server_code = _server_error_code(raw)
    if 300 <= status < 400:
        return ClientError(
            "redirect_refused",
            "KeepVoice returned a redirect, and the plugin never follows one with the agent token.",
            status=status,
        )
    if status in (401, 403):
        return ClientError(
            server_code or "auth_failed", "KeepVoice rejected the agent credential.", status=status
        )
    if status == 404:
        return ClientError(
            server_code or "not_found",
            "KeepVoice has no such upload or job for this credential.",
            status=status,
        )
    if status == 409:
        return ClientError(
            server_code or "conflict",
            "KeepVoice reported a state or idempotency conflict.",
            status=status,
        )
    if status == 422:
        return ClientError(
            server_code or "invalid_request", "KeepVoice rejected the request body.", status=status
        )
    if status == 429:
        return ClientError(
            server_code or "rate_limited",
            "KeepVoice is not accepting this request right now.",
            status=status,
            retry_after=_retry_after(headers),
        )
    if status >= 500:
        return ClientError(
            server_code or "backend_error", "KeepVoice returned a server error.", status=status
        )
    return ClientError(server_code or "http_error", f"KeepVoice returned HTTP {status}.", status=status)


def _server_error_code(raw: bytes) -> Optional[str]:
    """Read the stable code from KeepVoice's error envelope, if it is one we know."""
    if not raw:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    if isinstance(code, str) and _SERVER_CODE_RE.match(code) and code in _SERVER_ERROR_CODES:
        return code
    return None


def _retry_after(headers: Any) -> Optional[int]:
    if headers is None:
        return None
    try:
        value = headers.get("Retry-After")
    except AttributeError:
        return None
    try:
        seconds = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return max(0, min(seconds, MAX_RETRY_AFTER_S))


def trusted_artifact_url(url: Any, job_id: str, artifact_name: str) -> bool:
    """True only for the expected final-artifact route on the trusted origin.

    No user information, no port, no fragment, HTTPS only. The agent bearer is
    never sent to this link; it carries its own short-lived signature.
    """
    if not isinstance(url, str) or not url or not isinstance(artifact_name, str) or not artifact_name:
        return False
    if "/" in artifact_name or "\\" in artifact_name:
        return False
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    if parsed.username or parsed.password:
        return False
    if parsed.hostname != API_HOST:
        return False
    if parsed.port is not None:
        return False
    if parsed.fragment:
        return False
    expected = f"/v1/artifacts/{job_id}/{artifact_name}"
    return urllib.parse.unquote(parsed.path) == expected
