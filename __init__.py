"""KeepVoice for Hermes — register the three KeepVoice tools.

Media processing, subtitle edits and approval stay in KeepVoice. This plugin
starts a job from an existing upload, reports review state, and releases the
final video only after the current revision is approved.
"""

from __future__ import annotations

import json
from typing import Any

from . import tools

TOOLSET = "keepvoice"

# Hermes handlers must always return a JSON string and never raise (plugin guide,
# "Key rules for handlers"). Anything unforeseen becomes a stable code here.
_UNEXPECTED_JSON = json.dumps(
    {
        "ok": False,
        "code": "internal_error",
        "message": "The KeepVoice plugin hit an unexpected error and returned no result.",
        "recovery": (
            "Retry once. If it persists, check the job in KeepVoice and report the failure; "
            "no artifact was released."
        ),
    },
    sort_keys=True,
)

SUBMIT_SCHEMA = {
    "name": "keepvoice_submit",
    "description": (
        "Start a KeepVoice voice-cleanup job from a clip the creator already uploaded at "
        "https://keepvoice.yablokolabs.com. Requires the upload ID from that page, an explicit "
        "rights_confirmed=true from the creator, and source provenance. Never infer authorization. "
        "Returns the job ID, current state and whether KeepVoice replayed an earlier submission."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "upload_id": {
                "type": "string",
                "description": "32-character lowercase hex upload ID from the KeepVoice upload page.",
            },
            "rights_confirmed": {
                "type": "boolean",
                "description": (
                    "Literal true only after the creator explicitly confirms they are authorized to "
                    "process this clip. Ask; never infer it."
                ),
            },
            "source_provenance": {
                "type": "string",
                "description": "Where the clip came from (5-500 characters), e.g. who recorded it and where.",
            },
        },
        "required": ["upload_id", "rights_confirmed", "source_provenance"],
        "additionalProperties": False,
    },
}

STATUS_SCHEMA = {
    "name": "keepvoice_status",
    "description": (
        "Report the current state of a KeepVoice job: status, revision, whether the current revision is "
        "approved, warning codes and subtitle cue count. Returns no subtitle text and no artifact links. "
        "Use it after submission and before export; prefer a manual recheck over a polling loop."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "Job ID returned by keepvoice_submit."},
        },
        "required": ["job_id"],
        "additionalProperties": False,
    },
}

EXPORT_SCHEMA = {
    "name": "keepvoice_export",
    "description": (
        "Release the final video for a KeepVoice job. Fetches fresh state and returns the signed download "
        "link only when the job is completed, the approval covers the current revision, and the artifact "
        "link matches the trusted KeepVoice route. Withholds the link in non-private sessions. Call it "
        "after the creator approves the current revision."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "Job ID returned by keepvoice_submit."},
        },
        "required": ["job_id"],
        "additionalProperties": False,
    },
}


def register(ctx):
    """Register the KeepVoice tools with Hermes."""

    def _arguments(args: Any) -> dict:
        return args if isinstance(args, dict) else {}

    def keepvoice_submit(args, **_kwargs) -> str:
        try:
            values = _arguments(args)
            return tools.as_json(
                tools.submit(
                    token=tools.agent_token(),
                    upload_id=values.get("upload_id"),
                    rights_confirmed=values.get("rights_confirmed"),
                    source_provenance=values.get("source_provenance"),
                )
            )
        except Exception:
            return _UNEXPECTED_JSON

    def keepvoice_status(args, **_kwargs) -> str:
        try:
            values = _arguments(args)
            return tools.as_json(
                tools.status(token=tools.agent_token(), job_id=values.get("job_id"))
            )
        except Exception:
            return _UNEXPECTED_JSON

    def keepvoice_export(args, **_kwargs) -> str:
        try:
            values = _arguments(args)
            try:
                surface = str(ctx.session_surface())
            except Exception:
                surface = ""
            return tools.as_json(
                tools.export(token=tools.agent_token(), job_id=values.get("job_id"), surface=surface)
            )
        except Exception:
            return _UNEXPECTED_JSON

    ctx.register_tool(
        name="keepvoice_submit",
        toolset=TOOLSET,
        schema=SUBMIT_SCHEMA,
        handler=keepvoice_submit,
        description="Start a KeepVoice voice-cleanup job from an authorized upload.",
        emoji="🎙",
    )
    ctx.register_tool(
        name="keepvoice_status",
        toolset=TOOLSET,
        schema=STATUS_SCHEMA,
        handler=keepvoice_status,
        description="Report KeepVoice job state, revision and approval without subtitles or links.",
        emoji="📋",
    )
    ctx.register_tool(
        name="keepvoice_export",
        toolset=TOOLSET,
        schema=EXPORT_SCHEMA,
        handler=keepvoice_export,
        description="Release the final video only for an approved completed revision.",
        emoji="🎬",
    )
