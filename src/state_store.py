"""
Per-PU conversation state, keyed by session id.

No database in this pilot (per spec) — state lives in a single local JSON
file. This is fine for 5-10 PU over a 2-4 week test; it is NOT meant to
survive a move to a real rollout, where this should become a proper DB.
"""
import json
import os
import threading
import time

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "session_state.json")
_lock = threading.Lock()

# Sessions abandoned mid-conversation (closed tab, crashed browser, a demo
# that was never finished with /api/practice/end) used to sit in this file
# FOREVER - nothing ever pruned them. Confirmed during testing: 116
# accumulated sessions, none ever cleared, growing the file - and the
# read+rewrite cost paid on every single turn - a little more each time.
# 6 hours comfortably covers a same-day testing/demo session while still
# cleaning up genuinely abandoned ones.
STALE_AFTER_SECONDS = 6 * 60 * 60


def _prune_stale(data):
    now = time.time()
    # Fallback of 0, not `now`: a legacy entry saved before _last_saved
    # existed must look ARBITRARILY OLD so it gets swept up on the first
    # prune, not arbitrarily fresh (which would keep it forever - the
    # exact bug that let 116 dead sessions accumulate in the first place).
    return {
        k: v for k, v in data.items()
        if now - v.get("_last_saved", 0) < STALE_AFTER_SECONDS
    }


def _read_all():
    if not os.path.exists(STATE_PATH):
        return {}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_all(data):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_session(phone_number):
    with _lock:
        data = _prune_stale(_read_all())
        return data.get(phone_number, {
            "module": None,       # "practice" | "mera_madad"
            "scenario": None,     # "basic_pitch" | "price_objection"
            "turns": [],          # [{"role": "user"|"assistant", "text": "..."}]
        })


def save_session(phone_number, session):
    with _lock:
        data = _prune_stale(_read_all())
        session["_last_saved"] = time.time()
        data[phone_number] = session
        _write_all(data)


def clear_session(phone_number):
    with _lock:
        data = _prune_stale(_read_all())
        data.pop(phone_number, None)
        _write_all(data)
