"""
Sawal-Jawab (Knowledge Practice) question bank. Loads real vetted Q&A
content and serves it per service - no LLM involved anywhere in this
module. Both the question and the "approved answer" the PU sees are fixed,
vetted text sourced from Input/Sawal_Jawab_Vetted_QA.md, never
model-generated, to keep zero hallucination risk on real dosage/treatment
content.
"""
import json
import os
import random

_QUESTIONS_PATH = os.path.join(os.path.dirname(__file__), "..", "Input", "sawal_jawab_questions.json")
_QUESTIONS = None


def _load():
    global _QUESTIONS
    if _QUESTIONS is None:
        with open(_QUESTIONS_PATH, "r", encoding="utf-8") as f:
            _QUESTIONS = json.load(f)
    return _QUESTIONS


def services_available():
    """Which services actually have vetted Q&A content behind them right
    now - deworming/first/badhiya have none yet, so they're absent here
    rather than shown with invented questions."""
    return sorted({q["service"] for q in _load()})


def new_question_order(service):
    """A shuffled list of question indexes for this service, for one
    session - so each session sees every question for that service, once,
    in a different order."""
    indexes = [i for i, q in enumerate(_load()) if q["service"] == service]
    random.shuffle(indexes)
    return indexes


def get_question(index):
    return _load()[index]
