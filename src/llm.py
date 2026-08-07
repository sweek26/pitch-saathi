"""
LLM calls for both modules. Practice and Mera Madad each load their OWN
system prompt file — never merged into one call or one prompt.
"""
import json
import os

import anthropic

_PROMPT_DIR = os.path.join(os.path.dirname(__file__), "..", "system_prompts")
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _load_prompt(filename):
    with open(os.path.join(_PROMPT_DIR, filename), "r", encoding="utf-8") as f:
        return f.read()


def _extract_text(response, fallback=None):
    """The model may emit a thinking block before its text block — find the
    text block instead of assuming content[0] is it.

    If max_tokens is too small, thinking can consume the whole budget and
    leave no text block at all (stop_reason "max_tokens"). Rarely, a text
    block is present but empty/whitespace-only - treat that the same way.
    When a fallback is given, return that instead of crashing the
    conversation.
    """
    for block in response.content:
        if block.type == "text" and block.text.strip():
            return block.text.strip()
    if fallback is not None:
        return fallback
    raise RuntimeError(f"No usable text block in Claude's response (stop_reason={response.stop_reason})")


PRACTICE_PROMPT = None
MERA_MADAD_PROMPT = None


def _system_for(ptype, level):
    global PRACTICE_PROMPT
    if PRACTICE_PROMPT is None:
        PRACTICE_PROMPT = _load_prompt("practice.txt")
    return f"{PRACTICE_PROMPT}\n\nActive practice type: {ptype}\nActive level: {level}"


def practice_persona_reply(ptype, level, turns):
    """
    turns: [{"role": "user"|"assistant", "text": "..."}]
    Returns {"household_reply": str, "turn_quality": "strong"|"weak"|"short"}.

    Division of labour, deliberate: the model ONLY classifies this turn's
    quality and writes a natural in-character reply - it is not asked to
    manage the hostility-ceiling or rescue-rule THRESHOLDS itself. Verified
    in testing that asking the model to self-count "how many in a row" is
    unreliable (a real 3rd-consecutive-weak-turn failed to self-trigger
    rescue; asking it to pre-emptively soften also landed inconsistently,
    since the softened turn is sometimes the same one rescue discards a
    moment later). The caller (demo/server.py) tracks weak_run from
    turn_quality with plain code and OVERRIDES the displayed text with a
    scripted ceiling line or rescue message at the exact right count -
    both are fixed strings, not model output, so they never misfire.
    """
    messages = [{"role": t["role"], "content": t["text"]} for t in turns]

    response = _get_client().messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=_system_for(ptype, level),
        messages=messages,
    )
    raw = _extract_text(response, fallback="")
    try:
        parsed = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        # Rare: an occasional API hiccup returns a text block that's empty
        # or not valid JSON despite the fallback above. Never let a parsing
        # miss break the conversation - degrade to a safe, in-character-ish
        # line instead of a hard failure.
        parsed = {}
    return {
        "household_reply": parsed.get("household_reply") or "Maaf kijiye, thoda ruk kar dobara boliye — samajh nahi paayi.",
        "turn_quality": parsed.get("turn_quality", "weak"),
    }


def practice_score_session(ptype, level, turns):
    """
    Sends the [END_OF_SESSION] control message. Returns:
      {topic, gap_category, good, next_time, exact_phrase}
    None of these are raw numbers/scores - topic and gap_category are for
    the trainer/L&D view only; good/next_time/exact_phrase are what the PU
    actually sees, assembled by the caller into the 3-part feedback shown
    on screen.
    """
    messages = [{"role": t["role"], "content": t["text"]} for t in turns]
    messages.append({"role": "user", "content": "[END_OF_SESSION — SCORE THIS CONVERSATION]"})

    response = _get_client().messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=_system_for(ptype, level),
        messages=messages,
    )
    raw = _extract_text(response)
    return json.loads(raw)


def mera_madad_reply(history_summary):
    """
    history_summary: list of this PU's past Practice sessions, e.g.
      [{"scenario": ..., "introduction": ..., "rapport": ..., "service": ...,
        "gap_tag": ..., "date": ...}, ...]
    Returns the coach's plain-text Hindi reply.
    """
    global MERA_MADAD_PROMPT
    if MERA_MADAD_PROMPT is None:
        MERA_MADAD_PROMPT = _load_prompt("mera_madad.txt")

    user_content = (
        "Yeh iss PU ki pichhli Practice sessions hain:\n"
        + json.dumps(history_summary, ensure_ascii=False, indent=2)
    )

    response = _get_client().messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=MERA_MADAD_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return _extract_text(
        response,
        fallback="Maaf kijiye, abhi jawab dene mein dikkat ho rahi hai — thodi der baad phir try kijiye.",
    )


# ---------------------------------------------------------------------------
# Ask — TEST MODE ONLY. Not wired into router.py/webhook.py (the real
# WhatsApp pipeline stays Practice + Mera Madad only, per locked scope).
# Three modes for side-by-side evaluation before deciding on one long-term:
#   safe        - no generation at all, honest "not covered, ask your FE"
#   vetted      - answers only from a real vetted curative reference doc
#   experimental- AI-generated herbal-only suggestion, no vetted source
# ---------------------------------------------------------------------------

ASK_VETTED_PROMPT = None
ASK_EXPERIMENTAL_PROMPT = None
VETTED_CURATIVE_REFERENCE = None


def ask_safe_defer(question):
    """No LLM call at all - the safest possible floor. Matches the
    non-negotiable rule already in practice.txt."""
    return (
        f'Aapne poocha: "{question}" — iska pakka jawab abhi mere paas nahi hai. '
        "Kripya apne Field Executive se poochiye, taaki bakri ko sahi salah mil sake."
    )


def ask_vetted_retrieval(question):
    global ASK_VETTED_PROMPT, VETTED_CURATIVE_REFERENCE
    if ASK_VETTED_PROMPT is None:
        ASK_VETTED_PROMPT = _load_prompt("ask_vetted.txt")
    if VETTED_CURATIVE_REFERENCE is None:
        VETTED_CURATIVE_REFERENCE = _load_prompt("vetted_curative_reference.txt")

    system = f"{ASK_VETTED_PROMPT}\n\n## Vetted reference content\n{VETTED_CURATIVE_REFERENCE}"
    response = _get_client().messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": question}],
    )
    return _extract_text(
        response,
        fallback="Is sawaal ka jawab abhi vetted material mein nahi mila — apne FE se poochiye.",
    )


def ask_experimental_herbal(question):
    global ASK_EXPERIMENTAL_PROMPT
    if ASK_EXPERIMENTAL_PROMPT is None:
        ASK_EXPERIMENTAL_PROMPT = _load_prompt("ask_experimental_herbal.txt")

    response = _get_client().messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=ASK_EXPERIMENTAL_PROMPT,
        messages=[{"role": "user", "content": question}],
    )
    return _extract_text(
        response,
        fallback="Jawab generate nahi ho paya — dobara try kijiye.",
    )
