"""
Logs one row per interaction to a shared Google Sheet.

Columns: phone_number, timestamp, module, scenario, transcript,
transcript_confidence, introduction, rapport, service, gap_tag, reply_text

For Practice rows, introduction/rapport/service/gap_tag are filled in.
For Mera Madad rows, those are left blank (Mera Madad doesn't re-score).
"""
import datetime
import os

import gspread
from google.oauth2.service_account import Credentials

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_client = None
_sheet = None


def _get_sheet():
    global _client, _sheet
    if _sheet is None:
        creds = Credentials.from_service_account_file(
            os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"], scopes=_SCOPES
        )
        _client = gspread.authorize(creds)
        _sheet = _client.open_by_key(os.environ["GOOGLE_SHEET_ID"]).sheet1
    return _sheet


def log_interaction(
    phone_number,
    module,
    scenario,
    transcript,
    transcript_confidence,
    reply_text,
    score=None,
):
    """score: dict with introduction/rapport/service/gap_tag, or None for Mera Madad."""
    score = score or {}
    row = [
        phone_number,
        datetime.datetime.utcnow().isoformat(),
        module,
        scenario or "",
        transcript,
        transcript_confidence if transcript_confidence is not None else "",
        score.get("introduction", ""),
        score.get("rapport", ""),
        score.get("service", ""),
        score.get("gap_tag", ""),
        reply_text,
    ]
    _get_sheet().append_row(row, value_input_option="RAW")


def get_practice_history(phone_number):
    """
    Returns this PU's past Practice rows only, oldest first, as the shape
    llm.mera_madad_reply() expects. Reads the whole sheet each call — fine
    at pilot scale (5-10 PU, a few weeks of rows).
    """
    rows = _get_sheet().get_all_records()
    history = []
    for row in rows:
        if row.get("phone_number") == phone_number and row.get("module") == "practice":
            history.append({
                "scenario": row.get("scenario"),
                "introduction": row.get("introduction"),
                "rapport": row.get("rapport"),
                "service": row.get("service"),
                "gap_tag": row.get("gap_tag"),
                "date": row.get("timestamp"),
            })
    return history
