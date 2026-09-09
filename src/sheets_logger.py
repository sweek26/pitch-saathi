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

NEW (Question_Log): in addition to the existing per-SESSION practice log
above, this module now also logs one row per individual user
question/interaction - every Practice turn, and every call through the
Ask test-mode endpoints - to a SEPARATE worksheet tab named "Question_Log"
in the same spreadsheet. See QUESTION_LOG_COLUMNS and log_question() below.
Kept as a separate tab (not new columns bolted onto sheet1) because sheet1
already holds one-row-per-SESSION summaries with its own column schema
(CANONICAL_COLUMNS above) - mixing one-row-per-question data into that
would multiply its row count for no analytical benefit and risks the exact
column-drift bug documented above happening again.
"""
import datetime
import json
import logging
import os
import re
import threading
import time

import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_client = None
_spreadsheet = None
_sheet = None                # sheet1 - existing per-session log (unchanged)
_question_log_sheet = None   # NEW - Question_Log tab
# NEW - serializes every Question_Log write (lazy tab creation + the
# append/Question_ID-patch pair below). log_question_async fires one
# background thread per call, so back-to-back turns can genuinely overlap;
# without this lock, testing this build surfaced real data loss - two
# threads' append_row() calls landing close enough together silently lost
# one row (no exception, no duplicate tab - just gone). Cheap fix: since
# these are already background threads that never block the PU's request,
# serializing them costs nothing user-facing, only how fast the (invisible)
# logging catches up - irrelevant at this app's pilot scale.
_question_log_write_lock = threading.Lock()

_logger = logging.getLogger(__name__)

CANONICAL_COLUMNS = [
    "phone_number", "timestamp", "pu_name", "gram_panchayat", "module",
    "ptype", "level", "transcript", "transcript_confidence", "topic",
    "gap_category", "good", "next_time", "exact_phrase", "reply_text",
    "ended_via", "opening_line", "tier", "audio_ok",
]

# NEW - Question_Log tab's header row. Title_Case on purpose (distinct from
# CANONICAL_COLUMNS' lowercase style above) - this is a separate, newer log
# with its own conventions, not an extension of the old schema.
QUESTION_LOG_COLUMNS = [
    "Question_ID", "Timestamp", "Source", "Session_ID", "PU_Name",
    "Gram_Panchayat", "Village_Name", "Practice_Type", "Ask_Mode",
    "Input_Type", "User_Question", "LLM_Response", "Response_Status",
    "Error_Message", "Response_Time_Sec",
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


def _get_spreadsheet():
    """Shared handle to the whole spreadsheet (all tabs) - both sheet1's
    existing per-session log and the new Question_Log tab open the same
    spreadsheet, so this is factored out rather than each calling
    open_by_key() separately. Purely a refactor - _get_sheet()'s own
    behavior below is unchanged."""
    global _client, _spreadsheet
    if _spreadsheet is None:
        creds = _load_credentials()
        _client = gspread.authorize(creds)
        _spreadsheet = _client.open_by_key(os.environ["GOOGLE_SHEET_ID"])
    return _spreadsheet


def _get_sheet():
    global _sheet
    if _sheet is None:
        _sheet = _get_spreadsheet().sheet1
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


# ---------------------------------------------------------------------------
# NEW: Question_Log - one row per individual user question/interaction,
# across BOTH Practice turns and the Ask test-mode endpoints. See this
# file's module docstring for why this is a separate tab from sheet1.
# ---------------------------------------------------------------------------

def _get_question_log_sheet():
    global _question_log_sheet
    if _question_log_sheet is None:
        spreadsheet = _get_spreadsheet()
        try:
            ws = spreadsheet.worksheet("Question_Log")
        except gspread.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(
                title="Question_Log", rows=2000, cols=len(QUESTION_LOG_COLUMNS)
            )
            ws.update("A1", [QUESTION_LOG_COLUMNS])
        _question_log_sheet = ws
    return _question_log_sheet


def _question_id_from_range(updated_range):
    """updated_range looks like "'Question_Log'!A5:O5" - the row number in
    there (5) is this row's real position (row 1 is the header, so row 2
    is the first data row -> Q000001). Derived from the API's own response
    instead of a separately-maintained counter, so it can never drift out
    of sync with what's actually in the sheet."""
    cell_ref = updated_range.split("!")[1].split(":")[0]
    return int(re.search(r"\d+", cell_ref).group())


def log_question(
    source,
    user_question,
    llm_response="",
    session_id="",
    pu_name="",
    gram_panchayat="",
    village_name="",
    practice_type="",
    ask_mode="",
    input_type="",
    response_status="Success",
    error_message="",
    response_time_sec=None,
):
    """One row per individual user question/interaction - never combines
    multiple questions into one row, never deduplicates repeated ones
    (both deliberate, per spec).

    Safe to call directly (synchronous) - every failure is caught here and
    logged via the standard `logging` module, never raised, so a Sheets
    outage can never break the caller. Most call sites should use
    log_question_async() below instead, so the write happens off the
    request thread and adds no latency to what the PU experiences.

    Returns the assigned Question_ID, or None if logging failed (callers
    don't need to check this - it's for tests/debugging only).
    """
    try:
        row = [
            "",  # Question_ID - filled in below, only known after the row exists
            datetime.datetime.utcnow().isoformat(),
            source,
            session_id,
            pu_name,
            gram_panchayat,
            village_name,
            practice_type,
            ask_mode,
            input_type,
            user_question,
            llm_response,
            response_status,
            error_message,
            f"{response_time_sec:.2f}" if response_time_sec is not None else "",
        ]
        anchor = rowcol_to_a1(1, len(QUESTION_LOG_COLUMNS))
        # Locked: log_question_async fires one background thread per call, so
        # back-to-back turns/questions can genuinely run this concurrently.
        # Both the lazy tab creation in _get_question_log_sheet() and the
        # append-then-patch-the-ID pair below need to happen as one unit per
        # writer - see _question_log_write_lock's own comment for what broke
        # without this.
        with _question_log_write_lock:
            sheet = _get_question_log_sheet()
            result = sheet.append_row(row, value_input_option="RAW", table_range=f"A1:{anchor}")
            row_num = _question_id_from_range(result["updates"]["updatedRange"])
            question_id = f"Q{row_num - 1:06d}"
            # A second small API call to patch the ID in - Question_ID can only
            # be known after the row exists, and this keeps the append itself a
            # single positional write (same reasoning as log_interaction's
            # table_range fix above - simplicity and not fighting append_row's
            # own table-detection). If this second call fails, the row still
            # has all its real data, just a blank Question_ID - never worse
            # than that.
            sheet.update_cell(row_num, 1, question_id)
        return question_id
    except Exception:
        _logger.exception(
            "Question_Log write failed (source=%s, session=%s) - the question/answer "
            "itself was still shown to the user normally, it just wasn't recorded this time.",
            source, session_id,
        )
        return None


def log_question_async(**kwargs):
    """Fire-and-forget wrapper around log_question() - runs the Sheets
    write on a background thread so it never adds latency to the HTTP
    response the PU is waiting on. Appropriate at this app's current pilot
    scale (a handful of PUs) - a raw thread per write is not meant to
    scale to heavy concurrent load or protect against Sheets API rate
    limits under a burst of simultaneous writes, same caveat as
    state_store.py's file-based storage. Revisit with a proper queue if
    usage grows well past pilot scale."""
    threading.Thread(target=log_question, kwargs=kwargs, daemon=True).start()
