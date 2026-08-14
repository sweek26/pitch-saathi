"""
Sawal-Jawab (Knowledge Practice) question bank. Loads real vetted Q&A
content and serves it per service - no LLM involved anywhere in this
module. Both the question and the "approved answer" the PU sees are fixed,
vetted text originally sourced from Input/Sawal_Jawab_Vetted_QA.md, never
model-generated, to keep zero hallucination risk on real dosage/treatment
content.

Lives in system_prompts/, not Input/ - Input/ is gitignored (raw reference
material only), but this JSON is content the deployed app actually serves,
so it has to ship with the repo.
"""
import json
import os
import random

_QUESTIONS_PATH = os.path.join(os.path.dirname(__file__), "..", "system_prompts", "sawal_jawab_questions.json")
_QUESTIONS = None

MAX_QUESTIONS_PER_SESSION = 5


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
    session - capped at MAX_QUESTIONS_PER_SESSION so a service with more
    questions than that doesn't overwhelm her in one sitting. Reshuffled
    fresh every call, so which 5 (and their order) varies attempt to
    attempt - if the service has MAX_QUESTIONS_PER_SESSION or fewer total,
    she'll still see all of them, just in a new order each time."""
    indexes = [i for i, q in enumerate(_load()) if q["service"] == service]
    random.shuffle(indexes)
    return indexes[:MAX_QUESTIONS_PER_SESSION]


def get_question(index):
    return _load()[index]
