"""Fixture checks for the KeepVoice tool policy.

Runs without Hermes and without the network: a fake opener stands in for the
KeepVoice API, and every fixture is synthetic. Run with:

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
from email.message import Message
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_DIR))

import client  # noqa: E402
import tools  # noqa: E402

UPLOAD_ID = "9b3d1f0b6c2a4e5f8a7d0c1b2e3f4a5b"
JOB_ID = "job_7c1f2a9b"
TOKEN = "test-token-not-real"
ARTIFACT_URL = f"https://keepvoice.yablokolabs.com/v1/artifacts/{JOB_ID}/final_video.mp4?sig=redacted"


class FakeResponse:
    def __init__(self, status, payload, headers=None):
        if isinstance(payload, bytes):
            self._body = payload
        elif isinstance(payload, str):
            self._body = payload.encode("utf-8")
        else:
            self._body = json.dumps(payload).encode("utf-8")
        self.status = status
        self.headers = headers or {}

    def read(self, n=-1):
        return self._body if n is None or n < 0 else self._body[:n]


class FakeOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def http_error(status, body=b"{}", headers=None):
    return urllib.error.HTTPError(
        client.BASE_URL, status, "error", headers or Message(), io.BytesIO(body)
    )


def job(**overrides):
    payload = {
        "job_id": JOB_ID,
        "status": "needs_review",
        "revision": 3,
        "replayed": False,
        "created_at": "2026-11-08T20:00:00Z",
        "updated_at": "2026-11-08T20:04:00Z",
        "status_url": f"{client.BASE_URL}/v1/jobs/{JOB_ID}",
        "input": {
            "filename": "clip.mp4",
            "sha256": "0" * 64,
            "bytes": 1986228,
            "duration_s": 18.0,
            "provenance": "Creator-owned clip",
            "rights_confirmed_by_submitter": True,
        },
        "subtitles": {
            "srt": "1\n00:00:00,000 --> 00:00:01,500\nprivate subtitle line",
            "vtt": "WEBVTT\n\nprivate subtitle line",
            "sha256": "1" * 64,
            "cues": [{"index": 0, "start": 0.0, "end": 1.5, "text": "private subtitle line"}],
        },
        "music": None,
        "approval": None,
        "rejection": None,
        "warnings": [
            {"code": "speech_music_overlap", "severity": "warning", "message": "private backend prose"}
        ],
        "error": None,
        "artifacts": {},
        "retention_days": 7,
        "expires_at": "2026-11-15T20:00:00Z",
        "timings_ms": {},
        "processing_ms": None,
    }
    payload.update(overrides)
    return payload


def completed_job(**overrides):
    payload = job(
        status="completed",
        approval={
            "revision": 3,
            "approval_id": "apr_1",
            "approved_by": "creator",
            "approved_at": "2026-11-08T20:10:00Z",
        },
        artifacts={
            "final_video": {
                "name": "final_video.mp4",
                "url": ARTIFACT_URL,
                "content_type": "video/mp4",
                "sha256": "2" * 64,
                "bytes": 1986228,
            }
        },
        music={
            "asset_id": "asset_1",
            "sha256": "3" * 64,
            "level_db": -18.0,
            "provenance": "Licensed library track",
            "attribution": "Track by Example Artist (CC BY 4.0)",
            "rights_confirmed_by_creator": True,
        },
    )
    payload.update(overrides)
    return payload


class SubmissionChecks(unittest.TestCase):
    def test_submits_with_stable_key_and_exact_body(self):
        opener = FakeOpener(FakeResponse(202, job(status="queued")))
        result = tools.submit(TOKEN, UPLOAD_ID, True, "Creator-owned clip", opener=opener)
        self.assertTrue(result["ok"])
        self.assertEqual(result["job_id"], JOB_ID)
        self.assertEqual(result["status"], "queued")
        self.assertFalse(result["replayed"])

        request = opener.requests[0]
        self.assertEqual(request.full_url, client.BASE_URL + client.SUBMIT_PATH)
        self.assertEqual(request.get_header("Idempotency-key"), f"keepvoice-hermes:{UPLOAD_ID}")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {TOKEN}")
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {
                "upload_id": UPLOAD_ID,
                "rights_confirmed": True,
                "source_provenance": "Creator-owned clip",
            },
        )

    def test_retry_reuses_the_same_key_and_body(self):
        opener = FakeOpener(
            FakeResponse(202, job(status="queued")),
            FakeResponse(202, job(status="queued", replayed=True)),
        )
        tools.submit(TOKEN, UPLOAD_ID, True, "Creator-owned clip", opener=opener)
        second = tools.submit(TOKEN, UPLOAD_ID, True, "Creator-owned clip", opener=opener)
        self.assertTrue(second["replayed"])
        self.assertEqual(
            opener.requests[0].get_header("Idempotency-key"),
            opener.requests[1].get_header("Idempotency-key"),
        )
        self.assertEqual(opener.requests[0].data, opener.requests[1].data)

    def test_false_rights_are_rejected_before_any_request(self):
        opener = FakeOpener()
        result = tools.submit(TOKEN, UPLOAD_ID, False, "Creator-owned clip", opener=opener)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "rights_confirmation_required")
        self.assertEqual(opener.requests, [])

    def test_missing_rights_are_not_inferred(self):
        opener = FakeOpener()
        for value in (None, "true", 1):
            result = tools.submit(TOKEN, UPLOAD_ID, value, "Creator-owned clip", opener=opener)
            self.assertEqual(result["code"], "rights_confirmation_required")
        self.assertEqual(opener.requests, [])

    def test_invalid_upload_id_and_provenance_are_rejected_locally(self):
        opener = FakeOpener()
        for upload_id in ("", "ABC", "9b3d1f0b6c2a4e5f8a7d0c1b2e3f4a5", "../" + UPLOAD_ID):
            result = tools.submit(TOKEN, upload_id, True, "Creator-owned clip", opener=opener)
            self.assertEqual(result["code"], "invalid_upload_id")
        for provenance in ("", "four", "x" * 501, "line\nbreak"):
            result = tools.submit(TOKEN, UPLOAD_ID, True, provenance, opener=opener)
            self.assertEqual(result["code"], "invalid_provenance")
        self.assertEqual(opener.requests, [])

    def test_conflict_reports_existing_job_without_a_new_key(self):
        opener = FakeOpener(http_error(409))
        result = tools.submit(TOKEN, UPLOAD_ID, True, "Creator-owned clip", opener=opener)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "conflict")
        self.assertIn("same idempotency key", result["recovery"])
        self.assertEqual(opener.requests[0].get_header("Idempotency-key"), f"keepvoice-hermes:{UPLOAD_ID}")

    def test_missing_credential_is_reported(self):
        result = tools.submit("", UPLOAD_ID, True, "Creator-owned clip")
        self.assertEqual(result["code"], "missing_credential")

    def test_malformed_job_response_is_rejected(self):
        opener = FakeOpener(FakeResponse(202, {"job_id": JOB_ID}))
        result = tools.submit(TOKEN, UPLOAD_ID, True, "Creator-owned clip", opener=opener)
        self.assertEqual(result["code"], "invalid_response")


class StatusChecks(unittest.TestCase):
    def test_status_reports_review_state_without_private_content(self):
        opener = FakeOpener(FakeResponse(200, job()))
        result = tools.status(TOKEN, JOB_ID, opener=opener)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["revision"], 3)
        self.assertFalse(result["approved"])
        self.assertEqual(result["warning_codes"], ["speech_music_overlap"])
        self.assertEqual(result["subtitle_cue_count"], 1)
        rendered = json.dumps(result)
        self.assertNotIn("private subtitle line", rendered)
        self.assertNotIn("private backend prose", rendered)
        self.assertNotIn("artifacts", rendered)
        self.assertIn(client.REVIEW_URL, result["next_step"])

    def test_processing_and_finalizing_have_manual_recheck_steps(self):
        for status in ("queued", "processing", "finalizing"):
            opener = FakeOpener(FakeResponse(200, job(status=status)))
            result = tools.status(TOKEN, JOB_ID, opener=opener)
            self.assertEqual(result["status"], status)
            self.assertIn("check again", result["next_step"].lower())

    def test_completed_without_matching_approval_is_not_approved(self):
        stale = completed_job(approval={"revision": 2, "approval_id": "a", "approved_by": "c", "approved_at": "t"})
        opener = FakeOpener(FakeResponse(200, stale))
        result = tools.status(TOKEN, JOB_ID, opener=opener)
        self.assertFalse(result["approved"])
        self.assertEqual(result["approval_revision"], 2)
        self.assertIn("not approved", result["next_step"])

    def test_unknown_status_gets_a_cautious_step(self):
        opener = FakeOpener(FakeResponse(200, job(status="paused")))
        result = tools.status(TOKEN, JOB_ID, opener=opener)
        self.assertEqual(result["status"], "paused")
        self.assertIn("not one the plugin recognizes", result["next_step"])

    def test_status_requires_a_valid_job_id(self):
        opener = FakeOpener()
        for job_id in ("", "../secret", "a/b", "x" * 129):
            result = tools.status(TOKEN, job_id, opener=opener)
            self.assertEqual(result["code"], "invalid_job_id")
        self.assertEqual(opener.requests, [])

    def test_status_rejects_a_foreign_job_id_in_the_response(self):
        opener = FakeOpener(FakeResponse(200, job(job_id="job_other")))
        result = tools.status(TOKEN, JOB_ID, opener=opener)
        self.assertEqual(result["code"], "invalid_response")


class ExportChecks(unittest.TestCase):
    def test_releases_the_final_video_for_a_fresh_approved_revision(self):
        opener = FakeOpener(FakeResponse(200, completed_job()))
        result = tools.export(TOKEN, JOB_ID, surface="cli", opener=opener)
        self.assertTrue(result["ok"])
        self.assertTrue(result["export_ready"])
        self.assertEqual(result["download_url"], ARTIFACT_URL)
        self.assertEqual(result["revision"], 3)
        self.assertEqual(result["attribution"], "Track by Example Artist (CC BY 4.0)")
        self.assertIn("Authorization", opener.requests[0].headers)
        self.assertNotIn("sig=redacted", opener.requests[0].full_url)

    def test_stale_approval_is_withheld(self):
        stale = completed_job(approval={"revision": 2, "approval_id": "a", "approved_by": "c", "approved_at": "t"})
        opener = FakeOpener(FakeResponse(200, stale))
        result = tools.export(TOKEN, JOB_ID, surface="cli", opener=opener)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "approval_stale")
        self.assertNotIn("download_url", result)

    def test_missing_approval_is_withheld(self):
        opener = FakeOpener(FakeResponse(200, completed_job(approval=None)))
        result = tools.export(TOKEN, JOB_ID, surface="cli", opener=opener)
        self.assertEqual(result["code"], "approval_missing")

    def test_finalizing_job_releases_nothing(self):
        opener = FakeOpener(FakeResponse(200, job(status="finalizing")))
        result = tools.export(TOKEN, JOB_ID, surface="cli", opener=opener)
        self.assertEqual(result["code"], "not_completed")
        self.assertNotIn("download_url", result)

    def test_absent_final_artifact_is_withheld(self):
        opener = FakeOpener(FakeResponse(200, completed_job(artifacts={})))
        result = tools.export(TOKEN, JOB_ID, surface="cli", opener=opener)
        self.assertEqual(result["code"], "artifact_missing")

    def test_foreign_origin_and_wrong_route_are_withheld(self):
        bad_urls = [
            f"https://evil.example/v1/artifacts/{JOB_ID}/final_video.mp4",
            f"http://keepvoice.yablokolabs.com/v1/artifacts/{JOB_ID}/final_video.mp4",
            f"https://keepvoice.yablokolabs.com.evil.example/v1/artifacts/{JOB_ID}/final_video.mp4",
            f"https://keepvoice.yablokolabs.com:8443/v1/artifacts/{JOB_ID}/final_video.mp4",
            f"https://user:pass@keepvoice.yablokolabs.com/v1/artifacts/{JOB_ID}/final_video.mp4",
            f"https://keepvoice.yablokolabs.com/v1/artifacts/job_other/final_video.mp4",
            f"https://keepvoice.yablokolabs.com/v1/artifacts/{JOB_ID}/other.mp4",
            f"https://keepvoice.yablokolabs.com/v1/artifacts/{JOB_ID}/final_video.mp4#frag",
        ]
        for url in bad_urls:
            link = {"name": "final_video.mp4", "url": url, "content_type": "video/mp4"}
            opener = FakeOpener(FakeResponse(200, completed_job(artifacts={"final_video": link})))
            result = tools.export(TOKEN, JOB_ID, surface="cli", opener=opener)
            self.assertEqual(result["code"], "untrusted_artifact_url", url)
            self.assertNotIn("download_url", result)

    def test_unexpected_artifact_name_is_withheld(self):
        link = {"name": "../../etc/passwd", "url": ARTIFACT_URL, "content_type": "video/mp4"}
        opener = FakeOpener(FakeResponse(200, completed_job(artifacts={"final_video": link})))
        result = tools.export(TOKEN, JOB_ID, surface="cli", opener=opener)
        self.assertEqual(result["code"], "untrusted_artifact_url")

    def test_public_surface_withholds_the_link(self):
        opener = FakeOpener(FakeResponse(200, completed_job()))
        result = tools.export(TOKEN, JOB_ID, surface="telegram", opener=opener)
        self.assertTrue(result["ok"])
        self.assertTrue(result["export_ready"])
        self.assertTrue(result["restricted"])
        self.assertIsNone(result["download_url"])
        self.assertIn(client.REVIEW_URL, result["next_step"])
        self.assertNotIn("sig=redacted", json.dumps(result))

    def test_unknown_surface_fails_closed(self):
        opener = FakeOpener(FakeResponse(200, completed_job()))
        result = tools.export(TOKEN, JOB_ID, surface="", opener=opener)
        self.assertIsNone(result["download_url"])

    def test_export_fetches_fresh_state(self):
        opener = FakeOpener(FakeResponse(200, completed_job()))
        tools.export(TOKEN, JOB_ID, surface="cli", opener=opener)
        self.assertEqual(opener.requests[0].method, "GET")
        self.assertEqual(opener.requests[0].full_url, f"{client.BASE_URL}/v1/jobs/{JOB_ID}")


class ClientChecks(unittest.TestCase):
    def test_refuses_redirects(self):
        opener = FakeOpener(http_error(302))
        with self.assertRaises(client.ClientError) as caught:
            client.request_json("GET", f"/v1/jobs/{JOB_ID}", token=TOKEN, opener=opener)
        self.assertEqual(caught.exception.code, "redirect_refused")

    def test_auth_and_rate_limit_codes(self):
        for status, code in ((401, "auth_failed"), (403, "auth_failed"), (404, "not_found"), (500, "backend_error")):
            opener = FakeOpener(http_error(status))
            with self.assertRaises(client.ClientError) as caught:
                client.request_json("GET", f"/v1/jobs/{JOB_ID}", token=TOKEN, opener=opener)
            self.assertEqual(caught.exception.code, code)

        headers = Message()
        headers["Retry-After"] = "30"
        opener = FakeOpener(http_error(429, headers=headers))
        with self.assertRaises(client.ClientError) as caught:
            client.request_json("GET", f"/v1/jobs/{JOB_ID}", token=TOKEN, opener=opener)
        self.assertEqual(caught.exception.code, "rate_limited")
        self.assertEqual(caught.exception.retry_after, 30)

    def test_oversized_and_malformed_responses_are_refused(self):
        opener = FakeOpener(FakeResponse(200, b"{" + b" " * (client.MAX_RESPONSE_BYTES + 1)))
        with self.assertRaises(client.ClientError) as caught:
            client.request_json("GET", f"/v1/jobs/{JOB_ID}", token=TOKEN, opener=opener)
        self.assertEqual(caught.exception.code, "response_too_large")

        opener = FakeOpener(FakeResponse(200, b"not json"))
        with self.assertRaises(client.ClientError) as caught:
            client.request_json("GET", f"/v1/jobs/{JOB_ID}", token=TOKEN, opener=opener)
        self.assertEqual(caught.exception.code, "invalid_response")

    def test_only_fixed_routes_are_reachable(self):
        opener = FakeOpener()
        for path in ("https://evil.example/x", "/v1/assets", f"/v1/jobs/{JOB_ID}/approve", "/v1/jobs/a/b"):
            with self.assertRaises(client.ClientError) as caught:
                client.request_json("GET", path, token=TOKEN, opener=opener)
            self.assertEqual(caught.exception.code, "invalid_path")
        self.assertEqual(opener.requests, [])

    def test_artifact_url_validation(self):
        self.assertTrue(client.trusted_artifact_url(ARTIFACT_URL, JOB_ID, "final_video.mp4"))
        self.assertFalse(client.trusted_artifact_url("javascript:alert(1)", JOB_ID, "final_video.mp4"))
        self.assertFalse(client.trusted_artifact_url(ARTIFACT_URL, JOB_ID, "../final_video.mp4"))


class HandlerChecks(unittest.TestCase):
    def test_handlers_return_json_and_reject_bad_input(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "kv_plugin", PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(PLUGIN_DIR)]
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["kv_plugin"] = module
        spec.loader.exec_module(module)

        registered = {}

        class Ctx:
            def register_tool(self, **kwargs):
                registered[kwargs["name"]] = kwargs

            def session_surface(self):
                return "cli"

        module.register(Ctx())
        self.assertEqual(
            sorted(registered), ["keepvoice_export", "keepvoice_status", "keepvoice_submit"]
        )

        result = json.loads(registered["keepvoice_submit"]["handler"]({"upload_id": "bad"}))
        self.assertEqual(result["code"], "invalid_upload_id")
        result = json.loads(registered["keepvoice_status"]["handler"]({"job_id": "bad/id"}))
        self.assertEqual(result["code"], "invalid_job_id")


if __name__ == "__main__":
    unittest.main()
