"""
Logs one row per interaction to a shared Google Sheet.

Columns, in exact order (see CANONICAL_COLUMNS below - the live Sheet's
header row must match this exactly, via fix_header_row()):
  phone_number, timestamp, pu_name, gram_panchayat, module, ptype, level,
  transcript, transcript_confidence, topic, gap_category, good, next_time,
  exact_phrase, reply_text, ended_via, opening_line, tier, audio_ok

pu_name/gram_panchayat are read from the PU's onboarding (localStorage on
the client) so a session row is human-readable without cross-referencing
phone_number/session_id elsewhere. gram_panchayat is blank on a rescued
session - that path doesn't currently collect it (see practice_turn()'s
rescue branch).

topic/gap_category are for the trainer/L&D view only (topic-level, never a
score - see practice.txt). good/next_time/exact_phrase are the same 3-part
feedback shown to the PU. ended_via is "scored" normally, or "rescue" when
the hostility-ceiling rescue rule ended the session early (in which case
topic/gap_category/good/next_time/exact_phrase are blank - a rescued
session is deliberately never scored, per design).

opening_line/tier/audio_ok are from the spoken-feedback (Kiran Didi voice)
feature - which spoken opener was used, the excellent/good/improving tier
it was picked from, and whether Sarvam TTS actually returned audio for that
session (False means the PU only saw text feedback, no audio). Blank for
rows from before that feature, and for rescue endings, which never reach it.

NOTE: this schema replaced the old introduction/rapport/service/gap_tag/
scenario columns as part of the practice-type/level redesign. Mera Madad
(get_practice_history + mera_madad.txt) still expects the OLD field names
and has not been updated yet - it's paused, not broken by accident, until
its replacement (मेरी बातें) is built in a follow-up pass.

BUG FIXED HERE (part 1 - header/code mismatch): for a while, the code's row
order and the live Sheet's header row had drifted apart - the header still
read the OLD pre-redesign schema (phone_number/timestamp/PU_Name/GP_Name/
module/scenario/transcript/transcript_confidence/introduction/rapport/
service/gap_tag/reply_text) while append_row() had already moved on to this
richer shape. append_row() writes positionally and does not know or care
what the header says, so every row since the redesign landed under the
wrong column labels. Fixing only the code (this file) is NOT enough by
itself - fix_header_row() must also actually be run once against the live
Sheet, or the header stays wrong. Historical rows are deliberately left
untouched either way (see fix_header_row()'s docstring).

BUG FOUND AND FIXED HERE (part 2 - column drift, more severe, not part of
the original report): auditing the live Sheet to fix part 1 surfaced a
second, worse problem - the actual DATA in recent rows isn't even landing
in columns 1-19. The Sheet's column count has drifted to 112 (visible via
sheet.col_count), and without an explicit table_range, append_row() scans
the WHOLE sheet to guess where "the table" is - once that scan started
returning a wide, mostly-empty range, every subsequent call anchored its
insert further right instead of resetting to column A (gspread's own
docs: "search for a logical table of data... appended after the last row
of the table"). The most recent rows had their real 18-19 values sitting
around columns 94-112, not 1-19. Fixed by passing an explicit
table_range=f"A1:{{last column}}" on every append, forcing the anchor back
to column A regardless of the sheet's overall (now-oversized) dimensions.
This does NOT retroactively fix the columns of rows already written that
way - only new rows going forward.
"""
import datetime
import json
import os

import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_client = None
_sheet = None

CANONICAL_COLUMNS = [
    "phone_number", "timestamp", "pu_name", "gram_panchayat", "module",
    "ptype", "level", "transcript", "transcript_confidence", "topic",
    "gap_category", "good", "next_time", "exact_phrase", "reply_text",
    "ended_via", "opening_line", "tier", "audio_ok",
]


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
    pu_name="",
    gram_panchayat="",
):
    """feedback: dict with topic/gap_category/good/next_time/exact_phrase,
    plus (practice module only) opening_line/tier/audio_ok from the spoken
    feedback feature - or None for a mid-conversation turn row / a rescue
    ending. Row order here must match CANONICAL_COLUMNS exactly."""
    feedback = feedback or {}
    row = [
        phone_number,
        datetime.datetime.utcnow().isoformat(),
        pu_name,
        gram_panchayat,
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
        feedback.get("opening_line", ""),
        feedback.get("tier", ""),
        feedback.get("audio_ok", ""),
    ]
    # table_range anchors the append at column A - without it, append_row()
    # scans the WHOLE sheet for "the table" and, once the sheet's column
    # count has drifted wide for any reason, keeps anchoring further and
    # further right on every call instead of resetting to column A. This
    # is what caused the real column-drift bug found in the live Sheet
    # (see this file's module docstring) - historical rows already written
    # that way are not touched by this fix, only future appends.
    anchor = rowcol_to_a1(1, len(CANONICAL_COLUMNS))
    _get_sheet().append_row(row, value_input_option="RAW", table_range=f"A1:{anchor}")


def fix_header_row():
    """Run once, manually, after deploying this corrected log_interaction().
    Overwrites row 1 to match CANONICAL_COLUMNS exactly. Does NOT touch or
    migrate any existing data rows below it - old rows predate this schema
    and stay as historical records under their old (now-mislabeled)
    header; only the header itself and all NEW rows going forward are
    fixed by this."""
    sheet = _get_sheet()
    sheet.update("A1", [CANONICAL_COLUMNS])


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
