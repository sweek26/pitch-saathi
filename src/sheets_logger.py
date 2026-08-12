"""
Logs one row per interaction to a shared Google Sheet.

Columns: phone_number, timestamp, module, ptype, level, transcript,
transcript_confidence, topic, gap_category, good, next_time, exact_phrase,
reply_text, ended_via

topic/gap_category are for the trainer/L&D view only (topic-level, never a
score - see practice.txt). good/next_time/exact_phrase are the same 3-part
feedback shown to the PU. ended_via is "scored" normally, or "rescue" when
the hostility-ceiling rescue rule ended the session early (in which case
topic/gap_category/good/next_time/exact_phrase are blank - a rescued
session is deliberately never scored, per design).

NOTE: this schema replaced the old introduction/rapport/service/gap_tag/
scenario columns as part of the practice-type/level redesign. Mera Madad
(get_practice_history + mera_madad.txt) still expects the OLD field names
and has not been updated yet - it's paused, not broken by accident, until
its replacement (मेरी बातें) is built in a follow-up pass.
"""
import datetime
import json
import os

import gspread
from google.oauth2.service_account import Credentials

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_client = None
_sheet = None


def _load_credentials():
    """GOOGLE_SERVICE_ACCOUNT_JSON is a file path locally (service_account.json
    on disk, gitignored) but a cloud host like Render has no persistent file
    to point at - there, the same env var instead holds the key file's raw
    JSON content, pasted directly into the platform's secret env var UI.
    Detect which one we got rather than needing two separate env vars."""
    raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    if os.path.isfile(raw):
        return Credentials.from_service_account_file(raw, scopes=_SCOPES)
    return Credentials.from_service_account_info(json.loads(raw), scopes=_SCOPES)


def _get_sheet():
    global _client, _sheet
    if _sheet is None:
        creds = _load_credentials()
        _client = gspread.authorize(creds)
        _sheet = _client.open_by_key(os.environ["GOOGLE_SHEET_ID"]).sheet1
    return _sheet


def log_interaction(
    phone_number,
    module,
    ptype,
    level,
    transcript,
    transcript_confidence,
    reply_text,
    feedback=None,
    ended_via="scored",
):
    """feedback: dict with topic/gap_category/good/next_time/exact_phrase,
    or None for a mid-conversation turn row / a rescue ending."""
    feedback = feedback or {}
    row = [
        phone_number,
        datetime.datetime.utcnow().isoformat(),
        module,
        ptype or "",
        level if level is not None else "",
        transcript,
        transcript_confidence if transcript_confidence is not None else "",
        feedback.get("topic", ""),
        feedback.get("gap_category", ""),
        feedback.get("good", ""),
        feedback.get("next_time", ""),
        feedback.get("exact_phrase", ""),
        reply_text,
        ended_via,
    ]
    _get_sheet().append_row(row, value_input_option="RAW")


def get_practice_history(phone_number):
    """
    NOTE: returns the NEW schema shape. mera_madad.txt / llm.mera_madad_reply
    still expect the OLD shape (introduction/rapport/service/gap_tag) -
    Mera Madad is paused pending its रीबिल्ड, not wired to this yet.
    """
    rows = _get_sheet().get_all_records()
    history = []
    for row in rows:
        if row.get("phone_number") == phone_number and row.get("module") == "practice" and row.get("ended_via") == "scored":
            history.append({
                "ptype": row.get("ptype"),
                "level": row.get("level"),
                "topic": row.get("topic"),
                "gap_category": row.get("gap_category"),
                "date": row.get("timestamp"),
            })
    return history


def has_completed(phone_number, ptype):
    """Has this PU ever finished (scored) a session of this practice type?
    Used to decide Level 1 (first time, warm) vs Level 2 (interactive)."""
    rows = _get_sheet().get_all_records()
    for row in rows:
        if (row.get("phone_number") == phone_number and row.get("module") == "practice"
                and row.get("ptype") == ptype and row.get("ended_via") == "scored"):
            return True
    return False
