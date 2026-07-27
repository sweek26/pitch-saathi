"""
Per-PU conversation state, keyed by WhatsApp phone number.

No database in this pilot (per spec) — state lives in a single local JSON
file. This is fine for 5-10 PU over a 2-4 week test; it is NOT meant to
survive a move to a real rollout, where this should become a proper DB.
"""
import json
import os
import threading

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "session_state.json")
_lock = threading.Lock()


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
        data = _read_all()
        return data.get(phone_number, {
            "module": None,       # "practice" | "mera_madad"
            "scenario": None,     # "basic_pitch" | "price_objection"
            "turns": [],          # [{"role": "user"|"assistant", "text": "..."}]
        })


def save_session(phone_number, session):
    with _lock:
        data = _read_all()
        data[phone_number] = session
        _write_all(data)


def clear_session(phone_number):
    with _lock:
        data = _read_all()
        data.pop(phone_number, None)
        _write_all(data)
